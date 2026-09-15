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

    def to_portable(self) -> dict[str, Any]:
        """Everything needed to rebuild this truth in another process.

        Cases, probes and presentations ship in the package and are reloaded by
        id. A supplied memory does not, so the frozen evidence travels with the
        log; without it a saved run of caller-supplied memories could only be
        re-scored in the process that built it.
        """

        from dataclasses import asdict, is_dataclass

        evidence = self.evidence
        if evidence is not None and is_dataclass(evidence):
            payload = asdict(evidence)
            architecture = payload.get("architecture")
            payload["architecture"] = getattr(architecture, "value", architecture)
        else:
            payload = None
        return {
            **self.to_dict(),
            "presentation_id": getattr(self.presentation, "presentation_id", None),
            "presentation_hash": self.presentation_hash,
            "evidence": payload,
            "resources": self.resources.to_dict() if self.resources is not None else None,
        }

    @classmethod
    def from_portable(cls, row: Mapping[str, Any]) -> TrialTruth:
        """Rebuild a truth from `to_portable`, reloading what the package ships."""

        from experiments.authorization_memory.schemas import (
            FrozenEvidence,
            MemoryArchitecture,
            ModelProvenance,
        )

        from .resources import load_domain, resolve_presentation

        domain = load_domain(str(row["domain_id"]))
        resources = row.get("resources")
        version = (resources or {}).get("corpus_version") or domain.corpus.default_version
        case = next(
            (
                candidate
                for candidate in domain.corpus.load_cases(version)
                if domain.corpus.case_id(candidate) == row["case_id"]
            ),
            None,
        )
        if case is None:
            raise ValueError(f"case {row['case_id']!r} is absent from {row['domain_id']}/{version}")
        probe = next((p for p in domain.corpus.probes(case) if p.probe_id == row["probe_id"]), None)
        if probe is None:
            raise ValueError(f"probe {row['probe_id']!r} is absent from case {row['case_id']!r}")

        evidence = None
        if row.get("evidence") is not None:
            fields = dict(row["evidence"])
            architecture = fields.get("architecture")
            if architecture is not None:
                fields["architecture"] = MemoryArchitecture(architecture)
            writer = fields.get("writer")
            if isinstance(writer, Mapping):
                fields["writer"] = ModelProvenance(**writer)
            evidence = FrozenEvidence(**fields)

        return cls(
            trial_id=str(row["trial_id"]),
            domain_id=str(row["domain_id"]),
            case_id=str(row["case_id"]),
            probe_id=str(row["probe_id"]),
            pair_id=str(row["pair_id"]),
            dimension=str(row["dimension"]),
            condition_id=str(row["condition_id"]),
            request_authorized=bool(row["request_authorized"]),
            oracle_reason=str(row["oracle_reason"]),
            seed=int(row["seed"]),
            case=case,
            probe=probe,
            evidence=evidence,
            presentation=resolve_presentation(domain, row.get("presentation_id")),
            presentation_hash=str(row.get("presentation_hash") or ""),
            resources=ResourceVersions(**resources) if resources else None,
        )


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
