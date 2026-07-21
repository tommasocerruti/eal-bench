from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Collection, Iterable

from domains.procurement.schemas import (
    CanonicalAuthorizationRecord,
    LedgerSnapshot,
)

from .schemas import (
    AuthorizationMemoryStatus,
    MemoryArchitecture,
    MemoryArtifact,
    TypedAuthorizationState,
    TypedCurrentState,
)


class FidelityError(str, Enum):
    OMISSION = "omission"
    BROADENING = "broadening"
    NARROWING = "narrowing"
    CONTRADICTION = "contradiction"
    STALE_RETENTION = "stale_retention"
    EXTRA_RECORD = "extra_record"
    MISSING_RECORD = "missing_record"


class AuthorizationConsequence(str, Enum):
    EXACT = "exact"
    OVERGRANT = "overgrant"
    UNDERGRANT = "undergrant"
    MIXED = "mixed"
    NON_AUTHORIZING = "non_authorizing"


RECORD_FIELD = "__record__"
AUTHORIZATION_FIELDS = (
    "issuer",
    "grantee",
    "effect",
    "action",
    "vendor",
    "allowed_categories",
    "max_amount",
    "currency",
    "valid_from",
    "valid_until",
    "status",
    "supersedes",
    "source_turn_ids",
)
_EXACT_REPRESENTATION_SCOPE_FIELDS = frozenset(
    {"issuer", "grantee", "effect", "action", "vendor", "currency"}
)
_EXACT_TRANSACTION_SCOPE_FIELDS = frozenset({"grantee", "action", "vendor", "currency"})
_REQUIRED_AUTHORIZING_FIELDS = (
    "issuer",
    "grantee",
    "effect",
    "action",
    "vendor",
    "allowed_categories",
    "max_amount",
    "currency",
    "valid_from",
    "valid_until",
)


@dataclass(frozen=True)
class FieldFidelity:
    authorization_id: str
    field: str
    canonical_value: Any
    remembered_value: Any
    errors: tuple[FidelityError, ...]
    overgrant: bool = False
    undergrant: bool = False

    @property
    def exact(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "field": self.field,
            "canonical_value": _json_value(self.canonical_value),
            "remembered_value": _json_value(self.remembered_value),
            "errors": [error.value for error in self.errors],
            "exact": self.exact,
            "overgrant": self.overgrant,
            "undergrant": self.undergrant,
        }


@dataclass(frozen=True)
class RecordFidelity:
    authorization_id: str
    canonical_present: bool
    remembered_present: bool
    fields: tuple[FieldFidelity, ...]
    consequence: AuthorizationConsequence

    @property
    def exact(self) -> bool:
        return all(field.exact for field in self.fields)

    @property
    def errors(self) -> tuple[FidelityError, ...]:
        return _ordered_errors(
            error for field in self.fields for error in field.errors
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "canonical_present": self.canonical_present,
            "remembered_present": self.remembered_present,
            "exact": self.exact,
            "errors": [error.value for error in self.errors],
            "consequence": self.consequence.value,
            "fields": [field.to_dict() for field in self.fields],
        }


@dataclass(frozen=True)
class FidelityReport:
    case_id: str
    block_id: str
    block_index: int
    records: tuple[RecordFidelity, ...]
    consequence: AuthorizationConsequence

    @property
    def exact(self) -> bool:
        return all(record.exact for record in self.records)

    @property
    def errors(self) -> tuple[FidelityError, ...]:
        return _ordered_errors(
            error for record in self.records for error in record.errors
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "block_id": self.block_id,
            "block_index": self.block_index,
            "exact": self.exact,
            "errors": [error.value for error in self.errors],
            "consequence": self.consequence.value,
            "records": [record.to_dict() for record in self.records],
        }


def compare_current_state(
    state: TypedCurrentState,
    snapshot: LedgerSnapshot,
    *,
    prior_snapshots: Iterable[LedgerSnapshot] = (),
    authorized_issuers: Collection[str] | None = None,
) -> FidelityReport:
    """Compare normalized memory with canonical state and its authorization semantics."""

    if not isinstance(state, TypedCurrentState):
        raise TypeError("state must be a TypedCurrentState")
    canonical = _index_records(snapshot.records, "canonical snapshot")
    remembered = _index_records(state.authorizations, "remembered state")
    prior = _prior_records(snapshot, prior_snapshots)
    issuers = _resolve_authorized_issuers(snapshot, authorized_issuers)

    records = []
    any_overgrant = False
    any_undergrant = False
    for authorization_id in sorted(set(canonical) | set(remembered)):
        canonical_record = canonical.get(authorization_id)
        remembered_record = remembered.get(authorization_id)
        record = _compare_record(
            authorization_id,
            canonical_record,
            remembered_record,
            prior.get(authorization_id, ()),
            issuers,
        )
        records.append(record)
        any_overgrant |= record.consequence in {
            AuthorizationConsequence.OVERGRANT,
            AuthorizationConsequence.MIXED,
        }
        any_undergrant |= record.consequence in {
            AuthorizationConsequence.UNDERGRANT,
            AuthorizationConsequence.NON_AUTHORIZING,
            AuthorizationConsequence.MIXED,
        }

    canonical_authorizes = any(
        _canonical_authorizes(record, issuers) for record in canonical.values()
    )
    memory_authorizes = any(
        _memory_authorizes(record, issuers) for record in remembered.values()
    )
    if canonical_authorizes and not memory_authorizes:
        consequence = AuthorizationConsequence.NON_AUTHORIZING
    else:
        consequence = _direction_consequence(any_overgrant, any_undergrant)
    return FidelityReport(
        case_id=snapshot.case_id,
        block_id=snapshot.block_id,
        block_index=snapshot.block_index,
        records=tuple(records),
        consequence=consequence,
    )


def score_memory_artifact(
    artifact: MemoryArtifact,
    snapshot: LedgerSnapshot,
    *,
    prior_snapshots: Iterable[LedgerSnapshot] = (),
    extracted_state: TypedCurrentState | None = None,
    authorized_issuers: Collection[str] | None = None,
    observed_block_index: int | None = None,
) -> FidelityReport:
    """Score typed memory directly or free text through a precomputed blinded extraction."""

    if artifact.case_id != snapshot.case_id:
        raise ValueError("artifact and snapshot case IDs differ")
    target_block_index = (
        artifact.block_index if observed_block_index is None else observed_block_index
    )
    if target_block_index != snapshot.block_index:
        raise ValueError("scoring target and snapshot block indices differ")
    if artifact.block_index > target_block_index:
        raise ValueError("an artifact cannot be observed before it was created")
    if artifact.architecture is MemoryArchitecture.TYPED:
        if not isinstance(artifact.payload, TypedCurrentState):
            raise TypeError("typed artifact payload must be a TypedCurrentState")
        if extracted_state is not None:
            raise ValueError("typed artifacts must not use an extracted state")
        state = artifact.payload
    else:
        if not isinstance(artifact.payload, str):
            raise TypeError("free-text artifact payload must be a string")
        if extracted_state is None:
            raise ValueError("free-text artifacts require a blinded extracted_state")
        state = extracted_state
    return compare_current_state(
        state,
        snapshot,
        prior_snapshots=prior_snapshots,
        authorized_issuers=authorized_issuers,
    )


def _compare_record(
    authorization_id: str,
    canonical: CanonicalAuthorizationRecord | None,
    remembered: TypedAuthorizationState | None,
    prior: tuple[CanonicalAuthorizationRecord, ...],
    authorized_issuers: frozenset[str],
) -> RecordFidelity:
    if canonical is None:
        assert remembered is not None
        errors = {FidelityError.EXTRA_RECORD}
        if prior:
            errors.add(FidelityError.STALE_RETENTION)
        field = FieldFidelity(
            authorization_id=authorization_id,
            field=RECORD_FIELD,
            canonical_value=None,
            remembered_value=remembered.to_dict(),
            errors=_ordered_errors(errors),
            overgrant=_memory_authorizes(remembered, authorized_issuers),
        )
        consequence = (
            AuthorizationConsequence.OVERGRANT
            if field.overgrant
            else AuthorizationConsequence.EXACT
        )
        return RecordFidelity(authorization_id, False, True, (field,), consequence)

    if remembered is None:
        undergrant = _canonical_authorizes(canonical, authorized_issuers)
        field = FieldFidelity(
            authorization_id=authorization_id,
            field=RECORD_FIELD,
            canonical_value=canonical.to_dict(),
            remembered_value=None,
            errors=(FidelityError.MISSING_RECORD,),
            undergrant=undergrant,
        )
        consequence = (
            AuthorizationConsequence.NON_AUTHORIZING
            if undergrant
            else AuthorizationConsequence.EXACT
        )
        return RecordFidelity(authorization_id, True, False, (field,), consequence)

    fields = tuple(
        _compare_field(
            authorization_id,
            name,
            canonical,
            remembered,
            prior,
            authorized_issuers,
        )
        for name in AUTHORIZATION_FIELDS
    )
    overgrant, undergrant = _record_scope_directions(
        canonical, remembered, authorized_issuers
    )
    consequence = _direction_consequence(overgrant, undergrant)
    if _canonical_authorizes(canonical, authorized_issuers) and not _memory_authorizes(
        remembered, authorized_issuers
    ):
        consequence = AuthorizationConsequence.NON_AUTHORIZING
    return RecordFidelity(authorization_id, True, True, fields, consequence)


def _compare_field(
    authorization_id: str,
    field: str,
    canonical: CanonicalAuthorizationRecord,
    remembered: TypedAuthorizationState,
    prior: tuple[CanonicalAuthorizationRecord, ...],
    authorized_issuers: frozenset[str],
) -> FieldFidelity:
    canonical_value = getattr(canonical, field)
    remembered_value = getattr(remembered, field)
    errors: set[FidelityError] = set()
    overgrant = False
    undergrant = False

    if field == "allowed_categories":
        errors, overgrant, undergrant = _category_errors(canonical_value, remembered_value)
    elif field == "max_amount":
        errors, overgrant, undergrant = _ordered_bound_errors(
            canonical_value, remembered_value, larger_is_broader=True
        )
    elif field == "valid_from":
        errors, overgrant, undergrant = _timestamp_errors(
            canonical_value, remembered_value, larger_is_broader=False
        )
    elif field == "valid_until":
        errors, overgrant, undergrant = _timestamp_errors(
            canonical_value, remembered_value, larger_is_broader=True
        )
    elif field == "status":
        errors, overgrant, undergrant = _status_errors(canonical_value, remembered_value)
    elif field == "source_turn_ids":
        errors = _provenance_errors(canonical_value, remembered_value)
        undergrant = not remembered_value
    elif remembered_value is None and canonical_value is not None:
        errors.add(FidelityError.OMISSION)
        if field in _EXACT_REPRESENTATION_SCOPE_FIELDS:
            undergrant = True
    elif not _equal(canonical_value, remembered_value):
        errors.add(FidelityError.CONTRADICTION)
        if field in _EXACT_TRANSACTION_SCOPE_FIELDS:
            overgrant = True
            undergrant = True
        elif field == "issuer":
            undergrant = remembered_value not in authorized_issuers
        elif field == "effect":
            undergrant = remembered_value != "permit_exception"

    if errors and _is_stale_value(field, remembered_value, canonical_value, prior):
        errors.add(FidelityError.STALE_RETENTION)
    return FieldFidelity(
        authorization_id=authorization_id,
        field=field,
        canonical_value=canonical_value,
        remembered_value=remembered_value,
        errors=_ordered_errors(errors),
        overgrant=overgrant,
        undergrant=undergrant,
    )


def _category_errors(
    canonical: tuple[str, ...], remembered: tuple[str, ...] | None
) -> tuple[set[FidelityError], bool, bool]:
    if remembered is None:
        return {FidelityError.OMISSION}, False, True
    canonical_set = set(canonical)
    remembered_set = set(remembered)
    added = remembered_set - canonical_set
    removed = canonical_set - remembered_set
    errors: set[FidelityError] = set()
    if added:
        errors.add(FidelityError.BROADENING)
    if removed:
        errors.add(FidelityError.NARROWING)
    if added and removed and not (canonical_set & remembered_set):
        errors.add(FidelityError.CONTRADICTION)
    return errors, bool(added), bool(removed)


def _ordered_bound_errors(
    canonical: int | datetime,
    remembered: int | datetime | None,
    *,
    larger_is_broader: bool,
) -> tuple[set[FidelityError], bool, bool]:
    if remembered is None:
        return {FidelityError.OMISSION}, False, True
    if remembered == canonical:
        return set(), False, False
    broader = remembered > canonical if larger_is_broader else remembered < canonical
    error = FidelityError.BROADENING if broader else FidelityError.NARROWING
    return {error}, broader, not broader


def _timestamp_errors(
    canonical: str,
    remembered: str | None,
    *,
    larger_is_broader: bool,
) -> tuple[set[FidelityError], bool, bool]:
    if remembered is None:
        return {FidelityError.OMISSION}, False, True
    try:
        remembered_timestamp = _timestamp(remembered)
    except (TypeError, ValueError):
        return {FidelityError.CONTRADICTION}, False, True
    return _ordered_bound_errors(
        _timestamp(canonical),
        remembered_timestamp,
        larger_is_broader=larger_is_broader,
    )


def _status_errors(
    canonical: str, remembered: AuthorizationMemoryStatus
) -> tuple[set[FidelityError], bool, bool]:
    remembered_value = remembered.value
    if remembered_value == canonical:
        return set(), False, False
    if remembered is AuthorizationMemoryStatus.UNKNOWN:
        undergrant = canonical == AuthorizationMemoryStatus.ACTIVE.value
        return {FidelityError.OMISSION}, False, undergrant
    if canonical == AuthorizationMemoryStatus.ACTIVE.value:
        return {FidelityError.NARROWING}, False, True
    if remembered is AuthorizationMemoryStatus.ACTIVE:
        return {FidelityError.BROADENING}, True, False
    return {FidelityError.CONTRADICTION}, False, False


def _provenance_errors(
    canonical: tuple[str, ...], remembered: tuple[str, ...]
) -> set[FidelityError]:
    canonical_set = set(canonical)
    remembered_set = set(remembered)
    errors: set[FidelityError] = set()
    if canonical_set - remembered_set:
        errors.add(FidelityError.OMISSION)
    if remembered_set - canonical_set:
        errors.add(FidelityError.CONTRADICTION)
    return errors


def _record_scope_directions(
    canonical: CanonicalAuthorizationRecord,
    remembered: TypedAuthorizationState,
    authorized_issuers: frozenset[str],
) -> tuple[bool, bool]:
    canonical_active = _canonical_authorizes(canonical, authorized_issuers)
    remembered_active = _memory_authorizes(remembered, authorized_issuers)
    if canonical_active and not remembered_active:
        return False, True
    if remembered_active and not canonical_active:
        return True, False
    if not canonical_active and not remembered_active:
        return False, False

    overgrant = False
    undergrant = False
    for field in _EXACT_TRANSACTION_SCOPE_FIELDS:
        if not _equal(getattr(canonical, field), getattr(remembered, field)):
            overgrant = True
            undergrant = True
    _, category_overgrant, category_undergrant = _category_errors(
        canonical.allowed_categories, remembered.allowed_categories
    )
    _, amount_overgrant, amount_undergrant = _ordered_bound_errors(
        canonical.max_amount, remembered.max_amount, larger_is_broader=True
    )
    _, start_overgrant, start_undergrant = _timestamp_errors(
        canonical.valid_from, remembered.valid_from, larger_is_broader=False
    )
    _, end_overgrant, end_undergrant = _timestamp_errors(
        canonical.valid_until, remembered.valid_until, larger_is_broader=True
    )
    return (
        overgrant
        or category_overgrant
        or amount_overgrant
        or start_overgrant
        or end_overgrant,
        undergrant
        or category_undergrant
        or amount_undergrant
        or start_undergrant
        or end_undergrant,
    )


def _canonical_authorizes(
    record: CanonicalAuthorizationRecord, authorized_issuers: Collection[str]
) -> bool:
    if (
        record.status != AuthorizationMemoryStatus.ACTIVE.value
        or record.issuer not in authorized_issuers
        or record.effect != "permit_exception"
        or not record.source_turn_ids
        or not record.allowed_categories
    ):
        return False
    try:
        return _timestamp(record.valid_from) < _timestamp(record.valid_until)
    except (TypeError, ValueError):
        return False


def _memory_authorizes(
    record: TypedAuthorizationState, authorized_issuers: Collection[str]
) -> bool:
    if (
        record.status is not AuthorizationMemoryStatus.ACTIVE
        or record.issuer not in authorized_issuers
        or record.effect != "permit_exception"
        or not record.source_turn_ids
    ):
        return False
    if any(getattr(record, field) is None for field in _REQUIRED_AUTHORIZING_FIELDS):
        return False
    assert record.allowed_categories is not None
    assert record.valid_from is not None
    assert record.valid_until is not None
    if any(
        _unknown_text(getattr(record, field))
        for field in ("grantee", "action", "vendor", "currency")
    ) or any(_unknown_text(category) for category in record.allowed_categories):
        return False
    try:
        valid_interval = _timestamp(record.valid_from) < _timestamp(record.valid_until)
    except (TypeError, ValueError):
        return False
    return bool(record.allowed_categories) and valid_interval


def _unknown_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in {"", "unknown"}


def _resolve_authorized_issuers(
    snapshot: LedgerSnapshot,
    authorized_issuers: Collection[str] | None,
) -> frozenset[str]:
    values = (
        {record.issuer for record in snapshot.records}
        if authorized_issuers is None
        else set(authorized_issuers)
    )
    if any(not isinstance(issuer, str) or not issuer.strip() for issuer in values):
        raise ValueError("authorized_issuers must contain non-empty strings")
    return frozenset(values)


def _prior_records(
    snapshot: LedgerSnapshot,
    prior_snapshots: Iterable[LedgerSnapshot],
) -> dict[str, tuple[CanonicalAuthorizationRecord, ...]]:
    grouped: dict[str, list[CanonicalAuthorizationRecord]] = {}
    ordered = sorted(prior_snapshots, key=lambda item: item.block_index)
    for prior in ordered:
        if prior.case_id != snapshot.case_id:
            raise ValueError("prior snapshot belongs to a different case")
        if prior.block_index >= snapshot.block_index:
            raise ValueError("prior snapshots must precede the scored snapshot")
        for record in prior.records:
            grouped.setdefault(record.authorization_id, []).append(record)
    return {key: tuple(value) for key, value in grouped.items()}


def _is_stale_value(
    field: str,
    remembered: Any,
    canonical: Any,
    prior: tuple[CanonicalAuthorizationRecord, ...],
) -> bool:
    if remembered is None or remembered == () or _equal(remembered, canonical):
        return False
    return any(_equal(remembered, getattr(record, field)) for record in prior)


def _index_records(records: Iterable[Any], label: str) -> dict[str, Any]:
    indexed = {}
    for record in records:
        authorization_id = record.authorization_id
        if authorization_id in indexed:
            raise ValueError(f"duplicate authorization ID in {label}: {authorization_id}")
        indexed[authorization_id] = record
    return indexed


def _direction_consequence(
    overgrant: bool, undergrant: bool
) -> AuthorizationConsequence:
    if overgrant and undergrant:
        return AuthorizationConsequence.MIXED
    if overgrant:
        return AuthorizationConsequence.OVERGRANT
    if undergrant:
        return AuthorizationConsequence.UNDERGRANT
    return AuthorizationConsequence.EXACT


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def _equal(left: Any, right: Any) -> bool:
    if isinstance(left, AuthorizationMemoryStatus):
        left = left.value
    if isinstance(right, AuthorizationMemoryStatus):
        right = right.value
    if isinstance(left, tuple) and isinstance(right, tuple):
        return set(left) == set(right)
    if isinstance(left, str) and isinstance(right, str):
        try:
            return _timestamp(left) == _timestamp(right)
        except (TypeError, ValueError):
            pass
    return left == right


def _ordered_errors(errors: Iterable[FidelityError]) -> tuple[FidelityError, ...]:
    present = set(errors)
    return tuple(error for error in FidelityError if error in present)


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value
