from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
from typing import Any

from eal_bench.llm import LLM
from eal_bench.llm.logger import JSONLLogger

from domains.base import AuthorizationMemoryDomain, PresentationProfile

from .executor_plan import executor_plan_rows, planned_executor_calls
from .langmem_writer import framework_manifest, run_writer_chains
from .persistence import (
    content_hash,
    create_run_dir,
    file_hash,
    git_info,
    runtime_info,
    write_json,
    write_jsonl,
)
from .pipeline import (
    calibrate_capacity,
    run_executor_jobs,
    validate_executor_job_surfaces,
)
from .provenance import target_route_manifest
from .provenance import effective_behavioral_parameters
from .runner import (
    _implementation_files,
    _record_response_models,
    _repository_root,
    _validate_model_context_call_log,
)
from .schemas import (
    ARTIFACT_SCHEMA_VERSIONS,
    LANGMEM_IMPLEMENTATION_ID,
    FrozenEvidence,
    MemoryArtifact,
    frozen_evidence_from_dict,
    memory_artifact_from_dict,
    memory_attempt_from_dict,
    memory_state_from_dict,
    model_context_from_dict,
)
from .study_plan import StudyExpansion, StudyPlan, WriterRunBundle


@dataclass(frozen=True)
class PreparedExecution:
    memories: tuple[Any, ...]
    attempts: tuple[Any, ...]
    states: tuple[Any, ...]
    evidence: tuple[FrozenEvidence, ...]
    contexts: tuple[Any, ...]
    writer_bundle: WriterRunBundle
    jobs: tuple[Any, ...]
    dynamic_rows: Mapping[str, Sequence[Any]]
    manifest_metadata: Mapping[str, Any]


def validate_study_plan(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
    *,
    config: Any | None = None,
) -> dict[str, Any]:
    """Validate every plan surface that can be built without a provider call."""

    plan.validate_definition()
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    deferred = bool(plan.writer_chains and plan.job_builder is not None)
    expansion = _offline_expansion(domain, cases, plan, options)
    jobs = plan.validate(
        domain,
        cases,
        options,
        generated_evidence=(
            plan.validation_evidence if deferred else ()
        ),
        expansion_jobs=expansion.jobs,
    )
    executor_surfaces = validate_executor_job_surfaces(
        domain,
        jobs,
        presentation=presentation,
        pressure_specs=plan.pressure_specs,
    )
    logical_writer_updates = sum(
        len(chain.updates) for chain in plan.writer_chains
    )
    writer_max_attempts = int(options.get("writer_max_attempts", 2))
    capacity_enforced = plan.metadata.get("capacity_enforced", True)
    if not isinstance(capacity_enforced, bool):
        raise ValueError("capacity_enforced plan metadata must be boolean")
    calibrated_capacity_tokens = calibrate_capacity(
        domain,
        cases,
        corpus_version=str(options["corpus_version"]),
        presentation=presentation,
    ).tokens_for(str(options.get("capacity_tier") or "primary"))
    writer_visible_capacity_tokens = plan.metadata.get(
        "writer_visible_capacity_tokens", calibrated_capacity_tokens
    )
    if (
        isinstance(writer_visible_capacity_tokens, bool)
        or not isinstance(writer_visible_capacity_tokens, int)
        or writer_visible_capacity_tokens <= 0
    ):
        raise ValueError(
            "writer_visible_capacity_tokens plan metadata must be a positive integer"
        )
    reviewer_calls = int(plan.metadata.get("planned_reviewer_calls", 0))
    writer_route_timeout_seconds = int(
        options.get("writer_route_timeout_seconds", 3600)
    )
    executor_runs = int(options.get("executor_runs", 1))
    executor_targets = _targets(options.get("executor_targets"))
    ordinary_jobs = sum(
        job.executor_target_id is None for job in jobs
    )
    frozen_jobs = len(jobs) - ordinary_jobs
    executor_calls = (
        ordinary_jobs * executor_runs * max(1, len(executor_targets))
        + frozen_jobs
    )
    planned_ordinary_jobs = int(
        plan.metadata.get(
            "planned_ordinary_executor_jobs",
            ordinary_jobs,
        )
    )
    dynamic_min = int(
        plan.metadata.get(
            "planned_dynamic_executor_jobs_min",
            frozen_jobs,
        )
    )
    dynamic_max = int(
        plan.metadata.get(
            "planned_dynamic_executor_jobs_max",
            frozen_jobs,
        )
    )
    route_multiplier = executor_runs * max(1, len(executor_targets))
    executor_calls_min = (
        planned_ordinary_jobs + dynamic_min
    ) * route_multiplier
    executor_calls_max = (
        planned_ordinary_jobs + dynamic_max
    ) * route_multiplier
    if plan.executor_only and jobs and ordinary_jobs == 0:
        executor_calls_min = executor_calls
        executor_calls_max = executor_calls
    estimated_cost = options.get("estimated_cost_usd")
    if (
        executor_calls_max == 0
        and logical_writer_updates == 0
        and reviewer_calls == 0
    ):
        estimated_cost = 0.0
    checkpoint_validation = _validate_writer_checkpoint_round_trip(
        domain,
        cases,
        plan,
        options,
        presentation=presentation,
        config=config,
    )
    return {
        "status": "passed",
        "study_id": plan.study_id,
        "writer_only": plan.writer_only,
        "executor_only": plan.executor_only,
        "writer_chain_count": len(plan.writer_chains),
        "executor_job_count": len(jobs),
        "deferred_job_build": deferred,
        "validated_with_offline_evidence": deferred,
        "offline_validation_evidence_count": len(
            plan.validation_evidence
        ),
        "offline_post_writer_bundle_count": len(
            plan.validation_writer_bundles
        ),
        "offline_post_writer_job_count": len(expansion.jobs),
        "model_visible_executor_surfaces": executor_surfaces,
        "source_evidence_count": len(plan.source_evidence),
        "controlled_memory_count": len(plan.controlled_memories),
        "pressure_ids": [
            pressure.pressure_id for pressure in plan.pressure_specs
        ],
        "presentation_id": presentation.presentation_id,
        "presentation_hash": content_hash(presentation.to_dict()),
        "artifact_schemas": dict(plan.artifact_schemas),
        "artifact_paths": dict(plan.artifact_paths),
        "plan_metadata": dict(plan.metadata),
        "writer_checkpoint": checkpoint_validation,
        "call_plan": {
            "capacity_enforced": capacity_enforced,
            "calibrated_capacity_tokens": calibrated_capacity_tokens,
            "writer_visible_capacity_tokens": writer_visible_capacity_tokens,
            "writer_route_timeout_seconds": writer_route_timeout_seconds,
            "writer_route_timeout_override": (
                writer_route_timeout_seconds != 3600
            ),
            "writer_logical_updates": logical_writer_updates,
            "writer_calls_without_repairs": logical_writer_updates,
            "writer_calls_maximum": (
                logical_writer_updates * writer_max_attempts
            ),
            "reviewer_calls": reviewer_calls,
            "executor_calls": (
                executor_calls_min
                if executor_calls_min == executor_calls_max
                else None
            ),
            "offline_fixture_executor_calls": executor_calls,
            "executor_calls_range": [
                executor_calls_min,
                executor_calls_max,
            ],
            "dynamic_executor_job_cap": plan.metadata.get(
                "candidate_cap"
            ),
            "executor_calls_ordinary": (
                ordinary_jobs
                * executor_runs
                * max(1, len(executor_targets))
            ),
            "executor_calls_source_frozen": frozen_jobs,
            "scheduled_calls_without_writer_repairs": (
                logical_writer_updates + reviewer_calls + executor_calls_min
            ),
            "scheduled_calls_maximum": (
                logical_writer_updates * writer_max_attempts
                + reviewer_calls
                + executor_calls_max
            ),
            "transport_retries_excluded": True,
            "estimated_cost_usd": estimated_cost,
            "cost_estimate_status": (
                "documented_upper_bound"
                if estimated_cost is not None
                else (
                    "current provider pricing is not configured; attach a "
                    "documented estimate before any live run"
                )
            ),
        },
    }


def _validate_writer_checkpoint_round_trip(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
    *,
    presentation: PresentationProfile,
    config: Any | None,
) -> dict[str, Any]:
    if not plan.writer_chains:
        return {"status": "not_applicable"}
    if plan.post_writer_reviewer is not None:
        return {
            "status": "not_resumable",
            "reason": "post-writer reviewer requires a model call",
        }
    if not plan.validation_writer_bundles:
        raise ValueError("writer checkpoint validation requires an offline bundle")
    fixture_hashes = []
    executor_plan_hashes = []
    for bundle in plan.validation_writer_bundles:
        memories = tuple(
            memory_artifact_from_dict(item.to_dict()) for item in bundle.memories
        )
        attempts = tuple(
            memory_attempt_from_dict(item.to_dict()) for item in bundle.attempts
        )
        states = tuple(
            memory_state_from_dict(item.to_dict()) for item in bundle.states
        )
        evidence = tuple(
            frozen_evidence_from_dict(item.to_dict()) for item in bundle.evidence
        )
        contexts = tuple(
            model_context_from_dict(item.to_dict()) for item in bundle.contexts
        )
        base_evidence = [*plan.source_evidence]
        base_evidence.extend(
            item
            for item in plan.controlled_memories
            if isinstance(item, FrozenEvidence)
        )
        base_evidence.extend(evidence)
        prepared = prepare_execution(
            domain,
            cases,
            plan,
            options,
            memories=memories,
            attempts=attempts,
            states=states,
            evidence=base_evidence,
            contexts=contexts,
            writer_evidence=evidence,
            reviewer_llm=None,
        )
        round_trip = {
            "memories": prepared.memories,
            "attempts": prepared.attempts,
            "states": prepared.states,
            "evidence": prepared.evidence,
            "contexts": prepared.contexts,
            "dynamic_rows": prepared.dynamic_rows,
            "manifest_metadata": prepared.manifest_metadata,
            "job_ids": [job.job_id for job in prepared.jobs],
        }
        fixture_hashes.append(content_hash(round_trip))
        if config is not None:
            planned = planned_executor_calls(
                domain,
                prepared.jobs,
                study_id=plan.study_id,
                executor_task=str(options.get("executor_task") or "executor"),
                executor_targets=_targets(options.get("executor_targets")),
                executor_runs=int(options.get("executor_runs", 1)),
                seed=int(options.get("seed", 0)),
                presentation=presentation,
                config=config,
                pressure_specs=plan.pressure_specs,
            )
            executor_plan_hashes.append(content_hash(executor_plan_rows(planned)))
    return {
        "status": "passed",
        "schema_version": "writer_execution_checkpoint_v1",
        "offline_bundle_count": len(plan.validation_writer_bundles),
        "round_trip_hashes": fixture_hashes,
        "executor_plan_hashes": executor_plan_hashes,
        "writer_trajectories_regenerated_on_resume": 0,
        "deterministic_post_writer_expansion": True,
    }


def _offline_expansion(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
) -> StudyExpansion:
    if plan.post_writer_builder is None:
        return StudyExpansion()
    if not plan.validation_writer_bundles:
        raise ValueError(
            "post-writer studies require deterministic offline writer bundles"
        )
    expansions = [
        plan.post_writer_builder(domain, cases, bundle, options)
        for bundle in plan.validation_writer_bundles
    ]
    artifact_rows: dict[str, list[Any]] = {}
    manifest_metadata: dict[str, Any] = {}
    for expansion in expansions:
        for name, values in expansion.artifact_rows.items():
            artifact_rows.setdefault(name, []).extend(values)
        manifest_metadata.update(dict(expansion.manifest_metadata))
    return StudyExpansion(
        jobs=tuple(
            job for expansion in expansions for job in expansion.jobs
        ),
        additional_memories=tuple(
            memory
            for expansion in expansions
            for memory in expansion.additional_memories
        ),
        additional_evidence=tuple(
            evidence
            for expansion in expansions
            for evidence in expansion.additional_evidence
        ),
        additional_contexts=tuple(
            context
            for expansion in expansions
            for context in expansion.additional_contexts
        ),
        artifact_rows={
            name: tuple(values) for name, values in artifact_rows.items()
        },
        manifest_metadata=manifest_metadata,
    )


def run_study_plan(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
) -> Path:
    """Run and persist a domain-built study through shared infrastructure."""

    plan.validate_definition()
    corpus_version = str(options["corpus_version"])
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    writer_task = str(options.get("writer_task") or "writer")
    executor_task = str(options.get("executor_task") or "executor")
    writer_targets = _targets(options.get("writer_targets"))
    executor_targets = _targets(options.get("executor_targets"))
    writer_max_attempts = int(options.get("writer_max_attempts", 2))
    writer_route_timeout_seconds = int(
        options.get("writer_route_timeout_seconds", 3600)
    )
    executor_runs = int(options.get("executor_runs", 1))
    capacity_tier = str(options.get("capacity_tier") or "primary")
    batch_size = options.get("batch_size")
    seed = int(options.get("seed", 0))
    calibration = calibrate_capacity(
        domain,
        cases,
        corpus_version=corpus_version,
        presentation=presentation,
    )
    capacity_tokens = calibration.tokens_for(capacity_tier)
    capacity_enforced = plan.metadata.get("capacity_enforced", True)
    if not isinstance(capacity_enforced, bool):
        raise ValueError("capacity_enforced plan metadata must be boolean")
    writer_visible_capacity_tokens = plan.metadata.get(
        "writer_visible_capacity_tokens", capacity_tokens
    )
    if (
        isinstance(writer_visible_capacity_tokens, bool)
        or not isinstance(writer_visible_capacity_tokens, int)
        or writer_visible_capacity_tokens <= 0
    ):
        raise ValueError(
            "writer_visible_capacity_tokens plan metadata must be a positive integer"
        )
    if plan.writer_chains and not writer_targets:
        raise ValueError("writer-backed study plans require writer targets")
    if not plan.writer_only and not executor_targets:
        raise ValueError("executor-backed study plans require executor targets")
    chain_targets = {
        str(chain.target_id) for chain in plan.writer_chains
    }
    if chain_targets - set(writer_targets):
        raise ValueError(
            "writer chains reference targets outside --writer-targets: "
            + ", ".join(sorted(chain_targets - set(writer_targets)))
        )

    run_dir = create_run_dir(
        domain.domain_id,
        f"authorization-memory-{plan.study_id}",
        tag=options.get("tag"),
    )
    calls_path = run_dir / "calls.jsonl"
    manifest_path = run_dir / "manifest.json"
    llm = LLM(logger=JSONLLogger(calls_path))

    manifest = _manifest(
        domain,
        cases=cases,
        plan=plan,
        options=options,
        config=llm.config,
        presentation=presentation,
        writer_task=writer_task,
        executor_task=executor_task,
        writer_targets=writer_targets,
        executor_targets=executor_targets,
        calibration=calibration.to_dict(),
    )
    write_json(manifest_path, manifest)
    try:
        memories: list[MemoryArtifact] = []
        attempts: list[Any] = []
        states: list[Any] = []
        evidence: list[FrozenEvidence] = list(plan.source_evidence)
        contexts: list[Any] = []
        writer_evidence: list[FrozenEvidence] = []

        for item in plan.controlled_memories:
            if isinstance(item, FrozenEvidence):
                evidence.append(item)
            elif isinstance(item, MemoryArtifact):
                memories.append(item)
            else:
                raise TypeError(
                    "controlled memories must be MemoryArtifact or FrozenEvidence"
                )

        if plan.writer_chains:
            generated = run_writer_chains(
                llm,
                domain,
                plan.writer_chains,
                writer_task=writer_task,
                max_attempts=writer_max_attempts,
                capacity_tokens=writer_visible_capacity_tokens,
                batch_size=batch_size,
                enforce_capacity=capacity_enforced,
                route_timeout_seconds=writer_route_timeout_seconds,
            )
            memories.extend(generated.memories)
            attempts.extend(generated.attempts)
            states.extend(generated.states)
            evidence.extend(generated.final_evidence)
            writer_evidence.extend(generated.final_evidence)
            contexts.extend(generated.model_contexts)

        prepared = prepare_execution(
            domain,
            cases,
            plan,
            options,
            memories=memories,
            attempts=attempts,
            states=states,
            evidence=evidence,
            contexts=contexts,
            writer_evidence=writer_evidence,
            reviewer_llm=llm,
        )
        memories = list(prepared.memories)
        attempts = list(prepared.attempts)
        states = list(prepared.states)
        evidence = list(prepared.evidence)
        contexts = list(prepared.contexts)
        dynamic_rows = dict(prepared.dynamic_rows)
        jobs = prepared.jobs
        manifest.update(dict(prepared.manifest_metadata))
        manifest["model_visible_executor_surfaces"] = (
            validate_executor_job_surfaces(
                domain,
                jobs,
                presentation=presentation,
                pressure_specs=plan.pressure_specs,
            )
        )
        _freeze_pre_execution_checkpoint(
            run_dir,
            manifest_path,
            manifest,
            plan,
            prepared,
            calls_path=calls_path,
            domain=domain,
            executor_task=executor_task,
            executor_targets=executor_targets,
            executor_runs=executor_runs,
            seed=seed,
            presentation=presentation,
            config=llm.config,
        )
        trials: list[Any] = []
        if jobs:
            trials, executor_contexts = run_executor_jobs(
                llm,
                domain,
                jobs,
                study_id=plan.study_id,
                executor_task=executor_task,
                executor_targets=executor_targets,
                executor_runs=executor_runs,
                batch_size=batch_size,
                seed=seed,
                presentation=presentation,
                pressure_specs=plan.pressure_specs,
            )
            contexts.extend(executor_contexts)

        _validate_model_context_call_log(contexts, calls_path)
        rows: dict[str, tuple[Path, Sequence[Any]]] = {
            "memories": (run_dir / "memories.jsonl", memories),
            "memory_attempts": (
                run_dir / "memory_attempts.jsonl",
                attempts,
            ),
            "memory_states": (run_dir / "memory_states.jsonl", states),
            "evidence": (run_dir / "evidence.jsonl", evidence),
            "trials": (run_dir / "trials.jsonl", trials),
            "model_contexts": (
                run_dir / "model_contexts.jsonl",
                contexts,
            ),
        }
        rows.update(
            {
                name: (run_dir / f"{name}.jsonl", values)
                for name, values in {
                    **plan.artifact_rows,
                    **dynamic_rows,
                }.items()
            }
        )
        for name, filename in plan.artifact_paths.items():
            if name not in rows:
                raise ValueError(
                    f"artifact path {name!r} has no corresponding rows"
                )
            _, values = rows[name]
            rows[name] = (run_dir / filename, values)
        files: dict[str, dict[str, Any]] = {}
        counts: dict[str, int] = {}
        for name, (path, values) in rows.items():
            if not values and name not in plan.persist_empty_artifacts:
                continue
            count = write_jsonl(path, values)
            counts[name] = count
            files[name] = {
                "path": path.name,
                "sha256": file_hash(path),
                "rows": count,
            }
        if calls_path.exists():
            call_count = sum(
                1
                for line in calls_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            counts["calls"] = call_count
            files["calls"] = {
                "path": calls_path.name,
                "sha256": file_hash(calls_path),
                "rows": call_count,
            }
        checkpoint = manifest.get("checkpoint")
        if isinstance(checkpoint, Mapping):
            checkpoint_files = checkpoint.get("files")
            if not isinstance(checkpoint_files, Mapping):
                raise ValueError("writer checkpoint has no file map")
            for name in (
                "writer_bundle_memories",
                "writer_bundle_evidence",
                "writer_model_contexts",
                "executor_plan",
                "writer_calls",
            ):
                entry = checkpoint_files.get(name)
                if not isinstance(entry, Mapping):
                    raise ValueError(f"writer checkpoint is missing {name!r}")
                checkpoint_path = run_dir / str(entry["path"])
                if file_hash(checkpoint_path) != entry.get("sha256"):
                    raise ValueError(f"writer checkpoint artifact changed: {name}")
                files[name] = dict(entry)
                counts[name] = int(entry["rows"])
        for alias, target in plan.file_aliases.items():
            if target not in files:
                raise ValueError(
                    f"file alias {alias!r} refers to missing artifact {target!r}"
                )
            files[alias] = dict(files[target])
        manifest.update(
            {
                "status": "completed",
                "finished_at": datetime.now().astimezone().isoformat(),
                "files": files,
                "counts": counts,
            }
        )
        _record_response_models(
            manifest["writer"]["target_routes"],
            (attempt.writer for attempt in attempts),
        )
        _record_response_models(
            manifest["executor"]["target_routes"],
            (trial.executor for trial in trials),
        )
        if manifest.get("reviewer") is not None:
            _record_response_models(
                manifest["reviewer"]["target_routes"],
                (
                    context.model
                    for context in contexts
                    if context.stage == "writer_selector"
                ),
            )
        write_json(manifest_path, manifest)
        return run_dir
    except Exception as exc:
        manifest.update(
            {
                "status": "failed",
                "finished_at": datetime.now().astimezone().isoformat(),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        write_json(manifest_path, manifest)
        raise


def prepare_execution(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
    *,
    memories: Sequence[Any],
    attempts: Sequence[Any],
    states: Sequence[Any],
    evidence: Sequence[FrozenEvidence],
    contexts: Sequence[Any],
    writer_evidence: Sequence[FrozenEvidence],
    reviewer_llm: Any | None,
) -> PreparedExecution:
    writer_bundle = WriterRunBundle(
        memories=tuple(memories),
        attempts=tuple(attempts),
        states=tuple(states),
        evidence=tuple(writer_evidence),
        contexts=tuple(contexts),
    )
    if plan.post_writer_reviewer is not None:
        if reviewer_llm is None:
            raise ValueError("reviewer-backed writer checkpoints cannot be rebuilt")
        expansion = plan.post_writer_reviewer(
            reviewer_llm,
            domain,
            cases,
            writer_bundle,
            options,
        )
    elif plan.post_writer_builder is not None:
        expansion = plan.post_writer_builder(
            domain,
            cases,
            writer_bundle,
            options,
        )
    else:
        expansion = StudyExpansion()

    prepared_memories = [*memories, *expansion.additional_memories]
    prepared_evidence = [*evidence, *expansion.additional_evidence]
    prepared_contexts = [*contexts, *expansion.additional_contexts]
    unique_memories: dict[str, MemoryArtifact] = {}
    for memory in prepared_memories:
        prior = unique_memories.setdefault(memory.memory_id, memory)
        if prior != memory:
            raise ValueError(f"memory ID collision: {memory.memory_id}")
    prepared_memories = list(unique_memories.values())
    dynamic_rows: dict[str, Sequence[Any]] = {
        name: tuple(values)
        for name, values in expansion.artifact_rows.items()
    }
    manifest_metadata = dict(expansion.manifest_metadata)
    jobs = plan.validate(
        domain,
        cases,
        options,
        generated_evidence=writer_evidence,
        expansion_jobs=expansion.jobs,
    )
    evidence_by_id = {item.evidence_id: item for item in prepared_evidence}
    for job in jobs:
        prior = evidence_by_id.setdefault(
            job.evidence.evidence_id,
            job.evidence,
        )
        if prior != job.evidence:
            raise ValueError(f"evidence ID collision: {job.evidence.evidence_id}")
    prepared_evidence = list(evidence_by_id.values())
    if plan.finalizer is not None:
        finalized = plan.finalizer(
            domain,
            cases,
            prepared_memories,
            attempts,
            states,
            prepared_evidence,
            options,
        )
        if finalized.replace_evidence:
            prepared_evidence = list(finalized.additional_evidence)
        else:
            prepared_evidence.extend(finalized.additional_evidence)
        dynamic_rows.update(finalized.artifact_rows)
        manifest_metadata.update(dict(finalized.manifest_metadata))
    finalized_evidence: dict[str, FrozenEvidence] = {}
    for item in prepared_evidence:
        prior = finalized_evidence.setdefault(item.evidence_id, item)
        if prior != item:
            raise ValueError(f"evidence ID collision: {item.evidence_id}")
    return PreparedExecution(
        memories=tuple(prepared_memories),
        attempts=tuple(attempts),
        states=tuple(states),
        evidence=tuple(finalized_evidence.values()),
        contexts=tuple(prepared_contexts),
        writer_bundle=writer_bundle,
        jobs=tuple(jobs),
        dynamic_rows=dynamic_rows,
        manifest_metadata=manifest_metadata,
    )


def _freeze_pre_execution_checkpoint(
    run_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    plan: StudyPlan,
    prepared: PreparedExecution,
    *,
    calls_path: Path,
    domain: AuthorizationMemoryDomain,
    executor_task: str,
    executor_targets: Sequence[str],
    executor_runs: int,
    seed: int,
    presentation: PresentationProfile,
    config: Any,
) -> None:
    dynamic_rows = prepared.dynamic_rows
    if not plan.writer_chains:
        if (
            plan.post_writer_builder is None
            and plan.post_writer_reviewer is None
        ):
            return
        frozen_files: dict[str, dict[str, Any]] = {}
        frozen_counts: dict[str, int] = {}
        for name, values in dynamic_rows.items():
            filename = plan.artifact_paths.get(name, f"{name}.jsonl")
            path = run_dir / filename
            count = write_jsonl(path, values)
            frozen_counts[name] = count
            frozen_files[name] = {
                "path": path.name,
                "sha256": file_hash(path),
                "rows": count,
            }
        manifest.update(
            {
                "status": "expansion_frozen",
                "post_writer_expansion": {
                    "executor_jobs": len(prepared.jobs),
                    "files": frozen_files,
                    "counts": frozen_counts,
                    "selected_before_executor_calls": True,
                },
            }
        )
        write_json(manifest_path, manifest)
        return

    planned = planned_executor_calls(
        domain,
        prepared.jobs,
        study_id=plan.study_id,
        executor_task=executor_task,
        executor_targets=executor_targets,
        executor_runs=executor_runs,
        seed=seed,
        presentation=presentation,
        config=config,
        pressure_specs=plan.pressure_specs,
    )
    checkpoint_rows: dict[str, Sequence[Any]] = {
        "memories": prepared.memories,
        "memory_attempts": prepared.attempts,
        "memory_states": prepared.states,
        "evidence": prepared.evidence,
        "writer_bundle_memories": prepared.writer_bundle.memories,
        "writer_bundle_evidence": prepared.writer_bundle.evidence,
        "writer_model_contexts": prepared.writer_bundle.contexts,
        "executor_plan": executor_plan_rows(planned),
        **plan.artifact_rows,
        **dynamic_rows,
    }
    checkpoint_files: dict[str, dict[str, Any]] = {}
    checkpoint_counts: dict[str, int] = {}
    for name, values in checkpoint_rows.items():
        filename = plan.artifact_paths.get(name, f"{name}.jsonl")
        path = run_dir / filename
        count = write_jsonl(path, values)
        checkpoint_counts[name] = count
        checkpoint_files[name] = {
            "path": path.name,
            "sha256": file_hash(path),
            "rows": count,
        }
    if not calls_path.is_file():
        raise ValueError("writer checkpoint has no call log")
    writer_calls_path = run_dir / "writer_calls.jsonl"
    shutil.copy2(calls_path, writer_calls_path)
    writer_call_count = sum(
        bool(line.strip())
        for line in writer_calls_path.read_text(encoding="utf-8").splitlines()
    )
    checkpoint_counts["writer_calls"] = writer_call_count
    checkpoint_files["writer_calls"] = {
        "path": writer_calls_path.name,
        "sha256": file_hash(writer_calls_path),
        "rows": writer_call_count,
    }
    dynamic_files = {
        name: checkpoint_files[name] for name in dynamic_rows
    }
    dynamic_counts = {
        name: checkpoint_counts[name] for name in dynamic_rows
    }
    manifest.update(
        {
            "status": "execution_frozen",
            "files": checkpoint_files,
            "counts": checkpoint_counts,
            "checkpoint": {
                "schema_version": "writer_execution_checkpoint_v1",
                "executor_calls": len(planned),
                "executor_call_ids_sha256": content_hash(list(planned)),
                "files": checkpoint_files,
                "counts": checkpoint_counts,
                "writer_calls_immutable": True,
                "writer_trajectories_regenerated_on_resume": 0,
                "selected_before_executor_calls": True,
            },
            "post_writer_expansion": {
                "executor_jobs": len(prepared.jobs),
                "files": dynamic_files,
                "counts": dynamic_counts,
                "selected_before_executor_calls": True,
            },
        }
    )
    manifest["artifact_schema_versions"].update(
        {
            "writer_bundle_memories": ARTIFACT_SCHEMA_VERSIONS["memories"],
            "writer_bundle_evidence": ARTIFACT_SCHEMA_VERSIONS["evidence"],
            "writer_model_contexts": ARTIFACT_SCHEMA_VERSIONS["model_contexts"],
            "executor_plan": 1,
            "writer_calls": 1,
        }
    )
    write_json(manifest_path, manifest)


def _targets(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    return tuple(str(item) for item in value)


def _manifest(
    domain: AuthorizationMemoryDomain,
    *,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
    config: Any,
    presentation: PresentationProfile,
    writer_task: str,
    executor_task: str,
    writer_targets: Sequence[str],
    executor_targets: Sequence[str],
    calibration: Mapping[str, Any],
) -> dict[str, Any]:
    artifact_versions = {
        **ARTIFACT_SCHEMA_VERSIONS,
        **dict(plan.artifact_schemas),
    }
    writer_active = bool(plan.writer_chains)
    writer_route_timeout_seconds = int(
        options.get("writer_route_timeout_seconds", 3600)
    )
    implementation = framework_manifest(
        domain,
        route_timeout_seconds=writer_route_timeout_seconds,
    )
    memory_implementation_id = LANGMEM_IMPLEMENTATION_ID
    memory_implementation_hash = implementation[
        "memory_implementation_hash"
    ]
    writer_framework = implementation if writer_active else None
    writer_profiles = _writer_call_profiles(
        domain,
        config,
        writer_task,
        plan.writer_chains,
    )
    executor_profiles = _executor_call_profiles(
        domain,
        config,
        executor_task,
        runs=int(options.get("executor_runs", 1)),
        seed=int(options.get("seed", 0)),
    )
    reviewer_active = plan.post_writer_reviewer is not None
    reviewer_calls = int(plan.metadata.get("planned_reviewer_calls", 0))
    reviewer_task = str(options.get("reviewer_task") or "memory_selector")
    reviewer_target = str(
        options.get("reviewer_target")
        or (writer_targets[0] if writer_targets else "")
    )
    reviewer_seed = int(options.get("reviewer_seed", 0))
    reviewer_parameters = {
        "temperature": 0.0,
        "max_tokens": int(options.get("reviewer_max_tokens", 768)),
        "seed": reviewer_seed,
    }
    implementation_files = _implementation_files(domain)
    manifest = {
        "status": "running",
        "started_at": datetime.now().astimezone().isoformat(),
        "finished_at": None,
        "domain_id": domain.domain_id,
        "domain_adapter_version": domain.adapter_version,
        "domain_maturity": domain.maturity,
        "memory_implementation_id": memory_implementation_id,
        "memory_implementation_hash": memory_implementation_hash,
        "study": plan.study_id,
        "study_plan": {
            "writer_only": plan.writer_only,
            "executor_only": plan.executor_only,
            "pressure_specs": list(plan.pressure_specs),
            "metadata": dict(plan.metadata),
        },
        "artifact_schema_versions": artifact_versions,
        "corpus_version": str(options["corpus_version"]),
        "corpus_provenance": dict(
            domain.corpus.provenance(str(options["corpus_version"]))
        ),
        "case_ids": [domain.corpus.case_id(case) for case in cases],
        "presentation": presentation.to_dict(),
        "presentation_hash": content_hash(presentation.to_dict()),
        "writer": {
            "active": writer_active,
            "task": writer_task,
            "targets": list(writer_targets),
            "memory_implementation_id": memory_implementation_id,
            "memory_implementation_hash": memory_implementation_hash,
            "framework": writer_framework,
            "profile_schema": (
                {
                    "free_text": "langmem.knowledge.extraction.Memory",
                    "typed": (
                        f"{domain.memory.typed_profile_model.__module__}."
                        f"{domain.memory.typed_profile_model.__qualname__}"
                    ),
                    "typed_payload_schema_id": domain.memory.payload_schema_id,
                }
                if writer_active
                else None
            ),
            "task_parameters": dict(config.task(writer_task).params),
            "target_routes": [
                target_route_manifest(
                    config,
                    writer_task,
                    target,
                    call_profiles=writer_profiles,
                )
                for target in writer_targets
            ],
            "runs": len(
                {chain.run_id for chain in plan.writer_chains}
            ),
            "max_attempts": int(options.get("writer_max_attempts", 2)),
            "route_timeout_seconds": writer_route_timeout_seconds,
            "route_timeout_override": writer_route_timeout_seconds != 3600,
        },
        "executor": {
            "active": not plan.writer_only,
            "task": executor_task,
            "targets": list(executor_targets),
            "task_parameters": dict(config.task(executor_task).params),
            "target_routes": [
                target_route_manifest(
                    config,
                    executor_task,
                    target,
                    call_profiles=executor_profiles,
                )
                for target in executor_targets
            ],
            "runs": int(options.get("executor_runs", 1)),
        },
        "reviewer": (
            {
                "active": True,
                "task": reviewer_task,
                "target": reviewer_target,
                "task_parameters": dict(config.task(reviewer_task).params),
                "target_routes": [
                    target_route_manifest(
                        config,
                        reviewer_task,
                        reviewer_target,
                        call_profiles=[
                            {
                                "role": "trajectory_selector",
                                "effective_parameters": reviewer_parameters,
                            }
                        ],
                    )
                ],
                "planned_calls": reviewer_calls,
            }
            if reviewer_active
            else None
        ),
        "capacity_tier": str(options.get("capacity_tier") or "primary"),
        "capacity": dict(calibration),
        "batch_size": options.get("batch_size") or config.batch_size,
        "seed": int(options.get("seed", 0)),
        "source_files": {
            str(path): file_hash(path)
            for path in domain.corpus.source_files(str(options["corpus_version"]))
        },
        "implementation_files": {
            str(path.relative_to(_repository_root())): file_hash(path)
            for path in implementation_files
        },
        "command": str(options.get("command") or ""),
        "git": git_info(),
        "runtime": runtime_info(),
        "files": {},
    }
    reserved = set(manifest).intersection(plan.metadata)
    if reserved:
        joined = ", ".join(sorted(reserved))
        raise ValueError(
            f"study plan metadata collides with manifest fields: {joined}"
        )
    manifest.update(dict(plan.metadata))
    compatibility = options.get("_completed_release_replication_compatibility")
    if compatibility is not None:
        manifest["completed_release_replication_compatibility"] = dict(
            compatibility
        )
    return manifest


def _writer_call_profiles(
    domain: AuthorizationMemoryDomain,
    config: Any,
    task: str,
    chains: Sequence[Any],
) -> list[dict[str, Any]]:
    profiles = []
    seen: set[tuple[str, int, int, str | None]] = set()
    for chain in chains:
        key = (
            chain.architecture.value,
            int(chain.run_id),
            int(chain.writer_seed),
            chain.model_override,
        )
        if key in seen:
            continue
        seen.add(key)
        profiles.append(
            {
                "architecture": chain.architecture.value,
                "run_id": int(chain.run_id),
                "writer_seed": int(chain.writer_seed),
                "model_override": chain.model_override,
                "manager": framework_manifest(domain)["manager"],
                "effective_parameters": effective_behavioral_parameters(
                    config,
                    task,
                    overrides={
                        "temperature": 1.0,
                        "seed": int(chain.writer_seed),
                    },
                    tools=(),
                    required_capabilities=(
                        "native_tools",
                        "forced_tool_choice",
                        "seed",
                    ),
                ),
            }
        )
    return profiles


def _executor_call_profiles(
    domain: AuthorizationMemoryDomain,
    config: Any,
    task: str,
    *,
    runs: int,
    seed: int,
) -> list[dict[str, Any]]:
    tools = tuple(domain.executor.tools())
    return [
        {
            "run_id": run_id,
            "effective_parameters": effective_behavioral_parameters(
                config,
                task,
                overrides={
                    "temperature": 1.0,
                    "seed": seed + run_id,
                    "tool_choice": "auto",
                },
                tools=tools,
                required_capabilities=("native_tools", "seed"),
            ),
        }
        for run_id in range(runs)
    ]
