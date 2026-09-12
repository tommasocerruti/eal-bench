"""Framework-neutral trial types.

`Trial` holds model-visible data only. `TrialTruth` holds the oracle state and the
handles the official scorer needs. Splitting them is what keeps evaluator-only
information out of a model request by construction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .resources import ResourceVersions

__all__ = ["ModelResponse", "ToolCall", "Trial", "TrialTruth"]


@dataclass(frozen=True)
class Trial:
    trial_id: str
    messages: tuple[dict[str, str], ...]
    tools: tuple[dict[str, Any], ...]
    tool_choice: str
    resources: ResourceVersions

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "messages": [dict(message) for message in self.messages],
            "tools": [dict(tool) for tool in self.tools],
            "tool_choice": self.tool_choice,
            "resources": self.resources.to_dict(),
        }

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> Trial:
        return cls(
            trial_id=str(row["trial_id"]),
            messages=tuple(dict(message) for message in row["messages"]),
            tools=tuple(dict(tool) for tool in row["tools"]),
            tool_choice=str(row.get("tool_choice", "auto")),
            resources=ResourceVersions(**row["resources"]),
        )


@dataclass(frozen=True)
class TrialTruth:
    trial_id: str
    domain_id: str
    case_id: str
    probe_id: str
    pair_id: str
    dimension: str
    condition_id: str
    request_authorized: bool
    oracle_reason: str
    seed: int
    case: Any = field(repr=False, default=None)
    probe: Any = field(repr=False, default=None)
    evidence: Any = field(repr=False, default=None)
    presentation: Any = field(repr=False, default=None)
    presentation_hash: str = ""
    resources: ResourceVersions | None = None

    def to_dict(self) -> dict[str, Any]:
        """Scalar fields only. The object handles are deliberately omitted."""
        return {
            "trial_id": self.trial_id,
            "domain_id": self.domain_id,
            "case_id": self.case_id,
            "probe_id": self.probe_id,
            "pair_id": self.pair_id,
            "dimension": self.dimension,
            "condition_id": self.condition_id,
            "request_authorized": self.request_authorized,
            "oracle_reason": self.oracle_reason,
            "seed": self.seed,
            "resource_key": self.resources.key if self.resources is not None else None,
        }


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: str | Mapping[str, Any] | None


@dataclass(frozen=True)
class ModelResponse:
    """One executor reply, normalized away from any provider or framework shape."""

    tool_calls: tuple[ToolCall, ...] = ()
    text: str = ""
    finish_reason: str | None = None
    error: str | None = None
    error_type: str | None = None
    model: str | None = None

    @classmethod
    def from_tool_calls(
        cls,
        calls: Sequence[tuple[str, Any]],
        *,
        text: str = "",
        finish_reason: str | None = "tool_calls",
        model: str | None = None,
    ) -> ModelResponse:
        return cls(
            tool_calls=tuple(ToolCall(name, arguments) for name, arguments in calls),
            text=text,
            finish_reason=finish_reason,
            model=model,
        )

    @classmethod
    def provider_error(cls, detail: str, error_type: str = "ProviderError") -> ModelResponse:
        return cls(error=detail, error_type=error_type)

    @classmethod
    def from_openai(cls, completion: Any) -> ModelResponse:
        """Normalize an OpenAI-shaped reply, or an exception raised in its place.

        Accepts the SDK object or the equivalent mapping. Uses the runner's own
        readers, so a reply reaching the scorer through this path is read the same
        way the experiment runner reads it.
        """

        from experiments.authorization_memory.pipeline import (
            _finish_reason,
            _response_model,
            _response_text,
            _response_tool_calls,
            _tool_name_arguments,
        )

        if isinstance(completion, BaseException):
            return cls.provider_error(str(completion), error_type=type(completion).__name__)
        return cls.from_tool_calls(
            [_tool_name_arguments(call) for call in _response_tool_calls(completion)],
            text=_response_text(completion),
            finish_reason=_finish_reason(completion),
            model=_response_model(completion),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_calls": [
                {"name": call.name, "arguments": call.arguments} for call in self.tool_calls
            ],
            "text": self.text,
            "finish_reason": self.finish_reason,
            "error": self.error,
            "error_type": self.error_type,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> ModelResponse:
        return cls(
            tool_calls=tuple(
                ToolCall(str(call["name"]), call.get("arguments"))
                for call in row.get("tool_calls", ())
            ),
            text=str(row.get("text", "")),
            finish_reason=row.get("finish_reason"),
            error=row.get("error"),
            error_type=row.get("error_type"),
            model=row.get("model"),
        )
