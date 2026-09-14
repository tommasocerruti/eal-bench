"""Bounded event sourcing: study."""

from __future__ import annotations

import copy


import json


from collections.abc import Mapping, Sequence


from datetime import datetime

from pathlib import Path


from typing import Any

from eal_bench.llm import LLM, load_config

from eal_bench.llm.logger import JSONLLogger

from domains.base import (
    AuthorizationMemoryDomain,
    StudyProfile,
)


from experiments.authorization_memory.persistence import (
    content_hash,
    create_run_dir,
    file_hash,
    git_info,
    runtime_info,
    write_json,
)


from experiments.authorization_memory.provenance import (
    effective_behavioral_parameters,
    target_route_manifest,
)


from .core import (
    DIAGNOSTIC_SCHEMA_VERSION,
    EVENT_CONDITION_ID,
    EVENT_DELTA_SCHEMA_VERSION,
    EVENT_LOG_SCHEMA_VERSION,
    EVENT_SCHEMA_VERSION,
    EVENT_SOURCING_STUDY_ID,
    IMPLEMENTATION_ID,
    REDUCED_STATE_SCHEMA_VERSION,
    RESOURCE_SCHEMA_VERSION,
    _capacity_tokens,
    _forced_tool_choice,
    event_tool,
    event_writer_instruction,
)

from .runtime import (
    _event_diagnostic_rows,
    _executor_job_row,
    _executor_jobs,
    _final_writer_artifacts,
    _jsonl_count,
    _load_checkpoint,
    _representation_rows,
    _restore_trajectories,
    _run_event_writers,
    _run_resumable_executor_jobs,
    _validate_context_call_log_rows,
    _write_named_rows,
)

from .sources import (
    _baseline_executor_jobs,
    _portable_path,
    _source_files,
    _targets,
    validate_selected_sources,
)

from .validation import (
    validate_event_sourcing_offline,
    validate_options,
)


def shared_study_profile() -> StudyProfile:
    return StudyProfile(
        study_id=EVENT_SOURCING_STUDY_ID,
        description=(
            "Extract bounded-context authorization deltas and reduce them "
            "deterministically before executor replay."
        ),
        required_capabilities=("native_tools", "forced_tool_choice", "seed"),
        validator=validate_options,
        runner=run_event_sourcing_study,
        offline_validator=validate_event_sourcing_offline,
    )


def run_event_sourcing_study(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> Path:
    """Freeze a portable run plan, then extract events and replay evidence."""

    validate_options(options)
    if domain.event_sourcing is None or not cases:
        raise ValueError("event sourcing requires supported lifecycle rules and nonempty cases")
    if options.get("estimated_cost_usd") is None:
        raise ValueError("live event-sourcing runs require --estimated-cost-usd")
    presentation = domain.get_presentation(str(options.get("presentation_version") or "") or None)
    corpus_version = str(options["corpus_version"])
    capacity_tokens = _capacity_tokens(domain, corpus_version)
    writer_targets = _targets(options.get("writer_targets"))
    executor_targets = _targets(options.get("executor_targets"))
    if not writer_targets or not executor_targets:
        raise ValueError("event sourcing requires writer and executor targets")
    config = load_config(load_env=False)
    validate_routes(config, options)
    baseline_sources = validate_selected_sources(domain, cases, options, config=config)
    resume_value = str(options.get("resume_run") or "").strip()
    run_dir = (
        Path(resume_value).expanduser().resolve()
        if resume_value
        else create_run_dir(
            domain.domain_id,
            "authorization-memory-event-sourcing",
            tag=options.get("tag"),
        )
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    calls_path = run_dir / "calls.jsonl"
    checkpoint_path = run_dir / "event_writer_checkpoint.json"
    seed = int(options["seed"])
    writer_task = str(options.get("writer_task") or "writer")
    executor_task = str(options.get("executor_task") or "executor")
    batch_size = options.get("batch_size")
    implementation = event_sourcing_implementation(
        domain, cases, presentation.presentation_id, corpus_version=corpus_version
    )
    expected_manifest = _event_manifest(
        domain,
        cases,
        options,
        config,
        presentation_id=presentation.presentation_id,
        writer_targets=writer_targets,
        executor_targets=executor_targets,
        capacity_tokens=capacity_tokens,
        implementation=implementation,
        baseline_sources=baseline_sources,
    )
    if resume_value:
        if not manifest_path.is_file():
            raise ValueError("event-sourcing resume requires an existing manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _validate_resume_manifest(manifest, expected_manifest)
        _verify_frozen_files(run_dir, manifest)
        if manifest.get("status") == "completed":
            return run_dir
    else:
        manifest = expected_manifest
    manifest["status"] = "writer_running"
    write_json(manifest_path, manifest)
    checkpoint = _load_checkpoint(checkpoint_path, manifest)
    trajectories = _restore_trajectories(
        domain,
        cases,
        writer_targets,
        seed,
        checkpoint,
    )
    baseline_jobs, baseline_evidence, baseline_memories = _baseline_executor_jobs(
        domain, cases, baseline_sources
    )
    # All source, route, frozen-plan and checkpoint checks precede client construction.
    from dotenv import load_dotenv

    load_dotenv()
    llm = LLM(config=config, logger=JSONLLogger(calls_path))
    try:
        _run_event_writers(
            llm,
            domain,
            trajectories,
            checkpoint,
            checkpoint_path=checkpoint_path,
            writer_task=writer_task,
            presentation_id=presentation.presentation_id,
            capacity_tokens=capacity_tokens,
            batch_size=batch_size,
            implementation_hash=implementation["implementation_hash"],
        )
        artifacts = _final_writer_artifacts(
            domain,
            cases,
            trajectories,
            checkpoint,
            presentation_id=presentation.presentation_id,
            presentation_hash=content_hash(presentation.to_dict()),
            implementation_hash=implementation["implementation_hash"],
            writer_task=writer_task,
            config=llm.config,
        )
        representation_rows = _representation_rows(domain, cases, trajectories, checkpoint)
        diagnostic_rows = _event_diagnostic_rows(domain, cases, trajectories, checkpoint)
        jobs, oracle_memories, oracle_evidence, witness_rows = _executor_jobs(
            domain,
            cases,
            artifacts["evidence_objects"],
            presentation_id=presentation.presentation_id,
            presentation_hash=content_hash(presentation.to_dict()),
            implementation_hash=implementation["implementation_hash"],
        )
        jobs = (*jobs, *baseline_jobs)
        frozen_rows = {
            "event_deltas": checkpoint["event_deltas"],
            "event_log": checkpoint["event_log"],
            "reduced_states": checkpoint["reduced_states"],
            "event_attempts": checkpoint["event_attempts"],
            "writer_resources": checkpoint["writer_resources"],
            "writer_contexts": checkpoint["writer_contexts"],
            "memories": [*artifacts["memory_rows"], *oracle_memories, *baseline_memories],
            "evidence": [*artifacts["evidence_rows"], *oracle_evidence, *baseline_evidence],
            "representation_metrics": representation_rows,
            "event_diagnostics": diagnostic_rows,
            "residual_witnesses": witness_rows,
            "executor_jobs": [_executor_job_row(job) for job in jobs],
        }
        frozen_files = _write_named_rows(run_dir, frozen_rows)
        manifest.update(
            {
                "status": "executor_plan_frozen",
                "writer_checkpoint_sha256": file_hash(checkpoint_path),
                "pre_executor_files": frozen_files,
                "residual_witness_count": len(witness_rows),
                "executor_job_count": len(jobs),
                "residual_witnesses_selected_before_executor_calls": True,
            }
        )
        write_json(manifest_path, manifest)
        trial_rows, executor_context_rows = _run_resumable_executor_jobs(
            llm,
            domain,
            jobs,
            run_dir=run_dir,
            executor_task=executor_task,
            executor_targets=executor_targets,
            batch_size=batch_size,
            seed=seed,
            presentation=presentation,
        )
        all_contexts = [*checkpoint["writer_contexts"], *executor_context_rows]
        final_rows = {
            **frozen_rows,
            "trials": trial_rows,
            "model_contexts": all_contexts,
        }
        files = _write_named_rows(run_dir, final_rows)
        if calls_path.is_file():
            call_count = _jsonl_count(calls_path)
            files["calls"] = {
                "path": calls_path.name,
                "sha256": file_hash(calls_path),
                "rows": call_count,
            }
        _validate_context_call_log_rows(all_contexts, calls_path)
        manifest.update(
            {
                "status": "completed",
                "finished_at": datetime.now().astimezone().isoformat(),
                "files": files,
                "counts": {name: int(info["rows"]) for name, info in files.items()},
            }
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


def event_sourcing_implementation(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    presentation_id: str,
    *,
    corpus_version: str | None = None,
) -> dict[str, Any]:
    capacity = _capacity_tokens(domain, corpus_version or domain.corpus.default_version)
    contract = {
        "implementation_id": IMPLEMENTATION_ID,
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "event_tool": event_tool(domain),
        "writer_instructions": {
            domain.corpus.case_id(case): event_writer_instruction(
                domain,
                case,
                capacity_tokens=capacity,
                presentation_id=presentation_id,
            )
            for case in cases
        },
        "reducer": {
            "issue": "create_active_record",
            "patch": "merge_named_fields_and_scope",
            "revoke": "set_status_revoked",
            "replace": "supersede_target_and_create_active_record",
            "retain_inactive_records": domain.event_sourcing.retain_inactive_records,
            "semantic_repair": False,
        },
        "identity_policy": "system_case_target_seed_block_event_index_v1",
        "reference_index": {"fields": [], "tokens": 0},
        "writer_visible_history": "compact_previous_state_plus_current_raw_block_only",
        "cumulative_event_log_model_visible": False,
        "failed_update": "atomic_empty_append_retain_previous_state_after_two_structural_attempts",
        "capacity_policy": "same_domain_primary_typed_state_capacity",
        "implementation_files_sha256": _implementation_files(
            domain, corpus_version or domain.corpus.default_version
        ),
    }
    return {**contract, "implementation_hash": content_hash(contract)}


def _event_manifest(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    options: Mapping[str, Any],
    config: Any,
    *,
    presentation_id: str,
    writer_targets: Sequence[str],
    executor_targets: Sequence[str],
    capacity_tokens: int,
    implementation: Mapping[str, Any],
    baseline_sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    writer_task = str(options.get("writer_task") or "writer")
    executor_task = str(options.get("executor_task") or "executor")
    writer_tool = event_tool(domain)
    writer_choice = _forced_tool_choice()
    writer_seed = int(options["seed"])
    writer_profiles = [
        {
            "role": "bounded_event_extractor",
            "effective_parameters": effective_behavioral_parameters(
                config,
                writer_task,
                overrides={
                    "temperature": 1.0,
                    "max_tokens": 4096,
                    "seed": writer_seed,
                    "tool_choice": writer_choice,
                },
                tools=[writer_tool],
                required_capabilities=("native_tools", "forced_tool_choice", "seed"),
            ),
        }
    ]
    from experiments.authorization_memory.surfaces import model_visible_tools

    presentation = domain.get_presentation(presentation_id)
    executor_profiles = [
        {
            "role": "authorization_executor",
            "effective_parameters": effective_behavioral_parameters(
                config,
                executor_task,
                overrides={"temperature": 1.0, "seed": writer_seed, "tool_choice": "auto"},
                tools=model_visible_tools(domain, presentation),
                required_capabilities=("native_tools", "seed"),
            ),
        }
    ]
    presentation = domain.get_presentation(presentation_id)
    manifest = {
        "status": "initialized",
        "started_at": datetime.now().astimezone().isoformat(),
        "finished_at": None,
        "domain_id": domain.domain_id,
        "domain_adapter_version": domain.adapter_version,
        "study": EVENT_SOURCING_STUDY_ID,
        "condition_id": EVENT_CONDITION_ID,
        "corpus_version": str(options["corpus_version"]),
        "case_ids": [domain.corpus.case_id(case) for case in cases],
        "seed": writer_seed,
        "presentation": presentation.to_dict(),
        "presentation_hash": content_hash(presentation.to_dict()),
        "schema_version": "bounded_event_sourcing_run_v2",
        "memory_implementation_id": IMPLEMENTATION_ID,
        "memory_implementation_hash": implementation["implementation_hash"],
        "implementation": copy.deepcopy(dict(implementation)),
        "baseline_replay": "fresh_current_executor_on_original_final_typed_evidence",
        "fairness": {
            "writer_visible_state": "exact_domain_typed_current_state",
            "writer_visible_capacity_tokens": capacity_tokens,
            "reference_index": {"fields": [], "tokens": 0},
            "cumulative_event_log_model_visible": False,
            "raw_block_boundaries_unchanged": True,
            "writer_output_limit": 4096,
        },
        "writer": {
            "task": writer_task,
            "targets": list(writer_targets),
            "seed": writer_seed,
            "temperature": 1.0,
            "max_tokens": 4096,
            "max_structural_attempts": 2,
            "target_routes": [
                target_route_manifest(
                    config,
                    writer_task,
                    target,
                    call_profiles=writer_profiles,
                )
                for target in writer_targets
            ],
        },
        "executor": {
            "task": executor_task,
            "targets": list(executor_targets),
            "seed": writer_seed,
            "temperature": 1.0,
            "max_tokens": config.task(executor_task).params.get("max_tokens"),
            "target_routes": [
                target_route_manifest(
                    config,
                    executor_task,
                    target,
                    call_profiles=executor_profiles,
                )
                for target in executor_targets
            ],
        },
        "source_runs": list(options.get("source_runs") or ()),
        "verified_baseline_sources": copy.deepcopy(list(baseline_sources)),
        "estimated_cost_usd": options.get("estimated_cost_usd"),
        "batch_size": options.get("batch_size") or config.batch_size,
        "command": str(options.get("command") or ""),
        "source_files": _source_files(domain, str(options["corpus_version"])),
        "git": git_info(),
        "runtime": runtime_info(),
        "artifact_schema_versions": {
            "event_log": EVENT_LOG_SCHEMA_VERSION,
            "event_deltas": EVENT_DELTA_SCHEMA_VERSION,
            "reduced_states": REDUCED_STATE_SCHEMA_VERSION,
            "writer_resources": RESOURCE_SCHEMA_VERSION,
            "event_diagnostics": DIAGNOSTIC_SCHEMA_VERSION,
        },
        "files": {},
    }

    manifest["run_plan"] = {
        key: copy.deepcopy(manifest[key])
        for key in (
            "schema_version",
            "domain_id",
            "domain_adapter_version",
            "study",
            "condition_id",
            "corpus_version",
            "case_ids",
            "seed",
            "presentation",
            "presentation_hash",
            "memory_implementation_id",
            "memory_implementation_hash",
            "implementation",
            "fairness",
            "writer",
            "executor",
            "source_files",
            "artifact_schema_versions",
            "baseline_replay",
        )
    }
    manifest["run_plan"]["baseline_sources"] = [
        {
            "manifest_sha256": row["manifest_sha256"],
            "writer_target_id": row["writer_target_id"],
            "compatibility": copy.deepcopy(row["compatibility"]),
            "final_evidence": [
                {key: item[key] for key in ("evidence_id", "memory_id", "case_id", "content_hash")}
                for item in row["final_evidence"]
            ],
            "files": {
                name: {key: entry[key] for key in ("sha256", "rows") if key in entry}
                for name, entry in row["files"].items()
            },
        }
        for row in baseline_sources
    ]
    manifest["run_plan_sha256"] = content_hash(manifest["run_plan"])
    return manifest


def _validate_resume_manifest(manifest: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    plan = manifest.get("run_plan")
    if not isinstance(plan, Mapping) or content_hash(plan) != manifest.get("run_plan_sha256"):
        raise ValueError("resume requires an intact portable event-sourcing run plan")
    if manifest.get("run_plan_sha256") != expected["run_plan_sha256"]:
        raise ValueError("resume routes, cases, sources, presentation or implementation changed")
    for key, value in plan.items():
        if key != "baseline_sources" and manifest.get(key) != value:
            raise ValueError(f"resume manifest differs from frozen plan: {key}")


def _verify_frozen_files(run_dir: Path, manifest: Mapping[str, Any]) -> None:
    from .runtime import _read_checkpoint

    for checkpoint_name in ("event_writer_checkpoint.json", "executor_checkpoint.json"):
        path = run_dir / checkpoint_name
        if path.is_file():
            _read_checkpoint(path)
    for group in ("pre_executor_files", "files"):
        for name, entry in manifest.get(group, {}).items():
            path = (run_dir / entry["path"]).resolve()
            if (
                not path.is_relative_to(run_dir)
                or not path.is_file()
                or file_hash(path) != entry["sha256"]
            ):
                raise ValueError(f"resume frozen artifact changed: {name}")
    digest = manifest.get("writer_checkpoint_sha256")
    if digest is not None and file_hash(run_dir / "event_writer_checkpoint.json") != digest:
        raise ValueError("resume writer checkpoint hash changed")


def _implementation_files(domain: AuthorizationMemoryDomain, corpus_version: str) -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    paths = set(domain.corpus.source_files(corpus_version))
    for directory in (
        "experiments/mitigations/event_sourcing",
        "experiments/authorization_memory",
        "src/eal_bench/llm",
        f"domains/{domain.domain_id}",
    ):
        paths.update((root / directory).rglob("*.py"))
    paths.update(
        root / name
        for name in (
            "domains/base.py",
            "domains/__init__.py",
            "domains/event_sourcing.py",
            "experiments/run.py",
            "experiments/mitigations/__init__.py",
            "pyproject.toml",
            "uv.lock",
        )
    )
    return {_portable_path(path): file_hash(path) for path in sorted(paths)}


def validate_routes(config: Any, options: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for role, required in (
        ("writer", {"native_tools", "forced_tool_choice", "seed"}),
        ("executor", {"native_tools", "seed"}),
    ):
        targets = _targets(options.get(f"{role}_targets"))
        if not targets or len(set(targets)) != len(targets):
            raise ValueError(f"event sourcing requires nonempty, unique {role} targets")
        task = str(options.get(f"{role}_task") or role)
        routes = []
        for target in targets:
            route = config.resolve_target(task, target=target)
            config.provider(route.provider)
            missing = required - route.capabilities
            if missing:
                raise ValueError(f"{role} target {target} lacks capabilities: {sorted(missing)}")
            routes.append(
                {
                    "target_id": target,
                    "provider": route.provider,
                    "requested_model": route.requested_model,
                    "resolved_model": route.resolved_model,
                    "request_parameters": route.request_parameters,
                }
            )
        result[role] = routes
    return result
