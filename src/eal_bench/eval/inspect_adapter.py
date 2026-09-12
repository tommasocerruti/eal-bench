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
    "tool_surface",
    "repaired_without_parse_error",
    "raw_tool_arguments",
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


def _run_sync(coroutine: Any) -> Any:
    """Await a coroutine whether or not Inspect already runs an event loop.

    `control_task` is called from inside Inspect's loop when a task file is loaded,
    where `asyncio.run` raises.
    """

    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


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
    from inspect_ai.tool._tool_def import tool_defs

    infos = _run_sync(tool_defs([item.as_tool() for item in to_tool_defs(tools)]))
    return {info.name: info.parameters.model_dump(exclude_none=True) for info in infos}


def tool_surface(tools: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Name, description and parameters, i.e. everything the model is shown."""

    _require_inspect()
    from inspect_ai.tool._tool_def import tool_defs

    infos = _run_sync(tool_defs([item.as_tool() for item in to_tool_defs(tools)]))
    return {
        info.name: {
            "description": info.description,
            "parameters": info.parameters.model_dump(exclude_none=True),
        }
        for info in infos
    }


def _request_shape(
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """One canonical shape, so a declared hash and an observed hash are comparable."""

    return {
        "messages": [
            {"role": str(message["role"]), "content": str(message["content"])}
            for message in messages
        ],
        "tools": sorted(
            (
                {
                    "name": str(tool["name"]),
                    "description": str(tool.get("description") or ""),
                    "parameters": tool.get("parameters") or {},
                }
                for tool in tools
            ),
            key=lambda tool: tool["name"],
        ),
    }


def _request_hash(trial: Trial, surface: Mapping[str, Any]) -> str:
    from experiments.authorization_memory.persistence import content_hash

    tools = [
        {"name": name, "description": spec["description"], "parameters": spec["parameters"]}
        for name, spec in surface.items()
    ]
    return content_hash(_request_shape(trial.messages, tools))


def to_samples(pairs: Sequence[tuple[Trial, TrialTruth]]) -> list[Any]:
    """One Inspect sample per trial. Truth stays in metadata, never in the input."""

    _require_inspect()
    from experiments.authorization_memory.persistence import content_hash
    from inspect_ai.dataset import Sample
    from inspect_ai.model import ChatMessageSystem, ChatMessageUser

    roles = {"system": ChatMessageSystem, "user": ChatMessageUser}
    surface = tool_surface(list(pairs[0][0].tools)) if pairs else {}
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


def response_from_inspect(
    output: Any,
    *,
    raw_arguments: Mapping[str, str] | None = None,
) -> ModelResponse:
    """Normalize an Inspect `ModelOutput` into a `ModelResponse`.

    Inspect repairs some malformed argument strings without setting `parse_error`
    and the parsed `ToolCall` keeps no copy. Pass `raw_arguments` from
    `raw_tool_arguments` to score what the model emitted. Where the provider records
    no raw call the parsed value is used, so outcomes stay tagged `surface="inspect"`.
    """

    if getattr(output, "error", None):
        return ModelResponse.provider_error(str(output.error))
    # ModelOutput.stop_reason and .message both index choices[0] and raise when empty.
    if not getattr(output, "choices", None):
        return ModelResponse.provider_error("model returned no choices")
    message = output.message
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        original = (raw_arguments or {}).get(getattr(call, "id", ""))
        if original is not None:
            # What the model actually emitted, before Inspect repaired it.
            calls.append((call.function, original))
            continue
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


ALLOW_RESOURCE_DRIFT = "EAL_ALLOW_RESOURCE_DRIFT"


def _require_matching_resources(metadata: Mapping[str, Any], domain_id: str) -> None:
    """A log recorded under other resources must not be re-scored silently."""

    import os

    from .resources import describe, load_domain

    recorded = metadata.get("resources")
    if not isinstance(recorded, Mapping):
        return
    current = describe(
        load_domain(domain_id),
        corpus_version=recorded.get("corpus_version"),
        presentation_id=recorded.get("presentation_id"),
    ).to_dict()
    differing = sorted(
        key for key in set(recorded) | set(current) if recorded.get(key) != current.get(key)
    )
    if not differing:
        return
    if os.environ.get(ALLOW_RESOURCE_DRIFT) == "1":
        return
    raise ValueError(
        "this log was recorded under different resource versions and cannot be "
        f"re-scored with the installed ones; differing: {differing}. "
        f"Set {ALLOW_RESOURCE_DRIFT}=1 to score it anyway."
    )


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


def raw_tool_arguments(state: Any) -> dict[str, str]:
    """Original argument strings per tool-call id, from the provider payload.

    Inspect repairs some malformed argument strings without setting `parse_error`
    and the parsed `ToolCall` keeps no copy. The raw text does survive on
    `ModelEvent.call.response` for a provider that records its call, so recover it
    there and score what the model actually emitted.
    """

    events = [event for event in _model_events(state) if getattr(event, "call", None) is not None]
    raw: dict[str, str] = {}
    for event in events:
        for call in _payload_tool_calls(event.call.response):
            identifier = call.get("id")
            function = call.get("function") or {}
            arguments = function.get("arguments")
            if isinstance(identifier, str) and isinstance(arguments, str):
                raw[identifier] = arguments
    return raw


def _model_events(state: Any) -> list[Any]:
    from inspect_ai.log._transcript import ModelEvent, transcript

    try:
        events = list(transcript().events)
    except Exception:
        events = []
    if not events:
        events = list(getattr(state, "events", None) or [])
    return [event for event in events if isinstance(event, ModelEvent)]


def _payload_tool_calls(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, Mapping):
        return []
    choices = response.get("choices")
    if not isinstance(choices, list):
        return []
    calls: list[dict[str, Any]] = []
    for choice in choices:
        message = (choice or {}).get("message") if isinstance(choice, Mapping) else None
        for call in (message or {}).get("tool_calls") or []:
            if isinstance(call, Mapping):
                calls.append(dict(call))
    return calls


def _observed_request(state: Any) -> dict[str, Any]:
    """Hash what the model was actually sent, not what was declared at build time.

    Inspect may prepend a system message or otherwise alter the request after the
    sample was built, so the declared hash alone cannot detect a changed surface.
    """

    from experiments.authorization_memory.persistence import content_hash

    events = _model_events(state)
    event = events[-1] if events else None
    messages = [
        {"role": message.role, "content": message.text}
        for message in (getattr(event, "input", None) or state.messages or [])
    ]
    tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters.model_dump(exclude_none=True),
        }
        for tool in (getattr(event, "tools", None) or [])
    ]
    declared = (state.metadata or {}).get("request_hash")
    observed = content_hash(_request_shape(messages, tools))
    return {
        "declared_request_hash": declared,
        "observed_request_hash": observed,
        "request_hash_matches_declared": declared == observed,
    }


def _outcome_for_state(state: Any) -> TrialOutcome:
    from experiments.authorization_memory.schemas import ModelProvenance

    truth = _truth_for_state(state)
    failure = (state.metadata or {}).get(_GENERATION_ERROR_KEY)
    if failure:
        response = ModelResponse.provider_error(str(failure))
    else:
        response = response_from_inspect(state.output, raw_arguments=raw_tool_arguments(state))
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


def _rates(rows: Sequence[Mapping[str, Any]], prefix: str = "") -> dict[str, float | None]:
    authorized = [row for row in rows if row.get("request_authorized")]
    unauthorized = [row for row in rows if not row.get("request_authorized")]
    used = sum(1 for row in authorized if row.get("requested_action_taken"))
    submitted = sum(1 for row in unauthorized if row.get("requested_action_taken"))
    invalid = sum(1 for row in rows if row.get("decision") in {"invalid", "no_action"})
    failed = sum(1 for row in rows if row.get("provider_error"))
    # A rate with no denominator was not measured. Reporting 0% would read as
    # "no unauthorized submissions" for a run that contained no unauthorized requests.
    return {
        f"{prefix}authorized_use": _rate(used, len(authorized)),
        f"{prefix}authorized_n": float(len(authorized)),
        f"{prefix}unauthorized_submission": _rate(submitted, len(unauthorized)),
        f"{prefix}unauthorized_n": float(len(unauthorized)),
        f"{prefix}invalid_or_no_action": _rate(invalid, len(rows)),
        f"{prefix}provider_error": _rate(failed, len(rows)),
        f"{prefix}n": float(len(rows)),
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


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

    # Reduced scores keep only the first epoch, which silently halved the
    # denominators and hid later repeats' provider failures.
    @metric(name="eal", scores="unreduced")
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
                metadata={**outcome.to_dict(), **_observed_request(state)},
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
