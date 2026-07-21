from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from domains.base import ActionDecision, MemoryArchitecture


TRIAL_SCHEMA_VERSION = 5
TYPED_MEMORY_PAYLOAD_SCHEMA_VERSION = "3"
LANGMEM_IMPLEMENTATION_ID = "langmem_profile"
ARTIFACT_SCHEMA_VERSIONS = {
    "trials": TRIAL_SCHEMA_VERSION,
    "memories": 4,
    "memory_attempts": 6,
    "memory_states": 3,
    "evidence": 3,
    "model_contexts": 1,
    "typed_memory_payload": TYPED_MEMORY_PAYLOAD_SCHEMA_VERSION,
}


class MemoryOrigin(str, Enum):
    EMPTY = "empty"
    FULL_HISTORY = "full_history"
    FAITHFUL = "faithful"
    WRITER = "writer"
    CONTROLLED = "controlled"


class Decision(str, Enum):
    EXECUTE_REQUESTED = "execute_requested"
    EXECUTE_OTHER = "execute_other"
    DECLINE = "decline"
    ESCALATE = "escalate"
    NO_ACTION = "no_action"
    INVALID = "invalid"
    PROVIDER_ERROR = "provider_error"

    @classmethod
    def from_action(cls, action: ActionDecision) -> Decision:
        mapping = {
            ActionDecision.EXECUTE_REQUESTED: cls.EXECUTE_REQUESTED,
            ActionDecision.EXECUTE_OTHER: cls.EXECUTE_OTHER,
            ActionDecision.DECLINE: cls.DECLINE,
            ActionDecision.ESCALATE: cls.ESCALATE,
            ActionDecision.NO_ACTION: cls.NO_ACTION,
            ActionDecision.INVALID: cls.INVALID,
        }
        return mapping[action]


@dataclass(frozen=True)
class ModelProvenance:
    target_id: str | None
    provider: str | None
    requested_model: str | None
    resolved_model: str | None
    response_model: str | None = None
    effective_parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryArtifact:
    memory_id: str
    parent_memory_id: str | None
    chain_id: str
    domain_id: str
    case_id: str
    condition_id: str
    block_index: int
    writer_run_id: int | None
    writer_seed: int | None
    writer: ModelProvenance | None
    architecture: MemoryArchitecture
    origin: MemoryOrigin
    payload_schema_id: str | None
    payload_schema_version: str | None
    payload: str | dict[str, Any]
    reference_tokens: int
    reference_tokenizer: str
    content_hash: str
    presentation_id: str
    presentation_hash: str
    memory_implementation_id: str | None = None
    memory_implementation_hash: str | None = None
    profile_id: str | None = None
    source_attempt_id: str | None = None
    framework_run_ids: tuple[str, ...] = ()
    framework: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 4

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["architecture"] = self.architecture.value
        data["origin"] = self.origin.value
        return data


@dataclass(frozen=True)
class MemoryAttempt:
    attempt_id: str
    logical_update_id: str
    attempt_index: int
    repair_of_attempt_id: str | None
    domain_id: str
    case_id: str
    condition_id: str
    block_index: int
    writer_run_id: int
    writer_seed: int
    architecture: MemoryArchitecture
    writer: ModelProvenance
    parent_memory_id: str | None
    status: str
    detail: str
    raw_arguments: Any
    accepted_memory_id: str | None
    retained_memory_id: str | None
    memory_implementation_hash: str
    presentation_id: str
    presentation_hash: str
    memory_implementation_id: str = LANGMEM_IMPLEMENTATION_ID
    profile_id: str | None = None
    profile_schema_id: str | None = None
    payload_schema_id: str | None = None
    payload_schema_version: str | None = None
    framework_run_ids: tuple[str, ...] = ()
    framework: dict[str, Any] = field(default_factory=dict)
    candidate_payload: Any = None
    changed: bool | None = None
    schema_version: int = 6

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["architecture"] = self.architecture.value
        return data


@dataclass(frozen=True)
class MemoryState:
    state_id: str
    logical_update_id: str
    attempt_ids: tuple[str, ...]
    domain_id: str
    case_id: str
    condition_id: str
    block_index: int
    writer_run_id: int
    writer_seed: int
    architecture: MemoryArchitecture
    profile_id: str
    current_memory_id: str | None
    status: str
    changed: bool
    memory_implementation_hash: str
    presentation_id: str
    presentation_hash: str
    memory_implementation_id: str = LANGMEM_IMPLEMENTATION_ID
    schema_version: int = 3

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["architecture"] = self.architecture.value
        return data


@dataclass(frozen=True)
class FrozenEvidence:
    evidence_id: str
    domain_id: str
    case_id: str
    condition_id: str
    memory_run_id: int
    writer_seed: int | None
    writer: ModelProvenance | None
    architecture: MemoryArchitecture | None
    memory_id: str | None
    payload: str | dict[str, Any] | None
    source_history: str | None
    content_hash: str
    presentation_id: str
    presentation_hash: str
    memory_implementation_id: str | None = None
    memory_implementation_hash: str | None = None
    profile_id: str | None = None
    source_attempt_id: str | None = None
    schema_version: int = 3

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["architecture"] = (
            self.architecture.value if self.architecture is not None else None
        )
        return data


@dataclass(frozen=True)
class NormalizedTrial:
    domain_id: str
    domain_adapter_version: str
    case_id: str
    probe_id: str
    condition_id: str
    writer: ModelProvenance | None
    executor: ModelProvenance
    writer_run_id: int
    writer_seed: int | None
    executor_run_id: int
    seed: int
    evidence_id: str
    memory_id: str | None
    request_authorized: bool
    decision: Decision
    requested_action_taken: bool
    unauthorized_action_taken: bool
    action_mismatch: bool
    compliant: bool
    parseable: bool
    provider_error: str | None
    finish_reason: str | None
    response_text: str
    tool_call_count: int
    terminal_call_count: int
    raw_tool_name: str | None
    raw_tool_arguments: Any
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    schema_version: int = TRIAL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        return data


@dataclass(frozen=True)
class ModelContext:
    context_id: str
    content_hash: str
    stage: str
    domain_id: str
    case_id: str
    condition_id: str
    block_index: int | None
    probe_id: str | None
    writer_run_id: int | None
    executor_run_id: int | None
    memory_id: str | None
    memory_attempt_id: str | None
    evidence_id: str | None
    trial_id: str | None
    call_id: str
    framework_run_id: str | None
    messages: tuple[dict[str, Any], ...]
    tools: tuple[dict[str, Any], ...]
    tool_choice: Any
    model: ModelProvenance
    presentation_id: str
    presentation_hash: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["messages"] = list(self.messages)
        data["tools"] = list(self.tools)
        return data
