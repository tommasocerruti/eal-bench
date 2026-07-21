from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


EventType = Literal["issue", "patch", "revoke", "replace"]
AuthorizationEffect = Literal["permit_exception"]
AuthorizationAction = Literal["submit_order"]
TYPED_MEMORY_PAYLOAD_SCHEMA_ID = (
    "procurement/authorization-state/v3"
)
TYPED_MEMORY_PAYLOAD_SCHEMA_VERSION = "3"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ProcurementAuthorizationScopeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    vendor: str | None
    allowed_categories: list[_NonEmptyString] | None
    max_amount: Annotated[int, Field(ge=0)] | None
    currency: str | None

    @field_validator("allowed_categories")
    @classmethod
    def categories_must_be_unique(
        cls, value: list[str] | None
    ) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("allowed_categories must not contain duplicates")
        return value


class ProcurementAuthorizationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    authorization_id: _NonEmptyString
    issuer: str | None
    grantee: str | None
    effect: Literal["permit_exception"] | None
    action: Literal["submit_order"] | None
    status: Literal["active", "revoked", "superseded", "unknown"]
    valid_from: str | None
    valid_until: str | None
    scope: ProcurementAuthorizationScopeProfile
    supersedes: str | None
    source_turn_ids: Annotated[list[_NonEmptyString], Field(min_length=1)]

    @field_validator("source_turn_ids")
    @classmethod
    def source_turn_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("source_turn_ids must not contain duplicates")
        return value


class ProcurementAuthorizationMemoryProfile(BaseModel):
    """LangMem profile matching the domain's typed-memory payload v3."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["3"]
    authorizations: Annotated[
        list[ProcurementAuthorizationProfile], Field(max_length=32)
    ]

    @field_validator("authorizations")
    @classmethod
    def authorization_ids_must_be_unique(
        cls, value: list[ProcurementAuthorizationProfile]
    ) -> list[ProcurementAuthorizationProfile]:
        identifiers = [record.authorization_id for record in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("authorization_id values must be unique")
        return value


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_timestamp(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")


def _check_keys(data: dict[str, Any], cls: type[Any]) -> None:
    allowed = {field.name for field in fields(cls)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unexpected {cls.__name__} fields: {sorted(unknown)}")


@dataclass(frozen=True)
class ConversationTurn:
    turn_id: str
    actor_id: str
    speaker: str
    content: str
    occurred_at: str

    def __post_init__(self) -> None:
        _require_text(self.turn_id, "turn_id")
        _require_text(self.actor_id, "actor_id")
        _require_text(self.speaker, "speaker")
        _require_text(self.content, "content")
        _require_timestamp(self.occurred_at, "occurred_at")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationTurn:
        _check_keys(data, cls)
        return cls(**data)


@dataclass(frozen=True)
class ConversationBlock:
    block_id: str
    block_index: int
    title: str
    ended_at: str
    turns: tuple[ConversationTurn, ...]

    def __post_init__(self) -> None:
        _require_text(self.block_id, "block_id")
        _require_text(self.title, "title")
        _require_timestamp(self.ended_at, "ended_at")
        if not isinstance(self.block_index, int) or isinstance(self.block_index, bool):
            raise ValueError("block_index must be an integer")
        if self.block_index < 0:
            raise ValueError("block_index must be non-negative")
        if not isinstance(self.turns, tuple) or not self.turns:
            raise ValueError("a conversation block must contain at least one turn")
        if not all(isinstance(turn, ConversationTurn) for turn in self.turns):
            raise ValueError("turns must contain ConversationTurn objects")
        turn_times = [
            datetime.fromisoformat(turn.occurred_at.replace("Z", "+00:00"))
            for turn in self.turns
        ]
        if any(previous >= current for previous, current in zip(turn_times, turn_times[1:])):
            raise ValueError("turn occurred_at values must be strictly increasing within a block")
        block_end = datetime.fromisoformat(self.ended_at.replace("Z", "+00:00"))
        if turn_times[-1] > block_end:
            raise ValueError("turn occurred_at must not be later than block ended_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "block_index": self.block_index,
            "title": self.title,
            "ended_at": self.ended_at,
            "turns": [turn.to_dict() for turn in self.turns],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationBlock:
        _check_keys(data, cls)
        return cls(
            block_id=data["block_id"],
            block_index=data["block_index"],
            title=data["title"],
            ended_at=data["ended_at"],
            turns=tuple(ConversationTurn.from_dict(turn) for turn in data["turns"]),
        )


@dataclass(frozen=True)
class CanonicalAuthorizationRecord:
    authorization_id: str
    issuer: str
    grantee: str
    effect: AuthorizationEffect
    action: AuthorizationAction
    vendor: str
    allowed_categories: tuple[str, ...]
    max_amount: int
    currency: str
    valid_from: str
    valid_until: str
    status: Literal["active", "revoked", "superseded"]
    supersedes: str | None = None
    source_turn_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "authorization_id",
            "issuer",
            "grantee",
            "effect",
            "action",
            "vendor",
            "currency",
            "valid_from",
            "valid_until",
        ):
            _require_text(getattr(self, name), name)
        if self.status not in {"active", "revoked", "superseded"}:
            raise ValueError(f"invalid authorization status: {self.status!r}")
        if self.effect != "permit_exception":
            raise ValueError("effect must be 'permit_exception'")
        if self.action != "submit_order":
            raise ValueError("action must be 'submit_order'")
        if not isinstance(self.allowed_categories, tuple) or not self.allowed_categories:
            raise ValueError("allowed_categories must not be empty")
        if len(set(self.allowed_categories)) != len(self.allowed_categories):
            raise ValueError("allowed_categories must not contain duplicates")
        for category in self.allowed_categories:
            _require_text(category, "allowed_categories item")
        if not isinstance(self.max_amount, int) or isinstance(self.max_amount, bool):
            raise ValueError("max_amount must be an integer")
        if self.max_amount < 0:
            raise ValueError("max_amount must be non-negative")
        _require_timestamp(self.valid_from, "valid_from")
        _require_timestamp(self.valid_until, "valid_until")
        if not isinstance(self.source_turn_ids, tuple) or not self.source_turn_ids:
            raise ValueError("source_turn_ids must not be empty")
        for turn_id in self.source_turn_ids:
            _require_text(turn_id, "source_turn_ids item")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["allowed_categories"] = list(self.allowed_categories)
        data["source_turn_ids"] = list(self.source_turn_ids)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanonicalAuthorizationRecord:
        _check_keys(data, cls)
        return cls(
            **{
                key: value
                for key, value in data.items()
                if key not in {"allowed_categories", "source_turn_ids"}
            },
            allowed_categories=tuple(data["allowed_categories"]),
            source_turn_ids=tuple(data["source_turn_ids"]),
        )


@dataclass(frozen=True)
class AuthorizationPatch:
    issuer: str | None = None
    grantee: str | None = None
    effect: AuthorizationEffect | None = None
    action: AuthorizationAction | None = None
    vendor: str | None = None
    allowed_categories: tuple[str, ...] | None = None
    max_amount: int | None = None
    currency: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None

    def __post_init__(self) -> None:
        if not self.changed_fields():
            raise ValueError("authorization patch must change at least one field")
        for name in ("issuer", "grantee", "effect", "action", "vendor", "currency"):
            value = getattr(self, name)
            if value is not None:
                _require_text(value, name)
        if self.effect is not None and self.effect != "permit_exception":
            raise ValueError("effect must be 'permit_exception' when present")
        if self.action is not None and self.action != "submit_order":
            raise ValueError("action must be 'submit_order' when present")
        if self.allowed_categories is not None:
            if not isinstance(self.allowed_categories, tuple):
                raise ValueError("allowed_categories must be a tuple")
            if not self.allowed_categories or len(set(self.allowed_categories)) != len(self.allowed_categories):
                raise ValueError("allowed_categories must be non-empty and unique")
            for category in self.allowed_categories:
                _require_text(category, "allowed_categories item")
        if self.max_amount is not None:
            if not isinstance(self.max_amount, int) or isinstance(self.max_amount, bool):
                raise ValueError("max_amount must be an integer")
            if self.max_amount < 0:
                raise ValueError("max_amount must be non-negative")
        if self.valid_from is not None:
            _require_timestamp(self.valid_from, "valid_from")
        if self.valid_until is not None:
            _require_timestamp(self.valid_until, "valid_until")

    def changed_fields(self) -> dict[str, Any]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if getattr(self, field.name) is not None
        }

    def apply(
        self, record: CanonicalAuthorizationRecord, source_turn_ids: tuple[str, ...]
    ) -> CanonicalAuthorizationRecord:
        changes = self.changed_fields()
        changes["source_turn_ids"] = tuple(dict.fromkeys((*record.source_turn_ids, *source_turn_ids)))
        return replace(record, **changes)

    def to_dict(self) -> dict[str, Any]:
        data = self.changed_fields()
        if "allowed_categories" in data:
            data["allowed_categories"] = list(data["allowed_categories"])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthorizationPatch:
        _check_keys(data, cls)
        normalized = dict(data)
        if "allowed_categories" in normalized:
            normalized["allowed_categories"] = tuple(normalized["allowed_categories"])
        return cls(**normalized)


@dataclass(frozen=True)
class AuthorizationEvent:
    event_id: str
    event_type: EventType
    issuer: str
    block_id: str
    effective_at: str
    authorization_id: str
    source_turn_ids: tuple[str, ...]
    record: CanonicalAuthorizationRecord | None = None
    patch: AuthorizationPatch | None = None

    def __post_init__(self) -> None:
        _require_text(self.event_id, "event_id")
        _require_text(self.issuer, "issuer")
        _require_text(self.block_id, "block_id")
        _require_timestamp(self.effective_at, "effective_at")
        _require_text(self.authorization_id, "authorization_id")
        if self.event_type not in {"issue", "patch", "revoke", "replace"}:
            raise ValueError(f"invalid event_type: {self.event_type!r}")
        if not isinstance(self.source_turn_ids, tuple) or not self.source_turn_ids:
            raise ValueError("event source_turn_ids must not be empty")
        if self.record is not None and not isinstance(
            self.record, CanonicalAuthorizationRecord
        ):
            raise ValueError("record must be a CanonicalAuthorizationRecord")
        if self.patch is not None and not isinstance(self.patch, AuthorizationPatch):
            raise ValueError("patch must be an AuthorizationPatch")
        if self.event_type == "issue":
            if self.record is None or self.patch is not None:
                raise ValueError("issue events require a record and no patch")
            if self.record.authorization_id != self.authorization_id:
                raise ValueError("issue record ID must match authorization_id")
            if self.record.issuer != self.issuer:
                raise ValueError("issue record issuer must match event issuer")
            if self.record.status != "active":
                raise ValueError("issued records must start active")
        elif self.event_type == "patch":
            if self.patch is None or self.record is not None:
                raise ValueError("patch events require a patch and no record")
        elif self.event_type == "revoke":
            if self.record is not None or self.patch is not None:
                raise ValueError("revoke events accept neither record nor patch")
        elif self.record is None or self.patch is not None:
            raise ValueError("replace events require a replacement record and no patch")
        elif self.record.authorization_id == self.authorization_id:
            raise ValueError("replacement must use a new authorization ID")
        elif self.record.issuer != self.issuer:
            raise ValueError("replacement record issuer must match event issuer")
        elif self.record.supersedes != self.authorization_id:
            raise ValueError("replacement record must identify the superseded authorization")
        elif self.record.status != "active":
            raise ValueError("replacement records must start active")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "issuer": self.issuer,
            "block_id": self.block_id,
            "effective_at": self.effective_at,
            "authorization_id": self.authorization_id,
            "source_turn_ids": list(self.source_turn_ids),
            "record": self.record.to_dict() if self.record is not None else None,
            "patch": self.patch.to_dict() if self.patch is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthorizationEvent:
        _check_keys(data, cls)
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            issuer=data["issuer"],
            block_id=data["block_id"],
            effective_at=data["effective_at"],
            authorization_id=data["authorization_id"],
            source_turn_ids=tuple(data["source_turn_ids"]),
            record=(
                CanonicalAuthorizationRecord.from_dict(data["record"])
                if data.get("record") is not None
                else None
            ),
            patch=(
                AuthorizationPatch.from_dict(data["patch"])
                if data.get("patch") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    grantee: str
    action: AuthorizationAction
    vendor: str
    category: str
    amount: int
    currency: str
    action_time: str

    def __post_init__(self) -> None:
        for name in (
            "transaction_id",
            "grantee",
            "action",
            "vendor",
            "category",
            "currency",
            "action_time",
        ):
            _require_text(getattr(self, name), name)
        if not isinstance(self.amount, int) or isinstance(self.amount, bool):
            raise ValueError("amount must be an integer")
        if self.action != "submit_order":
            raise ValueError("action must be 'submit_order'")
        if self.amount < 0:
            raise ValueError("amount must be non-negative")
        _require_timestamp(self.action_time, "action_time")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transaction:
        _check_keys(data, cls)
        return cls(**data)


@dataclass(frozen=True)
class TransactionProbe:
    name: str
    request_scope: Literal["in_scope", "out_of_scope"]
    transaction: Transaction

    def __post_init__(self) -> None:
        _require_text(self.name, "name")
        if self.request_scope not in {"in_scope", "out_of_scope"}:
            raise ValueError(f"invalid request_scope: {self.request_scope!r}")
        if not isinstance(self.transaction, Transaction):
            raise ValueError("transaction must be a Transaction")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "request_scope": self.request_scope,
            "transaction": self.transaction.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransactionProbe:
        _check_keys(data, cls)
        return cls(
            name=data["name"],
            request_scope=data["request_scope"],
            transaction=Transaction.from_dict(data["transaction"]),
        )


@dataclass(frozen=True)
class MatchedProbePair:
    pair_id: str
    dimension: Literal["amount", "time", "category"]
    in_scope: TransactionProbe
    out_of_scope: TransactionProbe

    def __post_init__(self) -> None:
        _require_text(self.pair_id, "pair_id")
        if self.dimension not in {"amount", "time", "category"}:
            raise ValueError(f"invalid probe dimension: {self.dimension!r}")
        if not isinstance(self.in_scope, TransactionProbe) or not isinstance(
            self.out_of_scope, TransactionProbe
        ):
            raise ValueError("matched pair probes must be TransactionProbe objects")
        if self.in_scope.request_scope != "in_scope":
            raise ValueError("in_scope probe must have request_scope='in_scope'")
        if self.out_of_scope.request_scope != "out_of_scope":
            raise ValueError("out_of_scope probe must have request_scope='out_of_scope'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "dimension": self.dimension,
            "in_scope": self.in_scope.to_dict(),
            "out_of_scope": self.out_of_scope.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchedProbePair:
        _check_keys(data, cls)
        return cls(
            pair_id=data["pair_id"],
            dimension=data["dimension"],
            in_scope=TransactionProbe.from_dict(data["in_scope"]),
            out_of_scope=TransactionProbe.from_dict(data["out_of_scope"]),
        )


@dataclass(frozen=True)
class BenchmarkMetadata:
    split: str
    case_family_id: str
    lifecycle: str
    target_dimensions: tuple[str, ...]
    distractor_types: tuple[str, ...]
    history_length_band: str
    memory_hazards: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("split", "case_family_id", "lifecycle", "history_length_band"):
            _require_text(getattr(self, name), name)
        for name in ("target_dimensions", "distractor_types", "memory_hazards"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not values:
                raise ValueError(f"{name} must be a non-empty tuple")
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must not contain duplicates")
            for value in values:
                _require_text(value, f"{name} item")

    def to_dict(self) -> dict[str, Any]:
        return {
            "split": self.split,
            "case_family_id": self.case_family_id,
            "lifecycle": self.lifecycle,
            "target_dimensions": list(self.target_dimensions),
            "distractor_types": list(self.distractor_types),
            "history_length_band": self.history_length_band,
            "memory_hazards": list(self.memory_hazards),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkMetadata:
        _check_keys(data, cls)
        return cls(
            split=data["split"],
            case_family_id=data["case_family_id"],
            lifecycle=data["lifecycle"],
            target_dimensions=tuple(data["target_dimensions"]),
            distractor_types=tuple(data["distractor_types"]),
            history_length_band=data["history_length_band"],
            memory_hazards=tuple(data["memory_hazards"]),
        )


@dataclass(frozen=True)
class AuthorizationCase:
    schema_version: str
    case_id: str
    authoring_hash: str
    policy: str
    authorized_issuers: tuple[str, ...]
    benchmark: BenchmarkMetadata
    blocks: tuple[ConversationBlock, ...]
    events: tuple[AuthorizationEvent, ...]
    probe_pairs: tuple[MatchedProbePair, ...]
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.schema_version, "schema_version")
        _require_text(self.case_id, "case_id")
        if not _SHA256_PATTERN.fullmatch(self.authoring_hash):
            raise ValueError("authoring_hash must be a lowercase SHA-256 digest")
        _require_text(self.policy, "policy")
        if not isinstance(self.benchmark, BenchmarkMetadata):
            raise ValueError("benchmark must be BenchmarkMetadata")
        if not isinstance(self.authorized_issuers, tuple) or not self.authorized_issuers:
            raise ValueError("authorized_issuers must not be empty")
        if not all(isinstance(issuer, str) and issuer.strip() for issuer in self.authorized_issuers):
            raise ValueError("authorized_issuers must contain non-empty strings")
        if not isinstance(self.blocks, tuple) or not self.blocks:
            raise ValueError("blocks must not be empty")
        if not all(isinstance(block, ConversationBlock) for block in self.blocks):
            raise ValueError("blocks must contain ConversationBlock objects")
        if not isinstance(self.events, tuple) or not self.events:
            raise ValueError("events must not be empty")
        if not all(isinstance(event, AuthorizationEvent) for event in self.events):
            raise ValueError("events must contain AuthorizationEvent objects")
        if not isinstance(self.probe_pairs, tuple) or not self.probe_pairs:
            raise ValueError("probe_pairs must not be empty")
        if not all(isinstance(pair, MatchedProbePair) for pair in self.probe_pairs):
            raise ValueError("probe_pairs must contain MatchedProbePair objects")
        if not isinstance(self.tags, tuple) or not all(
            isinstance(tag, str) and tag.strip() for tag in self.tags
        ):
            raise ValueError("tags must contain non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "authoring_hash": self.authoring_hash,
            "policy": self.policy,
            "authorized_issuers": list(self.authorized_issuers),
            "benchmark": self.benchmark.to_dict(),
            "blocks": [block.to_dict() for block in self.blocks],
            "events": [event.to_dict() for event in self.events],
            "probe_pairs": [pair.to_dict() for pair in self.probe_pairs],
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthorizationCase:
        _check_keys(data, cls)
        return cls(
            schema_version=data["schema_version"],
            case_id=data["case_id"],
            authoring_hash=data["authoring_hash"],
            policy=data["policy"],
            authorized_issuers=tuple(data["authorized_issuers"]),
            benchmark=BenchmarkMetadata.from_dict(data["benchmark"]),
            blocks=tuple(ConversationBlock.from_dict(block) for block in data["blocks"]),
            events=tuple(AuthorizationEvent.from_dict(event) for event in data["events"]),
            probe_pairs=tuple(MatchedProbePair.from_dict(pair) for pair in data["probe_pairs"]),
            tags=tuple(data.get("tags", ())),
        )


@dataclass(frozen=True)
class LedgerSnapshot:
    case_id: str
    block_id: str
    block_index: int
    records: tuple[CanonicalAuthorizationRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "block_id": self.block_id,
            "block_index": self.block_index,
            "records": [record.to_dict() for record in self.records],
        }


@dataclass(frozen=True)
class AuthorizationDecision:
    authorized: bool
    reason: str
