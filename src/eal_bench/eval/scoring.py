"""Scoring for reusable evaluation tracks.

This module does not implement scoring. It delegates to the runner's own
`_score_executor_response`, so a track and the internal experiment runner cannot
drift apart. The private import is deliberate and follows the existing pattern in
`domains/cybersecurity/prepare_final_release.py`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from experiments.authorization_memory.pipeline import _score_executor_response
from experiments.authorization_memory.schemas import ModelProvenance, NormalizedTrial

from .resources import load_domain
from .trials import ModelResponse, Trial, TrialTruth

__all__ = ["TrialOutcome", "score_response", "score_many"]

_UNROUTED_EXECUTOR = ModelProvenance(
    target_id=None,
    provider=None,
    requested_model=None,
    resolved_model=None,
)


@dataclass(frozen=True)
class TrialOutcome:
    """The behavioral fields of a scored trial, without run provenance."""

    trial_id: str
    domain_id: str
    case_id: str
    probe_id: str
    pair_id: str
    condition_id: str
    request_authorized: bool
    decision: str
    requested_action_taken: bool
    unauthorized_action_taken: bool
    action_mismatch: bool
    compliant: bool
    parseable: bool
    provider_error: str | None
    finish_reason: str | None
    tool_call_count: int
    terminal_call_count: int
    tool_name: str | None
    tool_arguments: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _provider_payload(response: ModelResponse) -> dict[str, Any] | Exception:
    if response.error is not None:
        return RuntimeError(response.error)
    return {
        "model": response.model,
        "choices": [
            {
                "message": {
                    "content": response.text,
                    "tool_calls": [
                        {
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            }
                        }
                        for call in response.tool_calls
                    ],
                },
                "finish_reason": response.finish_reason,
            }
        ],
    }


def _project(trial_id: str, truth: TrialTruth, trial: NormalizedTrial) -> TrialOutcome:
    return TrialOutcome(
        trial_id=trial_id,
        domain_id=trial.domain_id,
        case_id=trial.case_id,
        probe_id=trial.probe_id,
        pair_id=truth.pair_id,
        condition_id=trial.condition_id,
        request_authorized=trial.request_authorized,
        decision=trial.decision.value,
        requested_action_taken=trial.requested_action_taken,
        unauthorized_action_taken=trial.unauthorized_action_taken,
        action_mismatch=trial.action_mismatch,
        compliant=trial.compliant,
        parseable=trial.parseable,
        provider_error=trial.provider_error,
        finish_reason=trial.finish_reason,
        tool_call_count=trial.tool_call_count,
        terminal_call_count=trial.terminal_call_count,
        tool_name=trial.raw_tool_name,
        tool_arguments=trial.raw_tool_arguments,
    )


def score_response(truth: TrialTruth, response: ModelResponse) -> TrialOutcome:
    if truth.case is None or truth.probe is None or truth.evidence is None:
        raise ValueError(
            f"trial {truth.trial_id!r} carries no scoring handles; "
            "build it with a track builder rather than from serialized fields"
        )
    domain = load_domain(truth.domain_id)
    normalized = _score_executor_response(
        domain,
        truth.case,
        truth.probe,
        truth.evidence,
        _provider_payload(response),
        _UNROUTED_EXECUTOR,
        executor_run_id=0,
        seed=truth.seed,
        trial_id=truth.trial_id,
        call_id=f"{truth.trial_id}:call",
        model_context_id=f"{truth.trial_id}:context",
        presentation=truth.presentation,
        presentation_hash=truth.presentation_hash,
    )
    return _project(truth.trial_id, truth, normalized)


def score_many(
    pairs: list[tuple[Trial, TrialTruth]],
    responses: list[ModelResponse],
) -> list[TrialOutcome]:
    if len(pairs) != len(responses):
        raise ValueError(f"got {len(responses)} responses for {len(pairs)} trials")
    return [score_response(truth, response) for (_, truth), response in zip(pairs, responses)]
