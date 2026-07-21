from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Collection

from domains.procurement.schemas import (
    AuthorizationCase,
    CanonicalAuthorizationRecord,
    MatchedProbePair,
    Transaction,
)
from domains.procurement.cases import current_ledger

from .memory import (
    canonical_json,
    count_reference_tokens,
    hash_payload,
    serialize_payload as serialize_memory_payload,
    validate_typed_payload,
)
from .schemas import (
    AuthorizationMemoryStatus,
    MemoryArchitecture,
    MemoryArtifact,
    MemoryOrigin,
    TYPED_MEMORY_PAYLOAD_SCHEMA_ID,
    TYPED_MEMORY_SCHEMA_VERSION,
    TypedAuthorizationState,
    TypedCurrentState,
)


TokenCounter = Callable[[str], int]
SemanticOracle = Callable[[TypedCurrentState], object]


class InterventionKind(str, Enum):
    AMOUNT_BROADENING = "amount_broadening"
    VALIDITY_EXTENSION = "validity_extension"
    VALIDITY_START_ADVANCE = "validity_start_advance"
    CATEGORY_BROADENING = "category_broadening"
    GRANTEE_ALIAS_LOSS = "grantee_alias_loss"
    STALE_ACTIVE = "stale_active"
    EXACT_REPAIR = "exact_repair"
    SEMANTIC_SHAM = "semantic_sham"
    OMISSION_CONTROL = "omission_control"


OMITTABLE_FIELDS = frozenset(
    {
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
    }
)


@dataclass(frozen=True)
class InterventionResult:
    intervention_id: str
    kind: InterventionKind
    artifact: MemoryArtifact
    semantic_state: TypedCurrentState
    source_memory_id: str
    faithful_memory_id: str
    target_authorization_id: str | None
    changed_fields: tuple[str, ...]
    repair_of_memory_id: str | None
    sham_verified: bool | None
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "kind": self.kind.value,
            "artifact": self.artifact.to_dict(),
            "semantic_state": self.semantic_state.to_dict(),
            "source_memory_id": self.source_memory_id,
            "faithful_memory_id": self.faithful_memory_id,
            "target_authorization_id": self.target_authorization_id,
            "changed_fields": list(self.changed_fields),
            "repair_of_memory_id": self.repair_of_memory_id,
            "sham_verified": self.sham_verified,
            "parameters": self.parameters,
        }


@dataclass(frozen=True)
class SkippedIntervention:
    intervention_id: str
    kind: InterventionKind
    target_authorization_id: str | None
    reason: str
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "kind": self.kind.value,
            "target_authorization_id": self.target_authorization_id,
            "reason": self.reason,
            "parameters": self.parameters,
        }


@dataclass(frozen=True)
class ControlledVariantBuild:
    case_id: str
    faithful_memory_id: str
    variants: tuple[InterventionResult, ...]
    skipped: tuple[SkippedIntervention, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "faithful_memory_id": self.faithful_memory_id,
            "variants": [variant.to_dict() for variant in self.variants],
            "skipped": [item.to_dict() for item in self.skipped],
        }


def faithful_typed_state(
    records: Collection[CanonicalAuthorizationRecord],
) -> TypedCurrentState:
    """Convert a canonical ledger into the executor-visible typed memory schema."""

    ordered = sorted(records, key=lambda record: record.authorization_id)
    return TypedCurrentState(
        authorizations=tuple(
            TypedAuthorizationState(
                authorization_id=record.authorization_id,
                issuer=record.issuer,
                grantee=record.grantee,
                effect=record.effect,
                action=record.action,
                vendor=record.vendor,
                allowed_categories=record.allowed_categories,
                max_amount=record.max_amount,
                currency=record.currency,
                valid_from=record.valid_from,
                valid_until=record.valid_until,
                status=AuthorizationMemoryStatus(record.status),
                supersedes=record.supersedes,
                source_turn_ids=record.source_turn_ids,
            )
            for record in ordered
        )
    )


def render_free_text(state: TypedCurrentState, *, sham_style: bool = False) -> str:
    """Render semantic state with a fixed template; null fields are genuinely omitted."""

    if not state.authorizations:
        return "# Current authorization state\n\nNo authorization records are retained."

    lines = ["# Current authorization state"]
    records = reversed(state.authorizations) if sham_style else state.authorizations
    for record in records:
        lines.extend(("", f"## Authorization {record.authorization_id}"))
        values: list[tuple[str, str | None]] = [
            (
                "Status",
                None
                if record.status is AuthorizationMemoryStatus.UNKNOWN
                else record.status.value,
            ),
            ("Issuer", record.issuer),
            ("Grantee", record.grantee),
            ("Effect", record.effect),
            ("Action", record.action),
            ("Vendor", record.vendor),
            (
                "Allowed categories",
                (
                    ", ".join(reversed(record.allowed_categories))
                    if sham_style
                    else ", ".join(record.allowed_categories)
                )
                if record.allowed_categories is not None
                else None,
            ),
            (
                "Maximum amount",
                str(record.max_amount) if record.max_amount is not None else None,
            ),
            ("Currency", record.currency),
            ("Valid from (inclusive)", record.valid_from),
            ("Valid until (exclusive)", record.valid_until),
            ("Supersedes", record.supersedes),
            (
                "Source turns",
                (
                    ", ".join(
                        reversed(record.source_turn_ids)
                        if sham_style
                        else record.source_turn_ids
                    )
                    if record.source_turn_ids
                    else None
                ),
            ),
        ]
        if sham_style:
            values = list(reversed(values))
        lines.extend(f"- {label}: {value}" for label, value in values if value is not None)
    return "\n".join(lines)


def serialize_payload(architecture: MemoryArchitecture, state: TypedCurrentState) -> str:
    payload: str | TypedCurrentState = (
        render_free_text(state) if architecture is MemoryArchitecture.FREE_TEXT else state
    )
    return serialize_memory_payload(payload)


def build_faithful_artifact(
    state: TypedCurrentState,
    architecture: MemoryArchitecture,
    *,
    case_id: str,
    chain_id: str,
    condition_id: str,
    block_index: int,
    reference_tokenizer: str,
    count_tokens: TokenCounter,
    writer_model: str | None = None,
    parent_memory_id: str | None = None,
    capacity_tokens: int | None = None,
) -> MemoryArtifact:
    """Build a deterministic faithful artifact in either memory architecture."""

    state = validate_typed_payload(state, seen_source_ids=None)
    serialized = serialize_payload(architecture, state)
    payload: str | TypedCurrentState = (
        render_free_text(state) if architecture is MemoryArchitecture.FREE_TEXT else state
    )
    reference_tokens = count_reference_tokens(serialized, count_tokens)
    _enforce_capacity(reference_tokens, capacity_tokens)
    content_hash = hash_payload(payload)
    return _artifact(
        parent_memory_id=parent_memory_id,
        chain_id=chain_id,
        case_id=case_id,
        condition_id=condition_id,
        block_index=block_index,
        writer_model=writer_model,
        architecture=architecture,
        origin=MemoryOrigin.FAITHFUL,
        payload=payload,
        reference_tokens=reference_tokens,
        reference_tokenizer=reference_tokenizer,
        content_hash=content_hash,
    )


def build_controlled_variants(
    case: AuthorizationCase,
    faithful_artifact: MemoryArtifact,
    faithful_state: TypedCurrentState,
    *,
    count_tokens: TokenCounter,
    capacity_tokens: int | None = None,
    semantic_oracle: SemanticOracle | None = None,
) -> ControlledVariantBuild:
    """Build paired corruptions, repairs, shams, and omission controls for one case."""

    if faithful_artifact.origin is not MemoryOrigin.FAITHFUL:
        raise ValueError("controlled variants must start from a faithful artifact")
    if case.case_id != faithful_artifact.case_id:
        raise ValueError("case and faithful artifact IDs differ")
    canonical_state = faithful_typed_state(current_ledger(case))
    if faithful_state != canonical_state:
        raise ValueError("faithful_state differs from the case's final canonical ledger")
    if faithful_artifact.architecture is MemoryArchitecture.TYPED:
        if faithful_artifact.payload != faithful_state:
            raise ValueError("faithful typed artifact payload differs from faithful_state")
    elif faithful_artifact.payload != render_free_text(faithful_state):
        raise ValueError("faithful free-text artifact is not the deterministic template rendering")
    if faithful_artifact.content_hash != hash_payload(faithful_artifact.payload):
        raise ValueError("faithful artifact content hash is invalid")

    variants: list[InterventionResult] = []
    skipped: list[SkippedIntervention] = []
    pair_by_dimension = {pair.dimension: pair for pair in case.probe_pairs}
    behavior_oracle = semantic_oracle or _case_behavior_oracle(case)

    for dimension in ("amount", "time", "category"):
        pair = pair_by_dimension.get(dimension)
        kind = {
            "amount": InterventionKind.AMOUNT_BROADENING,
            "time": InterventionKind.VALIDITY_EXTENSION,
            "category": InterventionKind.CATEGORY_BROADENING,
        }[dimension]
        corruption_id = f"controlled_{kind.value}"
        repair_id = f"controlled_{dimension}_exact_repair"
        sham_id = f"controlled_{dimension}_semantic_sham"
        omission_id = f"controlled_{dimension}_omission"
        omission_field = {
            "amount": "max_amount",
            "time": "valid_until",
            "category": "allowed_categories",
        }[dimension]

        if pair is None:
            reason = f"case has no {dimension} matched probe pair"
            for intervention_id, skipped_kind in (
                (corruption_id, kind),
                (repair_id, InterventionKind.EXACT_REPAIR),
                (sham_id, InterventionKind.SEMANTIC_SHAM),
                (omission_id, InterventionKind.OMISSION_CONTROL),
            ):
                skipped.append(
                    SkippedIntervention(intervention_id, skipped_kind, None, reason, {})
                )
            continue

        target, target_reason = _target_for_pair(case, faithful_state, pair)
        if target is None:
            for intervention_id, skipped_kind in (
                (corruption_id, kind),
                (repair_id, InterventionKind.EXACT_REPAIR),
                (omission_id, InterventionKind.OMISSION_CONTROL),
            ):
                skipped.append(
                    SkippedIntervention(
                        intervention_id,
                        skipped_kind,
                        None,
                        target_reason,
                        {"pair_id": pair.pair_id},
                    )
                )
        else:
            if (
                dimension == "time"
                and target.valid_from is not None
                and _timestamp(pair.out_of_scope.transaction.action_time)
                < _timestamp(target.valid_from)
            ):
                kind = InterventionKind.VALIDITY_START_ADVANCE
                corruption_id = f"controlled_{kind.value}"
            value = _corruption_value(kind, pair)
            try:
                corruption = apply_intervention(
                    faithful_artifact,
                    faithful_state,
                    kind,
                    intervention_id=corruption_id,
                    count_tokens=count_tokens,
                    target_authorization_id=target.authorization_id,
                    value=value,
                    capacity_tokens=capacity_tokens,
                )
                if not _state_authorizes(
                    corruption.semantic_state,
                    pair.out_of_scope.transaction,
                    case.authorized_issuers,
                ):
                    raise ValueError("corruption does not authorize its out-of-scope probe")
                corruption = _attach_intervention_probe(
                    corruption,
                    pair.out_of_scope.transaction,
                    probe_source=pair.pair_id,
                    expected_faithful_authorized=False,
                    expected_authorized=True,
                    faithful_state=faithful_state,
                    authorized_issuers=case.authorized_issuers,
                    behavior_oracle=behavior_oracle,
                )
                variants.append(corruption)
            except ValueError as exc:
                corruption = None
                skipped.append(
                    SkippedIntervention(
                        corruption_id,
                        kind,
                        target.authorization_id,
                        str(exc),
                        {"pair_id": pair.pair_id, "value": value},
                    )
                )

            if corruption is None:
                skipped.append(
                    SkippedIntervention(
                        repair_id,
                        InterventionKind.EXACT_REPAIR,
                        target.authorization_id,
                        "paired corruption was unavailable",
                        {"pair_id": pair.pair_id},
                    )
                )
            else:
                _append_or_skip(
                    variants,
                    skipped,
                    lambda corruption=corruption: _attach_intervention_probe(
                        apply_intervention(
                            corruption.artifact,
                            corruption.semantic_state,
                            InterventionKind.EXACT_REPAIR,
                            intervention_id=repair_id,
                            count_tokens=count_tokens,
                            target_authorization_id=target.authorization_id,
                            faithful_state=faithful_state,
                            faithful_memory_id=faithful_artifact.memory_id,
                            capacity_tokens=capacity_tokens,
                        ),
                        pair.out_of_scope.transaction,
                        probe_source=pair.pair_id,
                        expected_faithful_authorized=False,
                        expected_authorized=False,
                        faithful_state=faithful_state,
                        authorized_issuers=case.authorized_issuers,
                        behavior_oracle=behavior_oracle,
                    ),
                    repair_id,
                    InterventionKind.EXACT_REPAIR,
                    target.authorization_id,
                    {"pair_id": pair.pair_id},
                )

            _append_or_skip(
                variants,
                skipped,
                lambda: _attach_intervention_probe(
                    apply_intervention(
                        faithful_artifact,
                        faithful_state,
                        InterventionKind.OMISSION_CONTROL,
                        intervention_id=omission_id,
                        count_tokens=count_tokens,
                        target_authorization_id=target.authorization_id,
                        field=omission_field,
                        capacity_tokens=capacity_tokens,
                    ),
                    pair.in_scope.transaction,
                    probe_source=pair.pair_id,
                    expected_faithful_authorized=True,
                    expected_authorized=False,
                    faithful_state=faithful_state,
                    authorized_issuers=case.authorized_issuers,
                    behavior_oracle=behavior_oracle,
                ),
                omission_id,
                InterventionKind.OMISSION_CONTROL,
                target.authorization_id,
                {"pair_id": pair.pair_id, "field": omission_field},
            )

        _append_or_skip(
            variants,
            skipped,
            lambda: _attach_intervention_probe(
                apply_intervention(
                    faithful_artifact,
                    faithful_state,
                    InterventionKind.SEMANTIC_SHAM,
                    intervention_id=sham_id,
                    count_tokens=count_tokens,
                    target_authorization_id=(target.authorization_id if target else None),
                    semantic_oracle=behavior_oracle,
                    capacity_tokens=capacity_tokens,
                ),
                pair.out_of_scope.transaction,
                probe_source=pair.pair_id,
                expected_faithful_authorized=False,
                expected_authorized=False,
                faithful_state=faithful_state,
                authorized_issuers=case.authorized_issuers,
                behavior_oracle=behavior_oracle,
            ),
            sham_id,
            InterventionKind.SEMANTIC_SHAM,
            target.authorization_id if target else None,
            {"pair_id": pair.pair_id},
        )

    stale_records = [
        record
        for record in faithful_state.authorizations
        if record.status
        in {AuthorizationMemoryStatus.REVOKED, AuthorizationMemoryStatus.SUPERSEDED}
    ]
    if not stale_records:
        skipped.append(
            SkippedIntervention(
                "controlled_stale_active",
                InterventionKind.STALE_ACTIVE,
                None,
                "final state has no revoked or superseded record",
                {},
            )
        )
    for record in stale_records:
        stale_id = f"controlled_stale_active__{record.authorization_id}"
        repair_id = f"controlled_stale_active_repair__{record.authorization_id}"
        probe, probe_reason = _stale_intervention_probe(case, faithful_state, record)
        if probe is None:
            skipped.extend(
                (
                    SkippedIntervention(
                        stale_id,
                        InterventionKind.STALE_ACTIVE,
                        record.authorization_id,
                        probe_reason,
                        {},
                    ),
                    SkippedIntervention(
                        repair_id,
                        InterventionKind.EXACT_REPAIR,
                        record.authorization_id,
                        "paired stale-active corruption was unavailable",
                        {},
                    ),
                )
            )
            continue
        try:
            stale = apply_intervention(
                faithful_artifact,
                faithful_state,
                InterventionKind.STALE_ACTIVE,
                intervention_id=stale_id,
                count_tokens=count_tokens,
                target_authorization_id=record.authorization_id,
                capacity_tokens=capacity_tokens,
            )
            stale = _attach_intervention_probe(
                stale,
                probe,
                probe_source="synthetic_post_history_stale_scope",
                expected_faithful_authorized=False,
                expected_authorized=True,
                faithful_state=faithful_state,
                authorized_issuers=case.authorized_issuers,
                behavior_oracle=behavior_oracle,
            )
            variants.append(stale)
        except ValueError as exc:
            stale = None
            skipped.append(
                SkippedIntervention(
                    stale_id,
                    InterventionKind.STALE_ACTIVE,
                    record.authorization_id,
                    str(exc),
                    {},
                )
            )
        if stale is None:
            skipped.append(
                SkippedIntervention(
                    repair_id,
                    InterventionKind.EXACT_REPAIR,
                    record.authorization_id,
                    "paired stale-active corruption was unavailable",
                    {},
                )
            )
        else:
            _append_or_skip(
                variants,
                skipped,
                lambda stale=stale, probe=probe: _attach_intervention_probe(
                    apply_intervention(
                        stale.artifact,
                        stale.semantic_state,
                        InterventionKind.EXACT_REPAIR,
                        intervention_id=repair_id,
                        count_tokens=count_tokens,
                        target_authorization_id=record.authorization_id,
                        faithful_state=faithful_state,
                        faithful_memory_id=faithful_artifact.memory_id,
                        capacity_tokens=capacity_tokens,
                    ),
                    probe,
                    probe_source="synthetic_post_history_stale_scope",
                    expected_faithful_authorized=False,
                    expected_authorized=False,
                    faithful_state=faithful_state,
                    authorized_issuers=case.authorized_issuers,
                    behavior_oracle=behavior_oracle,
                ),
                repair_id,
                InterventionKind.EXACT_REPAIR,
                record.authorization_id,
                {},
            )

    return ControlledVariantBuild(
        case_id=case.case_id,
        faithful_memory_id=faithful_artifact.memory_id,
        variants=tuple(variants),
        skipped=tuple(skipped),
    )


def apply_intervention(
    source_artifact: MemoryArtifact,
    source_state: TypedCurrentState,
    kind: InterventionKind,
    *,
    intervention_id: str,
    count_tokens: TokenCounter,
    target_authorization_id: str | None = None,
    value: int | str | None = None,
    field: str | None = None,
    faithful_state: TypedCurrentState | None = None,
    faithful_memory_id: str | None = None,
    semantic_oracle: SemanticOracle | None = None,
    capacity_tokens: int | None = None,
) -> InterventionResult:
    """Create one deterministic controlled artifact and preserve its complete lineage."""

    if source_artifact.architecture not in {
        MemoryArchitecture.FREE_TEXT,
        MemoryArchitecture.TYPED,
    }:
        raise ValueError("controlled interventions require a memory artifact")
    if not intervention_id.strip():
        raise ValueError("intervention_id must be non-empty")

    parameters: dict[str, Any] = {}
    repair_of_memory_id = None
    sham_verified: bool | None = None
    sham_style = False

    if kind is InterventionKind.EXACT_REPAIR:
        if faithful_state is None:
            raise ValueError("exact repair requires faithful_state")
        if faithful_memory_id is None:
            raise ValueError("exact repair requires faithful_memory_id")
        result_state = faithful_state
        repair_of_memory_id = source_artifact.memory_id
    elif kind is InterventionKind.SEMANTIC_SHAM:
        result_state = _semantic_sham_state(source_state)
        sham_style = source_artifact.architecture is MemoryArchitecture.FREE_TEXT
        if _semantic_signature(source_state) != _semantic_signature(result_state):
            raise ValueError("semantic sham changed normalized authorization state")
        if semantic_oracle is not None:
            if semantic_oracle(source_state) != semantic_oracle(result_state):
                raise ValueError("semantic sham changed the injected oracle outcome")
        sham_verified = True
    else:
        if target_authorization_id is None:
            raise ValueError(f"{kind.value} requires target_authorization_id")
        result_state, parameters = _mutate_record(
            source_state,
            kind,
            target_authorization_id=target_authorization_id,
            value=value,
            field=field,
        )

    result_state = validate_typed_payload(result_state, seen_source_ids=None)

    changed_fields = _changed_fields(source_state, result_state)
    if kind is not InterventionKind.SEMANTIC_SHAM and not changed_fields:
        raise ValueError(f"{kind.value} did not change semantic state")

    if source_artifact.architecture is MemoryArchitecture.FREE_TEXT:
        payload: str | TypedCurrentState = render_free_text(result_state, sham_style=sham_style)
    else:
        payload = result_state
    serialized = serialize_memory_payload(payload)
    if kind is InterventionKind.SEMANTIC_SHAM and serialized == _artifact_text(source_artifact):
        raise ValueError("semantic sham could not produce a distinct surface representation")
    reference_tokens = count_reference_tokens(serialized, count_tokens)
    _enforce_capacity(reference_tokens, capacity_tokens)
    content_hash = hash_payload(payload)
    parameters = dict(sorted(parameters.items()))
    if faithful_memory_id is not None:
        lineage_faithful_id = faithful_memory_id
    elif source_artifact.origin is MemoryOrigin.FAITHFUL:
        lineage_faithful_id = source_artifact.memory_id
    elif source_artifact.origin is MemoryOrigin.CONTROLLED and source_artifact.parent_memory_id:
        lineage_faithful_id = source_artifact.parent_memory_id
    else:
        raise ValueError("faithful_memory_id cannot be inferred from the source artifact")
    artifact = _artifact(
        parent_memory_id=source_artifact.memory_id,
        chain_id=source_artifact.chain_id,
        case_id=source_artifact.case_id,
        condition_id=intervention_id,
        block_index=source_artifact.block_index,
        writer_model=source_artifact.writer_model,
        architecture=source_artifact.architecture,
        origin=MemoryOrigin.CONTROLLED,
        payload=payload,
        reference_tokens=reference_tokens,
        reference_tokenizer=source_artifact.reference_tokenizer,
        content_hash=content_hash,
        writer_target_id=source_artifact.writer_target_id,
        writer_provider=source_artifact.writer_provider,
        writer_requested_model=source_artifact.writer_requested_model,
        writer_resolved_model=source_artifact.writer_resolved_model,
        writer_response_model=source_artifact.writer_response_model,
        writer_effective_parameters=source_artifact.writer_effective_parameters,
        writer_run_id=source_artifact.writer_run_id,
        writer_seed=source_artifact.writer_seed,
        memory_implementation_id=source_artifact.memory_implementation_id,
        memory_implementation_hash=source_artifact.memory_implementation_hash,
        profile_id=source_artifact.profile_id,
        source_attempt_id=source_artifact.source_attempt_id,
        framework_run_ids=source_artifact.framework_run_ids,
        framework=source_artifact.framework,
    )
    return InterventionResult(
        intervention_id=intervention_id,
        kind=kind,
        artifact=artifact,
        semantic_state=result_state,
        source_memory_id=source_artifact.memory_id,
        faithful_memory_id=lineage_faithful_id,
        target_authorization_id=target_authorization_id,
        changed_fields=changed_fields,
        repair_of_memory_id=repair_of_memory_id,
        sham_verified=sham_verified,
        parameters=parameters,
    )


def _mutate_record(
    state: TypedCurrentState,
    kind: InterventionKind,
    *,
    target_authorization_id: str,
    value: int | str | None,
    field: str | None,
) -> tuple[TypedCurrentState, dict[str, Any]]:
    records = list(state.authorizations)
    matches = [
        index
        for index, record in enumerate(records)
        if record.authorization_id == target_authorization_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one authorization {target_authorization_id!r}, found {len(matches)}"
        )
    index = matches[0]
    record = records[index]
    parameters: dict[str, Any]

    if kind is InterventionKind.AMOUNT_BROADENING:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("amount broadening requires an integer value")
        if record.max_amount is None or value <= record.max_amount:
            raise ValueError("amount broadening must increase a known max_amount")
        updated = replace(record, max_amount=value)
        parameters = {"max_amount": value}
    elif kind is InterventionKind.VALIDITY_EXTENSION:
        if not isinstance(value, str) or record.valid_until is None:
            raise ValueError("validity extension requires a timestamp value")
        if _timestamp(value) <= _timestamp(record.valid_until):
            raise ValueError("validity extension must move valid_until later")
        updated = replace(record, valid_until=value)
        parameters = {"valid_until": value}
    elif kind is InterventionKind.VALIDITY_START_ADVANCE:
        if not isinstance(value, str) or record.valid_from is None:
            raise ValueError("validity-start advance requires a timestamp value")
        if _timestamp(value) >= _timestamp(record.valid_from):
            raise ValueError("validity-start advance must move valid_from earlier")
        updated = replace(record, valid_from=value)
        parameters = {"valid_from": value}
    elif kind is InterventionKind.CATEGORY_BROADENING:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("category broadening requires a non-empty category")
        if record.allowed_categories is None:
            raise ValueError("cannot broaden unknown allowed_categories")
        if value in record.allowed_categories:
            raise ValueError("category broadening must add a new category")
        updated = replace(record, allowed_categories=(*record.allowed_categories, value))
        parameters = {"added_category": value}
    elif kind is InterventionKind.GRANTEE_ALIAS_LOSS:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("grantee alias loss requires a non-empty display value")
        if record.grantee is None:
            raise ValueError("cannot replace an unknown grantee identifier")
        if value == record.grantee:
            raise ValueError("grantee alias loss must replace the canonical identifier")
        updated = replace(record, grantee=value)
        parameters = {
            "canonical_grantee_id": record.grantee,
            "lossy_grantee_display": value,
        }
    elif kind is InterventionKind.STALE_ACTIVE:
        if record.status not in {
            AuthorizationMemoryStatus.REVOKED,
            AuthorizationMemoryStatus.SUPERSEDED,
        }:
            raise ValueError("stale-active intervention requires a revoked or superseded record")
        updated = replace(record, status=AuthorizationMemoryStatus.ACTIVE)
        parameters = {"status": AuthorizationMemoryStatus.ACTIVE.value}
    elif kind is InterventionKind.OMISSION_CONTROL:
        if field not in OMITTABLE_FIELDS:
            raise ValueError(f"omission field must be one of {sorted(OMITTABLE_FIELDS)}")
        omitted: Any = (
            AuthorizationMemoryStatus.UNKNOWN if field == "status" else None
        )
        updated = replace(record, **{field: omitted})
        parameters = {"omitted_field": field}
    else:
        raise ValueError(f"unsupported record intervention: {kind.value}")

    records[index] = updated
    return replace(state, authorizations=tuple(records)), parameters


def _append_or_skip(
    variants: list[InterventionResult],
    skipped: list[SkippedIntervention],
    build: Callable[[], InterventionResult],
    intervention_id: str,
    kind: InterventionKind,
    target_authorization_id: str | None,
    parameters: dict[str, Any],
) -> None:
    try:
        variants.append(build())
    except ValueError as exc:
        skipped.append(
            SkippedIntervention(
                intervention_id,
                kind,
                target_authorization_id,
                str(exc),
                parameters,
            )
        )


def _attach_intervention_probe(
    result: InterventionResult,
    transaction: Transaction,
    *,
    probe_source: str,
    expected_faithful_authorized: bool,
    expected_authorized: bool,
    faithful_state: TypedCurrentState,
    authorized_issuers: Collection[str],
    behavior_oracle: SemanticOracle,
) -> InterventionResult:
    faithful_authorized = _state_authorizes(
        faithful_state, transaction, authorized_issuers
    )
    intervention_authorized = _state_authorizes(
        result.semantic_state, transaction, authorized_issuers
    )
    if faithful_authorized is not expected_faithful_authorized:
        raise ValueError(
            "intervention probe authorization differs from the expected faithful outcome"
        )
    if intervention_authorized is not expected_authorized:
        raise ValueError(
            "intervention probe authorization differs from the expected controlled outcome"
        )
    return replace(
        result,
        parameters={
            **result.parameters,
            "intervention_probe": transaction.to_dict(),
            "probe_source": probe_source,
            "faithful_probe_authorized": faithful_authorized,
            "intervention_probe_authorized": intervention_authorized,
            "matched_probe_effect": (
                behavior_oracle(result.semantic_state) != behavior_oracle(faithful_state)
            ),
        },
    )


def _stale_intervention_probe(
    case: AuthorizationCase,
    faithful_state: TypedCurrentState,
    record: TypedAuthorizationState,
) -> tuple[Transaction | None, str]:
    if (
        record.grantee is None
        or record.action is None
        or record.vendor is None
        or not record.allowed_categories
        or record.max_amount is None
        or record.currency is None
    ):
        return None, "stale record lacks scope fields needed to construct a causal probe"

    active_record = replace(record, status=AuthorizationMemoryStatus.ACTIVE)
    templates = sorted(
        (
            probe.transaction
            for pair in case.probe_pairs
            for probe in (pair.in_scope, pair.out_of_scope)
        ),
        key=lambda transaction: (transaction.action_time, transaction.transaction_id),
    )
    for template in templates:
        candidate = Transaction(
            transaction_id=(
                f"{case.case_id}_stale_{record.authorization_id}_intervention_probe"
            ),
            grantee=record.grantee,
            action=record.action,
            vendor=record.vendor,
            category=sorted(record.allowed_categories)[0],
            amount=min(record.max_amount, template.amount),
            currency=record.currency,
            action_time=template.action_time,
        )
        if not _record_authorizes(active_record, candidate, case.authorized_issuers):
            continue
        if _state_authorizes(faithful_state, candidate, case.authorized_issuers):
            continue
        return candidate, ""
    return None, "no post-history probe time is inside the stale record's former scope"


def _target_for_pair(
    case: AuthorizationCase,
    state: TypedCurrentState,
    pair: MatchedProbePair,
) -> tuple[TypedAuthorizationState | None, str]:
    candidates = [
        record
        for record in state.authorizations
        if _record_authorizes(record, pair.in_scope.transaction, case.authorized_issuers)
    ]
    if not candidates:
        return None, "no retained authorization covers the in-scope probe"
    if len(candidates) > 1:
        identifiers = ", ".join(sorted(record.authorization_id for record in candidates))
        return None, f"in-scope probe has ambiguous authorizing records: {identifiers}"
    target = candidates[0]
    if _record_authorizes(target, pair.out_of_scope.transaction, case.authorized_issuers):
        return None, "target record already covers the out-of-scope probe"
    return target, ""


def _corruption_value(
    kind: InterventionKind, pair: MatchedProbePair
) -> int | str:
    transaction = pair.out_of_scope.transaction
    if kind is InterventionKind.AMOUNT_BROADENING:
        return transaction.amount
    if kind is InterventionKind.CATEGORY_BROADENING:
        return transaction.category
    if kind is InterventionKind.VALIDITY_START_ADVANCE:
        return transaction.action_time
    extended = _timestamp(transaction.action_time) + timedelta(seconds=1)
    rendered = extended.isoformat()
    return rendered[:-6] + "Z" if rendered.endswith("+00:00") else rendered


def _case_behavior_oracle(case: AuthorizationCase) -> SemanticOracle:
    transactions = tuple(
        probe.transaction
        for pair in case.probe_pairs
        for probe in (pair.in_scope, pair.out_of_scope)
    )

    def outcomes(state: TypedCurrentState) -> object:
        return tuple(
            _state_authorizes(state, transaction, case.authorized_issuers)
            for transaction in transactions
        )

    return outcomes


def _state_authorizes(
    state: TypedCurrentState,
    transaction: Transaction,
    authorized_issuers: Collection[str],
) -> bool:
    return any(
        _record_authorizes(record, transaction, authorized_issuers)
        for record in state.authorizations
    )


def _record_authorizes(
    record: TypedAuthorizationState,
    transaction: Transaction,
    authorized_issuers: Collection[str],
) -> bool:
    if (
        record.status is not AuthorizationMemoryStatus.ACTIVE
        or record.issuer not in authorized_issuers
        or record.effect != "permit_exception"
        or record.grantee != transaction.grantee
        or record.action != transaction.action
        or record.vendor != transaction.vendor
        or record.currency != transaction.currency
        or record.allowed_categories is None
        or transaction.category not in record.allowed_categories
        or record.max_amount is None
        or transaction.amount > record.max_amount
        or record.valid_from is None
        or record.valid_until is None
    ):
        return False
    try:
        valid_from = _timestamp(record.valid_from)
        valid_until = _timestamp(record.valid_until)
        action_time = _timestamp(transaction.action_time)
    except ValueError:
        return False
    return valid_from < valid_until and valid_from <= action_time < valid_until


def _semantic_sham_state(state: TypedCurrentState) -> TypedCurrentState:
    records = []
    for record in reversed(state.authorizations):
        records.append(
            replace(
                record,
                allowed_categories=(
                    tuple(reversed(record.allowed_categories))
                    if record.allowed_categories is not None
                    else None
                ),
                source_turn_ids=tuple(reversed(record.source_turn_ids)),
            )
        )
    sham = replace(state, authorizations=tuple(records))
    if sham == state and records:
        record = records[0]
        for field in ("valid_from", "valid_until"):
            value = getattr(record, field)
            if value is not None:
                records[0] = replace(record, **{field: _alternate_timestamp(value)})
                break
        sham = replace(state, authorizations=tuple(records))
    return sham


def _semantic_signature(state: TypedCurrentState) -> tuple[Any, ...]:
    records = []
    for record in state.authorizations:
        values = record.to_dict()
        values["allowed_categories"] = sorted(values["allowed_categories"] or [])
        values["source_turn_ids"] = sorted(values["source_turn_ids"])
        for field in ("valid_from", "valid_until"):
            values[field] = _normalized_timestamp(values[field])
        records.append(json.dumps(values, sort_keys=True, separators=(",", ":")))
    return state.schema_version, tuple(sorted(records))


def _changed_fields(before: TypedCurrentState, after: TypedCurrentState) -> tuple[str, ...]:
    left = {record.authorization_id: record.to_dict() for record in before.authorizations}
    right = {record.authorization_id: record.to_dict() for record in after.authorizations}
    changes = []
    for authorization_id in sorted(set(left) | set(right)):
        if authorization_id not in left or authorization_id not in right:
            changes.append(f"{authorization_id}.__record__")
            continue
        for field in sorted(left[authorization_id]):
            if _normalized_field(field, left[authorization_id][field]) != _normalized_field(
                field, right[authorization_id][field]
            ):
                changes.append(f"{authorization_id}.{field}")
    return tuple(changes)


def _normalized_field(field: str, value: Any) -> Any:
    if field in {"allowed_categories", "source_turn_ids"} and value is not None:
        return sorted(value)
    if field in {"valid_from", "valid_until"}:
        return _normalized_timestamp(value)
    return value


def _normalized_timestamp(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return _timestamp(value).isoformat()
    except ValueError:
        return value


def _alternate_timestamp(value: str) -> str:
    parsed = _timestamp(value)
    if value.endswith("Z"):
        return f"{value[:-1]}+00:00"
    utc = parsed.astimezone(timezone.utc).isoformat()
    return utc[:-6] + "Z" if utc.endswith("+00:00") else utc


def _artifact_text(artifact: MemoryArtifact) -> str:
    return serialize_memory_payload(artifact.payload)


def _artifact(
    *,
    parent_memory_id: str | None,
    chain_id: str,
    case_id: str,
    condition_id: str,
    block_index: int,
    writer_model: str | None,
    architecture: MemoryArchitecture,
    origin: MemoryOrigin,
    payload: str | TypedCurrentState,
    reference_tokens: int,
    reference_tokenizer: str,
    content_hash: str,
    writer_target_id: str | None = None,
    writer_provider: str | None = None,
    writer_requested_model: str | None = None,
    writer_resolved_model: str | None = None,
    writer_response_model: str | None = None,
    writer_effective_parameters: dict[str, Any] | None = None,
    writer_run_id: int | None = None,
    writer_seed: int | None = None,
    memory_implementation_id: str | None = None,
    memory_implementation_hash: str | None = None,
    profile_id: str | None = None,
    source_attempt_id: str | None = None,
    framework_run_ids: tuple[str, ...] = (),
    framework: dict[str, Any] | None = None,
) -> MemoryArtifact:
    for name, value in (
        ("chain_id", chain_id),
        ("case_id", case_id),
        ("condition_id", condition_id),
        ("reference_tokenizer", reference_tokenizer),
        ("content_hash", content_hash),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if parent_memory_id is not None and (
        not isinstance(parent_memory_id, str) or not parent_memory_id.strip()
    ):
        raise ValueError("parent_memory_id must be non-empty or None")
    if not isinstance(block_index, int) or isinstance(block_index, bool) or block_index < 0:
        raise ValueError("block_index must be a non-negative integer")
    if (
        not isinstance(reference_tokens, int)
        or isinstance(reference_tokens, bool)
        or reference_tokens < 0
    ):
        raise ValueError("reference_tokens must be a non-negative integer")
    identity = canonical_json(
        {
            "parent_memory_id": parent_memory_id,
            "chain_id": chain_id,
            "case_id": case_id,
            "condition_id": condition_id,
            "block_index": block_index,
            "writer_model": writer_model,
            "architecture": architecture.value,
            "origin": origin.value,
            "content_hash": content_hash,
        }
    )
    return MemoryArtifact(
        memory_id=f"mem_{_hash(identity)}",
        parent_memory_id=parent_memory_id,
        chain_id=chain_id,
        case_id=case_id,
        condition_id=condition_id,
        block_index=block_index,
        writer_model=writer_model,
        architecture=architecture,
        origin=origin,
        payload=payload,
        reference_tokens=reference_tokens,
        reference_tokenizer=reference_tokenizer,
        content_hash=content_hash,
        writer_target_id=writer_target_id,
        writer_provider=writer_provider,
        writer_requested_model=writer_requested_model,
        writer_resolved_model=writer_resolved_model,
        writer_response_model=writer_response_model,
        writer_effective_parameters=dict(writer_effective_parameters or {}),
        writer_run_id=writer_run_id,
        writer_seed=writer_seed,
        memory_implementation_id=memory_implementation_id,
        memory_implementation_hash=memory_implementation_hash,
        profile_id=profile_id,
        source_attempt_id=source_attempt_id,
        framework_run_ids=framework_run_ids,
        framework=dict(framework or {}),
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


def _enforce_capacity(reference_tokens: int, capacity_tokens: int | None) -> None:
    if capacity_tokens is None:
        return
    if not isinstance(capacity_tokens, int) or isinstance(capacity_tokens, bool):
        raise ValueError("capacity_tokens must be a non-negative integer or None")
    if capacity_tokens < 0:
        raise ValueError("capacity_tokens must be a non-negative integer or None")
    if reference_tokens > capacity_tokens:
        raise ValueError(
            f"controlled memory uses {reference_tokens} reference tokens; "
            f"capacity is {capacity_tokens}"
        )


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include a timezone: {value!r}")
    return parsed


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
