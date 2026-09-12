"""Optional Inspect integration.

Requires the `inspect` extra. The caller supplies its own model and model
configuration; this module supplies the trials, the tools, the official scorer and
EAL's own metrics.

Inspect's request surface is not identical to the runner's, so every outcome scored
here is tagged `surface="inspect"` and carries the adapter version and a hash of the
request actually sent. Do not pool these with native results.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .controls import CONTROL_CONDITIONS, build_control_trials
from .scoring import TrialOutcome, score_response
from .trials import ModelResponse, Trial, TrialTruth

__all__ = [
    "INSPECT_ADAPTER_VERSION",
    "INSTALL_HINT",
    "available",
    "control_task",
    "eal_controls_scorer",
    "eal_generate",
    "eal_metrics",
    "missing_parameter_descriptions",
    "rendered_tool_surface",
    "repaired_without_parse_error",
    "response_from_inspect",
    "to_samples",
    "to_tool_defs",
]

INSPECT_ADAPTER_VERSION = "eal_bench.eval.inspect_adapter/v1"
INSTALL_HINT = 'install the Inspect extra: pip install "eal-bench[inspect]"'

_GENERATION_ERROR_KEY = "eal_generation_error"
_TRUTH_CACHE: dict[tuple[str, str | None, str | None], dict[str, TrialTruth]] = {}


def available() -> bool:
    try:
        import inspect_ai  # noqa: F401
    except ImportError:
        return False
    return True


def _require_inspect() -> None:
    if not available():
        raise ImportError(INSTALL_HINT)


def missing_parameter_descriptions(tools: Sequence[dict[str, Any]]) -> list[str]:
    """Tool parameters EAL leaves undescribed, which Inspect refuses to accept."""

    missing = []
    for tool in tools:
        function = tool["function"]
        for name, spec in function.get("parameters", {}).get("properties", {}).items():
            if not str(spec.get("description", "")).strip():
                missing.append(f"{function['name']}.{name}")
    return sorted(missing)


def _described_parameters(schema: dict[str, Any]) -> dict[str, Any]:
    described = dict(schema)
    properties = {}
    for name, spec in schema.get("properties", {}).items():
        filled = dict(spec)
        if not str(filled.get("description", "")).strip():
            filled["description"] = name
        properties[name] = filled
    described["properties"] = properties
    return described


def to_tool_defs(tools: Sequence[dict[str, Any]]) -> list[Any]:
    """Convert EAL's OpenAI-shaped tool schemas into Inspect tool definitions.

    The callables are never invoked. A terminal action is scored from the call rather
    than executed. Inspect rejects a parameter with no description, so those are
    filled with the parameter name; `missing_parameter_descriptions` lists them.
    """

    _require_inspect()
    from inspect_ai.tool import ToolDef
    from inspect_ai.tool._tool_params import ToolParams

    defs = []
    for tool in tools:
        function = tool["function"]

        async def _unused(**kwargs: Any) -> str:
            del kwargs
            return ""

        defs.append(
            ToolDef(
                tool=_unused,
                name=function["name"],
                description=function.get("description", ""),
                parameters=ToolParams.model_validate(
                    _described_parameters(function.get("parameters", {}))
                ),
            )
        )
    return defs


def rendered_tool_surface(tools: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The parameter schema Inspect actually sends, after conversion."""

    _require_inspect()
    import asyncio

    from inspect_ai.tool._tool_def import tool_defs

    infos = asyncio.run(tool_defs([item.as_tool() for item in to_tool_defs(tools)]))
    return {info.name: info.parameters.model_dump(exclude_none=True) for info in infos}


def _request_hash(trial: Trial, tool_surface: Mapping[str, Any]) -> str:
    from experiments.authorization_memory.persistence import content_hash

    return content_hash(
        {
            "messages": [dict(message) for message in trial.messages],
            "tools": dict(tool_surface),
            "tool_choice": trial.tool_choice,
        }
    )


def to_samples(pairs: Sequence[tuple[Trial, TrialTruth]]) -> list[Any]:
    """One Inspect sample per trial. Truth stays in metadata, never in the input."""

    _require_inspect()
    from experiments.authorization_memory.persistence import content_hash
    from inspect_ai.dataset import Sample
    from inspect_ai.model import ChatMessageSystem, ChatMessageUser

    roles = {"system": ChatMessageSystem, "user": ChatMessageUser}
    surface = rendered_tool_surface(list(pairs[0][0].tools)) if pairs else {}
    surface_hash = content_hash(surface)
    return [
        Sample(
            id=trial.trial_id,
            input=[
                roles[message["role"]](content=message["content"]) for message in trial.messages
            ],
            metadata={
                "resources": trial.resources.to_dict(),
                "truth": truth.to_dict(),
                "corpus_version": trial.resources.corpus_version,
                "presentation_id": trial.resources.presentation_id,
                "inspect_adapter_version": INSPECT_ADAPTER_VERSION,
                "tool_surface_hash": surface_hash,
                "request_hash": _request_hash(trial, surface),
            },
        )
        for trial, truth in pairs
    ]


def response_from_inspect(output: Any) -> ModelResponse:
    """Normalize an Inspect `ModelOutput` into a `ModelResponse`.

    Inspect repairs some malformed argument strings without setting `parse_error`
    and does not keep the original text, so a reply the native scorer would reject
    can be scored here. Outcomes from this path are tagged `surface="inspect"`.
    """

    if getattr(output, "error", None):
        return ModelResponse.provider_error(str(output.error))
    # ModelOutput.stop_reason and .message both index choices[0] and raise when empty.
    if not getattr(output, "choices", None):
        return ModelResponse.provider_error("model returned no choices")
    message = output.message
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        parse_error = getattr(call, "parse_error", None)
        calls.append((call.function, parse_error if parse_error else call.arguments))
    return ModelResponse.from_tool_calls(
        calls,
        text=message.text or "",
        finish_reason=output.stop_reason,
        model=str(getattr(output, "model", "") or "") or None,
    )


def _truths_for(
    domain_id: str,
    corpus_version: str | None,
    presentation_id: str | None,
) -> dict[str, TrialTruth]:
    key = (domain_id, corpus_version, presentation_id)
    if key not in _TRUTH_CACHE:
        _TRUTH_CACHE[key] = {
            truth.trial_id: truth
            for _, truth in build_control_trials(
                domain_id,
                corpus_version=corpus_version,
                presentation_id=presentation_id,
                check_leakage=False,
            )
        }
    return _TRUTH_CACHE[key]


def _truth_for_state(state: Any) -> TrialTruth:
    """Rebuild truth from sample metadata, so a saved log can be re-scored."""

    metadata = state.metadata or {}
    recorded = metadata.get("truth") or {}
    domain_id = recorded.get("domain_id")
    if not domain_id:
        raise ValueError(
            f"sample {state.sample_id!r} carries no EAL truth metadata; "
            "it was not produced by eal_bench.eval.inspect_adapter"
        )
    truths = _truths_for(domain_id, metadata.get("corpus_version"), metadata.get("presentation_id"))
    trial_id = str(state.sample_id)
    if trial_id not in truths:
        raise ValueError(
            f"sample {trial_id!r} no longer builds for domain {domain_id!r}; "
            "the corpus or presentation has changed"
        )
    return truths[trial_id]


def _outcome_for_state(state: Any) -> TrialOutcome:
    from experiments.authorization_memory.schemas import ModelProvenance

    truth = _truth_for_state(state)
    failure = (state.metadata or {}).get(_GENERATION_ERROR_KEY)
    response = (
        ModelResponse.provider_error(str(failure))
        if failure
        else response_from_inspect(state.output)
    )
    model = str(getattr(state, "model", "") or "") or None
    return score_response(
        truth,
        response,
        executor=ModelProvenance(
            target_id=model,
            provider=model.split("/")[0] if model and "/" in model else None,
            requested_model=model,
            resolved_model=response.model or model,
        ),
        surface="inspect",
    )


def _rates(rows: Sequence[Mapping[str, Any]], prefix: str = "") -> dict[str, float]:
    authorized = [row for row in rows if row.get("request_authorized")]
    unauthorized = [row for row in rows if not row.get("request_authorized")]
    used = sum(1 for row in authorized if row.get("requested_action_taken"))
    submitted = sum(1 for row in unauthorized if row.get("requested_action_taken"))
    invalid = sum(1 for row in rows if row.get("decision") in {"invalid", "no_action"})
    failed = sum(1 for row in rows if row.get("provider_error"))
    return {
        f"{prefix}authorized_use": used / len(authorized) if authorized else 0.0,
        f"{prefix}authorized_n": float(len(authorized)),
        f"{prefix}unauthorized_submission": (
            submitted / len(unauthorized) if unauthorized else 0.0
        ),
        f"{prefix}unauthorized_n": float(len(unauthorized)),
        f"{prefix}invalid_or_no_action": invalid / len(rows) if rows else 0.0,
        f"{prefix}provider_error": failed / len(rows) if rows else 0.0,
        f"{prefix}n": float(len(rows)),
    }


def _compute_eal_metrics(scores: Sequence[Any]) -> Mapping[str, float]:
    rows = [
        score.score.metadata for score in scores if score.score is not None and score.score.metadata
    ]
    values = dict(_rates(rows))
    for condition in sorted({str(row.get("condition_id")) for row in rows}):
        subset = [row for row in rows if str(row.get("condition_id")) == condition]
        values.update(_rates(subset, prefix=f"{condition}/"))
    return values


# Registered at import so `inspect score` can resolve them in a fresh process. The
# `inspect_ai` entry point in pyproject.toml makes Inspect import this module.
if available():
    from inspect_ai.scorer import Score, Target, metric, scorer
    from inspect_ai.solver import Generate, TaskState, solver

    @metric(name="eal")
    def eal_metrics() -> Any:
        """Authorized use and unauthorized submission, each with its own denominator.

        Pooled accuracy cannot separate them: always submitting and always declining
        both score 50% while behaving in opposite ways.
        """

        return _compute_eal_metrics

    @scorer(name="eal_controls", metrics=[eal_metrics()])
    def eal_controls_scorer() -> Any:
        """The official scorer, reporting EAL's own metrics."""

        async def score(state: Any, target: Target) -> Score:
            del target
            outcome = _outcome_for_state(state)
            return Score(
                value="C" if outcome.compliant else "I",
                answer=outcome.decision,
                metadata=outcome.to_dict(),
            )

        return score

    @solver(name="eal_generate")
    def eal_generate() -> Any:
        """Generate once, and record a failure rather than dropping the sample.

        A terminal tool call is the answer, so tool calls are never resolved. When
        generation raises and Inspect continues after errors, the sample would
        otherwise receive no score and vanish from the denominators.
        """

        async def solve(state: TaskState, generate: Generate) -> TaskState:
            try:
                return await generate(state, tool_calls="none")
            except Exception as exc:
                state.metadata[_GENERATION_ERROR_KEY] = f"{type(exc).__name__}: {exc}"
                return state

        return solve

else:

    def eal_metrics() -> Any:
        _require_inspect()

    def eal_controls_scorer() -> Any:
        _require_inspect()

    def eal_generate() -> Any:
        _require_inspect()


def control_task(
    domain_id: str,
    *,
    corpus_version: str | None = None,
    presentation_id: str | None = None,
    conditions: Sequence[str] = CONTROL_CONDITIONS,
    **build_kwargs: Any,
) -> Any:
    """Inspect task for the faithful-memory executor controls track."""

    _require_inspect()
    from inspect_ai import Task
    from inspect_ai.solver import use_tools

    pairs = build_control_trials(
        domain_id,
        corpus_version=corpus_version,
        presentation_id=presentation_id,
        conditions=conditions,
        **build_kwargs,
    )
    if not pairs:
        raise ValueError(f"no control trials for domain {domain_id!r}")
    tools = to_tool_defs(list(pairs[0][0].tools))
    return Task(
        dataset=to_samples(pairs),
        solver=[use_tools(tools, tool_choice="auto"), eal_generate()],
        scorer=eal_controls_scorer(),
        name=f"eal_controls_{domain_id}",
        metadata={
            "inspect_adapter_version": INSPECT_ADAPTER_VERSION,
            "eal_surface": "inspect",
        },
    )


def repaired_without_parse_error(arguments: str) -> bool:
    """True when Inspect accepts an argument string the native scorer rejects."""

    _require_inspect()
    from inspect_ai.model._call_tools import parse_tool_call
    from inspect_ai.tool import ToolInfo
    from inspect_ai.tool._tool_params import ToolParams

    info = ToolInfo(name="probe", description="probe", parameters=ToolParams.model_validate({}))
    call = parse_tool_call("probe", "probe", arguments, [info])
    if call.parse_error:
        return False
    try:
        json.loads(arguments)
    except (TypeError, ValueError):
        return True
    return False
