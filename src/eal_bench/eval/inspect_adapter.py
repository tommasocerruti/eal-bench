"""Optional Inspect integration.

Requires the `inspect` extra. The caller supplies its own model and model
configuration; this module supplies the trials, the tools and the official scorer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .controls import build_control_trials
from .scoring import TrialOutcome, score_response
from .trials import ModelResponse, Trial, TrialTruth

__all__ = [
    "INSTALL_HINT",
    "available",
    "control_task",
    "missing_parameter_descriptions",
    "rendered_tool_surface",
    "response_from_inspect",
    "score_inspect_state",
    "to_samples",
    "to_tool_defs",
]

INSTALL_HINT = 'install the Inspect extra: pip install "eal-bench[inspect]"'


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


def to_tool_defs(tools: Sequence[dict[str, Any]]) -> list[Any]:
    """Convert EAL's OpenAI-shaped tool schemas into Inspect tool definitions.

    The callables are never invoked. A terminal action is scored from the call rather
    than executed.

    Inspect rejects a parameter with no description, and some EAL parameters have none.
    Those are filled with the parameter name, which adds no meaning the key does not
    already carry. `missing_parameter_descriptions` lists exactly which ones.
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


def rendered_tool_surface(tools: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The parameter schema Inspect actually sends, after conversion.

    Inspect re-derives tool info from the converted definitions, so this can differ
    from the schema the native runner sends. Use it to audit that difference.
    """

    _require_inspect()
    import asyncio

    from inspect_ai.tool._tool_def import tool_defs

    infos = asyncio.run(tool_defs([item.as_tool() for item in to_tool_defs(tools)]))
    return {info.name: info.parameters.model_dump(exclude_none=True) for info in infos}


def to_samples(pairs: Sequence[tuple[Trial, TrialTruth]]) -> list[Any]:
    """One Inspect sample per trial. Truth stays in metadata, never in the input."""

    _require_inspect()
    from inspect_ai.dataset import Sample
    from inspect_ai.model import ChatMessageSystem, ChatMessageUser

    roles = {"system": ChatMessageSystem, "user": ChatMessageUser}
    return [
        Sample(
            id=trial.trial_id,
            input=[
                roles[message["role"]](content=message["content"]) for message in trial.messages
            ],
            metadata={"resources": trial.resources.to_dict(), "truth": truth.to_dict()},
        )
        for trial, truth in pairs
    ]


def response_from_inspect(output: Any) -> ModelResponse:
    """Normalize an Inspect `ModelOutput` into a `ModelResponse`."""

    if getattr(output, "error", None):
        return ModelResponse.provider_error(str(output.error))
    # ModelOutput.stop_reason and .message both index choices[0] and raise when empty.
    if not getattr(output, "choices", None):
        return ModelResponse.provider_error("model returned no choices")
    message = output.message
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        # Inspect reports unparseable arguments in `parse_error` and leaves `arguments`
        # empty. Forward the failure so the scorer reaches the same invalid outcome.
        parse_error = getattr(call, "parse_error", None)
        calls.append((call.function, parse_error if parse_error else call.arguments))
    return ModelResponse.from_tool_calls(
        calls,
        text=message.text or "",
        finish_reason=output.stop_reason,
        model=str(getattr(output, "model", "") or "") or None,
    )


def score_inspect_state(truth: TrialTruth, state: Any) -> TrialOutcome:
    return score_response(truth, response_from_inspect(state.output))


def control_task(
    domain_id: str,
    *,
    corpus_version: str | None = None,
    presentation_id: str | None = None,
    **build_kwargs: Any,
) -> Any:
    """Inspect task for the faithful-memory executor controls track."""

    _require_inspect()
    from inspect_ai import Task
    from inspect_ai.scorer import Score, Target, accuracy, scorer
    from inspect_ai.solver import generate, use_tools

    pairs = build_control_trials(
        domain_id,
        corpus_version=corpus_version,
        presentation_id=presentation_id,
        **build_kwargs,
    )
    if not pairs:
        raise ValueError(f"no control trials for domain {domain_id!r}")
    truths = {truth.trial_id: truth for _, truth in pairs}
    tools = to_tool_defs(list(pairs[0][0].tools))

    @scorer(metrics=[accuracy()])
    def eal_controls_scorer() -> Any:
        async def score(state: Any, target: Target) -> Score:
            del target
            outcome = score_inspect_state(truths[str(state.sample_id)], state)
            return Score(
                value="C" if outcome.compliant else "I",
                answer=outcome.decision,
                metadata=outcome.to_dict(),
            )

        return score

    return Task(
        dataset=to_samples(pairs),
        # A terminal tool call is the answer. Resolving it would execute the action
        # and loop for another generation.
        solver=[use_tools(tools, tool_choice="auto"), generate(tool_calls="none")],
        scorer=eal_controls_scorer(),
        name=f"eal_controls_{domain_id}",
    )
