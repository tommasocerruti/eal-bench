from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from experiments.authorization_memory.schemas import ModelProvenance

from ..schemas import (
    TYPED_MEMORY_PAYLOAD_SCHEMA_ID,
    TYPED_MEMORY_PAYLOAD_SCHEMA_VERSION,
)

TYPED_MEMORY_SCHEMA_VERSION = TYPED_MEMORY_PAYLOAD_SCHEMA_VERSION
MEMORY_ATTEMPT_SCHEMA_VERSION = 3
TypedAuthorizationAction = Literal["submit_order"]
TypedAuthorizationEffect = Literal["permit_exception"]


class MemoryArchitecture(str, Enum):
    FREE_TEXT = "free_text"
    TYPED = "typed"


class MemoryOrigin(str, Enum):
    EMPTY = "empty"
    FULL_HISTORY = "full_history"
    FAITHFUL = "faithful"
    WRITER = "writer"
    CONTROLLED = "controlled"


class ExecutorPressure(str, Enum):
    BASELINE = "baseline"


class AuthorizationMemoryStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class MemoryUpdateStatus(str, Enum):
    ACCEPTED = "accepted"
    MISSING_TOOL_CALL = "missing_tool_call"
    MULTIPLE_TOOL_CALLS = "multiple_tool_calls"
    UNEXPECTED_TOOL = "unexpected_tool"
    MALFORMED_ARGUMENTS = "malformed_arguments"
    INVALID_PAYLOAD = "invalid_payload"
    UNKNOWN_SOURCE_ID = "unknown_source_id"
    CAPACITY_OVERFLOW = "capacity_overflow"
    WRITER_ERROR = "writer_error"


@dataclass(frozen=True)
class TypedAuthorizationState:
    authorization_id: str
    issuer: str | None
    grantee: str | None
    effect: TypedAuthorizationEffect | None
    action: TypedAuthorizationAction | None
    vendor: str | None
    allowed_categories: tuple[str, ...] | None
    max_amount: int | None
    currency: str | None
    valid_from: str | None
    valid_until: str | None
    status: AuthorizationMemoryStatus
    supersedes: str | None
    source_turn_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the domain-native flat representation used by study logic."""

        return {
            "authorization_id": self.authorization_id,
            "issuer": self.issuer,
            "grantee": self.grantee,
            "effect": self.effect,
            "action": self.action,
            "vendor": self.vendor,
            "allowed_categories": (
                list(self.allowed_categories) if self.allowed_categories is not None else None
            ),
            "max_amount": self.max_amount,
            "currency": self.currency,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "status": self.status.value,
            "supersedes": self.supersedes,
            "source_turn_ids": list(self.source_turn_ids),
        }

    def to_envelope_dict(self) -> dict[str, Any]:
        """Return the shared authorization envelope with a procurement scope."""

        return {
            "authorization_id": self.authorization_id,
            "issuer": self.issuer,
            "grantee": self.grantee,
            "effect": (
                self.effect if self.effect in {None, "permit_exception"} else None
            ),
            "action": self.action if self.action in {None, "submit_order"} else None,
            "status": self.status.value,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "scope": {
                "vendor": self.vendor,
                "allowed_categories": (
                    list(self.allowed_categories)
                    if self.allowed_categories is not None
                    else None
                ),
                "max_amount": self.max_amount,
                "currency": self.currency,
            },
            "supersedes": self.supersedes,
            "source_turn_ids": list(self.source_turn_ids),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> TypedAuthorizationState:
        scope = data.get("scope")
        if not isinstance(scope, dict):
            raise ValueError("schema-v3 authorization scope must be an object")
        vendor = scope["vendor"]
        allowed_categories = scope["allowed_categories"]
        max_amount = scope["max_amount"]
        currency = scope["currency"]
        effect = data["effect"]
        action = data["action"]
        return cls(
            authorization_id=data["authorization_id"],
            issuer=data["issuer"],
            grantee=data["grantee"],
            effect=effect,
            action=action,
            vendor=vendor,
            allowed_categories=(
                tuple(allowed_categories) if allowed_categories is not None else None
            ),
            max_amount=max_amount,
            currency=currency,
            valid_from=data["valid_from"],
            valid_until=data["valid_until"],
            status=AuthorizationMemoryStatus(data["status"]),
            supersedes=data["supersedes"],
            source_turn_ids=tuple(data["source_turn_ids"]),
        )


@dataclass(frozen=True)
class TypedCurrentState:
    authorizations: tuple[TypedAuthorizationState, ...]
    schema_version: str = TYPED_MEMORY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TYPED_MEMORY_SCHEMA_VERSION,
            "authorizations": [
                record.to_envelope_dict() for record in self.authorizations
            ],
        }

    def to_source_dict(self) -> dict[str, Any]:
        return self.to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TypedCurrentState:
        schema_version = str(data["schema_version"])
        if schema_version != TYPED_MEMORY_SCHEMA_VERSION:
            raise ValueError(f"unsupported typed-memory schema version: {schema_version!r}")
        authorizations = tuple(
            TypedAuthorizationState.from_dict(record)
            for record in data["authorizations"]
        )
        for record in authorizations:
            if record.action not in {None, "submit_order"}:
                raise ValueError("schema-v3 action must be 'submit_order' or null")
            if record.effect not in {None, "permit_exception"}:
                raise ValueError(
                    "schema-v3 effect must be 'permit_exception' or null"
                )
        return cls(authorizations=authorizations, schema_version=schema_version)


MemoryPayload = str | TypedCurrentState


def _writer_provenance(
    *,
    writer_model: str | None,
    target_id: str | None,
    provider: str | None,
    requested_model: str | None,
    resolved_model: str | None,
    response_model: str | None,
    effective_parameters: dict[str, Any],
) -> ModelProvenance | None:
    values = (
        target_id,
        provider,
        requested_model,
        resolved_model,
        response_model,
        writer_model,
    )
    if all(value is None for value in values) and not effective_parameters:
        return None
    return ModelProvenance(
        target_id=target_id,
        provider=provider,
        requested_model=requested_model or writer_model,
        resolved_model=resolved_model or writer_model,
        response_model=response_model,
        effective_parameters=dict(effective_parameters),
    )


def _read_writer_provenance(data: dict[str, Any]) -> dict[str, Any]:
    nested = data.get("writer")
    if nested is None:
        return {
            "writer_model": None,
            "writer_target_id": None,
            "writer_provider": None,
            "writer_requested_model": None,
            "writer_resolved_model": None,
            "writer_response_model": None,
            "writer_effective_parameters": {},
        }
    if isinstance(nested, dict):
        parameters = nested.get("effective_parameters", {})
        if not isinstance(parameters, dict):
            raise ValueError("writer effective_parameters must be an object")
        return {
            "writer_model": data.get("writer_model")
            or nested.get("requested_model")
            or nested.get("resolved_model"),
            "writer_target_id": nested.get("target_id"),
            "writer_provider": nested.get("provider"),
            "writer_requested_model": nested.get("requested_model"),
            "writer_resolved_model": nested.get("resolved_model"),
            "writer_response_model": nested.get("response_model"),
            "writer_effective_parameters": dict(parameters),
        }
    raise ValueError("writer provenance must be an object or null")


def _serialized_payload_hash(payload: str | dict[str, Any]) -> str:
    text = (
        payload
        if isinstance(payload, str)
        else json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryArtifact:
    memory_id: str
    parent_memory_id: str | None
    chain_id: str
    case_id: str
    condition_id: str
    block_index: int
    writer_model: str | None
    architecture: MemoryArchitecture
    origin: MemoryOrigin
    payload: MemoryPayload
    reference_tokens: int
    reference_tokenizer: str
    content_hash: str
    writer_target_id: str | None = None
    writer_provider: str | None = None
    writer_requested_model: str | None = None
    writer_resolved_model: str | None = None
    writer_response_model: str | None = None
    writer_effective_parameters: dict[str, Any] = field(default_factory=dict)
    writer_run_id: int | None = None
    writer_seed: int | None = None
    payload_schema_id: str | None = None
    payload_schema_version: str | None = None
    memory_implementation_id: str | None = None
    memory_implementation_hash: str | None = None
    profile_id: str | None = None
    source_attempt_id: str | None = None
    framework_run_ids: tuple[str, ...] = ()
    framework: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: str | dict[str, Any]
        if isinstance(self.payload, TypedCurrentState):
            payload = self.payload.to_dict()
        else:
            payload = self.payload
        typed = self.architecture is MemoryArchitecture.TYPED
        writer = _writer_provenance(
            writer_model=self.writer_model,
            target_id=self.writer_target_id,
            provider=self.writer_provider,
            requested_model=self.writer_requested_model,
            resolved_model=self.writer_resolved_model,
            response_model=self.writer_response_model,
            effective_parameters=self.writer_effective_parameters,
        )
        return {
            "schema_version": 4,
            "domain_id": "procurement",
            "memory_id": self.memory_id,
            "parent_memory_id": self.parent_memory_id,
            "chain_id": self.chain_id,
            "case_id": self.case_id,
            "condition_id": self.condition_id,
            "block_index": self.block_index,
            "writer_model": self.writer_model,
            "writer_target_id": self.writer_target_id,
            "writer_provider": self.writer_provider,
            "writer_requested_model": self.writer_requested_model,
            "writer_resolved_model": self.writer_resolved_model,
            "writer_response_model": self.writer_response_model,
            "writer_effective_parameters": dict(self.writer_effective_parameters),
            "writer": writer.to_dict() if writer is not None else None,
            "writer_run_id": self.writer_run_id,
            "writer_seed": self.writer_seed,
            "memory_implementation_id": self.memory_implementation_id,
            "memory_implementation_hash": self.memory_implementation_hash,
            "profile_id": self.profile_id,
            "source_attempt_id": self.source_attempt_id,
            "framework_run_ids": list(self.framework_run_ids),
            "framework": dict(self.framework),
            "architecture": self.architecture.value,
            "origin": self.origin.value,
            "payload_schema_id": (
                TYPED_MEMORY_PAYLOAD_SCHEMA_ID if typed else None
            ),
            "payload_schema_version": (
                TYPED_MEMORY_SCHEMA_VERSION if typed else None
            ),
            "payload": payload,
            "reference_tokens": self.reference_tokens,
            "reference_tokenizer": self.reference_tokenizer,
            "content_hash": _serialized_payload_hash(payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryArtifact:
        architecture = MemoryArchitecture(data["architecture"])
        provenance = _read_writer_provenance(data)
        if architecture is MemoryArchitecture.TYPED:
            schema_id = data.get("payload_schema_id")
            if schema_id not in {None, TYPED_MEMORY_PAYLOAD_SCHEMA_ID}:
                raise ValueError(f"unsupported typed payload schema ID: {schema_id!r}")
            payload_version = str(
                data.get(
                    "payload_schema_version",
                    data["payload"].get("schema_version", ""),
                )
            )
            if payload_version != TYPED_MEMORY_SCHEMA_VERSION:
                raise ValueError(
                    f"unsupported typed payload schema version: {payload_version!r}"
                )
        payload: MemoryPayload = (
            TypedCurrentState.from_dict(data["payload"])
            if architecture is MemoryArchitecture.TYPED
            else data["payload"]
        )
        return cls(
            memory_id=data["memory_id"],
            parent_memory_id=data["parent_memory_id"],
            chain_id=data["chain_id"],
            case_id=data["case_id"],
            condition_id=data["condition_id"],
            block_index=data["block_index"],
            writer_model=provenance["writer_model"],
            architecture=architecture,
            origin=MemoryOrigin(data["origin"]),
            payload=payload,
            reference_tokens=data["reference_tokens"],
            reference_tokenizer=data["reference_tokenizer"],
            content_hash=data["content_hash"],
            writer_target_id=provenance["writer_target_id"],
            writer_provider=provenance["writer_provider"],
            writer_requested_model=provenance["writer_requested_model"],
            writer_resolved_model=provenance["writer_resolved_model"],
            writer_response_model=provenance["writer_response_model"],
            writer_effective_parameters=provenance[
                "writer_effective_parameters"
            ],
            writer_run_id=data.get("writer_run_id"),
            writer_seed=data.get("writer_seed"),
            memory_implementation_id=data.get("memory_implementation_id"),
            memory_implementation_hash=data.get("memory_implementation_hash"),
            profile_id=data.get("profile_id"),
            source_attempt_id=data.get("source_attempt_id"),
            framework_run_ids=tuple(data.get("framework_run_ids", ())),
            framework=dict(data.get("framework", {})),
            payload_schema_id=(
                TYPED_MEMORY_PAYLOAD_SCHEMA_ID
                if architecture is MemoryArchitecture.TYPED
                else None
            ),
            payload_schema_version=(
                TYPED_MEMORY_SCHEMA_VERSION
                if architecture is MemoryArchitecture.TYPED
                else None
            ),
        )


@dataclass(frozen=True)
class MemoryUpdateAttempt:
    attempt_id: str
    logical_update_id: str
    attempt_index: int
    repair_of_attempt_id: str | None
    chain_id: str
    case_id: str
    condition_id: str
    block_index: int
    writer_model: str
    architecture: MemoryArchitecture
    parent_memory_id: str | None
    tool_call_count: int
    status: MemoryUpdateStatus
    detail: str
    raw_arguments: Any
    candidate_reference_tokens: int | None
    candidate_content_hash: str | None
    accepted_memory_id: str | None
    retained_memory_id: str | None
    writer_target_id: str | None = None
    writer_provider: str | None = None
    writer_requested_model: str | None = None
    writer_resolved_model: str | None = None
    writer_response_model: str | None = None
    writer_effective_parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.status is MemoryUpdateStatus.ACCEPTED

    def to_dict(self) -> dict[str, Any]:
        writer = _writer_provenance(
            writer_model=self.writer_model,
            target_id=self.writer_target_id,
            provider=self.writer_provider,
            requested_model=self.writer_requested_model,
            resolved_model=self.writer_resolved_model,
            response_model=self.writer_response_model,
            effective_parameters=self.writer_effective_parameters,
        )
        return {
            "schema_version": MEMORY_ATTEMPT_SCHEMA_VERSION,
            "domain_id": "procurement",
            "attempt_id": self.attempt_id,
            "logical_update_id": self.logical_update_id,
            "attempt_index": self.attempt_index,
            "repair_of_attempt_id": self.repair_of_attempt_id,
            "chain_id": self.chain_id,
            "case_id": self.case_id,
            "condition_id": self.condition_id,
            "block_index": self.block_index,
            "writer_model": self.writer_model,
            "writer_target_id": self.writer_target_id,
            "writer_provider": self.writer_provider,
            "writer_requested_model": self.writer_requested_model,
            "writer_resolved_model": self.writer_resolved_model,
            "writer_response_model": self.writer_response_model,
            "writer_effective_parameters": dict(self.writer_effective_parameters),
            "writer": writer.to_dict() if writer is not None else None,
            "architecture": self.architecture.value,
            "parent_memory_id": self.parent_memory_id,
            "tool_call_count": self.tool_call_count,
            "status": self.status.value,
            "detail": self.detail,
            "raw_arguments": self.raw_arguments,
            "candidate_reference_tokens": self.candidate_reference_tokens,
            "candidate_content_hash": self.candidate_content_hash,
            "accepted_memory_id": self.accepted_memory_id,
            "retained_memory_id": self.retained_memory_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryUpdateAttempt:
        attempt_id = data["attempt_id"]
        provenance = _read_writer_provenance(data)
        return cls(
            attempt_id=attempt_id,
            logical_update_id=data["logical_update_id"],
            attempt_index=data["attempt_index"],
            repair_of_attempt_id=data.get("repair_of_attempt_id"),
            chain_id=data["chain_id"],
            case_id=data["case_id"],
            condition_id=data["condition_id"],
            block_index=data["block_index"],
            writer_model=provenance["writer_model"],
            architecture=MemoryArchitecture(data["architecture"]),
            parent_memory_id=data["parent_memory_id"],
            tool_call_count=data["tool_call_count"],
            status=MemoryUpdateStatus(data["status"]),
            detail=data["detail"],
            raw_arguments=data["raw_arguments"],
            candidate_reference_tokens=data["candidate_reference_tokens"],
            candidate_content_hash=data["candidate_content_hash"],
            accepted_memory_id=data["accepted_memory_id"],
            retained_memory_id=data["retained_memory_id"],
            writer_target_id=provenance["writer_target_id"],
            writer_provider=provenance["writer_provider"],
            writer_requested_model=provenance["writer_requested_model"],
            writer_resolved_model=provenance["writer_resolved_model"],
            writer_response_model=provenance["writer_response_model"],
            writer_effective_parameters=provenance[
                "writer_effective_parameters"
            ],
        )


@dataclass(frozen=True)
class MemoryUpdateResult:
    attempt: MemoryUpdateAttempt
    current_artifact: MemoryArtifact | None
    accepted_artifact: MemoryArtifact | None
