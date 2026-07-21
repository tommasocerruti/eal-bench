from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from domains.procurement.cases import (
    current_ledger,
)
from domains.procurement.oracle import evaluate_ledger
from domains.procurement.schemas import (
    AuthorizationCase,
    CanonicalAuthorizationRecord,
    LedgerSnapshot,
    Transaction,
)

from .interventions import (
    InterventionKind,
    InterventionResult,
    apply_intervention,
    build_faithful_artifact,
    faithful_typed_state,
)
from .memory import canonical_json, count_reference_tokens
from .pipeline import (
    AuthorizationCheckpoint,
    CheckpointEvidenceLink,
    ExplicitExecutorJob,
    ExplicitExecutorProbe,
    FrozenEvidence,
    freeze_memory_evidence,
)
from .schemas import (
    AuthorizationMemoryStatus,
    ExecutorPressure,
    MemoryArchitecture,
    MemoryArtifact,
    TypedAuthorizationState,
    TypedCurrentState,
)


SUBSTANTIVE_STUDY_ID = "substantive_overgrant_v1"
EVIDENCE_ROLES = (
    "natural_error",
    "exact_repair",
    "surface_sham",
    "faithful_canonical",
)
REQUEST_ROLES = ("witness", "utility")
MAX_SELECTED_PER_CASE = 2
MAX_SELECTED_TOTAL = 20
_DIMENSION_ORDER = {
    "status": 0,
    "vendor": 1,
    "category": 2,
    "amount": 3,
    "time": 4,
    "grantee": 5,
    "stitched_scope": 6,
    "multi_field": 7,
    "extra_record": 8,
}
_REQUIRED_MEMORY_FIELDS = (
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
class SourceCheckpointEvidence:
    checkpoint: AuthorizationCheckpoint
    link: CheckpointEvidenceLink
    evidence: FrozenEvidence
    snapshot: LedgerSnapshot
    update_policy: str = "bounded_repair"
    counterfactual_of_evidence_id: str | None = None
    first_attempt_id: str | None = None
    first_attempt_status: str | None = None


@dataclass(frozen=True)
class SourceCheckpointRun:
    path: Path
    manifest: Mapping[str, Any]
    manifest_sha256: str
    file_sha256: Mapping[str, str]
    artifacts: Mapping[str, MemoryArtifact]
    items: tuple[SourceCheckpointEvidence, ...]

    def manifest_record(self) -> dict[str, Any]:
        counterfactuals = sum(
            item.update_policy == "no_repair_counterfactual"
            for item in self.items
        )
        return {
            "path": str(self.path),
            "run": self.manifest["run"],
            "status": self.manifest["status"],
            "manifest_sha256": self.manifest_sha256,
            "file_sha256": dict(sorted(self.file_sha256.items())),
            "writer_profile": self.manifest["writer_profile"],
            "writer_runs": self.manifest["writer_runs"],
            "saved_checkpoint_evidence_count": (
                self.manifest["counts"]["checkpoint_evidence"]
            ),
            "derived_no_repair_counterfactuals": counterfactuals,
            "screened_checkpoint_states": len(self.items),
        }


@dataclass(frozen=True)
class SubstantiveWitness:
    witness_id: str
    transaction: Transaction
    authorizing_record_id: str
    candidate_dimension: str
    candidate_dimensions: tuple[str, ...]
    canonical_reason: str
    final_canonical_authorized: bool
    final_canonical_reason: str
    stale_scope: bool
    stitched_scope: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "witness_id": self.witness_id,
            "transaction": self.transaction.to_dict(),
            "authorizing_record_id": self.authorizing_record_id,
            "candidate_dimension": self.candidate_dimension,
            "candidate_dimensions": list(self.candidate_dimensions),
            "canonical_reason": self.canonical_reason,
            "final_canonical_reason": self.final_canonical_reason,
            "memory_authorized": True,
            "checkpoint_canonical_authorized": False,
            "final_canonical_authorized": self.final_canonical_authorized,
            "stale_scope": self.stale_scope,
            "stitched_scope": self.stitched_scope,
        }


@dataclass(frozen=True)
class EligibilityRecord:
    eligibility_id: str
    source_run: str
    source_run_manifest_sha256: str
    source_file_sha256: Mapping[str, str]
    checkpoint_id: str
    case_id: str
    block_id: str
    block_index: int
    event_ids: tuple[str, ...]
    event_types: tuple[str, ...]
    authorization_ids: tuple[str, ...]
    source_evidence_id: str
    source_memory_id: str | None
    source_content_hash: str
    source_condition_id: str
    update_policy: str
    counterfactual_of_evidence_id: str | None
    first_attempt_id: str | None
    first_attempt_status: str | None
    writer_run_id: int
    writer_seed: int
    memory_run_id: int
    writer_model: str | None
    accepted_memory: bool
    actor_id_exact: bool
    eligible: bool
    executor_eligible: bool
    exclusion_reason: str | None
    witness: SubstantiveWitness | None
    utility_transaction: Transaction | None
    selected_for_executor: bool = False
    case_selection_rank: int | None = None
    global_selection_rank: int | None = None

    @property
    def candidate_id(self) -> str | None:
        if self.witness is None:
            return None
        return "substantive_candidate_" + _hash_json(
            {
                "source_evidence_id": self.source_evidence_id,
                "checkpoint_id": self.checkpoint_id,
                "witness_id": self.witness.witness_id,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "substantive_study_id": SUBSTANTIVE_STUDY_ID,
            "eligibility_id": self.eligibility_id,
            "candidate_id": self.candidate_id,
            "source_run": self.source_run,
            "source_run_manifest_sha256": self.source_run_manifest_sha256,
            "source_file_sha256": dict(sorted(self.source_file_sha256.items())),
            "checkpoint_id": self.checkpoint_id,
            "case_id": self.case_id,
            "block_id": self.block_id,
            "block_index": self.block_index,
            "event_ids": list(self.event_ids),
            "event_types": list(self.event_types),
            "authorization_ids": list(self.authorization_ids),
            "source_evidence_id": self.source_evidence_id,
            "source_memory_id": self.source_memory_id,
            "source_content_hash": self.source_content_hash,
            "source_condition_id": self.source_condition_id,
            "update_policy": self.update_policy,
            "counterfactual_of_evidence_id": self.counterfactual_of_evidence_id,
            "first_attempt_id": self.first_attempt_id,
            "first_attempt_status": self.first_attempt_status,
            "writer_run_id": self.writer_run_id,
            "writer_seed": self.writer_seed,
            "memory_run_id": self.memory_run_id,
            "writer_model": self.writer_model,
            "accepted_memory": self.accepted_memory,
            "actor_id_exact": self.actor_id_exact,
            "eligible": self.eligible,
            "executor_eligible": self.executor_eligible,
            "exclusion_reason": self.exclusion_reason,
            "witness": self.witness.to_dict() if self.witness else None,
            "utility_transaction": (
                self.utility_transaction.to_dict()
                if self.utility_transaction is not None
                else None
            ),
            "selected_for_executor": self.selected_for_executor,
            "case_selection_rank": self.case_selection_rank,
            "global_selection_rank": self.global_selection_rank,
        }


@dataclass(frozen=True)
class SubstantiveOvergrantBuild:
    candidate_id: str
    eligibility_id: str
    case_id: str
    checkpoint_id: str
    source_evidence_id: str
    source_memory_id: str
    witness: SubstantiveWitness
    utility_transaction: Transaction
    exact_repair: InterventionResult
    surface_sham: InterventionResult
    faithful_artifact: MemoryArtifact

    def to_dict(self) -> dict[str, Any]:
        return {
            "substantive_study_id": SUBSTANTIVE_STUDY_ID,
            "candidate_id": self.candidate_id,
            "eligibility_id": self.eligibility_id,
            "case_id": self.case_id,
            "checkpoint_id": self.checkpoint_id,
            "source_evidence_id": self.source_evidence_id,
            "source_memory_id": self.source_memory_id,
            "witness": self.witness.to_dict(),
            "utility_transaction": self.utility_transaction.to_dict(),
            "exact_repair": self.exact_repair.to_dict(),
            "surface_sham": self.surface_sham.to_dict(),
            "faithful_artifact": self.faithful_artifact.to_dict(),
        }


@dataclass(frozen=True)
class SubstantiveOvergrantBundle:
    source: SourceCheckpointRun
    eligibility: tuple[EligibilityRecord, ...]
    builds: tuple[SubstantiveOvergrantBuild, ...]
    artifacts: tuple[MemoryArtifact, ...]
    evidence: tuple[FrozenEvidence, ...]
    jobs: tuple[ExplicitExecutorJob, ...]

    def study_manifest(self) -> dict[str, Any]:
        eligible = [row for row in self.eligibility if row.eligible]
        executor_eligible = [
            row for row in self.eligibility if row.executor_eligible
        ]
        selected = [row for row in self.eligibility if row.selected_for_executor]
        return {
            "study_id": SUBSTANTIVE_STUDY_ID,
            "description": (
                "Source-linked natural typed-memory overgrant study at frozen "
                "authorization-change checkpoints."
            ),
            "source_run": self.source.manifest_record(),
            "evidence_roles": list(EVIDENCE_ROLES),
            "request_roles": list(REQUEST_ROLES),
            "pressure_conditions": ["none"],
            "harvested_artifacts": len(self.eligibility),
            "states_by_update_policy": dict(
                sorted(
                    {
                        policy: sum(
                            row.update_policy == policy
                            for row in self.eligibility
                        )
                        for policy in {
                            row.update_policy for row in self.eligibility
                        }
                    }.items()
                )
            ),
            "substantive_eligible_artifacts": len(eligible),
            "executor_eligible_artifacts": len(executor_eligible),
            "selected_candidates": len(selected),
            "selected_cases": len({row.case_id for row in selected}),
            "selection_policy": {
                "maximum_per_case": MAX_SELECTED_PER_CASE,
                "maximum_total": MAX_SELECTED_TOTAL,
                "order": "sha256(candidate_id)",
            },
            "base_executor_jobs": len(self.jobs),
        }


def screen_substantive_overgrants(
    cases: Sequence[AuthorizationCase],
    source: SourceCheckpointRun,
    *,
    selected_update_policies: frozenset[str] | None = None,
) -> tuple[EligibilityRecord, ...]:
    case_by_id = {case.case_id: case for case in cases}
    rows = []
    for item in source.items:
        case = case_by_id[item.checkpoint.case_id]
        evidence = item.evidence
        state = evidence.memory_payload
        actor_ids = {
            turn.actor_id for block in case.blocks for turn in block.turns
        }
        accepted = (
            evidence.artifact is not None
            and isinstance(state, TypedCurrentState)
            and not evidence.used_empty_fallback
        )
        actor_exact = False
        witness = None
        utility = None
        exclusion = None
        if not accepted:
            exclusion = "no_accepted_typed_memory"
        elif not state.authorizations:
            exclusion = "empty_memory"
        else:
            actor_exact = all(
                record.grantee is None or record.grantee in actor_ids
                for record in state.authorizations
            )
            witness = synthesize_substantive_witness(
                case,
                item.snapshot,
                state,
                checkpoint_block_end=case.blocks[
                    item.checkpoint.block_index
                ].ended_at,
                known_actor_ids=actor_ids,
            )
            if witness is None:
                exclusion = (
                    "identity_alias_or_no_transaction_realizable_overgrant"
                    if not actor_exact
                    else "no_transaction_realizable_overgrant"
                )
            else:
                utility = nearest_canonical_utility_transaction(
                    case,
                    item.snapshot,
                    witness.transaction,
                    checkpoint_block_end=case.blocks[
                        item.checkpoint.block_index
                    ].ended_at,
                )
                if utility is None:
                    exclusion = "no_stable_canonical_utility_control"
        eligible = witness is not None
        executor_eligible = eligible and utility is not None
        eligibility_id = "substantive_eligibility_" + _hash_json(
            {
                "source_run": source.manifest["run"],
                "checkpoint_id": item.checkpoint.checkpoint_id,
                "source_evidence_id": evidence.evidence_id,
            }
        )
        rows.append(
            EligibilityRecord(
                eligibility_id=eligibility_id,
                source_run=source.manifest["run"],
                source_run_manifest_sha256=source.manifest_sha256,
                source_file_sha256=source.file_sha256,
                checkpoint_id=item.checkpoint.checkpoint_id,
                case_id=case.case_id,
                block_id=item.checkpoint.block_id,
                block_index=item.checkpoint.block_index,
                event_ids=item.checkpoint.event_ids,
                event_types=item.checkpoint.event_types,
                authorization_ids=item.checkpoint.authorization_ids,
                source_evidence_id=evidence.evidence_id,
                source_memory_id=evidence.memory_id,
                source_content_hash=evidence.content_hash,
                source_condition_id=evidence.condition_id,
                update_policy=item.update_policy,
                counterfactual_of_evidence_id=(
                    item.counterfactual_of_evidence_id
                ),
                first_attempt_id=item.first_attempt_id,
                first_attempt_status=item.first_attempt_status,
                writer_run_id=item.link.writer_run_id,
                writer_seed=item.link.writer_seed,
                memory_run_id=evidence.memory_run_id,
                writer_model=evidence.writer_model,
                accepted_memory=accepted,
                actor_id_exact=actor_exact,
                eligible=eligible,
                executor_eligible=executor_eligible,
                exclusion_reason=exclusion,
                witness=witness,
                utility_transaction=utility,
            )
        )
    return _freeze_selection(
        rows,
        selected_update_policies=selected_update_policies,
    )


def build_substantive_overgrant_jobs(
    cases: Sequence[AuthorizationCase],
    source: SourceCheckpointRun,
    *,
    selected_update_policies: frozenset[str] | None = None,
) -> SubstantiveOvergrantBundle:
    case_by_id = {case.case_id: case for case in cases}
    source_by_evidence = {
        item.evidence.evidence_id: item for item in source.items
    }
    eligibility = screen_substantive_overgrants(
        cases,
        source,
        selected_update_policies=selected_update_policies,
    )
    selected = [row for row in eligibility if row.selected_for_executor]
    builds = []
    artifacts: dict[str, MemoryArtifact] = {}
    frozen: dict[str, FrozenEvidence] = {}
    jobs = []
    for row in selected:
        assert row.candidate_id is not None
        assert row.source_memory_id is not None
        assert row.witness is not None
        assert row.utility_transaction is not None
        source_item = source_by_evidence[row.source_evidence_id]
        source_evidence = source_item.evidence
        source_artifact = source_evidence.artifact
        source_state = source_evidence.memory_payload
        if source_artifact is None or not isinstance(source_state, TypedCurrentState):
            raise AssertionError("selected natural candidate lacks a typed source artifact")
        case = case_by_id[row.case_id]
        canonical_state = faithful_typed_state(source_item.snapshot.records)
        faithful_artifact = build_faithful_artifact(
            canonical_state,
            MemoryArchitecture.TYPED,
            case_id=case.case_id,
            chain_id=f"{row.candidate_id}:faithful_checkpoint",
            condition_id=f"{row.candidate_id}_faithful_canonical",
            block_index=row.block_index,
            reference_tokenizer=source_artifact.reference_tokenizer,
            count_tokens=count_reference_tokens,
            capacity_tokens=source_evidence.capacity_tokens,
        )
        repair = apply_intervention(
            source_artifact,
            source_state,
            InterventionKind.EXACT_REPAIR,
            intervention_id=f"{row.candidate_id}_exact_repair",
            count_tokens=count_reference_tokens,
            target_authorization_id=row.witness.authorizing_record_id,
            faithful_state=canonical_state,
            faithful_memory_id=faithful_artifact.memory_id,
            capacity_tokens=source_evidence.capacity_tokens,
        )
        sham = apply_intervention(
            source_artifact,
            source_state,
            InterventionKind.SEMANTIC_SHAM,
            intervention_id=f"{row.candidate_id}_surface_sham",
            count_tokens=count_reference_tokens,
            target_authorization_id=row.witness.authorizing_record_id,
            faithful_memory_id=faithful_artifact.memory_id,
            capacity_tokens=source_evidence.capacity_tokens,
        )
        if _state_authorizes(
            repair.semantic_state,
            row.witness.transaction,
            case.authorized_issuers,
        ):
            raise ValueError(f"{row.candidate_id}: exact repair retains witness authority")
        if not _state_authorizes(
            sham.semantic_state,
            row.witness.transaction,
            case.authorized_issuers,
        ):
            raise ValueError(f"{row.candidate_id}: surface sham changed witness authority")

        role_artifacts = {
            "natural_error": source_artifact,
            "exact_repair": repair.artifact,
            "surface_sham": sham.artifact,
            "faithful_canonical": faithful_artifact,
        }
        role_evidence = {
            "natural_error": source_evidence,
            "exact_repair": freeze_memory_evidence(
                repair.artifact,
                memory_run_id=row.memory_run_id,
                capacity_tier=source_evidence.capacity_tier,
                capacity_tokens=source_evidence.capacity_tokens,
                writer_seed=row.writer_seed,
            ),
            "surface_sham": freeze_memory_evidence(
                sham.artifact,
                memory_run_id=row.memory_run_id,
                capacity_tier=source_evidence.capacity_tier,
                capacity_tokens=source_evidence.capacity_tokens,
                writer_seed=row.writer_seed,
            ),
            "faithful_canonical": freeze_memory_evidence(
                faithful_artifact,
                memory_run_id=row.memory_run_id,
                capacity_tier=source_evidence.capacity_tier,
                capacity_tokens=source_evidence.capacity_tokens,
                writer_seed=row.writer_seed,
            ),
        }
        build = SubstantiveOvergrantBuild(
            candidate_id=row.candidate_id,
            eligibility_id=row.eligibility_id,
            case_id=row.case_id,
            checkpoint_id=row.checkpoint_id,
            source_evidence_id=row.source_evidence_id,
            source_memory_id=row.source_memory_id,
            witness=row.witness,
            utility_transaction=row.utility_transaction,
            exact_repair=repair,
            surface_sham=sham,
            faithful_artifact=faithful_artifact,
        )
        builds.append(build)
        for artifact in role_artifacts.values():
            artifacts[artifact.memory_id] = artifact
        for evidence in role_evidence.values():
            frozen[evidence.evidence_id] = evidence

        transactions = {
            "witness": row.witness.transaction,
            "utility": row.utility_transaction,
        }
        checkpoint_labels = {"witness": False, "utility": True}
        final_labels = {
            request_role: evaluate_ledger(
                current_ledger(case),
                transaction,
                authorized_issuers=case.authorized_issuers,
            ).authorized
            for request_role, transaction in transactions.items()
        }
        for evidence_role in EVIDENCE_ROLES:
            role_state = role_evidence[evidence_role].memory_payload
            assert isinstance(role_state, TypedCurrentState)
            for request_role in REQUEST_ROLES:
                transaction = transactions[request_role]
                memory_authorized = _state_authorizes(
                    role_state, transaction, case.authorized_issuers
                )
                metadata = {
                    "substantive_study_id": SUBSTANTIVE_STUDY_ID,
                    "candidate_id": row.candidate_id,
                    "eligibility_id": row.eligibility_id,
                    "checkpoint_id": row.checkpoint_id,
                    "checkpoint_block_id": row.block_id,
                    "checkpoint_block_index": row.block_index,
                    "checkpoint_event_ids": list(row.event_ids),
                    "checkpoint_event_types": list(row.event_types),
                    "checkpoint_authorization_ids": list(row.authorization_ids),
                    "source_run": row.source_run,
                    "source_run_manifest_sha256": row.source_run_manifest_sha256,
                    "source_evidence_id": row.source_evidence_id,
                    "source_memory_id": row.source_memory_id,
                    "source_content_hash": row.source_content_hash,
                    "source_condition_id": row.source_condition_id,
                    "source_update_policy": row.update_policy,
                    "counterfactual_of_evidence_id": (
                        row.counterfactual_of_evidence_id
                    ),
                    "first_attempt_id": row.first_attempt_id,
                    "first_attempt_status": row.first_attempt_status,
                    "source_writer_run_id": row.writer_run_id,
                    "source_writer_seed": row.writer_seed,
                    "source_writer_model": row.writer_model,
                    "evidence_role": evidence_role,
                    "request_role": request_role,
                    "witness_id": row.witness.witness_id,
                    "witness_dimension": row.witness.candidate_dimension,
                    "witness_dimensions": list(
                        row.witness.candidate_dimensions
                    ),
                    "witness_transaction_sha256": _hash_json(
                        row.witness.transaction.to_dict()
                    ),
                    "utility_transaction_sha256": _hash_json(
                        row.utility_transaction.to_dict()
                    ),
                    "authorizing_record_id": (
                        row.witness.authorizing_record_id
                    ),
                    "checkpoint_canonical_authorized": checkpoint_labels[
                        request_role
                    ],
                    "final_canonical_authorized": final_labels[
                        request_role
                    ],
                    "artifact_memory_authorized": memory_authorized,
                    "repair_changed_fields": list(repair.changed_fields),
                    "sham_verified": (
                        sham.sham_verified
                        if evidence_role == "surface_sham"
                        else None
                    ),
                    "pressure_family": "none",
                }
                jobs.append(
                    ExplicitExecutorJob(
                        role_evidence[evidence_role],
                        ExplicitExecutorProbe(
                            case_id=case.case_id,
                            probe_name=(
                                f"{row.candidate_id}_{evidence_role}_{request_role}"
                            ),
                            pair_id=row.candidate_id,
                            dimension=row.witness.candidate_dimension,
                            transaction=transaction,
                            request_scope=(
                                "out_of_scope"
                                if request_role == "witness"
                                else "in_scope"
                            ),
                            pressure_condition=ExecutorPressure.BASELINE,
                            oracle_block_index=row.block_index,
                            metadata=metadata,
                        ),
                    )
                )

    expected_jobs = len(builds) * len(EVIDENCE_ROLES) * len(REQUEST_ROLES)
    if len(jobs) != expected_jobs:
        raise AssertionError(
            f"substantive follow-up built {len(jobs)} jobs; expected {expected_jobs}"
        )
    return SubstantiveOvergrantBundle(
        source=source,
        eligibility=eligibility,
        builds=tuple(builds),
        artifacts=tuple(artifacts.values()),
        evidence=tuple(frozen.values()),
        jobs=tuple(jobs),
    )


def synthesize_substantive_witness(
    case: AuthorizationCase,
    snapshot: LedgerSnapshot,
    state: TypedCurrentState,
    *,
    checkpoint_block_end: str,
    known_actor_ids: set[str],
) -> SubstantiveWitness | None:
    candidates = []
    final_records = current_ledger(case)
    for record in state.authorizations:
        if not _complete_active_record(record, case.authorized_issuers):
            continue
        if record.grantee not in known_actor_ids:
            continue
        for transaction in _transactions_from_record(
            case,
            snapshot,
            record,
            checkpoint_block_end=checkpoint_block_end,
        ):
            if not _record_authorizes(
                record, transaction, case.authorized_issuers
            ):
                continue
            if not _state_authorizes(
                state, transaction, case.authorized_issuers
            ):
                continue
            checkpoint_decision = evaluate_ledger(
                snapshot.records,
                transaction,
                authorized_issuers=case.authorized_issuers,
            )
            if checkpoint_decision.authorized:
                continue
            final_decision = evaluate_ledger(
                final_records,
                transaction,
                authorized_issuers=case.authorized_issuers,
            )
            dimensions, stale, stitched = _candidate_dimensions(
                snapshot.records, record, transaction
            )
            primary = (
                "stitched_scope"
                if stitched
                else dimensions[0]
                if len(dimensions) == 1
                else "multi_field"
            )
            identity = {
                "case_id": case.case_id,
                "checkpoint_block_index": snapshot.block_index,
                "authorizing_record_id": record.authorization_id,
                "transaction": transaction.to_dict(),
            }
            witness = SubstantiveWitness(
                witness_id="substantive_witness_" + _hash_json(identity),
                transaction=replace(
                    transaction,
                    transaction_id="substantive_witness_" + _hash_json(identity),
                ),
                authorizing_record_id=record.authorization_id,
                candidate_dimension=primary,
                candidate_dimensions=dimensions,
                canonical_reason=checkpoint_decision.reason,
                final_canonical_authorized=final_decision.authorized,
                final_canonical_reason=final_decision.reason,
                stale_scope=stale,
                stitched_scope=stitched,
            )
            candidates.append(
                (
                    len(dimensions),
                    _DIMENSION_ORDER.get(primary, 99),
                    _hash_json(witness.transaction.to_dict()),
                    witness,
                )
            )
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[:3])[-1]


def nearest_canonical_utility_transaction(
    case: AuthorizationCase,
    snapshot: LedgerSnapshot,
    witness: Transaction,
    *,
    checkpoint_block_end: str,
) -> Transaction | None:
    after_checkpoint = _timestamp(checkpoint_block_end) + timedelta(seconds=1)
    candidates = []
    for record in snapshot.records:
        if (
            record.status != "active"
            or record.issuer not in case.authorized_issuers
        ):
            continue
        start = max(_timestamp(record.valid_from), after_checkpoint)
        end = _timestamp(record.valid_until)
        if start >= end:
            continue
        action_time = _timestamp_text(start)
        for category in sorted(record.allowed_categories):
            amount = min(witness.amount, record.max_amount)
            transaction = Transaction(
                transaction_id="utility_candidate",
                grantee=record.grantee,
                action=record.action,
                vendor=record.vendor,
                category=category,
                amount=amount,
                currency=record.currency,
                action_time=action_time,
            )
            checkpoint = evaluate_ledger(
                snapshot.records,
                transaction,
                authorized_issuers=case.authorized_issuers,
            )
            if not checkpoint.authorized:
                continue
            distance = (
                sum(
                    getattr(transaction, field) != getattr(witness, field)
                    for field in (
                        "grantee",
                        "action",
                        "vendor",
                        "category",
                        "currency",
                    )
                ),
                abs(transaction.amount - witness.amount),
                abs(
                    (
                        _timestamp(transaction.action_time)
                        - _timestamp(witness.action_time)
                    ).total_seconds()
                ),
                record.authorization_id,
                canonical_json(transaction.to_dict()),
            )
            candidates.append((distance, transaction))
    if not candidates:
        return None
    selected = min(candidates, key=lambda item: item[0])[-1]
    identity = {
        "case_id": case.case_id,
        "checkpoint_block_index": snapshot.block_index,
        "witness_id": witness.transaction_id,
        "transaction": selected.to_dict(),
    }
    return replace(
        selected,
        transaction_id="substantive_utility_" + _hash_json(identity),
    )


def _transactions_from_record(
    case: AuthorizationCase,
    snapshot: LedgerSnapshot,
    record: TypedAuthorizationState,
    *,
    checkpoint_block_end: str,
) -> tuple[Transaction, ...]:
    assert record.grantee is not None
    assert record.action is not None
    assert record.vendor is not None
    assert record.allowed_categories is not None
    assert record.max_amount is not None
    assert record.currency is not None
    assert record.valid_from is not None
    assert record.valid_until is not None
    after_checkpoint = _timestamp(checkpoint_block_end) + timedelta(seconds=1)
    remembered_start = _timestamp(record.valid_from)
    remembered_end = _timestamp(record.valid_until)
    lower = max(after_checkpoint, remembered_start)
    if lower >= remembered_end:
        return ()

    times = {lower, remembered_end - timedelta(seconds=1)}
    amounts = {record.max_amount}
    for canonical in snapshot.records:
        for boundary in (
            _timestamp(canonical.valid_from) - timedelta(seconds=1),
            _timestamp(canonical.valid_from),
            _timestamp(canonical.valid_until) - timedelta(seconds=1),
            _timestamp(canonical.valid_until),
        ):
            if lower <= boundary < remembered_end:
                times.add(boundary)
        if canonical.max_amount < record.max_amount:
            amounts.add(canonical.max_amount + 1)
    transactions = []
    for category in sorted(record.allowed_categories):
        for amount in sorted(amounts):
            for action_time in sorted(times):
                identity = {
                    "case_id": case.case_id,
                    "record_id": record.authorization_id,
                    "category": category,
                    "amount": amount,
                    "action_time": _timestamp_text(action_time),
                }
                transactions.append(
                    Transaction(
                        transaction_id="candidate_" + _hash_json(identity),
                        grantee=record.grantee,
                        action=record.action,
                        vendor=record.vendor,
                        category=category,
                        amount=amount,
                        currency=record.currency,
                        action_time=_timestamp_text(action_time),
                    )
                )
    return tuple(transactions)


def _candidate_dimensions(
    canonical_records: Sequence[CanonicalAuthorizationRecord],
    remembered: TypedAuthorizationState,
    transaction: Transaction,
) -> tuple[tuple[str, ...], bool, bool]:
    same_id = next(
        (
            record
            for record in canonical_records
            if record.authorization_id == remembered.authorization_id
        ),
        None,
    )
    dimensions = []
    stale = False
    if same_id is None:
        dimensions.append("extra_record")
    else:
        if same_id.status != "active":
            dimensions.append("status")
            stale = True
        if same_id.grantee != transaction.grantee:
            dimensions.append("grantee")
        if same_id.vendor != transaction.vendor:
            dimensions.append("vendor")
        if transaction.category not in same_id.allowed_categories:
            dimensions.append("category")
        if transaction.amount > same_id.max_amount:
            dimensions.append("amount")
        action_time = _timestamp(transaction.action_time)
        if not (
            _timestamp(same_id.valid_from)
            <= action_time
            < _timestamp(same_id.valid_until)
        ):
            dimensions.append("time")
    active = [record for record in canonical_records if record.status == "active"]
    stitched = (
        len(dimensions) >= 2
        and _looks_stitched(active, transaction)
        and (same_id is None or same_id.status != "active")
    )
    if not dimensions:
        dimensions.append("multi_field")
    ordered = tuple(
        sorted(set(dimensions), key=lambda item: _DIMENSION_ORDER.get(item, 99))
    )
    return ordered, stale, stitched


def _looks_stitched(
    records: Sequence[CanonicalAuthorizationRecord],
    transaction: Transaction,
) -> bool:
    if len(records) < 2:
        return False
    supports = []
    predicates = (
        lambda record: record.grantee == transaction.grantee,
        lambda record: record.action == transaction.action,
        lambda record: record.vendor == transaction.vendor,
        lambda record: transaction.category in record.allowed_categories,
        lambda record: transaction.amount <= record.max_amount,
        lambda record: record.currency == transaction.currency,
        lambda record: (
            _timestamp(record.valid_from)
            <= _timestamp(transaction.action_time)
            < _timestamp(record.valid_until)
        ),
    )
    for predicate in predicates:
        matched = {
            record.authorization_id for record in records if predicate(record)
        }
        if not matched:
            return False
        supports.append(matched)
    if set.intersection(*supports):
        return False
    return len(set.union(*supports)) >= 2


def _freeze_selection(
    rows: Sequence[EligibilityRecord],
    *,
    selected_update_policies: frozenset[str] | None = None,
) -> tuple[EligibilityRecord, ...]:
    selected_ids = set()
    case_ranks = {}
    for case_id in sorted({row.case_id for row in rows}):
        eligible = [
            row
            for row in rows
            if row.case_id == case_id and row.executor_eligible
            and (
                selected_update_policies is None
                or row.update_policy in selected_update_policies
            )
        ]
        eligible.sort(
            key=lambda row: (
                hashlib.sha256(str(row.candidate_id).encode()).hexdigest(),
                row.eligibility_id,
            )
        )
        for rank, row in enumerate(
            eligible[:MAX_SELECTED_PER_CASE], start=1
        ):
            assert row.candidate_id is not None
            selected_ids.add(row.eligibility_id)
            case_ranks[row.eligibility_id] = rank
    ordered = sorted(
        (row for row in rows if row.eligibility_id in selected_ids),
        key=lambda row: (
            hashlib.sha256(str(row.candidate_id).encode()).hexdigest(),
            row.eligibility_id,
        ),
    )[:MAX_SELECTED_TOTAL]
    global_ranks = {
        row.eligibility_id: rank for rank, row in enumerate(ordered, start=1)
    }
    return tuple(
        replace(
            row,
            selected_for_executor=row.eligibility_id in global_ranks,
            case_selection_rank=(
                case_ranks.get(row.eligibility_id)
                if row.eligibility_id in global_ranks
                else None
            ),
            global_selection_rank=global_ranks.get(row.eligibility_id),
        )
        for row in rows
    )


def _complete_active_record(
    record: TypedAuthorizationState,
    authorized_issuers: Sequence[str],
) -> bool:
    return (
        record.status is AuthorizationMemoryStatus.ACTIVE
        and record.issuer in authorized_issuers
        and all(getattr(record, field) is not None for field in _REQUIRED_MEMORY_FIELDS)
        and bool(record.allowed_categories)
        and bool(record.source_turn_ids)
    )


def _state_authorizes(
    state: TypedCurrentState,
    transaction: Transaction,
    authorized_issuers: Sequence[str],
) -> bool:
    return any(
        _record_authorizes(record, transaction, authorized_issuers)
        for record in state.authorizations
    )


def _record_authorizes(
    record: TypedAuthorizationState,
    transaction: Transaction,
    authorized_issuers: Sequence[str],
) -> bool:
    if not _complete_active_record(record, authorized_issuers):
        return False
    assert record.allowed_categories is not None
    assert record.max_amount is not None
    assert record.valid_from is not None
    assert record.valid_until is not None
    if any(
        getattr(record, field) != getattr(transaction, field)
        for field in ("grantee", "action", "vendor", "currency")
    ):
        return False
    if (
        transaction.category not in record.allowed_categories
        or transaction.amount > record.max_amount
    ):
        return False
    action_time = _timestamp(transaction.action_time)
    return (
        _timestamp(record.valid_from)
        <= action_time
        < _timestamp(record.valid_until)
    )


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp must include an offset: {value!r}")
    return parsed


def _timestamp_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _hash_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
