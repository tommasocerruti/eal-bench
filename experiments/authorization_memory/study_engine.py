from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from eal_bench.llm import LLM
from eal_bench.llm.logger import JSONLLogger

from domains.base import AuthorizationMemoryDomain, PresentationProfile

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
)
from .study_plan import StudyExpansion, StudyPlan, WriterRunBundle


def validate_study_plan(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
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
    if executor_calls_max == 0 and logical_writer_updates == 0:
        estimated_cost = 0.0
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
                logical_writer_updates + executor_calls_min
            ),
            "scheduled_calls_maximum": (
                logical_writer_updates * writer_max_attempts
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

        writer_bundle = WriterRunBundle(
            memories=tuple(memories),
            attempts=tuple(attempts),
            states=tuple(states),
            evidence=tuple(writer_evidence),
            contexts=tuple(contexts),
        )
        expansion = (
            plan.post_writer_builder(
                domain,
                cases,
                writer_bundle,
                options,
            )
            if plan.post_writer_builder is not None
            else StudyExpansion()
        )
        memories.extend(expansion.additional_memories)
        evidence.extend(expansion.additional_evidence)
        unique_memories: dict[str, MemoryArtifact] = {}
        for memory in memories:
            prior = unique_memories.setdefault(memory.memory_id, memory)
            if prior != memory:
                raise ValueError(
                    f"memory ID collision: {memory.memory_id}"
                )
        memories = list(unique_memories.values())
        dynamic_rows: dict[str, Sequence[Any]] = {
            name: tuple(values)
            for name, values in expansion.artifact_rows.items()
        }
        manifest.update(dict(expansion.manifest_metadata))
        jobs = plan.validate(
            domain,
            cases,
            options,
            generated_evidence=writer_evidence,
            expansion_jobs=expansion.jobs,
        )
        manifest["model_visible_executor_surfaces"] = (
            validate_executor_job_surfaces(
                domain,
                jobs,
                presentation=presentation,
                pressure_specs=plan.pressure_specs,
            )
        )
        evidence_by_id = {
            item.evidence_id: item for item in evidence
        }
        for job in jobs:
            prior = evidence_by_id.setdefault(
                job.evidence.evidence_id,
                job.evidence,
            )
            if prior != job.evidence:
                raise ValueError(
                    f"evidence ID collision: {job.evidence.evidence_id}"
                )
        evidence = list(evidence_by_id.values())
        if plan.finalizer is not None:
            finalized = plan.finalizer(
                domain,
                cases,
                memories,
                attempts,
                states,
                evidence,
                options,
            )
            if finalized.replace_evidence:
                evidence = list(finalized.additional_evidence)
            else:
                evidence.extend(finalized.additional_evidence)
            dynamic_rows.update(finalized.artifact_rows)
            manifest.update(dict(finalized.manifest_metadata))
        finalized_evidence: dict[str, FrozenEvidence] = {}
        for item in evidence:
            prior = finalized_evidence.setdefault(item.evidence_id, item)
            if prior != item:
                raise ValueError(f"evidence ID collision: {item.evidence_id}")
        evidence = list(finalized_evidence.values())

        _freeze_pre_execution_expansion(
            run_dir,
            manifest_path,
            manifest,
            plan,
            dynamic_rows,
            jobs,
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


def _freeze_pre_execution_expansion(
    run_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    plan: StudyPlan,
    dynamic_rows: Mapping[str, Sequence[Any]],
    jobs: Sequence[Any],
) -> None:
    if plan.post_writer_builder is None:
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
                "executor_jobs": len(jobs),
                "files": frozen_files,
                "counts": frozen_counts,
                "selected_before_executor_calls": True,
            },
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
