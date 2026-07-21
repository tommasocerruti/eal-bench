from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from domains.base import BenchmarkProbe, MemoryArchitecture
from experiments.authorization_memory.challenges import (
    prepare_challenge,
    prepare_challenge_context,
)
from experiments.authorization_memory.langmem_writer import framework_manifest
from experiments.authorization_memory.persistence import (
    content_hash,
    file_hash,
    write_json,
    write_jsonl,
)
from experiments.authorization_memory.pipeline import (
    _evidence_from_artifact,
    calibrate_capacity,
    planned_study_job_identity,
    run_executor_jobs,
)
from experiments.authorization_memory.schemas import (
    LANGMEM_IMPLEMENTATION_ID,
    FrozenEvidence,
    MemoryArtifact,
    MemoryOrigin,
    MemoryState,
    ModelProvenance,
)
from experiments.authorization_memory.study_plan import (
    ExecutorJob,
    PressureSpec,
    StudyExpansion,
    StudyPlan,
    WriterRunBundle,
)
from experiments.authorization_memory.study_engine import (
    validate_study_plan,
)
from eal_bench.llm import load_config

from ..cases import current_ledger, replay_case
from ..challenge import (
    BASELINE_PRESSURE_ID,
    PRESSURE_PROFILE_ID,
    STRONG_PRESSURE_ID,
    distinguishable_preferred_transaction,
    intervention_challenge_context,
    writer_pressure_context,
)
from ..schemas import Transaction
from .interventions import (
    InterventionKind,
    build_faithful_artifact,
    build_controlled_variants,
    faithful_typed_state,
)
from .memory import count_reference_tokens
from .pipeline import (
    AuthorizationCheckpoint,
    CapacityCalibration,
    CapacityTier,
    CaseCapacity,
    CheckpointEvidenceLink,
    build_baseline_evidence,
    freeze_memory_evidence,
)
from .route_support import (
    artifact_from_domain as _artifact,
    evidence_from_domain as _evidence,
    evidence_to_domain as _domain_evidence,
    stable_id as _stable_id,
    standard_writer_specs as _standard_writer_specs,
)
from .schemas import (
    MemoryArchitecture as DomainMemoryArchitecture,
)
from .schemas import MemoryArtifact as DomainMemoryArtifact
from .substantive_overgrant import (
    SourceCheckpointEvidence,
    SourceCheckpointRun,
    build_substantive_overgrant_jobs,
)


_CONTROL_BROADENINGS = {
    InterventionKind.AMOUNT_BROADENING,
    InterventionKind.VALIDITY_EXTENSION,
    InterventionKind.VALIDITY_START_ADVANCE,
    InterventionKind.CATEGORY_BROADENING,
}
_CONTROL_KINDS = {
    *_CONTROL_BROADENINGS,
    InterventionKind.EXACT_REPAIR,
    InterventionKind.SEMANTIC_SHAM,
}
_WRITER_CONDITIONS = (
    "one_shot_text",
    "one_shot_typed",
    "incremental_text",
    "incremental_typed",
)
_WRITER_ARTIFACTS = (
    "fidelity",
    "substantive_eligibility",
    "witnesses",
    "interventions",
    "pressure_source_jobs",
)
_SCIENTIFIC_ROUTE_PRESENTATIONS = {
    "benchmark_v1": "naturalistic_v1",
}


def validate_controls_options(options: Mapping[str, Any]) -> None:
    _require_scientific_route(options, "controls")
    if str(options.get("source_run") or "").strip():
        raise ValueError("controls does not accept --source-run")


def validate_writer_options(options: Mapping[str, Any]) -> None:
    _require_scientific_route(options, "writer")
    if str(options.get("source_run") or "").strip():
        raise ValueError("writer does not accept --source-run")
    architecture = str(options.get("writer_architecture") or "all")
    strategy = str(options.get("writer_strategy") or "all")
    if architecture not in {"all", "typed", "free_text"}:
        raise ValueError(
            "--writer-architecture must be all, typed, or free_text"
        )
    if strategy not in {"all", "one_shot", "incremental"}:
        raise ValueError(
            "--writer-strategy must be all, one_shot, or incremental"
        )


def validate_pressure_options(options: Mapping[str, Any]) -> None:
    _require_scientific_route(options, "pressure")
    if not str(options.get("source_run") or "").strip():
        raise ValueError("pressure requires --source-run from a completed writer route")


def build_controls_plan(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyPlan:
    validate_controls_options(options)
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    tier, capacity_tokens, baselines = _deterministic_baselines(
        domain,
        cases,
        options,
        presentation,
    )
    baseline_evidence = tuple(
        _evidence(item, presentation)
        for item in baselines.evidence
        if item.condition_id != "empty_memory"
    )
    controlled_artifacts: dict[str, MemoryArtifact] = {
        item.memory_id: item
        for item in (
            _artifact(value, presentation) for value in baselines.artifacts
        )
    }
    controlled_evidence: list[FrozenEvidence] = []
    intervention_rows: list[dict[str, Any]] = []
    jobs: list[ExecutorJob] = []
    case_by_id = {case.case_id: case for case in cases}

    for item in baseline_evidence:
        case = case_by_id[item.case_id]
        for probe in domain.corpus.probes(case):
            jobs.append(
                _ordinary_job(
                    case,
                    probe,
                    item,
                    route="controls",
                    evidence_role=item.condition_id,
                )
            )

    for source in baselines.evidence:
        if source.condition_id not in {"faithful_text", "faithful_typed"}:
            continue
        if source.artifact is None:
            raise ValueError(f"{source.evidence_id}: faithful artifact is missing")
        case = case_by_id[source.case_id]
        source_generic_evidence = _evidence(source, presentation)
        build = build_controlled_variants(
            case,
            source.artifact,
            faithful_typed_state(current_ledger(case)),
            count_tokens=count_reference_tokens,
            capacity_tokens=capacity_tokens,
        )
        variant_by_memory_id = {
            variant.artifact.memory_id: variant
            for variant in build.variants
        }
        retained = []
        for variant in build.variants:
            if (
                variant.kind in _CONTROL_BROADENINGS
                or variant.kind is InterventionKind.SEMANTIC_SHAM
            ):
                retained.append(variant)
                continue
            repaired = variant_by_memory_id.get(
                variant.repair_of_memory_id or ""
            )
            if (
                variant.kind is InterventionKind.EXACT_REPAIR
                and repaired is not None
                and repaired.kind in _CONTROL_BROADENINGS
            ):
                retained.append(variant)
        intervention_rows.append(
            {
                "case_id": build.case_id,
                "faithful_memory_id": build.faithful_memory_id,
                "variants": [variant.to_dict() for variant in retained],
                "skipped": [
                    skipped.to_dict()
                    for skipped in build.skipped
                    if skipped.kind in _CONTROL_KINDS
                ],
            }
        )
        pair_by_id = {pair.pair_id: pair for pair in case.probe_pairs}
        for variant in retained:
            domain_evidence = freeze_memory_evidence(
                variant.artifact,
                memory_run_id=source.memory_run_id,
                capacity_tier=tier,
                capacity_tokens=capacity_tokens,
            )
            generic_evidence = _evidence(domain_evidence, presentation)
            generic_artifact = _artifact(variant.artifact, presentation)
            controlled_evidence.append(generic_evidence)
            controlled_artifacts[generic_artifact.memory_id] = generic_artifact
            probe_data = variant.parameters.get("intervention_probe")
            if not isinstance(probe_data, Mapping):
                raise ValueError(
                    f"{variant.intervention_id}: intervention probe is missing"
                )
            pair_id = str(
                variant.parameters.get("probe_source")
                or variant.parameters.get("pair_id")
                or ""
            )
            pair = pair_by_id.get(pair_id)
            transactions = (
                (
                    ("authorized", pair.in_scope.transaction),
                    ("witness", Transaction.from_dict(dict(probe_data))),
                )
                if pair is not None
                else (("witness", Transaction.from_dict(dict(probe_data))),)
            )
            preferred_transaction = Transaction.from_dict(
                dict(probe_data)
            )
            for request_role, transaction in transactions:
                challenge_preferred = preferred_transaction
                if (
                    request_role == "authorized"
                    and domain.conformance.action_arguments(
                        transaction,
                        "submit_order",
                    )
                    == domain.conformance.action_arguments(
                        preferred_transaction,
                        "submit_order",
                    )
                ):
                    challenge_preferred = (
                        distinguishable_preferred_transaction(
                            case,
                            transaction,
                        )
                    )
                probe = BenchmarkProbe(
                    probe_id=(
                        f"{variant.intervention_id}:{request_role}"
                    ),
                    pair_id=variant.intervention_id,
                    dimension=_control_dimension(variant.kind),
                    request_scope=(
                        "in_scope"
                        if request_role == "authorized"
                        else "out_of_scope"
                    ),
                    request=transaction,
                )
                comparison_id = (
                    f"{source.evidence_id}:{variant.intervention_id}"
                    if variant.kind is InterventionKind.SEMANTIC_SHAM
                    else (
                        variant.repair_of_memory_id
                        if variant.kind is InterventionKind.EXACT_REPAIR
                        else generic_artifact.memory_id
                    )
                )
                shared_metadata = {
                    "intervention_id": variant.intervention_id,
                    "intervention_kind": variant.kind.value,
                    "changed_fields": list(variant.changed_fields),
                    "repair_of_memory_id": variant.repair_of_memory_id,
                    "sham_verified": variant.sham_verified,
                    "request_role": request_role,
                    "comparison_id": comparison_id,
                }
                if variant.kind is InterventionKind.SEMANTIC_SHAM:
                    jobs.append(
                        _ordinary_job(
                            case,
                            probe,
                            source_generic_evidence,
                            route="controls",
                            evidence_role="faithful_sham_control",
                            metadata=shared_metadata,
                            challenge_context=intervention_challenge_context(
                                case,
                                requested_transaction=transaction,
                                preferred_transaction=challenge_preferred,
                                candidate_id=variant.intervention_id,
                            ),
                        )
                    )
                jobs.append(
                    _ordinary_job(
                        case,
                        probe,
                        generic_evidence,
                        route="controls",
                        evidence_role=_control_role(variant.kind),
                        metadata=shared_metadata,
                        challenge_context=intervention_challenge_context(
                            case,
                            requested_transaction=transaction,
                            preferred_transaction=challenge_preferred,
                            candidate_id=variant.intervention_id,
                        ),
                    )
                )

    return StudyPlan(
        study_id="controls",
        executor_only=True,
        jobs=tuple(jobs),
        controlled_memories=tuple(controlled_artifacts.values()),
        source_evidence=(
            *baseline_evidence,
            *controlled_evidence,
        ),
        artifact_schemas={"interventions": 2},
        artifact_rows={"interventions": tuple(intervention_rows)},
        metadata={
            "route": "controls",
            "writer_calls": 0,
            "evidence_roles": [
                "full_history",
                "faithful_text",
                "faithful_typed",
                "controlled_broadening",
                "exact_repair",
                "faithful_sham_control",
                "semantic_sham",
            ],
        },
    )


def build_writer_plan(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyPlan:
    validate_writer_options(options)
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    target_ids = _targets(options.get("writer_targets"))
    selected_conditions = _selected_writer_conditions(options)
    all_specs = _standard_writer_specs(
        domain,
        cases,
        presentation=presentation,
        target_ids=target_ids,
        writer_runs=int(options.get("writer_runs", 1)),
        seed=int(options.get("seed", 0)),
    )
    specs = tuple(
        spec
        for spec in all_specs
        if spec.condition_id in selected_conditions
    )
    validation_bundle = _writer_validation_bundle(
        domain,
        cases,
        options,
        presentation,
    )
    zero_validation_bundle = _writer_zero_validation_bundle(
        domain,
        cases,
        options,
        presentation,
    )
    typed_screening_active = any(
        condition.endswith("_typed") for condition in selected_conditions
    )

    def ordinary_jobs(
        selected_domain: Any,
        selected_cases: Sequence[Any],
        evidence: Sequence[FrozenEvidence],
        selected_options: Mapping[str, Any],
    ) -> Sequence[ExecutorJob]:
        del selected_options
        by_case = {
            selected_domain.corpus.case_id(case): case
            for case in selected_cases
        }
        return tuple(
            _ordinary_job(
                by_case[item.case_id],
                probe,
                item,
                route="writer",
                evidence_role="generated_final",
            )
            for item in evidence
            for probe in selected_domain.corpus.probes(by_case[item.case_id])
        )

    validation_evidence = tuple(validation_bundle.evidence)
    ordinary_baseline_jobs = sum(
        len(domain.corpus.probes(spec.case)) for spec in specs
    )
    return StudyPlan(
        study_id="writer",
        writer_chains=specs,
        validation_evidence=validation_evidence,
        validation_writer_bundles=(
            (
                validation_bundle,
                zero_validation_bundle,
            )
            if typed_screening_active
            else (zero_validation_bundle,)
        ),
        job_builder=ordinary_jobs,
        post_writer_builder=_writer_post_builder,
        artifact_schemas={name: 1 for name in _WRITER_ARTIFACTS},
        persist_empty_artifacts=_WRITER_ARTIFACTS,
        metadata={
            "route": "writer",
            "writer_architecture": str(
                options.get("writer_architecture") or "all"
            ),
            "writer_strategy": str(
                options.get("writer_strategy") or "all"
            ),
            "conditions": list(selected_conditions),
            "candidate_cap": 20 if typed_screening_active else 0,
            "selection_uses_executor_behavior": False,
            "offline_writer_fixture_scenarios": [
                "exact_memory",
                "substantive_typed_overgrant",
                "typed_undergrant",
                "failed_update",
                "no_change_update",
                "repair",
                "zero_eligible_overgrant",
            ],
            "planned_ordinary_executor_jobs": ordinary_baseline_jobs,
            "planned_dynamic_executor_jobs_min": 0,
            "planned_dynamic_executor_jobs_max": (
                40 if typed_screening_active else 0
            ),
        },
    )


def build_pressure_plan(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyPlan:
    validate_pressure_options(options)
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    source_path = Path(str(options["source_run"])).expanduser().resolve()
    source = _load_pressure_source(
        domain,
        cases,
        source_path,
        options,
        presentation,
    )
    source_executor_task = str(
        source["manifest"]["executor"].get("task") or ""
    )
    if not source_executor_task:
        raise ValueError("pressure source has no executor task")
    if isinstance(options, dict):
        options["executor_task"] = source_executor_task
    source_rows = source["pressure_source_jobs"]
    writer_baseline_rows = source["writer_baseline_jobs"]
    evidence_by_id = source["evidence"]
    case_by_id = {case.case_id: case for case in cases}
    probe_by_id = {
        (case.case_id, probe.probe_id): probe
        for case in cases
        for probe in domain.corpus.probes(case)
    }
    jobs: list[ExecutorJob] = []
    memories: dict[str, MemoryArtifact] = {}
    evidence: dict[str, FrozenEvidence] = {}
    pair_rows: list[dict[str, Any]] = []

    for row in writer_baseline_rows:
        source_id = str(row["writer_baseline_source_id"])
        item = evidence_by_id[str(row["evidence_id"])]
        case = case_by_id[str(row["case_id"])]
        probe = probe_by_id[(case.case_id, str(row["probe_id"]))]
        prepared = prepare_challenge(
            domain,
            case,
            probe,
            pressure_id=STRONG_PRESSURE_ID,
        )
        if prepared is None:
            raise ValueError(f"{source_id}: challenge adapter is unavailable")
        _validate_strong_pressure_render(source_id, row, prepared)
        job = ExecutorJob(
            job_id=_stable_id(
                "job",
                "pressure",
                "writer_factorial",
                str(row["baseline_trial_id"]),
            ),
            case=case,
            probe=probe,
            evidence=item,
            pressure_id=STRONG_PRESSURE_ID,
            executor_target_id=str(row["executor_target_id"]),
            executor_run_id=int(row["executor_run_id"]),
            executor_seed=int(row["executor_seed"]),
            metadata={
                "route": "pressure",
                "analysis_family": "writer_factorial",
                "source_condition_id": row["condition_id"],
                "evidence_role": "generated_final",
                "baseline_trial_id": row["baseline_trial_id"],
                "baseline_call_id": row["baseline_call_id"],
                "writer_baseline_source_id": source_id,
                "source_run": str(source_path),
                "pressure_intensity": "strong",
            },
        )
        jobs.append(job)
        evidence[item.evidence_id] = item
        memory = source["memories"].get(item.memory_id)
        if memory is not None:
            memories[memory.memory_id] = memory
        identity = planned_study_job_identity(
            domain,
            job,
            study_id="pressure",
            executor_task=source_executor_task,
            target_id=job.executor_target_id,
            executor_run_id=job.executor_run_id,
            seed=job.executor_seed,
            presentation=presentation,
            config=load_config(),
        )
        pair_rows.append(
            {
                "pressure_pair_id": _stable_id(
                    "pressure_pair",
                    "writer_factorial",
                    str(row["baseline_trial_id"]),
                    identity["trial_id"],
                ),
                "analysis_family": "writer_factorial",
                "source_run": str(source_path),
                "writer_baseline_source_id": source_id,
                "candidate_id": None,
                "condition_id": row["condition_id"],
                "evidence_role": "generated_final",
                "request_authorized": row["request_authorized"],
                "request_scope": row["request_scope"],
                "case_id": row["case_id"],
                "probe_id": row["probe_id"],
                "pair_id": row["pair_id"],
                "dimension": row["dimension"],
                "baseline_trial_id": row["baseline_trial_id"],
                "pressured_trial_id": identity["trial_id"],
                "baseline_challenge_hash": row[
                    "baseline_challenge_hash"
                ],
                "pressured_challenge_hash": prepared.rendered_sha256,
                "pressured_challenge_text": prepared.rendered_text,
                "choice_set_hash": prepared.choice_set_sha256,
                "objective_framing": (
                    prepared.pressure.objective_framing
                ),
                "operational_stakes": (
                    prepared.pressure.operational_stakes
                ),
                "alternative_disadvantage": (
                    prepared.pressure.alternative_disadvantage
                ),
            }
        )

    for row in source_rows:
        item = evidence_by_id[str(row["evidence_id"])]
        case = case_by_id[str(row["case_id"])]
        transaction = Transaction.from_dict(dict(row["witness_request"]))
        probe = BenchmarkProbe(
            probe_id=(
                f"pressure:{row['candidate_id']}:{row['evidence_role']}:"
                f"{row['executor_target_id']}:{row['executor_run_id']}"
            ),
            pair_id=str(row["candidate_id"]),
            dimension=str(row.get("witness_dimension") or "natural_overgrant"),
            request_scope="out_of_scope",
            request=transaction,
        )
        challenge = writer_pressure_context(
            case,
            transaction,
            candidate_id=str(row["candidate_id"]),
        )
        prepared = prepare_challenge_context(
            domain,
            challenge,
            pressure_id=STRONG_PRESSURE_ID,
        )
        _validate_strong_pressure_render(
            str(row["pressure_source_job_id"]),
            row,
            prepared,
        )
        job = ExecutorJob(
            job_id=_stable_id(
                "job",
                "pressure",
                str(row["pressure_source_job_id"]),
            ),
            case=case,
            probe=probe,
            evidence=item,
            pressure_id=STRONG_PRESSURE_ID,
            oracle_block_index=int(row["oracle_block_index"]),
            challenge_context=challenge,
            executor_target_id=str(row["executor_target_id"]),
            executor_run_id=int(row["executor_run_id"]),
            executor_seed=int(row["executor_seed"]),
            metadata={
                "route": "pressure",
                "analysis_family": "natural_error_repair",
                "candidate_id": row["candidate_id"],
                "evidence_role": row["evidence_role"],
                "baseline_trial_id": row["baseline_trial_id"],
                "baseline_call_id": row["baseline_call_id"],
                "pressure_source_job_id": row["pressure_source_job_id"],
                "source_run": str(source_path),
                "pressure_intensity": "strong",
            },
        )
        jobs.append(job)
        evidence[item.evidence_id] = item
        memory = source["memories"].get(item.memory_id)
        if memory is not None:
            memories[memory.memory_id] = memory
        identity = planned_study_job_identity(
            domain,
            job,
            study_id="pressure",
            executor_task=source_executor_task,
            target_id=job.executor_target_id,
            executor_run_id=job.executor_run_id,
            seed=job.executor_seed,
            presentation=presentation,
            config=load_config(),
        )
        pair_rows.append(
            {
                "pressure_pair_id": _stable_id(
                    "pressure_pair",
                    "natural_error_repair",
                    str(row["baseline_trial_id"]),
                    identity["trial_id"],
                ),
                "analysis_family": "natural_error_repair",
                "source_run": str(source_path),
                "pressure_source_job_id": row["pressure_source_job_id"],
                "candidate_id": row["candidate_id"],
                "condition_id": item.condition_id,
                "evidence_role": row["evidence_role"],
                "baseline_trial_id": row["baseline_trial_id"],
                "pressured_trial_id": identity["trial_id"],
                "baseline_challenge_hash": row[
                    "baseline_challenge_hash"
                ],
                "pressured_challenge_hash": prepared.rendered_sha256,
                "pressured_challenge_text": prepared.rendered_text,
                "choice_set_hash": prepared.choice_set_sha256,
                "objective_framing": prepared.pressure.objective_framing,
                "operational_stakes": prepared.pressure.operational_stakes,
                "alternative_disadvantage": (
                    prepared.pressure.alternative_disadvantage
                ),
            }
        )
    target_ids = tuple(
        sorted(
            {
                str(row["executor_target_id"])
                for row in (*writer_baseline_rows, *source_rows)
            }
            or set(source["manifest"]["executor"]["targets"])
        )
    )
    if isinstance(options, dict):
        options["executor_targets"] = target_ids
        options["executor_runs"] = int(
            source["manifest"]["executor"]["runs"]
        )
        options["seed"] = int(source["manifest"]["seed"])
    return StudyPlan(
        study_id="pressure",
        executor_only=True,
        jobs=tuple(jobs),
        controlled_memories=tuple(memories.values()),
        source_evidence=tuple(evidence.values()),
        pressure_specs=(
            PressureSpec(
                pressure_id=STRONG_PRESSURE_ID,
                placement="operational_context",
                text="",
                metadata={
                    "pressure_profile": PRESSURE_PROFILE_ID,
                    "pressure_intensity": "strong",
                    "case_specific": True,
                },
                challenge_pressure_id=STRONG_PRESSURE_ID,
            ),
        ),
        artifact_schemas={
            "pressure_pairs": 2,
            "source_pressure_jobs": 1,
            "source_writer_baseline_jobs": 1,
        },
        artifact_rows={
            "pressure_pairs": tuple(pair_rows),
            "source_pressure_jobs": tuple(source_rows),
            "source_writer_baseline_jobs": tuple(writer_baseline_rows),
        },
        persist_empty_artifacts=(
            "pressure_pairs",
            "source_pressure_jobs",
            "source_writer_baseline_jobs",
        ),
        allow_empty_jobs=True,
        metadata={
            "route": "pressure",
            "source_writer_run": str(source_path),
            "source_manifest_sha256": source["manifest_sha256"],
            "source_pressure_job_count": len(source_rows),
            "source_writer_baseline_job_count": len(writer_baseline_rows),
            "writer_factorial_pressure_calls": len(writer_baseline_rows),
            "targeted_error_repair_pressure_calls": len(source_rows),
            "status_detail": (
                "ready"
                if writer_baseline_rows and source_rows
                else (
                    "ready_writer_factorial_no_natural_overgrant"
                    if writer_baseline_rows
                    else (
                        "ready_targeted_only"
                        if source_rows
                        else "contrast_not_estimable_no_writer_baselines"
                    )
                )
            ),
            "writer_calls": 0,
            "baseline_executor_calls": 0,
        },
    )


def validate_pressure_zero_source_fixture(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> Mapping[str, Any]:
    corpus_version = str(options.get("corpus_version"))
    presentation_version = _SCIENTIFIC_ROUTE_PRESENTATIONS.get(
        corpus_version
    )
    if presentation_version is None:
        return {"status": "not_applicable"}
    from experiments.authorization_memory.validation import OfflineLLM

    presentation = domain.get_presentation(presentation_version)
    targets = _targets(options.get("executor_targets"))
    target_id = (
        targets[0]
        if targets
        else load_config().task(
            str(options.get("executor_task") or "executor")
        ).default_target
    )
    if target_id is None:
        raise ValueError("offline pressure fixture requires an executor target")
    source_options = {
        **dict(options),
        "corpus_version": corpus_version,
        "presentation_version": presentation_version,
        "writer_targets": (target_id,),
        "executor_targets": (target_id,),
        "writer_runs": 1,
        "executor_runs": 1,
        "seed": int(options.get("seed", 0)),
    }
    bundle = _writer_zero_validation_bundle(
        domain,
        cases,
        source_options,
        presentation,
    )
    expansion = _writer_post_builder(
        domain,
        cases,
        bundle,
        source_options,
    )
    if (
        expansion.jobs
        or expansion.artifact_rows["pressure_source_jobs"]
    ):
        raise AssertionError(
            "zero-overgrant writer fixture produced targeted pressure jobs"
        )
    ordinary_jobs = tuple(
        _ordinary_job(
            case,
            probe,
            item,
            route="writer",
            evidence_role="generated_final",
        )
        for item in bundle.evidence
        for case in cases
        if case.case_id == item.case_id
        for probe in domain.corpus.probes(case)
    )
    trials, contexts = run_executor_jobs(
        OfflineLLM(),
        domain,
        ordinary_jobs,
        study_id="writer",
        executor_task=str(
            source_options.get("executor_task") or "executor"
        ),
        executor_targets=(target_id,),
        executor_runs=1,
        batch_size=None,
        seed=int(source_options["seed"]),
        presentation=presentation,
    )
    calls = tuple(
        {
            "call_id": context.call_id,
            "request": {
                "messages": list(context.messages),
                "tools": list(context.tools),
                "tool_choice": context.tool_choice,
            },
        }
        for context in contexts
    )
    with TemporaryDirectory(prefix="pressure-zero-source-") as directory:
        source_path = Path(directory)
        rows = {
            "pressure_source_jobs": (),
            "trials": trials,
            "model_contexts": contexts,
            "evidence": bundle.evidence,
            "memories": bundle.memories,
            "calls": calls,
        }
        files: dict[str, dict[str, Any]] = {}
        for name, values in rows.items():
            path = source_path / f"{name}.jsonl"
            count = write_jsonl(path, values)
            files[name] = {
                "path": path.name,
                "sha256": file_hash(path),
                "rows": count,
            }
        write_json(
            source_path / "manifest.json",
            {
                "status": "completed",
                "study": "writer",
                "domain_id": domain.domain_id,
                "memory_implementation_id": (
                    framework_manifest(domain)["memory_implementation_id"]
                ),
                "memory_implementation_hash": (
                    framework_manifest(domain)["memory_implementation_hash"]
                ),
                "corpus_version": corpus_version,
                "corpus_provenance": dict(
                    domain.corpus.provenance(corpus_version)
                ),
                "case_ids": [
                    domain.corpus.case_id(case) for case in cases
                ],
                "presentation_hash": content_hash(
                    presentation.to_dict()
                ),
                "executor": {
                    "task": str(
                        source_options.get("executor_task") or "executor"
                    ),
                    "targets": [target_id],
                    "runs": 1,
                },
                "writer": {
                    "memory_implementation_hash": framework_manifest(domain)[
                        "memory_implementation_hash"
                    ]
                },
                "conditions": sorted(
                    {item.condition_id for item in bundle.evidence}
                ),
                "planned_ordinary_executor_jobs": len(ordinary_jobs),
                "seed": int(source_options["seed"]),
                "files": files,
            },
        )
        fixture_options = {
            **source_options,
            "source_run": str(source_path),
            "writer_targets": (),
            "executor_targets": (),
        }
        plan = build_pressure_plan(
            domain,
            cases,
            fixture_options,
        )
        validation = validate_study_plan(
            domain,
            cases,
            plan,
            fixture_options,
        )
        pressured_trials, pressured_contexts = run_executor_jobs(
            OfflineLLM(),
            domain,
            plan.jobs,
            study_id="pressure",
            executor_task=str(fixture_options["executor_task"]),
            executor_targets=_targets(
                fixture_options["executor_targets"]
            ),
            executor_runs=int(fixture_options["executor_runs"]),
            batch_size=None,
            seed=int(fixture_options["seed"]),
            presentation=presentation,
            pressure_specs=plan.pressure_specs,
        )
    if (
        len(plan.jobs) != len(ordinary_jobs)
        or len(pressured_trials) != len(ordinary_jobs)
        or len(pressured_contexts) != len(ordinary_jobs)
        or any(
            context.metadata["challenge"]["pressure_id"]
            != STRONG_PRESSURE_ID
            for context in pressured_contexts
        )
        or validation["call_plan"]["writer_calls_maximum"] != 0
        or validation["call_plan"]["scheduled_calls_maximum"]
        != len(ordinary_jobs)
    ):
        raise AssertionError(
            "zero-overgrant pressure fixture did not preserve the full "
            "writer-factorial comparison"
        )
    return {
        "status": "passed",
        "source_writer_baseline_jobs": len(ordinary_jobs),
        "source_pressure_jobs": 0,
        "executor_jobs": len(plan.jobs),
        "scheduled_calls_maximum": len(plan.jobs),
        "status_detail": plan.metadata["status_detail"],
    }


def validate_pressure_linked_source_fixture(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> Mapping[str, Any]:
    corpus_version = str(options.get("corpus_version"))
    presentation_version = _SCIENTIFIC_ROUTE_PRESENTATIONS.get(
        corpus_version
    )
    if presentation_version is None:
        return {"status": "not_applicable"}
    from experiments.authorization_memory.validation import OfflineLLM

    presentation = domain.get_presentation(presentation_version)
    targets = _targets(options.get("executor_targets"))
    target_id = (
        targets[0]
        if targets
        else load_config().task(
            str(options.get("executor_task") or "executor")
        ).default_target
    )
    if target_id is None:
        raise ValueError("offline pressure fixture requires an executor target")
    fixture_options = {
        **dict(options),
        "corpus_version": corpus_version,
        "presentation_version": presentation_version,
        "writer_targets": (target_id,),
        "executor_targets": (target_id,),
        "writer_runs": 1,
        "executor_runs": 1,
        "seed": int(options.get("seed", 0)),
    }
    bundle = _writer_validation_bundle(
        domain,
        cases,
        fixture_options,
        presentation,
    )
    expansion = _writer_post_builder(
        domain,
        cases,
        bundle,
        fixture_options,
    )
    if (
        len(expansion.jobs) != 2
        or len(expansion.artifact_rows["pressure_source_jobs"]) != 2
    ):
        raise AssertionError(
            "linked pressure fixture did not create one natural/repair pair"
        )
    ordinary_jobs = tuple(
        _ordinary_job(
            case,
            probe,
            item,
            route="writer",
            evidence_role="generated_final",
        )
        for item in bundle.evidence
        for case in cases
        if case.case_id == item.case_id
        for probe in domain.corpus.probes(case)
    )
    source_jobs = (*ordinary_jobs, *expansion.jobs)
    trials, contexts = run_executor_jobs(
        OfflineLLM(),
        domain,
        source_jobs,
        study_id="writer",
        executor_task=str(
            fixture_options.get("executor_task") or "executor"
        ),
        executor_targets=(target_id,),
        executor_runs=1,
        batch_size=None,
        seed=int(fixture_options["seed"]),
        presentation=presentation,
    )
    memories = _unique_artifacts(
        (*bundle.memories, *expansion.additional_memories),
        key="memory_id",
    )
    evidence = _unique_artifacts(
        (*bundle.evidence, *expansion.additional_evidence),
        key="evidence_id",
    )
    calls = tuple(
        {
            "call_id": context.call_id,
            "request": {
                "messages": list(context.messages),
                "tools": list(context.tools),
                "tool_choice": context.tool_choice,
            },
        }
        for context in contexts
    )
    with TemporaryDirectory(prefix="pressure-linked-source-") as directory:
        source_path = Path(directory)
        rows = {
            "pressure_source_jobs": expansion.artifact_rows[
                "pressure_source_jobs"
            ],
            "trials": trials,
            "model_contexts": contexts,
            "evidence": evidence,
            "memories": memories,
            "calls": calls,
        }
        files: dict[str, dict[str, Any]] = {}
        for name, values in rows.items():
            path = source_path / f"{name}.jsonl"
            count = write_jsonl(path, values)
            files[name] = {
                "path": path.name,
                "sha256": file_hash(path),
                "rows": count,
            }
        write_json(
            source_path / "manifest.json",
            {
                "status": "completed",
                "study": "writer",
                "domain_id": domain.domain_id,
                "memory_implementation_id": (
                    framework_manifest(domain)["memory_implementation_id"]
                ),
                "memory_implementation_hash": (
                    framework_manifest(domain)["memory_implementation_hash"]
                ),
                "corpus_version": corpus_version,
                "corpus_provenance": dict(
                    domain.corpus.provenance(corpus_version)
                ),
                "case_ids": [
                    domain.corpus.case_id(case) for case in cases
                ],
                "presentation_hash": content_hash(
                    presentation.to_dict()
                ),
                "executor": {
                    "task": str(
                        fixture_options.get("executor_task") or "executor"
                    ),
                    "targets": [target_id],
                    "runs": 1,
                },
                "writer": {
                    "memory_implementation_hash": framework_manifest(domain)[
                        "memory_implementation_hash"
                    ]
                },
                "conditions": [
                    item.condition_id for item in bundle.evidence
                ],
                "seed": int(fixture_options["seed"]),
                "files": files,
            },
        )
        pressure_options = {
            **fixture_options,
            "source_run": str(source_path),
            "writer_targets": (),
            "executor_targets": (),
        }
        plan = build_pressure_plan(
            domain,
            cases,
            pressure_options,
        )
        validation = validate_study_plan(
            domain,
            cases,
            plan,
            pressure_options,
        )
        pressured_trials, pressured_contexts = run_executor_jobs(
            OfflineLLM(),
            domain,
            plan.jobs,
            study_id="pressure",
            executor_task=str(pressure_options["executor_task"]),
            executor_targets=_targets(
                pressure_options["executor_targets"]
            ),
            executor_runs=int(pressure_options["executor_runs"]),
            batch_size=None,
            seed=int(pressure_options["seed"]),
            presentation=presentation,
            pressure_specs=plan.pressure_specs,
        )
    if (
        len(plan.jobs) != len(ordinary_jobs) + 2
        or len(pressured_trials) != len(plan.jobs)
        or len(pressured_contexts) != len(plan.jobs)
        or any(
            context.metadata["challenge"]["pressure_id"]
            != STRONG_PRESSURE_ID
            for context in pressured_contexts
        )
        or validation["call_plan"]["writer_calls_maximum"] != 0
        or validation["call_plan"]["scheduled_calls_maximum"]
        != len(plan.jobs)
        or len(
            plan.artifact_rows["source_writer_baseline_jobs"]
        )
        != len(ordinary_jobs)
    ):
        raise AssertionError(
            "linked pressure fixture did not schedule the frozen writer "
            "factorial plus the natural/repair pair"
        )
    return {
        "status": "passed",
        "source_writer_baseline_jobs": len(ordinary_jobs),
        "source_pressure_jobs": 2,
        "saved_baseline_calls": len(source_jobs),
        "new_writer_factorial_calls": len(ordinary_jobs),
        "new_targeted_calls": 2,
        "new_pressure_calls": len(plan.jobs),
        "writer_calls": 0,
    }


def _validate_strong_pressure_render(
    source_id: str,
    row: Mapping[str, Any],
    prepared: Any,
) -> None:
    if (
        prepared.pressure.pressure_id != STRONG_PRESSURE_ID
        or prepared.choice_set_sha256 != row["choice_set_hash"]
    ):
        raise ValueError(f"{source_id}: pressure changed the frozen choice set")
    expected = str(row["baseline_challenge_text"])
    addition = prepared.pressure.addition.strip()
    if addition:
        expected += "\n\nCurrent business priority\n" + addition
    if prepared.rendered_text != expected:
        raise ValueError(
            f"{source_id}: pressure differs outside the registered addition"
        )


def _load_pressure_source(
    domain: Any,
    cases: Sequence[Any],
    source_path: Path,
    options: Mapping[str, Any],
    presentation: Any,
) -> dict[str, Any]:
    manifest_path = source_path / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"writer source run has no manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_adoption") is not None:
        from ..release_adoption import load_adopted_pressure_source

        return load_adopted_pressure_source(
            domain=domain,
            cases=cases,
            source_path=source_path,
            options=options,
            presentation=presentation,
        )
    if manifest.get("status") != "completed":
        raise ValueError("pressure source writer run is not completed")
    if manifest.get("study") != "writer":
        raise ValueError("pressure source run must use study writer")
    if manifest.get("domain_id") != domain.domain_id:
        raise ValueError("pressure source run uses another domain")
    implementation = framework_manifest(domain)
    if (
        manifest.get("memory_implementation_id")
        != implementation["memory_implementation_id"]
        or manifest.get("memory_implementation_hash")
        != implementation["memory_implementation_hash"]
        or manifest.get("writer", {}).get("memory_implementation_hash")
        != implementation["memory_implementation_hash"]
    ):
        raise ValueError("pressure source memory implementation differs")
    if manifest.get("corpus_version") != options["corpus_version"]:
        raise ValueError("pressure source corpus version differs")
    if manifest.get("presentation_hash") != content_hash(
        presentation.to_dict()
    ):
        raise ValueError("pressure source presentation differs")
    current_provenance = dict(
        domain.corpus.provenance(str(options["corpus_version"]))
    )
    if manifest.get("corpus_provenance") != current_provenance:
        raise ValueError("pressure source corpus provenance differs")
    current_case_ids = [case.case_id for case in cases]
    if manifest.get("case_ids") != current_case_ids:
        raise ValueError("pressure source case selection differs")
    required = {
        "pressure_source_jobs",
        "trials",
        "model_contexts",
        "evidence",
        "memories",
        "calls",
    }
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("pressure source manifest has no file inventory")
    missing = sorted(required - set(files))
    if missing:
        raise ValueError(
            "pressure source is missing artifacts: " + ", ".join(missing)
        )
    loaded: dict[str, list[dict[str, Any]]] = {}
    for name in required:
        entry = files[name]
        if not isinstance(entry, Mapping):
            raise ValueError(f"pressure source file entry {name!r} is invalid")
        path = source_path / str(entry["path"])
        if not path.is_file() or file_hash(path) != entry.get("sha256"):
            raise ValueError(f"pressure source artifact {name!r} failed hashing")
        loaded[name] = _load_jsonl(path)
    calls = loaded["calls"]
    memories = {
        row["memory_id"]: _memory_from_row(row)
        for row in loaded["memories"]
    }
    evidence = {
        row["evidence_id"]: _evidence_from_row(row)
        for row in loaded["evidence"]
    }
    trials = _unique_by(
        loaded["trials"],
        lambda row: str(row["metadata"]["core"]["trial_id"]),
        "source trial",
    )
    contexts = _unique_by(
        (
            row
            for row in loaded["model_contexts"]
            if row.get("stage") == "executor"
        ),
        lambda row: str(row["trial_id"]),
        "source executor context",
    )
    calls_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        if call.get("call_id") is not None:
            calls_by_id[str(call["call_id"])].append(call)
    source_job_ids = [
        str(row["pressure_source_job_id"])
        for row in loaded["pressure_source_jobs"]
    ]
    if len(source_job_ids) != len(set(source_job_ids)):
        raise ValueError("pressure source job IDs are not unique")
    pair_roles: dict[tuple[str, str, int, int], list[str]] = defaultdict(list)
    case_by_id = {case.case_id: case for case in cases}
    config = load_config()
    source_executor_task = str(
        manifest.get("executor", {}).get("task") or ""
    )
    if not source_executor_task:
        raise ValueError("pressure source has no executor task")
    presentation_hash = content_hash(presentation.to_dict())
    corpus_provenance = dict(
        domain.corpus.provenance(str(options["corpus_version"]))
    )
    for row in loaded["pressure_source_jobs"]:
        source_id = str(row["pressure_source_job_id"])
        item = evidence.get(str(row["evidence_id"]))
        if item is None or item.content_hash != row["evidence_hash"]:
            raise ValueError(f"{source_id}: evidence link is invalid")
        if (
            row.get("presentation_id") != presentation.presentation_id
            or row.get("presentation_hash") != presentation_hash
            or item.presentation_id != presentation.presentation_id
            or item.presentation_hash != presentation_hash
            or row.get("corpus_version") != options["corpus_version"]
            or row.get("corpus_provenance") != corpus_provenance
        ):
            raise ValueError(
                f"{source_id}: corpus or presentation lineage is invalid"
            )
        memory = memories.get(str(row["memory_id"]))
        if (
            memory is None
            or item.memory_id != memory.memory_id
            or memory.content_hash != row["evidence_hash"]
            or memory.content_hash != content_hash(memory.payload)
        ):
            raise ValueError(f"{source_id}: memory link is invalid")
        writer = item.writer
        if (
            item.memory_id != row["memory_id"]
            or item.memory_run_id != row["memory_run_id"]
            or item.writer_seed != row["writer_seed"]
            or item.memory_implementation_id
            != row["memory_implementation_id"]
            or item.memory_implementation_hash
            != row["memory_implementation_hash"]
            or item.profile_id != row["profile_id"]
            or item.source_attempt_id != row["source_attempt_id"]
            or (
                writer.target_id if writer is not None else None
            )
            != row["writer_target_id"]
            or (
                writer.provider if writer is not None else None
            )
            != row["writer_provider"]
            or (
                writer.requested_model if writer is not None else None
            )
            != row["writer_requested_model"]
            or (
                writer.resolved_model if writer is not None else None
            )
            != row["writer_resolved_model"]
            or (
                writer.response_model if writer is not None else None
            )
            != row["writer_response_model"]
            or (
                dict(writer.effective_parameters)
                if writer is not None
                else {}
            )
            != row["writer_effective_parameters"]
        ):
            raise ValueError(f"{source_id}: writer lineage is invalid")
        if content_hash(row["witness_request"]) != row["witness_request_hash"]:
            raise ValueError(f"{source_id}: witness hash is invalid")
        baseline_challenge = prepare_challenge_context(
            domain,
            writer_pressure_context(
                case_by_id[str(row["case_id"])],
                Transaction.from_dict(dict(row["witness_request"])),
                candidate_id=str(row["candidate_id"]),
            ),
            pressure_id=BASELINE_PRESSURE_ID,
        )
        if (
            baseline_challenge.choice_set_sha256
            != row["choice_set_hash"]
            or baseline_challenge.rendered_sha256
            != row["baseline_challenge_hash"]
            or baseline_challenge.rendered_text
            != row["baseline_challenge_text"]
            or baseline_challenge.pressure.objective_framing
            != row["objective_framing"]
            or baseline_challenge.pressure.operational_stakes
            != row["operational_stakes"]
            or baseline_challenge.pressure.alternative_disadvantage
            != row["alternative_disadvantage"]
        ):
            raise ValueError(
                f"{source_id}: frozen baseline challenge changed"
            )
        trial = trials.get(str(row["baseline_trial_id"]))
        if trial is None:
            raise ValueError(f"{source_id}: baseline trial is missing")
        context = contexts.get(str(row["baseline_trial_id"]))
        if (
            context is None
            or context.get("call_id") != row["baseline_call_id"]
        ):
            raise ValueError(f"{source_id}: baseline context lineage is invalid")
        matching_calls = calls_by_id[str(row["baseline_call_id"])]
        matching_call = _successful_source_call(
            matching_calls,
            source_id=source_id,
            expected_context_hash=str(context.get("content_hash") or ""),
        )
        trial_core = trial.get("metadata", {}).get("core", {})
        if (
            trial_core.get("call_id") != row["baseline_call_id"]
            or trial_core.get("model_context_id")
            != context.get("context_id")
            or _source_call_context_hash(matching_call)
            != context.get("content_hash")
        ):
            raise ValueError(
                f"{source_id}: baseline call/context hash linkage is invalid"
            )
        if (
            trial.get("evidence_id") != row["evidence_id"]
            or trial.get("case_id") != row["case_id"]
        ):
            raise ValueError(f"{source_id}: baseline trial linkage is invalid")
        trial_challenge = (
            trial.get("metadata", {})
            .get("domain", {})
            .get("challenge", {})
        )
        context_challenge = context.get("metadata", {}).get(
            "challenge", {}
        )
        for challenge in (trial_challenge, context_challenge):
            if (
                challenge.get("choice_set_sha256")
                != row["choice_set_hash"]
                or challenge.get("rendered_text_sha256")
                != row["baseline_challenge_hash"]
            ):
                raise ValueError(
                    f"{source_id}: baseline challenge linkage is invalid"
                )
        route = planned_study_job_identity(
            domain,
            ExecutorJob(
                job_id=str(row["baseline_job_id"]),
                case=case_by_id[str(row["case_id"])],
                probe=BenchmarkProbe(
                    probe_id=str(trial["probe_id"]),
                    pair_id=str(row["candidate_id"]),
                    dimension="natural_overgrant",
                    request_scope="out_of_scope",
                    request=Transaction.from_dict(
                        dict(row["witness_request"])
                    ),
                ),
                evidence=item,
            ),
            study_id="writer",
            executor_task=source_executor_task,
            target_id=str(row["executor_target_id"]),
            executor_run_id=int(row["executor_run_id"]),
            seed=int(row["executor_seed"]),
            presentation=presentation,
            config=config,
        )
        for key in (
            "provider",
            "requested_model",
            "resolved_model",
            "effective_parameters",
        ):
            expected = row[
                f"executor_{key}"
                if key != "effective_parameters"
                else "executor_effective_parameters"
            ]
            if route[key] != expected:
                raise ValueError(
                    f"{source_id}: executor route or parameters changed"
                )
        if (
            route["trial_id"] != row["baseline_trial_id"]
            or route["call_id"] != row["baseline_call_id"]
        ):
            raise ValueError(
                f"{source_id}: planned baseline identity changed"
            )
        pair_roles[
            (
                str(row["candidate_id"]),
                str(row["executor_target_id"]),
                int(row["executor_run_id"]),
                int(row["executor_seed"]),
            )
        ].append(str(row["evidence_role"]))
    for key, roles in pair_roles.items():
        if sorted(roles) != ["exact_repair", "natural_error"]:
            raise ValueError(
                f"pressure source causal pair {key!r} has roles {sorted(roles)}"
            )
    writer_baseline_jobs = _validated_writer_baseline_rows(
        domain=domain,
        cases=cases,
        manifest=manifest,
        presentation=presentation,
        memories=memories,
        evidence=evidence,
        trials=trials,
        contexts=contexts,
        calls_by_id=calls_by_id,
        executor_task=source_executor_task,
        config=config,
    )
    return {
        "manifest": manifest,
        "manifest_sha256": file_hash(manifest_path),
        "pressure_source_jobs": loaded["pressure_source_jobs"],
        "writer_baseline_jobs": writer_baseline_jobs,
        "memories": memories,
        "evidence": evidence,
    }


def _validated_writer_baseline_rows(
    *,
    domain: Any,
    cases: Sequence[Any],
    manifest: Mapping[str, Any],
    presentation: Any,
    memories: Mapping[str, MemoryArtifact],
    evidence: Mapping[str, FrozenEvidence],
    trials: Mapping[str, dict[str, Any]],
    contexts: Mapping[str, dict[str, Any]],
    calls_by_id: Mapping[str, Sequence[dict[str, Any]]],
    executor_task: str,
    config: Any,
) -> tuple[dict[str, Any], ...]:
    case_by_id = {case.case_id: case for case in cases}
    probe_by_id = {
        (case.case_id, probe.probe_id): probe
        for case in cases
        for probe in domain.corpus.probes(case)
    }
    declared_conditions = {
        str(condition) for condition in manifest.get("conditions", ())
    }
    selected = []
    for trial_id, trial in sorted(trials.items()):
        study = trial.get("metadata", {}).get("study", {})
        if study.get("evidence_role") != "generated_final":
            continue
        source_id = _stable_id("writer_baseline_source", trial_id)
        if (
            study.get("route") != "writer"
            or study.get("study_id") != "writer"
            or study.get("pressure_id") is not None
            or trial.get("provider_error") is not None
            or trial.get("parseable") is not True
        ):
            raise ValueError(
                f"{source_id}: ordinary writer baseline trial is invalid"
            )
        case_id = str(trial["case_id"])
        probe_id = str(trial["probe_id"])
        case = case_by_id.get(case_id)
        probe = probe_by_id.get((case_id, probe_id))
        if case is None or probe is None:
            raise ValueError(
                f"{source_id}: source case or probe is unavailable"
            )
        condition_id = str(trial["condition_id"])
        if declared_conditions and condition_id not in declared_conditions:
            raise ValueError(
                f"{source_id}: source condition is not declared"
            )
        item = evidence.get(str(trial["evidence_id"]))
        if (
            item is None
            or item.case_id != case_id
            or item.condition_id != condition_id
            or item.memory_id != trial.get("memory_id")
        ):
            raise ValueError(f"{source_id}: evidence lineage is invalid")
        memory = memories.get(str(item.memory_id))
        if (
            memory is None
            or memory.case_id != case_id
            or memory.condition_id != condition_id
            or memory.content_hash != item.content_hash
            or memory.content_hash != content_hash(memory.payload)
        ):
            raise ValueError(f"{source_id}: memory lineage is invalid")
        core = trial.get("metadata", {}).get("core", {})
        call_id = str(core.get("call_id") or "")
        context = contexts.get(trial_id)
        if (
            not call_id
            or context is None
            or context.get("call_id") != call_id
            or context.get("context_id") != core.get("model_context_id")
            or context.get("case_id") != case_id
            or context.get("condition_id") != condition_id
            or context.get("evidence_id") != item.evidence_id
            or context.get("memory_id") != item.memory_id
        ):
            raise ValueError(
                f"{source_id}: baseline context lineage is invalid"
            )
        matching_call = _successful_source_call(
            calls_by_id.get(call_id, ()),
            source_id=source_id,
            expected_context_hash=str(context.get("content_hash") or ""),
        )
        if _source_call_context_hash(matching_call) != context.get(
            "content_hash"
        ):
            raise ValueError(
                f"{source_id}: baseline call/context hash linkage is invalid"
            )
        baseline = prepare_challenge(
            domain,
            case,
            probe,
            pressure_id=BASELINE_PRESSURE_ID,
        )
        trial_challenge = (
            trial.get("metadata", {})
            .get("domain", {})
            .get("challenge", {})
        )
        context_challenge = context.get("metadata", {}).get(
            "challenge", {}
        )
        for challenge in (trial_challenge, context_challenge):
            if (
                challenge.get("pressure_id") != BASELINE_PRESSURE_ID
                or challenge.get("choice_set_sha256")
                != baseline.choice_set_sha256
                or challenge.get("rendered_text_sha256")
                != baseline.rendered_sha256
                or challenge.get("rendered_text") != baseline.rendered_text
            ):
                raise ValueError(
                    f"{source_id}: frozen baseline challenge changed"
                )
        baseline_job = _ordinary_job(
            case,
            probe,
            item,
            route="writer",
            evidence_role="generated_final",
        )
        if baseline_job.job_id != study.get("job_id"):
            raise ValueError(
                f"{source_id}: baseline writer job identity changed"
            )
        executor = trial.get("executor", {})
        target_id = str(executor.get("target_id") or "")
        run_id = int(trial["executor_run_id"])
        route_seed = int(trial["seed"])
        route = planned_study_job_identity(
            domain,
            baseline_job,
            study_id="writer",
            executor_task=executor_task,
            target_id=target_id,
            executor_run_id=run_id,
            seed=route_seed,
            presentation=presentation,
            config=config,
        )
        if (
            route["trial_id"] != trial_id
            or route["call_id"] != call_id
            or route["provider"] != executor.get("provider")
            or route["requested_model"] != executor.get("requested_model")
            or route["resolved_model"] != executor.get("resolved_model")
            or route["effective_parameters"]
            != executor.get("effective_parameters")
        ):
            raise ValueError(
                f"{source_id}: executor route or parameters changed"
            )
        if (
            bool(trial["request_authorized"])
            != (
                domain.executor.oracle(case, probe.request).authorized
            )
            or core.get("pair_id") != probe.pair_id
            or core.get("dimension") != probe.dimension
            or core.get("request_scope") != probe.request_scope
        ):
            raise ValueError(
                f"{source_id}: request or oracle lineage is invalid"
            )
        selected.append(
            {
                "writer_baseline_source_id": source_id,
                "case_id": case_id,
                "probe_id": probe_id,
                "pair_id": probe.pair_id,
                "dimension": probe.dimension,
                "request_scope": probe.request_scope,
                "request_authorized": bool(trial["request_authorized"]),
                "condition_id": condition_id,
                "evidence_id": item.evidence_id,
                "evidence_hash": item.content_hash,
                "memory_id": item.memory_id,
                "memory_hash": memory.content_hash,
                "baseline_job_id": baseline_job.job_id,
                "baseline_trial_id": trial_id,
                "baseline_call_id": call_id,
                "baseline_context_id": context["context_id"],
                "baseline_context_hash": context["content_hash"],
                "baseline_challenge_text": baseline.rendered_text,
                "baseline_challenge_hash": baseline.rendered_sha256,
                "choice_set_hash": baseline.choice_set_sha256,
                "executor_target_id": target_id,
                "executor_run_id": run_id,
                "executor_seed": route_seed,
                "executor_provider": route["provider"],
                "executor_requested_model": route["requested_model"],
                "executor_resolved_model": route["resolved_model"],
                "executor_effective_parameters": route[
                    "effective_parameters"
                ],
            }
        )
    observed_conditions = {row["condition_id"] for row in selected}
    if selected and observed_conditions != declared_conditions:
        raise ValueError(
            "pressure source ordinary baselines do not cover every declared "
            "writer condition"
        )
    expected_count = manifest.get("planned_ordinary_executor_jobs")
    if expected_count is not None and len(selected) != int(expected_count):
        raise ValueError(
            "pressure source ordinary baseline count differs from the "
            "writer plan"
        )
    condition_counts = {
        condition: sum(
            row["condition_id"] == condition for row in selected
        )
        for condition in observed_conditions
    }
    if len(set(condition_counts.values())) > 1:
        raise ValueError(
            "pressure source writer conditions have unmatched baseline "
            "choice sets"
        )
    return tuple(selected)


def _successful_source_call(
    calls: Sequence[dict[str, Any]],
    *,
    source_id: str,
    expected_context_hash: str,
) -> dict[str, Any]:
    successful = [call for call in calls if call.get("error") is None]
    if len(successful) != 1 or not calls:
        raise ValueError(f"{source_id}: baseline call lineage is invalid")
    if any(
        _source_call_context_hash(call) != expected_context_hash
        for call in calls
    ):
        raise ValueError(
            f"{source_id}: baseline retry changed the model-visible context"
        )
    return successful[0]


def _memory_from_row(row: Mapping[str, Any]) -> MemoryArtifact:
    writer = _provenance_from_row(row.get("writer"))
    return MemoryArtifact(
        memory_id=str(row["memory_id"]),
        parent_memory_id=row.get("parent_memory_id"),
        chain_id=str(row["chain_id"]),
        domain_id=str(row["domain_id"]),
        case_id=str(row["case_id"]),
        condition_id=str(row["condition_id"]),
        block_index=int(row["block_index"]),
        writer_run_id=row.get("writer_run_id"),
        writer_seed=row.get("writer_seed"),
        writer=writer,
        architecture=MemoryArchitecture(str(row["architecture"])),
        origin=MemoryOrigin(str(row["origin"])),
        payload_schema_id=row.get("payload_schema_id"),
        payload_schema_version=row.get("payload_schema_version"),
        payload=row["payload"],
        reference_tokens=int(row["reference_tokens"]),
        reference_tokenizer=str(row["reference_tokenizer"]),
        content_hash=str(row["content_hash"]),
        memory_implementation_id=row.get("memory_implementation_id"),
        memory_implementation_hash=row.get("memory_implementation_hash"),
        profile_id=row.get("profile_id"),
        source_attempt_id=row.get("source_attempt_id"),
        framework_run_ids=tuple(row.get("framework_run_ids", ())),
        framework=dict(row.get("framework", {})),
        presentation_id=str(row["presentation_id"]),
        presentation_hash=row.get("presentation_hash"),
    )


def _evidence_from_row(row: Mapping[str, Any]) -> FrozenEvidence:
    architecture = row.get("architecture")
    return FrozenEvidence(
        evidence_id=str(row["evidence_id"]),
        domain_id=str(row["domain_id"]),
        case_id=str(row["case_id"]),
        condition_id=str(row["condition_id"]),
        memory_run_id=int(row["memory_run_id"]),
        writer_seed=row.get("writer_seed"),
        writer=_provenance_from_row(row.get("writer")),
        architecture=(
            MemoryArchitecture(str(architecture))
            if architecture is not None
            else None
        ),
        memory_id=row.get("memory_id"),
        payload=row.get("payload"),
        source_history=row.get("source_history"),
        content_hash=str(row["content_hash"]),
        memory_implementation_id=row.get("memory_implementation_id"),
        memory_implementation_hash=row.get("memory_implementation_hash"),
        profile_id=row.get("profile_id"),
        source_attempt_id=row.get("source_attempt_id"),
        presentation_id=str(row["presentation_id"]),
        presentation_hash=row.get("presentation_hash"),
    )


def _provenance_from_row(value: Any) -> ModelProvenance | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("model provenance must be an object or null")
    return ModelProvenance(
        target_id=value.get("target_id"),
        provider=value.get("provider"),
        requested_model=value.get("requested_model"),
        resolved_model=value.get("resolved_model"),
        response_model=value.get("response_model"),
        effective_parameters=dict(value.get("effective_parameters", {})),
    )


def _unique_by(
    rows: Iterable[dict[str, Any]],
    key: Any,
    label: str,
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        identity = key(row)
        if identity in selected:
            raise ValueError(f"duplicate {label} ID {identity!r}")
        selected[identity] = row
    return selected


def _unique_artifacts(
    rows: Iterable[Any],
    *,
    key: str,
) -> tuple[Any, ...]:
    selected: dict[str, Any] = {}
    for row in rows:
        identity = str(getattr(row, key))
        prior = selected.setdefault(identity, row)
        if prior != row:
            raise ValueError(f"{key} collision: {identity}")
    return tuple(selected.values())


def _source_call_context_hash(record: Mapping[str, Any]) -> str:
    request = record.get("request")
    if not isinstance(request, Mapping):
        raise ValueError("source call row has no request object")
    messages = request.get("messages")
    if not isinstance(messages, list):
        raise ValueError("source call request has no message sequence")
    params = request.get("params")
    tools = request.get("tools")
    if tools is None and isinstance(params, Mapping):
        tools = params.get("tools")
    if tools is None:
        tools = []
    if not isinstance(tools, list):
        raise ValueError("source call request tools must be an array")
    tool_choice = request.get("tool_choice")
    if tool_choice is None and isinstance(params, Mapping):
        tool_choice = params.get("tool_choice")
    return content_hash(
        {
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
        }
    )


def _writer_post_builder(
    domain: Any,
    cases: Sequence[Any],
    bundle: WriterRunBundle,
    options: Mapping[str, Any],
) -> StudyExpansion:
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    source = _checkpoint_source(domain, cases, bundle, options)
    substantive = build_substantive_overgrant_jobs(
        cases,
        source,
        selected_update_policies=frozenset({"bounded_repair"}),
    )
    selected_jobs = [
        item
        for item in substantive.jobs
        if item.probe.metadata.get("evidence_role")
        in {"natural_error", "exact_repair"}
        and item.probe.metadata.get("request_role") == "witness"
    ]
    by_case = {case.case_id: case for case in cases}
    jobs: list[ExecutorJob] = []
    generic_evidence: dict[str, FrozenEvidence] = {}
    generic_memories: dict[str, MemoryArtifact] = {}
    source_memories = {
        memory.memory_id: memory for memory in bundle.memories
    }
    for item in selected_jobs:
        evidence = _evidence(item.evidence, presentation)
        case = by_case[item.probe.case_id]
        probe = BenchmarkProbe(
            probe_id=item.probe.probe_name,
            pair_id=item.probe.pair_id,
            dimension=item.probe.dimension,
            request_scope=item.probe.request_scope,
            request=item.probe.transaction,
        )
        candidate_id = str(item.probe.metadata["candidate_id"])
        jobs.append(
            ExecutorJob(
                job_id=_stable_id(
                    "job",
                    "writer",
                    evidence.evidence_id,
                    probe.probe_id,
                ),
                case=case,
                probe=probe,
                evidence=evidence,
                oracle_block_index=item.probe.oracle_block_index,
                challenge_context=writer_pressure_context(
                    case,
                    item.probe.transaction,
                    candidate_id=candidate_id,
                ),
                metadata={
                    **dict(item.probe.metadata),
                    "route": "writer",
                    "pressure_intensity": "baseline",
                },
            )
        )
        generic_evidence[evidence.evidence_id] = evidence
        if item.evidence.artifact is not None:
            converted = _artifact(item.evidence.artifact, presentation)
            source_memory = source_memories.get(converted.memory_id)
            if source_memory is None:
                generic_memories[converted.memory_id] = converted
            elif source_memory.content_hash != converted.content_hash:
                raise ValueError(
                    f"memory ID collision: {converted.memory_id}"
                )

    fidelity_rows = _fidelity_rows(domain, cases, bundle)
    source_rows = _pressure_source_rows(
        domain,
        jobs,
        substantive,
        options,
        presentation,
    )
    selected_count = len(substantive.builds)
    status_detail = (
        "ready_pressure_sources"
        if selected_count
        else "inconclusive_no_natural_overgrant"
    )
    return StudyExpansion(
        jobs=tuple(jobs),
        additional_memories=tuple(generic_memories.values()),
        additional_evidence=tuple(generic_evidence.values()),
        artifact_rows={
            "fidelity": fidelity_rows,
            "substantive_eligibility": tuple(
                row.to_dict() for row in substantive.eligibility
            ),
            "witnesses": tuple(
                {
                    "candidate_id": build.candidate_id,
                    **build.witness.to_dict(),
                }
                for build in substantive.builds
            ),
            "interventions": tuple(
                {
                    "candidate_id": build.candidate_id,
                    "source_memory_id": build.source_memory_id,
                    "exact_repair": build.exact_repair.to_dict(),
                }
                for build in substantive.builds
            ),
            "pressure_source_jobs": source_rows,
        },
        manifest_metadata={
            "substantive_overgrant": {
                **substantive.study_manifest(),
                "status": status_detail,
                "pressure_source_jobs": len(source_rows),
                "selected_before_executor_calls": True,
            },
            "status_detail": status_detail,
        },
    )


def _checkpoint_source(
    domain: Any,
    cases: Sequence[Any],
    bundle: WriterRunBundle,
    options: Mapping[str, Any],
) -> SourceCheckpointRun:
    case_by_id = {case.case_id: case for case in cases}
    memory_by_id = {memory.memory_id: memory for memory in bundle.memories}
    attempts_by_id = {
        attempt.attempt_id: attempt for attempt in bundle.attempts
    }
    checkpoint_by_key = {
        (checkpoint.case_id, checkpoint.block_index): checkpoint
        for checkpoint in _route_checkpoints(cases)
    }
    capacity_tokens = calibrate_capacity(
        domain,
        cases,
        corpus_version=str(options["corpus_version"]),
        presentation=domain.get_presentation(
            str(options.get("presentation_version") or "") or None
        ),
    ).tokens_for(str(options.get("capacity_tier") or "primary"))
    items: list[SourceCheckpointEvidence] = []
    artifacts: dict[str, DomainMemoryArtifact] = {}
    for state in bundle.states:
        if state.architecture is not MemoryArchitecture.TYPED:
            continue
        checkpoint = checkpoint_by_key.get(
            (state.case_id, state.block_index)
        )
        if checkpoint is None or state.current_memory_id is None:
            continue
        memory = memory_by_id.get(state.current_memory_id)
        if memory is None:
            raise ValueError(
                f"{state.state_id}: current checkpoint memory is missing"
            )
        evidence = _evidence_from_artifact(
            memory,
            memory_run_id=state.writer_run_id,
        )
        domain_evidence = _domain_evidence(
            evidence,
            tier=CapacityTier(str(options.get("capacity_tier") or "primary")),
            capacity_tokens=capacity_tokens,
        )
        if domain_evidence.artifact is None:
            raise ValueError(f"{state.state_id}: typed checkpoint has no artifact")
        artifacts[domain_evidence.artifact.memory_id] = domain_evidence.artifact
        final_attempt = (
            attempts_by_id.get(state.attempt_ids[-1])
            if state.attempt_ids
            else None
        )
        link = CheckpointEvidenceLink(
            checkpoint_id=checkpoint.checkpoint_id,
            evidence_id=domain_evidence.evidence_id,
            memory_id=domain_evidence.memory_id,
            case_id=state.case_id,
            condition_id=state.condition_id,
            memory_run_id=state.writer_run_id,
            writer_run_id=state.writer_run_id,
            writer_seed=state.writer_seed,
            observed_block_index=state.block_index,
        )
        case = case_by_id[state.case_id]
        items.append(
            SourceCheckpointEvidence(
                checkpoint=checkpoint,
                link=link,
                evidence=domain_evidence,
                snapshot=replay_case(case)[state.block_index],
                update_policy="bounded_repair",
                first_attempt_id=(
                    final_attempt.attempt_id
                    if final_attempt is not None
                    else None
                ),
                first_attempt_status=(
                    final_attempt.status
                    if final_attempt is not None
                    else None
                ),
            )
        )
    manifest = {
        "run": "current-writer-route",
        "status": "completed",
        "writer_profile": "writer",
        "writer_runs": int(options.get("writer_runs", 1)),
        "counts": {"checkpoint_evidence": len(items)},
    }
    return SourceCheckpointRun(
        path=Path("<current-writer-route>"),
        manifest=manifest,
        manifest_sha256=content_hash(manifest),
        file_sha256={},
        artifacts=artifacts,
        items=tuple(items),
    )


def _fidelity_rows(
    domain: Any,
    cases: Sequence[Any],
    bundle: WriterRunBundle,
) -> tuple[dict[str, Any], ...]:
    case_by_id = {case.case_id: case for case in cases}
    memory_by_id = {memory.memory_id: memory for memory in bundle.memories}
    rows = []
    for state in bundle.states:
        if (
            state.architecture is not MemoryArchitecture.TYPED
            or state.current_memory_id is None
        ):
            continue
        memory = memory_by_id[state.current_memory_id]
        remembered = domain.memory.parse_typed(memory.payload)
        report = domain.fidelity.compare(
            case_by_id[state.case_id],
            remembered,
            through_block_index=state.block_index,
        )
        rows.extend(
            {
                "state_id": state.state_id,
                "memory_id": memory.memory_id,
                "case_id": state.case_id,
                "condition_id": state.condition_id,
                "block_index": state.block_index,
                **field.to_dict(),
            }
            for field in report.fields
        )
    return tuple(rows)


def _pressure_source_rows(
    domain: Any,
    jobs: Sequence[ExecutorJob],
    substantive: Any,
    options: Mapping[str, Any],
    presentation: Any,
) -> tuple[dict[str, Any], ...]:
    config = load_config()
    executor_task = str(options.get("executor_task") or "executor")
    target_ids = _targets(options.get("executor_targets"))
    runs = int(options.get("executor_runs", 1))
    seed = int(options.get("seed", 0))
    build_by_candidate = {
        build.candidate_id: build for build in substantive.builds
    }
    rows = []
    for job in jobs:
        candidate_id = str(job.metadata["candidate_id"])
        evidence_role = str(job.metadata["evidence_role"])
        build = build_by_candidate[candidate_id]
        prepared = prepare_challenge_context(
            domain,
            job.challenge_context,
            pressure_id=BASELINE_PRESSURE_ID,
        )
        for target_id in target_ids:
            for run_id in range(runs):
                route_seed = seed + run_id
                identity = planned_study_job_identity(
                    domain,
                    job,
                    study_id="writer",
                    executor_task=executor_task,
                    target_id=target_id,
                    executor_run_id=run_id,
                    seed=route_seed,
                    presentation=presentation,
                    config=config,
                )
                rows.append(
                    {
                        "pressure_source_job_id": _stable_id(
                            "pressure_source",
                            candidate_id,
                            evidence_role,
                            target_id,
                            str(run_id),
                            str(route_seed),
                        ),
                        "candidate_id": candidate_id,
                        "witness_id": build.witness.witness_id,
                        "case_id": job.evidence.case_id,
                        "checkpoint_id": build.checkpoint_id,
                        "oracle_block_index": job.oracle_block_index,
                        "evidence_role": evidence_role,
                        "natural_evidence_id": build.source_evidence_id,
                        "evidence_id": job.evidence.evidence_id,
                        "evidence_hash": job.evidence.content_hash,
                        "memory_id": job.evidence.memory_id,
                        "memory_run_id": job.evidence.memory_run_id,
                        "writer_seed": job.evidence.writer_seed,
                        "memory_implementation_id": (
                            job.evidence.memory_implementation_id
                        ),
                        "memory_implementation_hash": (
                            job.evidence.memory_implementation_hash
                        ),
                        "profile_id": job.evidence.profile_id,
                        "source_attempt_id": (
                            job.evidence.source_attempt_id
                        ),
                        "writer_target_id": (
                            job.evidence.writer.target_id
                            if job.evidence.writer is not None
                            else None
                        ),
                        "writer_provider": (
                            job.evidence.writer.provider
                            if job.evidence.writer is not None
                            else None
                        ),
                        "writer_requested_model": (
                            job.evidence.writer.requested_model
                            if job.evidence.writer is not None
                            else None
                        ),
                        "writer_resolved_model": (
                            job.evidence.writer.resolved_model
                            if job.evidence.writer is not None
                            else None
                        ),
                        "writer_response_model": (
                            job.evidence.writer.response_model
                            if job.evidence.writer is not None
                            else None
                        ),
                        "writer_effective_parameters": (
                            dict(
                                job.evidence.writer.effective_parameters
                            )
                            if job.evidence.writer is not None
                            else {}
                        ),
                        "witness_request": job.probe.request.to_dict(),
                        "witness_request_hash": content_hash(
                            job.probe.request.to_dict()
                        ),
                        "choice_set_hash": prepared.choice_set_sha256,
                        "baseline_challenge_text": prepared.rendered_text,
                        "baseline_challenge_hash": prepared.rendered_sha256,
                        "objective_framing": (
                            prepared.pressure.objective_framing
                        ),
                        "operational_stakes": (
                            prepared.pressure.operational_stakes
                        ),
                        "alternative_disadvantage": (
                            prepared.pressure.alternative_disadvantage
                        ),
                        "presentation_id": presentation.presentation_id,
                        "presentation_hash": content_hash(
                            presentation.to_dict()
                        ),
                        "corpus_version": str(options["corpus_version"]),
                        "corpus_provenance": dict(
                            domain.corpus.provenance(
                                str(options["corpus_version"])
                            )
                        ),
                        "baseline_job_id": job.job_id,
                        "baseline_trial_id": identity["trial_id"],
                        "baseline_call_id": identity["call_id"],
                        "executor_target_id": target_id,
                        "executor_run_id": run_id,
                        "executor_seed": route_seed,
                        "executor_provider": identity["provider"],
                        "executor_requested_model": identity[
                            "requested_model"
                        ],
                        "executor_resolved_model": identity[
                            "resolved_model"
                        ],
                        "executor_effective_parameters": identity[
                            "effective_parameters"
                        ],
                        "pressure_profile": PRESSURE_PROFILE_ID,
                    }
                )
    return tuple(rows)


def _writer_validation_bundle(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
    presentation: Any,
) -> WriterRunBundle:
    _, capacity_tokens, baselines = _deterministic_baselines(
        domain,
        cases,
        options,
        presentation,
    )
    checkpoint_by_case: dict[str, tuple[AuthorizationCheckpoint, ...]] = {}
    for case in cases:
        try:
            checkpoint_by_case[case.case_id] = _case_checkpoints(case)
        except ValueError:
            continue
    typed = next(
        item
        for item in baselines.evidence
        if item.condition_id == "faithful_typed"
        and item.case_id in checkpoint_by_case
    )
    if typed.artifact is None:
        raise ValueError("validation faithful typed artifact is missing")
    case = next(case for case in cases if case.case_id == typed.case_id)
    build = build_controlled_variants(
        case,
        typed.artifact,
        faithful_typed_state(current_ledger(case)),
        count_tokens=count_reference_tokens,
        capacity_tokens=capacity_tokens,
    )
    overgrant = next(
        variant
        for variant in build.variants
        if variant.kind
        in {
            InterventionKind.AMOUNT_BROADENING,
            InterventionKind.VALIDITY_EXTENSION,
            InterventionKind.VALIDITY_START_ADVANCE,
            InterventionKind.CATEGORY_BROADENING,
        }
    )
    generic = _artifact(overgrant.artifact, presentation)
    checkpoint = max(
        (
            item for item in checkpoint_by_case[case.case_id]
        ),
        key=lambda item: item.block_index,
    )
    writer = ModelProvenance(
        target_id="offline_fixture",
        provider="offline",
        requested_model="fixture",
        resolved_model="fixture",
        response_model="fixture",
        effective_parameters={"temperature": 1.0, "seed": 0},
    )
    generic = replace(
        generic,
        condition_id="incremental_typed",
        block_index=checkpoint.block_index,
        writer_run_id=0,
        writer_seed=0,
        writer=writer,
        origin=MemoryOrigin.WRITER,
        memory_implementation_id=LANGMEM_IMPLEMENTATION_ID,
        memory_implementation_hash=framework_manifest(domain)[
            "memory_implementation_hash"
        ],
        profile_id="offline-writer-fixture",
    )
    evidence = _evidence_from_artifact(generic, memory_run_id=0)
    state = MemoryState(
        state_id="offline-writer-overgrant-state",
        logical_update_id="offline-writer-overgrant-update",
        attempt_ids=(),
        domain_id=domain.domain_id,
        case_id=case.case_id,
        condition_id="incremental_typed",
        block_index=checkpoint.block_index,
        writer_run_id=0,
        writer_seed=0,
        architecture=MemoryArchitecture.TYPED,
        profile_id="offline-writer-fixture",
        current_memory_id=generic.memory_id,
        status="accepted",
        changed=True,
        memory_implementation_hash=generic.memory_implementation_hash,
        presentation_id=presentation.presentation_id,
        presentation_hash=content_hash(presentation.to_dict()),
    )
    return WriterRunBundle(
        memories=(generic,),
        states=(state,),
        evidence=(evidence,),
    )


def _writer_zero_validation_bundle(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
    presentation: Any,
) -> WriterRunBundle:
    _, capacity_tokens, _ = _deterministic_baselines(
        domain,
        cases,
        options,
        presentation,
    )
    case = next(
        case
        for case in cases
        if _case_checkpoints(case)
    )
    checkpoint = max(
        _case_checkpoints(case),
        key=lambda item: item.block_index,
    )
    snapshot = replay_case(case)[checkpoint.block_index]
    exact_domain = build_faithful_artifact(
        faithful_typed_state(snapshot.records),
        architecture=DomainMemoryArchitecture.TYPED,
        case_id=case.case_id,
        chain_id="offline-zero-exact-chain",
        condition_id="incremental_typed",
        block_index=checkpoint.block_index,
        reference_tokenizer="cl100k_base",
        count_tokens=count_reference_tokens,
        capacity_tokens=capacity_tokens,
    )
    exact = _fixture_writer_memory(
        domain,
        _artifact(exact_domain, presentation),
        condition_id="incremental_typed",
        block_index=checkpoint.block_index,
        profile_id="offline-zero-exact-profile",
    )
    empty_payload = {"schema_version": "3", "authorizations": []}
    undergrant = replace(
        exact,
        memory_id=_stable_id(
            "mem",
            "offline-zero-undergrant",
            content_hash(empty_payload),
        ),
        chain_id="offline-zero-undergrant-chain",
        payload=empty_payload,
        content_hash=content_hash(empty_payload),
        profile_id="offline-zero-undergrant-profile",
    )
    states = tuple(
        MemoryState(
            state_id=f"offline-{role}-state",
            logical_update_id=f"offline-{role}-update",
            attempt_ids=(),
            domain_id=domain.domain_id,
            case_id=case.case_id,
            condition_id="incremental_typed",
            block_index=checkpoint.block_index,
            writer_run_id=run_id,
            writer_seed=run_id,
            architecture=MemoryArchitecture.TYPED,
            profile_id=memory.profile_id or "",
            current_memory_id=memory.memory_id,
            status="accepted",
            changed=True,
            memory_implementation_hash=memory.memory_implementation_hash,
            presentation_id=presentation.presentation_id,
            presentation_hash=content_hash(presentation.to_dict()),
        )
        for role, run_id, memory in (
            ("exact", 1000, replace(exact, writer_run_id=1000, writer_seed=1000)),
            (
                "undergrant",
                1001,
                replace(
                    undergrant,
                    writer_run_id=1001,
                    writer_seed=1001,
                ),
            ),
        )
    )
    memories = (
        replace(exact, writer_run_id=1000, writer_seed=1000),
        replace(undergrant, writer_run_id=1001, writer_seed=1001),
    )
    return WriterRunBundle(
        memories=memories,
        states=states,
        evidence=tuple(
            _evidence_from_artifact(memory, memory_run_id=memory.writer_run_id)
            for memory in memories
        ),
    )


def _fixture_writer_memory(
    domain: Any,
    memory: MemoryArtifact,
    *,
    condition_id: str,
    block_index: int,
    profile_id: str,
) -> MemoryArtifact:
    return replace(
        memory,
        condition_id=condition_id,
        block_index=block_index,
        writer_run_id=0,
        writer_seed=0,
        writer=ModelProvenance(
            target_id="offline_fixture",
            provider="offline",
            requested_model="fixture",
            resolved_model="fixture",
            response_model="fixture",
            effective_parameters={"temperature": 1.0, "seed": 0},
        ),
        origin=MemoryOrigin.WRITER,
        memory_implementation_id=LANGMEM_IMPLEMENTATION_ID,
        memory_implementation_hash=framework_manifest(domain)[
            "memory_implementation_hash"
        ],
        profile_id=profile_id,
    )


def _case_checkpoints(case: Any) -> tuple[AuthorizationCheckpoint, ...]:
    return _route_checkpoints((case,))


def _route_checkpoints(
    cases: Sequence[Any],
) -> tuple[AuthorizationCheckpoint, ...]:
    checkpoints = []
    for case in cases:
        events_by_index: dict[int, list[Any]] = defaultdict(list)
        block_index = {
            block.block_id: block.block_index for block in case.blocks
        }
        for event in case.events:
            events_by_index[block_index[event.block_id]].append(event)
        selected_indexes = {
            *events_by_index,
            case.blocks[-1].block_index,
        }
        snapshots = replay_case(case)
        for index in sorted(selected_indexes):
            events = sorted(
                events_by_index.get(index, ()),
                key=lambda item: item.event_id,
            )
            identity = {
                "case_id": case.case_id,
                "block_index": index,
                "event_ids": [event.event_id for event in events],
                "route": "writer_typed_screening",
            }
            snapshot = snapshots[index]
            checkpoints.append(
                AuthorizationCheckpoint(
                    checkpoint_id=(
                        "route_checkpoint_" + content_hash(identity)
                    ),
                    case_id=case.case_id,
                    block_id=case.blocks[index].block_id,
                    block_index=index,
                    event_ids=tuple(event.event_id for event in events),
                    event_types=tuple(event.event_type for event in events),
                    authorization_ids=tuple(
                        event.authorization_id for event in events
                    ),
                    canonical_snapshot_sha256=content_hash(
                        snapshot.to_dict()
                    ),
                )
            )
    return tuple(checkpoints)


def _deterministic_baselines(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
    presentation: Any,
) -> tuple[CapacityTier, int, Any]:
    shared = calibrate_capacity(
        domain,
        cases,
        corpus_version=str(options["corpus_version"]),
        presentation=presentation,
    )
    domain_calibration = CapacityCalibration(
        reference_tokenizer=shared.reference_tokenizer,
        largest_faithful_tokens=shared.largest_faithful_tokens,
        primary_tokens=shared.primary_tokens,
        tight_tokens=shared.tight_tokens,
        minimum_history_ratio=shared.minimum_history_ratio,
        cases=tuple(
            CaseCapacity(
                case_id=row.case_id,
                history_tokens=row.history_tokens,
                faithful_text_tokens=row.faithful_text_tokens,
                faithful_typed_tokens=row.faithful_typed_tokens,
            )
            for row in shared.cases
        ),
    )
    tier = CapacityTier(str(options.get("capacity_tier") or "primary"))
    capacity_tokens = domain_calibration.tokens_for(tier)
    return (
        tier,
        capacity_tokens,
        build_baseline_evidence(
            cases,
            domain_calibration,
            n_runs=1,
            capacity_tier=tier,
            presentation=presentation,
        ),
    )


def _ordinary_job(
    case: Any,
    probe: BenchmarkProbe,
    evidence: FrozenEvidence,
    *,
    route: str,
    evidence_role: str,
    metadata: Mapping[str, Any] | None = None,
    challenge_context: Any | None = None,
) -> ExecutorJob:
    return ExecutorJob(
        job_id=_stable_id(
            "job",
            route,
            evidence.evidence_id,
            probe.probe_id,
        ),
        case=case,
        probe=probe,
        evidence=evidence,
        challenge_context=challenge_context,
        metadata={
            "route": route,
            "evidence_role": evidence_role,
            **dict(metadata or {}),
        },
    )


def _selected_writer_conditions(
    options: Mapping[str, Any],
) -> tuple[str, ...]:
    architecture = str(options.get("writer_architecture") or "all")
    strategy = str(options.get("writer_strategy") or "all")
    selected = []
    for condition in _WRITER_CONDITIONS:
        if architecture == "typed" and not condition.endswith("_typed"):
            continue
        if architecture == "free_text" and not condition.endswith("_text"):
            continue
        if strategy == "one_shot" and not condition.startswith("one_shot_"):
            continue
        if strategy == "incremental" and not condition.startswith(
            "incremental_"
        ):
            continue
        selected.append(condition)
    return tuple(selected)


def _control_role(kind: InterventionKind) -> str:
    if kind is InterventionKind.EXACT_REPAIR:
        return "exact_repair"
    if kind is InterventionKind.SEMANTIC_SHAM:
        return "semantic_sham"
    return "controlled_broadening"


def _control_dimension(kind: InterventionKind) -> str:
    if kind is InterventionKind.AMOUNT_BROADENING:
        return "amount"
    if kind is InterventionKind.CATEGORY_BROADENING:
        return "category"
    if kind in {
        InterventionKind.VALIDITY_EXTENSION,
        InterventionKind.VALIDITY_START_ADVANCE,
    }:
        return "time"
    return kind.value


def _targets(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return tuple(str(item) for item in (value or ()))


def _require_scientific_route(
    options: Mapping[str, Any],
    route: str,
) -> None:
    corpus_version = str(options.get("corpus_version"))
    try:
        expected_presentation = _SCIENTIFIC_ROUTE_PRESENTATIONS[
            corpus_version
        ]
    except KeyError as exc:
        supported = ", ".join(sorted(_SCIENTIFIC_ROUTE_PRESENTATIONS))
        raise ValueError(
            f"{route} requires one of the scientific corpora: {supported}"
        ) from exc
    presentation = str(options.get("presentation_version") or "")
    if presentation != expected_presentation:
        raise ValueError(
            f"{route} with {corpus_version} requires presentation "
            f"{expected_presentation}"
        )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
