"""Optional Inspect integration.

Requires the `inspect` extra. The caller supplies its own model and model
configuration; this module supplies the trials, the tools and the official scorer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .controls import build_control_trials
from .scoring import score_response
from .trials import ModelResponse, Trial, TrialTruth

__all__ = ["INSTALL_HINT", "control_task", "response_from_inspect", "to_samples"]

INSTALL_HINT = 'install the Inspect extra: pip install "eal-bench[inspect]"'


def _require_inspect() -> Any:
    try:
        import inspect_ai
    except ImportError as exc:  # pragma: no cover - depends on the extra
        raise ImportError(INSTALL_HINT) from exc
    return inspect_ai


def to_samples(pairs: Sequence[tuple[Trial, TrialTruth]]) -> list[Any]:
    """One Inspect sample per trial. Truth stays in metadata, never in the input."""

    from inspect_ai.dataset import Sample

    return [
        Sample(
            id=trial.trial_id,
            input=[dict(message) for message in trial.messages],
            metadata={
                "trial": trial.to_dict(),
                "truth": truth.to_dict(),
            },
        )
        for trial, truth in pairs
    ]


def response_from_inspect(state: Any) -> ModelResponse:
    """Normalize an Inspect `TaskState` output into a `ModelResponse`."""

    message = state.output.message
    error = getattr(state.output, "error", None)
    if error:
        return ModelResponse.provider_error(str(error))
    calls = [
        (call.function, call.arguments)
        for call in (getattr(message, "tool_calls", None) or [])
    ]
    return ModelResponse.from_tool_calls(
        calls,
        text=message.text or "",
        finish_reason=getattr(state.output, "stop_reason", None),
        model=getattr(state.output, "model", None),
    )


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
    truths = {truth.trial_id: truth for _, truth in pairs}
    tools = list(pairs[0][0].tools) if pairs else []

    @scorer(metrics=[accuracy()])
    def eal_scorer() -> Any:
        async def score(state: Any, target: Target) -> Score:
            del target
            truth = truths[str(state.sample_id)]
            outcome = score_response(truth, response_from_inspect(state))
            return Score(
                value="C" if outcome.compliant else "I",
                answer=outcome.decision,
                metadata=outcome.to_dict(),
            )

        return score

    return Task(
        dataset=to_samples(pairs),
        solver=[use_tools(tools), generate()],
        scorer=eal_scorer(),
        name=f"eal_controls_{domain_id}",
    )
