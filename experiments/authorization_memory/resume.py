from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from eal_bench.llm import LLM
from eal_bench.llm.logger import JSONLLogger

from domains.base import AuthorizationMemoryDomain

from .executor_plan import (
    PlannedExecutorCall,
    executor_plan_rows,
    planned_executor_calls,
)
from .persistence import content_hash, file_hash, jsonable, write_json, write_jsonl
from .pipeline import (
    _job_challenge_metadata,
    _score_executor_response,
    _study_job_model_context,
    calibrate_capacity,
    run_executor_jobs,
    validate_executor_job_surfaces,
)
from .provenance import with_response_model
from .runner import _record_response_models, _validate_model_context_call_log
from .schemas import (
    FrozenEvidence,
    MemoryArtifact,
    frozen_evidence_from_dict,
    memory_artifact_from_dict,
    memory_attempt_from_dict,
    memory_state_from_dict,
    model_context_from_dict,
)
from .study_engine import (
    PreparedExecution,
    _freeze_pre_execution_checkpoint,
    _manifest,
    prepare_execution,
)
from .study_plan import StudyPlan
from .surfaces import model_visible_tools


@dataclass(frozen=True)
class ResumeValidation:
    run_dir: Path
    manifest: Mapping[str, Any]
    calls: tuple[Mapping[str, Any], ...]
    planned: Mapping[str, PlannedExecutorCall]
    completed_call_ids: tuple[str, ...]
    missing_call_ids: tuple[str, ...]
    implementation_drift: tuple[str, ...]
    source_drift: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "passed",
            "run_dir": str(self.run_dir),
            "manifest_status": self.manifest.get("status"),
            "planned_executor_calls": len(self.planned),
            "completed_executor_calls": len(self.completed_call_ids),
            "missing_executor_calls": len(self.missing_call_ids),
            "all_saved_requests_match": True,
            "implementation_drift": list(self.implementation_drift),
            "source_drift": list(self.source_drift),
        }


@dataclass(frozen=True)
class WriterCheckpointValidation:
    run_dir: Path
    manifest: Mapping[str, Any]
    calls: tuple[Mapping[str, Any], ...]
    planned: Mapping[str, PlannedExecutorCall]
    prepared: PreparedExecution
    completed_call_ids: tuple[str, ...]
    missing_call_ids: tuple[str, ...]
    writer_call_count: int
    implementation_drift: tuple[str, ...]
    source_drift: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "passed",
            "run_dir": str(self.run_dir),
            "manifest_status": self.manifest.get("status"),
            "checkpoint_schema": "writer_execution_checkpoint_v1",
            "writer_calls_preserved": self.writer_call_count,
            "writer_trajectories_to_regenerate": 0,
            "planned_executor_calls": len(self.planned),
            "completed_executor_calls": len(self.completed_call_ids),
            "missing_executor_calls": len(self.missing_call_ids),
            "all_saved_requests_match": True,
            "deterministic_expansion_matches": True,
            "implementation_drift": list(self.implementation_drift),
            "source_drift": list(self.source_drift),
        }


def validate_writer_checkpoint_resume_fixture(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
    *,
    config: Any,
) -> dict[str, Any]:
    if not plan.writer_chains:
        return {"status": "not_applicable"}
    if plan.post_writer_reviewer is not None:
        return {"status": "not_resumable", "reason": "model-backed reviewer"}
    if not plan.validation_writer_bundles:
        raise ValueError("writer resume fixture requires an offline writer bundle")
    bundle = plan.validation_writer_bundles[0]
    memories = [
        item
        for item in plan.controlled_memories
        if isinstance(item, MemoryArtifact)
    ]
    memories.extend(bundle.memories)
    evidence = [*plan.source_evidence]
    evidence.extend(
        item
        for item in plan.controlled_memories
        if isinstance(item, FrozenEvidence)
    )
    evidence.extend(bundle.evidence)
    prepared = prepare_execution(
        domain,
        cases,
        plan,
        options,
        memories=memories,
        attempts=bundle.attempts,
        states=bundle.states,
        evidence=evidence,
        contexts=bundle.contexts,
        writer_evidence=bundle.evidence,
        reviewer_llm=None,
    )
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    executor_targets = _targets(options.get("executor_targets"))
    executor_runs = int(options.get("executor_runs", 1))
    seed = int(options.get("seed", 0))
    executor_task = str(options.get("executor_task") or "executor")
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
    if not planned:
        raise ValueError("writer resume fixture requires an executor plan")
    with TemporaryDirectory(prefix="writer-checkpoint-resume-") as directory:
        run_dir = Path(directory)
        calls_path = run_dir / "calls.jsonl"
        manifest_path = run_dir / "manifest.json"
        writer_call = {"call_id": "offline-writer-prefix", "fixture": True}
        write_jsonl(calls_path, (writer_call,))
        calibration = calibrate_capacity(
            domain,
            cases,
            corpus_version=str(options["corpus_version"]),
            presentation=presentation,
        )
        manifest = _manifest(
            domain,
            cases=cases,
            plan=plan,
            options=options,
            config=config,
            presentation=presentation,
            writer_task=str(options.get("writer_task") or "writer"),
            executor_task=executor_task,
            writer_targets=_targets(options.get("writer_targets")),
            executor_targets=executor_targets,
            calibration=calibration.to_dict(),
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
            config=config,
        )
        tools = list(model_visible_tools(domain, presentation))
        saved_calls = [writer_call]
        call_ids = list(planned)
        for call_id in call_ids[:-1]:
            item = planned[call_id]
            params = dict(item.executor.effective_parameters)
            params["tools"] = tools
            saved_calls.append(
                {
                    "call_id": call_id,
                    "task": "executor",
                    "target_id": item.target_id,
                    "provider": item.executor.provider,
                    "requested_model": item.executor.requested_model,
                    "resolved_model": item.executor.resolved_model,
                    "response_model": item.executor.resolved_model,
                    "request": {
                        "messages": list(item.messages),
                        "tools": tools,
                        "params": params,
                        "required_capabilities": ["native_tools", "seed"],
                    },
                    "response": {"content": None, "tool_calls": []},
                    "error": None,
                }
            )
        write_jsonl(calls_path, saved_calls)
        validation = validate_writer_checkpoint_resume(
            domain,
            cases,
            plan,
            {**dict(options), "resume_run": str(run_dir)},
            config=config,
        )
    if len(validation.missing_call_ids) != 1:
        raise AssertionError("writer resume fixture did not preserve one missing call")
    return {
        "status": "passed",
        "checkpoint_schema": "writer_execution_checkpoint_v1",
        "writer_calls_preserved": validation.writer_call_count,
        "completed_executor_calls_preserved": len(validation.completed_call_ids),
        "missing_executor_calls": 1,
        "writer_trajectories_regenerated": 0,
        "all_saved_requests_match": True,
        "deterministic_expansion_matches": True,
    }


def prepare_provider_error_resume(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
    *,
    config: Any,
) -> Path:
    """Create an immutable continuation containing only unfinished provider calls."""
    source = Path(str(options.get("resume_run") or "")).expanduser().resolve()
    manifest_path = source / "manifest.json"
    calls_path = source / "calls.jsonl"
    trials_path = source / "trials.jsonl"
    if not all(path.is_file() for path in (manifest_path, calls_path, trials_path)):
        raise ValueError("provider-error retry requires a completed executor run")
    manifest = _read_json_object(manifest_path, "provider-error source manifest")
    if manifest.get("status") != "completed":
        raise ValueError("provider-error retry requires a completed source run")
    if not plan.executor_only or plan.writer_chains or plan.finalizer is not None:
        raise ValueError("provider-error retry supports executor-only plans")

    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    executor_targets = _targets(options.get("executor_targets"))
    executor_runs = int(options.get("executor_runs", 1))
    seed = int(options.get("seed", 0))
    jobs = plan.validate(domain, cases, options)
    planned = planned_executor_calls(
        domain,
        jobs,
        study_id=plan.study_id,
        executor_task=str(options.get("executor_task") or "executor"),
        executor_targets=executor_targets,
        executor_runs=executor_runs,
        seed=seed,
        presentation=presentation,
        config=config,
        pressure_specs=plan.pressure_specs,
    )
    _require_equal(manifest.get("domain_id"), domain.domain_id, "domain")
    _require_equal(manifest.get("study"), plan.study_id, "study")
    _require_equal(
        manifest.get("corpus_version"), options.get("corpus_version"), "corpus version"
    )
    _require_equal(
        manifest.get("case_ids"),
        [domain.corpus.case_id(case) for case in cases],
        "case IDs",
    )
    _require_equal(
        manifest.get("presentation_hash"),
        content_hash(presentation.to_dict()),
        "presentation hash",
    )
    _require_equal(manifest.get("seed"), seed, "seed")
    executor_manifest = manifest.get("executor")
    if not isinstance(executor_manifest, Mapping):
        raise ValueError("provider-error source has no executor object")
    _require_equal(
        executor_manifest.get("targets"), list(executor_targets), "executor targets"
    )
    _require_equal(executor_manifest.get("runs"), executor_runs, "executor runs")

    tools = list(model_visible_tools(domain, presentation))
    grouped: dict[str, list[dict[str, Any]]] = {}
    source_calls = _read_jsonl_objects(calls_path, "provider-error source calls")
    for row in source_calls:
        call_id = row.get("call_id")
        if not isinstance(call_id, str) or call_id not in planned:
            raise ValueError("provider-error source contains an unplanned call")
        _validate_saved_call(row, planned[call_id], tools=tools)
        grouped.setdefault(call_id, []).append(row)
    if set(grouped) != set(planned):
        raise ValueError("provider-error source call IDs differ from the frozen plan")

    completed: list[dict[str, Any]] = []
    failed_call_ids: list[str] = []
    for call_id in planned:
        successes = [row for row in grouped[call_id] if row.get("error") is None]
        if len(successes) > 1:
            raise ValueError("provider-error source repeats a successful logical call")
        if successes:
            completed.append(successes[0])
        else:
            failed_call_ids.append(call_id)
    if not failed_call_ids:
        raise ValueError("provider-error source has no failed logical calls")

    source_trials = _read_jsonl_objects(trials_path, "provider-error source trials")
    failed_trial_call_ids = {
        str(row.get("metadata", {}).get("core", {}).get("call_id"))
        for row in source_trials
        if row.get("provider_error") is not None
    }
    if failed_trial_call_ids != set(failed_call_ids):
        raise ValueError("provider-error trials do not match failed call-log entries")

    destination = source.with_name(source.name + "__provider-error-continuation")
    if destination.exists():
        raise ValueError(f"provider-error continuation already exists: {destination}")
    destination.mkdir(parents=False)
    source_calls_copy = destination / "source_calls.jsonl"
    shutil.copy2(calls_path, source_calls_copy)
    write_jsonl(destination / "calls.jsonl", completed)
    derived = dict(manifest)
    derived.update(
        {
            "status": "failed",
            "finished_at": None,
            "batch_size": int(options.get("batch_size") or manifest["batch_size"]),
            "error": "technical continuation prepared for provider failures",
            "files": {},
            "counts": {"calls": len(completed)},
            "technical_continuation": {
                "schema_version": "provider_error_continuation_v1",
                "source_run": str(source),
                "source_manifest_sha256": file_hash(manifest_path),
                "source_calls_sha256": file_hash(source_calls_copy),
                "source_trials_sha256": file_hash(trials_path),
                "source_call_records": len(source_calls),
                "retained_successful_calls": len(completed),
                "provider_error_calls_to_retry": len(failed_call_ids),
                "failed_call_ids_sha256": content_hash(failed_call_ids),
                "successful_outcomes_rerun": 0,
                "network_request_made": False,
            },
        }
    )
    write_json(destination / "manifest.json", derived)
    return destination


def validate_executor_only_resume(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
    *,
    config: Any,
    require_missing: bool = True,
) -> ResumeValidation:
    run_dir = Path(str(options.get("resume_run") or "")).expanduser().resolve()
    if not run_dir.is_dir():
        raise ValueError(f"resume run directory does not exist: {run_dir}")
    manifest_path = run_dir / "manifest.json"
    calls_path = run_dir / "calls.jsonl"
    if not manifest_path.is_file() or not calls_path.is_file():
        raise ValueError("resume run requires manifest.json and calls.jsonl")
    manifest = _read_json_object(manifest_path, "resume manifest")
    calls = tuple(_read_jsonl_objects(calls_path, "resume call log"))

    if not plan.executor_only or plan.writer_chains:
        raise ValueError("resume currently supports executor-only study plans")
    if plan.job_builder is not None or plan.post_writer_builder is not None:
        raise ValueError("resume does not support dynamically expanded study plans")
    if plan.finalizer is not None:
        raise ValueError("resume does not support study finalizers")
    if manifest.get("status") not in {"running", "failed", "resuming"}:
        raise ValueError("only interrupted or failed runs can be resumed")

    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    executor_targets = _targets(options.get("executor_targets"))
    executor_runs = int(options.get("executor_runs", 1))
    seed = int(options.get("seed", 0))
    executor_task = str(options.get("executor_task") or "executor")
    jobs = plan.validate(domain, cases, options)
    if not jobs:
        raise ValueError("resume plan has no executor jobs")

    _require_equal(manifest.get("domain_id"), domain.domain_id, "domain")
    _require_equal(manifest.get("study"), plan.study_id, "study")
    _require_equal(
        manifest.get("corpus_version"),
        str(options.get("corpus_version") or ""),
        "corpus version",
    )
    _require_equal(
        manifest.get("case_ids"),
        [domain.corpus.case_id(case) for case in cases],
        "case IDs",
    )
    _require_equal(
        manifest.get("presentation_hash"),
        content_hash(presentation.to_dict()),
        "presentation hash",
    )
    _require_equal(manifest.get("seed"), seed, "seed")
    _require_equal(
        manifest.get("capacity_tier"),
        str(options.get("capacity_tier") or "primary"),
        "capacity tier",
    )
    expected_batch_size = options.get("batch_size") or config.batch_size
    _require_equal(manifest.get("batch_size"), expected_batch_size, "batch size")
    executor_manifest = manifest.get("executor")
    if not isinstance(executor_manifest, Mapping):
        raise ValueError("resume manifest has no executor object")
    _require_equal(executor_manifest.get("active"), True, "executor active flag")
    _require_equal(executor_manifest.get("task"), executor_task, "executor task")
    _require_equal(
        executor_manifest.get("targets"), list(executor_targets), "executor targets"
    )
    _require_equal(executor_manifest.get("runs"), executor_runs, "executor runs")
    _require_equal(
        manifest.get("capacity"),
        calibrate_capacity(
            domain,
            cases,
            corpus_version=str(options["corpus_version"]),
            presentation=presentation,
        ).to_dict(),
        "capacity calibration",
    )
    _require_equal(
        manifest.get("corpus_provenance"),
        dict(domain.corpus.provenance(str(options["corpus_version"]))),
        "corpus provenance",
    )

    planned = planned_executor_calls(
        domain,
        jobs,
        study_id=plan.study_id,
        executor_task=executor_task,
        executor_targets=executor_targets,
        executor_runs=executor_runs,
        seed=seed,
        presentation=presentation,
        config=config,
        pressure_specs=plan.pressure_specs,
    )
    tools = list(model_visible_tools(domain, presentation))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in calls:
        call_id = row.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("resume call log contains a missing call ID")
        expected = planned.get(call_id)
        if expected is None:
            raise ValueError(f"saved call is outside the frozen plan: {call_id}")
        _validate_saved_call(row, expected, tools=tools)
        grouped.setdefault(call_id, []).append(row)
    completed: list[str] = []
    for call_id, rows in grouped.items():
        successes = [row for row in rows if row.get("error") is None]
        if len(successes) > 1:
            raise ValueError(f"resume repeats a successful logical call: {call_id}")
        if successes:
            completed.append(call_id)
    missing = tuple(call_id for call_id in planned if call_id not in completed)
    if not missing and require_missing:
        recoverable_finalization = (
            manifest.get("status") == "failed"
            and isinstance(manifest.get("technical_continuation"), Mapping)
            and str(manifest.get("error") or "").startswith(
                "ValueError: duplicate resume call ID:"
            )
        )
        if not recoverable_finalization:
            raise ValueError("resume run has no missing executor calls")

    expected_missing = options.get("expected_missing_calls")
    if expected_missing is not None and int(expected_missing) != len(missing):
        raise ValueError(
            f"resume expected {expected_missing} missing calls, found {len(missing)}"
        )
    implementation_drift = _file_drift(
        manifest.get("implementation_files"), Path.cwd()
    )
    source_drift = _file_drift(manifest.get("source_files"), None)
    return ResumeValidation(
        run_dir=run_dir,
        manifest=manifest,
        calls=calls,
        planned=planned,
        completed_call_ids=tuple(completed),
        missing_call_ids=missing,
        implementation_drift=implementation_drift,
        source_drift=source_drift,
    )


def validate_writer_checkpoint_resume(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
    *,
    config: Any,
    require_missing: bool = True,
) -> WriterCheckpointValidation:
    run_dir = Path(str(options.get("resume_run") or "")).expanduser().resolve()
    if not run_dir.is_dir():
        raise ValueError(f"resume run directory does not exist: {run_dir}")
    manifest_path = run_dir / "manifest.json"
    calls_path = run_dir / "calls.jsonl"
    if not manifest_path.is_file() or not calls_path.is_file():
        raise ValueError("resume run requires manifest.json and calls.jsonl")
    manifest = _read_json_object(manifest_path, "resume manifest")
    calls = tuple(_read_jsonl_objects(calls_path, "resume call log"))
    if not plan.writer_chains or plan.writer_only:
        raise ValueError("writer checkpoint resume requires writer and executor calls")
    if plan.post_writer_reviewer is not None:
        raise ValueError("reviewer-backed writer checkpoints cannot be resumed")
    if manifest.get("status") not in {
        "execution_frozen",
        "running",
        "failed",
        "resuming",
    }:
        raise ValueError("only frozen, interrupted, or failed runs can be resumed")

    checkpoint = manifest.get("checkpoint")
    if not isinstance(checkpoint, Mapping):
        raise ValueError("resume manifest has no writer checkpoint")
    _require_equal(
        checkpoint.get("schema_version"),
        "writer_execution_checkpoint_v1",
        "checkpoint schema",
    )
    _require_equal(
        checkpoint.get("writer_calls_immutable"), True, "writer immutability flag"
    )
    _require_equal(
        checkpoint.get("selected_before_executor_calls"),
        True,
        "pre-execution selection flag",
    )
    checkpoint_files = checkpoint.get("files")
    if not isinstance(checkpoint_files, Mapping):
        raise ValueError("writer checkpoint has no file map")
    required_files = (
        "memories",
        "memory_attempts",
        "memory_states",
        "evidence",
        "writer_bundle_memories",
        "writer_bundle_evidence",
        "writer_model_contexts",
        "executor_plan",
        "writer_calls",
    )
    saved_rows: dict[str, list[dict[str, Any]]] = {}
    for name in required_files:
        entry = checkpoint_files.get(name)
        if not isinstance(entry, Mapping):
            raise ValueError(f"writer checkpoint is missing {name!r}")
        path = run_dir / str(entry.get("path") or "")
        if not path.is_file() or file_hash(path) != entry.get("sha256"):
            raise ValueError(f"writer checkpoint artifact changed: {name}")
        rows = _read_jsonl_objects(path, f"writer checkpoint {name}")
        _require_equal(len(rows), entry.get("rows"), f"checkpoint {name} rows")
        saved_rows[name] = rows

    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    writer_targets = _targets(options.get("writer_targets"))
    executor_targets = _targets(options.get("executor_targets"))
    executor_runs = int(options.get("executor_runs", 1))
    seed = int(options.get("seed", 0))
    writer_task = str(options.get("writer_task") or "writer")
    executor_task = str(options.get("executor_task") or "executor")
    _validate_resume_configuration(
        domain,
        cases,
        manifest,
        options,
        config=config,
        presentation=presentation,
        executor_targets=executor_targets,
        executor_runs=executor_runs,
        seed=seed,
        executor_task=executor_task,
    )
    _require_equal(manifest.get("study"), plan.study_id, "study")
    writer_manifest = manifest.get("writer")
    if not isinstance(writer_manifest, Mapping):
        raise ValueError("resume manifest has no writer object")
    _require_equal(writer_manifest.get("active"), True, "writer active flag")
    _require_equal(writer_manifest.get("task"), writer_task, "writer task")
    _require_equal(
        writer_manifest.get("targets"), list(writer_targets), "writer targets"
    )
    _require_equal(
        writer_manifest.get("max_attempts"),
        int(options.get("writer_max_attempts", 2)),
        "writer maximum attempts",
    )
    _require_equal(
        writer_manifest.get("route_timeout_seconds"),
        int(options.get("writer_route_timeout_seconds", 3600)),
        "writer route timeout",
    )

    writer_bundle_memories = tuple(
        memory_artifact_from_dict(row)
        for row in saved_rows["writer_bundle_memories"]
    )
    writer_bundle_evidence = tuple(
        frozen_evidence_from_dict(row)
        for row in saved_rows["writer_bundle_evidence"]
    )
    attempts = tuple(
        memory_attempt_from_dict(row) for row in saved_rows["memory_attempts"]
    )
    states = tuple(
        memory_state_from_dict(row) for row in saved_rows["memory_states"]
    )
    writer_contexts = tuple(
        model_context_from_dict(row) for row in saved_rows["writer_model_contexts"]
    )
    base_evidence = [*plan.source_evidence]
    base_evidence.extend(
        item
        for item in plan.controlled_memories
        if isinstance(item, FrozenEvidence)
    )
    base_evidence.extend(writer_bundle_evidence)
    prepared = prepare_execution(
        domain,
        cases,
        plan,
        options,
        memories=writer_bundle_memories,
        attempts=attempts,
        states=states,
        evidence=base_evidence,
        contexts=writer_contexts,
        writer_evidence=writer_bundle_evidence,
        reviewer_llm=None,
    )
    expected_rows: dict[str, Sequence[Any]] = {
        "memories": prepared.memories,
        "memory_attempts": prepared.attempts,
        "memory_states": prepared.states,
        "evidence": prepared.evidence,
        "writer_bundle_memories": prepared.writer_bundle.memories,
        "writer_bundle_evidence": prepared.writer_bundle.evidence,
        "writer_model_contexts": prepared.writer_bundle.contexts,
        **plan.artifact_rows,
        **prepared.dynamic_rows,
    }
    for name, values in expected_rows.items():
        entry = checkpoint_files.get(name)
        if not isinstance(entry, Mapping):
            raise ValueError(f"writer checkpoint is missing {name!r}")
        path = run_dir / str(entry["path"])
        actual = _read_jsonl_objects(path, f"writer checkpoint {name}")
        _require_equal(actual, jsonable(values), f"deterministic {name}")

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
    _require_equal(
        saved_rows["executor_plan"],
        jsonable(executor_plan_rows(planned)),
        "frozen executor plan",
    )
    _require_equal(
        checkpoint.get("executor_calls"), len(planned), "executor call count"
    )
    _require_equal(
        checkpoint.get("executor_call_ids_sha256"),
        content_hash(list(planned)),
        "executor call ID hash",
    )

    writer_calls = tuple(saved_rows["writer_calls"])
    if tuple(calls[: len(writer_calls)]) != writer_calls:
        raise ValueError("resume call log does not preserve the frozen writer prefix")
    tools = list(model_visible_tools(domain, presentation))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in calls[len(writer_calls) :]:
        call_id = row.get("call_id")
        if not isinstance(call_id, str) or call_id not in planned:
            raise ValueError("resume call log contains an unplanned executor call")
        _validate_saved_call(row, planned[call_id], tools=tools)
        grouped.setdefault(call_id, []).append(dict(row))
    completed: list[str] = []
    for call_id, rows in grouped.items():
        successes = [row for row in rows if row.get("error") is None]
        if len(successes) > 1:
            raise ValueError(f"resume repeats a successful logical call: {call_id}")
        if successes:
            completed.append(call_id)
    missing = tuple(call_id for call_id in planned if call_id not in completed)
    if not missing and require_missing:
        raise ValueError("resume run has no missing executor calls")
    expected_missing = options.get("expected_missing_calls")
    if expected_missing is not None and int(expected_missing) != len(missing):
        raise ValueError(
            f"resume expected {expected_missing} missing calls, found {len(missing)}"
        )
    return WriterCheckpointValidation(
        run_dir=run_dir,
        manifest=manifest,
        calls=calls,
        planned=planned,
        prepared=prepared,
        completed_call_ids=tuple(completed),
        missing_call_ids=missing,
        writer_call_count=len(writer_calls),
        implementation_drift=_file_drift(
            manifest.get("implementation_files"), Path.cwd()
        ),
        source_drift=_file_drift(manifest.get("source_files"), None),
    )


def resume_executor_only_study_plan(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
) -> Path:
    calls_path = Path(str(options["resume_run"])).expanduser().resolve() / "calls.jsonl"
    llm = LLM(logger=JSONLLogger(calls_path))
    validation = validate_executor_only_resume(
        domain,
        cases,
        plan,
        options,
        config=llm.config,
    )
    run_dir = validation.run_dir
    manifest_path = run_dir / "manifest.json"
    manifest = dict(validation.manifest)
    resumed_at = datetime.now().astimezone().isoformat()
    manifest.update(
        {
            "status": "resuming",
            "finished_at": None,
            "resume": {
                **validation.to_dict(),
                "resumed_at": resumed_at,
                "resume_command": str(options.get("command") or ""),
                "total_cost_ceiling_usd": options.get("estimated_cost_usd"),
            },
        }
    )
    write_json(manifest_path, manifest)
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    missing_jobs = tuple(
        replace(
            validation.planned[call_id].job,
            executor_target_id=validation.planned[call_id].target_id,
            executor_run_id=validation.planned[call_id].executor_run_id,
            executor_seed=validation.planned[call_id].executor_seed,
        )
        for call_id in validation.missing_call_ids
    )
    try:
        run_executor_jobs(
            llm,
            domain,
            missing_jobs,
            study_id=plan.study_id,
            executor_task=str(options.get("executor_task") or "executor"),
            executor_targets=_targets(options.get("executor_targets")),
            executor_runs=int(options.get("executor_runs", 1)),
            batch_size=options.get("batch_size"),
            seed=int(options.get("seed", 0)),
            presentation=presentation,
            pressure_specs=plan.pressure_specs,
        )
        final_validation = validate_executor_only_resume(
            domain,
            cases,
            plan,
            {**dict(options), "expected_missing_calls": None},
            config=llm.config,
            require_missing=False,
        )
        if final_validation.missing_call_ids:
            raise ValueError("resume finished with missing executor calls")
    except BaseException as exc:
        manifest.update(
            {
                "status": "failed",
                "finished_at": datetime.now().astimezone().isoformat(),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        write_json(manifest_path, manifest)
        raise

    calls = tuple(_read_jsonl_objects(calls_path, "completed resume call log"))
    trials, contexts = _reconstruct_trials_and_contexts(
        domain,
        plan,
        final_validation.planned,
        calls,
        presentation=presentation,
    )
    _validate_model_context_call_log(contexts, calls_path)
    files, counts = _persist_executor_only_artifacts(
        run_dir,
        plan,
        trials=trials,
        contexts=contexts,
    )
    call_count = len(calls)
    counts["calls"] = call_count
    files["calls"] = {
        "path": calls_path.name,
        "sha256": file_hash(calls_path),
        "rows": call_count,
    }
    manifest["model_visible_executor_surfaces"] = validate_executor_job_surfaces(
        domain,
        tuple(item.job for item in final_validation.planned.values()),
        presentation=presentation,
        pressure_specs=plan.pressure_specs,
    )
    manifest.update(
        {
            "status": "completed",
            "finished_at": datetime.now().astimezone().isoformat(),
            "files": files,
            "counts": counts,
        }
    )
    resume_metadata = dict(manifest.get("resume") or {})
    resume_metadata.update(
        {
            "completed_after_resume": len(calls),
            "new_executor_calls": len(validation.missing_call_ids),
            "all_saved_requests_match": True,
            "completed_at": manifest["finished_at"],
        }
    )
    manifest["resume"] = resume_metadata
    executor_manifest = manifest.get("executor")
    if isinstance(executor_manifest, dict):
        _record_response_models(
            executor_manifest.get("target_routes", []),
            (trial.executor for trial in trials),
        )
    write_json(manifest_path, manifest)
    return run_dir


def resume_writer_checkpoint_study_plan(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    plan: StudyPlan,
    options: Mapping[str, Any],
) -> Path:
    run_dir = Path(str(options["resume_run"])).expanduser().resolve()
    calls_path = run_dir / "calls.jsonl"
    llm = LLM(logger=JSONLLogger(calls_path))
    validation = validate_writer_checkpoint_resume(
        domain,
        cases,
        plan,
        options,
        config=llm.config,
    )
    manifest_path = run_dir / "manifest.json"
    manifest = dict(validation.manifest)
    resumed_at = datetime.now().astimezone().isoformat()
    manifest.update(
        {
            "status": "resuming",
            "finished_at": None,
            "resume": {
                **validation.to_dict(),
                "resumed_at": resumed_at,
                "resume_command": str(options.get("command") or ""),
                "total_cost_ceiling_usd": options.get("estimated_cost_usd"),
            },
        }
    )
    write_json(manifest_path, manifest)
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    missing_jobs = tuple(
        replace(
            validation.planned[call_id].job,
            executor_target_id=validation.planned[call_id].target_id,
            executor_run_id=validation.planned[call_id].executor_run_id,
            executor_seed=validation.planned[call_id].executor_seed,
        )
        for call_id in validation.missing_call_ids
    )
    try:
        run_executor_jobs(
            llm,
            domain,
            missing_jobs,
            study_id=plan.study_id,
            executor_task=str(options.get("executor_task") or "executor"),
            executor_targets=_targets(options.get("executor_targets")),
            executor_runs=int(options.get("executor_runs", 1)),
            batch_size=options.get("batch_size"),
            seed=int(options.get("seed", 0)),
            presentation=presentation,
            pressure_specs=plan.pressure_specs,
        )
        final_validation = validate_writer_checkpoint_resume(
            domain,
            cases,
            plan,
            {**dict(options), "expected_missing_calls": None},
            config=llm.config,
            require_missing=False,
        )
        if final_validation.missing_call_ids:
            raise ValueError("resume finished with missing executor calls")
    except BaseException as exc:
        manifest.update(
            {
                "status": "failed",
                "finished_at": datetime.now().astimezone().isoformat(),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        write_json(manifest_path, manifest)
        raise

    calls = tuple(_read_jsonl_objects(calls_path, "completed resume call log"))
    executor_calls = calls[final_validation.writer_call_count :]
    trials, executor_contexts = _reconstruct_trials_and_contexts(
        domain,
        plan,
        final_validation.planned,
        executor_calls,
        presentation=presentation,
    )
    contexts = [*final_validation.prepared.contexts, *executor_contexts]
    _validate_model_context_call_log(contexts, calls_path)
    files, counts = _persist_writer_checkpoint_artifacts(
        run_dir,
        plan,
        final_validation,
        trials=trials,
        contexts=contexts,
    )
    counts["calls"] = len(calls)
    files["calls"] = {
        "path": calls_path.name,
        "sha256": file_hash(calls_path),
        "rows": len(calls),
    }
    manifest["model_visible_executor_surfaces"] = validate_executor_job_surfaces(
        domain,
        final_validation.prepared.jobs,
        presentation=presentation,
        pressure_specs=plan.pressure_specs,
    )
    manifest.update(
        {
            "status": "completed",
            "finished_at": datetime.now().astimezone().isoformat(),
            "files": files,
            "counts": counts,
        }
    )
    resume_metadata = dict(manifest.get("resume") or {})
    resume_metadata.update(
        {
            "completed_after_resume": len(final_validation.planned),
            "new_executor_calls": len(validation.missing_call_ids),
            "writer_calls_repeated": 0,
            "all_saved_requests_match": True,
            "deterministic_expansion_matches": True,
            "completed_at": manifest["finished_at"],
        }
    )
    manifest["resume"] = resume_metadata
    writer_manifest = manifest.get("writer")
    if isinstance(writer_manifest, dict):
        _record_response_models(
            writer_manifest.get("target_routes", []),
            (attempt.writer for attempt in final_validation.prepared.attempts),
        )
    executor_manifest = manifest.get("executor")
    if isinstance(executor_manifest, dict):
        _record_response_models(
            executor_manifest.get("target_routes", []),
            (trial.executor for trial in trials),
        )
    write_json(manifest_path, manifest)
    return run_dir


def _validate_saved_call(
    row: Mapping[str, Any],
    expected: PlannedExecutorCall,
    *,
    tools: Sequence[Mapping[str, Any]],
) -> None:
    for key, value in (
        ("task", "executor"),
        ("target_id", expected.target_id),
        ("provider", expected.executor.provider),
        ("requested_model", expected.executor.requested_model),
        ("resolved_model", expected.executor.resolved_model),
    ):
        _require_equal(row.get(key), value, f"saved call {key}")
    request = row.get("request")
    if not isinstance(request, Mapping):
        raise ValueError(f"saved call {expected.call_id} has no request object")
    _require_equal(
        request.get("messages"), list(expected.messages), "saved request messages"
    )
    _require_equal(request.get("tools"), list(tools), "saved request tools")
    params = request.get("params")
    if not isinstance(params, Mapping):
        raise ValueError(f"saved call {expected.call_id} has no parameters")
    expected_params = expected.executor.effective_parameters
    for key in ("max_tokens", "temperature", "seed", "tool_choice"):
        _require_equal(params.get(key), expected_params.get(key), f"saved {key}")
    _require_equal(params.get("tools"), list(tools), "saved parameter tools")
    _require_equal(
        request.get("required_capabilities"),
        ["native_tools", "seed"],
        "saved required capabilities",
    )
    if row.get("error") is None and not isinstance(row.get("response"), Mapping):
        raise ValueError(f"saved call {expected.call_id} has no response")


def _reconstruct_trials_and_contexts(
    domain: AuthorizationMemoryDomain,
    plan: StudyPlan,
    planned: Mapping[str, PlannedExecutorCall],
    calls: Sequence[Mapping[str, Any]],
    *,
    presentation: Any,
) -> tuple[list[Any], list[Any]]:
    pressure_by_id = {item.pressure_id: item for item in plan.pressure_specs}
    presentation_hash = content_hash(presentation.to_dict())
    trials = []
    contexts = []
    by_id = {str(row["call_id"]): row for row in calls}
    for call_id, item in planned.items():
        row = by_id[call_id]
        job = item.job
        pressure = (
            pressure_by_id[job.pressure_id]
            if job.pressure_id is not None
            else None
        )
        context = _study_job_model_context(
            domain,
            job,
            messages=item.messages,
            tools=model_visible_tools(domain, presentation),
            executor=item.executor,
            executor_run_id=item.executor_run_id,
            call_id=call_id,
            trial_id=item.trial_id,
            study_id=plan.study_id,
            pressure=pressure,
            presentation=presentation,
            presentation_hash=presentation_hash,
        )
        response_model = row.get("response_model")
        context = replace(
            context,
            model=with_response_model(context.model, response_model),
        )
        contexts.append(context)
        response = _saved_response(row)
        trials.append(
            _score_executor_response(
                domain,
                job.case,
                job.probe,
                job.evidence,
                response,
                item.executor,
                executor_run_id=item.executor_run_id,
                seed=item.executor_seed,
                trial_id=item.trial_id,
                call_id=call_id,
                model_context_id=context.context_id,
                presentation=presentation,
                presentation_hash=presentation_hash,
                oracle_block_index=job.oracle_block_index,
                study_id=plan.study_id,
                study_metadata={
                    "job_id": job.job_id,
                    "pressure_id": job.pressure_id,
                    **dict(job.metadata),
                },
                challenge_pressure_id=(
                    pressure.challenge_pressure_id if pressure is not None else None
                ),
                challenge_metadata=_job_challenge_metadata(
                    domain, job, pressure=pressure
                ),
            )
        )
    return trials, contexts


def _saved_response(row: Mapping[str, Any]) -> Any:
    error = row.get("error")
    if error is not None:
        return RuntimeError(str(error))
    saved = row.get("response")
    if not isinstance(saved, Mapping):
        raise ValueError(f"call {row.get('call_id')} has no saved response")
    return {
        "model": row.get("response_model"),
        "choices": [
            {
                "message": {
                    "content": saved.get("content"),
                    "tool_calls": saved.get("tool_calls") or [],
                },
                "finish_reason": saved.get("finish_reason"),
            }
        ],
    }


def _persist_executor_only_artifacts(
    run_dir: Path,
    plan: StudyPlan,
    *,
    trials: Sequence[Any],
    contexts: Sequence[Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    memories = [
        item for item in plan.controlled_memories if isinstance(item, MemoryArtifact)
    ]
    evidence = [
        *plan.source_evidence,
        *(
            item
            for item in plan.controlled_memories
            if isinstance(item, FrozenEvidence)
        ),
    ]
    rows: dict[str, tuple[Path, Sequence[Any]]] = {
        "memories": (run_dir / "memories.jsonl", memories),
        "evidence": (run_dir / "evidence.jsonl", evidence),
        "trials": (run_dir / "trials.jsonl", trials),
        "model_contexts": (run_dir / "model_contexts.jsonl", contexts),
        **{
            name: (run_dir / f"{name}.jsonl", values)
            for name, values in plan.artifact_rows.items()
        },
    }
    for name, filename in plan.artifact_paths.items():
        if name not in rows:
            raise ValueError(f"artifact path {name!r} has no corresponding rows")
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
    for alias, target in plan.file_aliases.items():
        if target not in files:
            raise ValueError(f"file alias {alias!r} refers to missing artifact {target!r}")
        files[alias] = dict(files[target])
    return files, counts


def _persist_writer_checkpoint_artifacts(
    run_dir: Path,
    plan: StudyPlan,
    validation: WriterCheckpointValidation,
    *,
    trials: Sequence[Any],
    contexts: Sequence[Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    prepared = validation.prepared
    rows: dict[str, tuple[Path, Sequence[Any]]] = {
        "memories": (run_dir / "memories.jsonl", prepared.memories),
        "memory_attempts": (
            run_dir / "memory_attempts.jsonl",
            prepared.attempts,
        ),
        "memory_states": (run_dir / "memory_states.jsonl", prepared.states),
        "evidence": (run_dir / "evidence.jsonl", prepared.evidence),
        "trials": (run_dir / "trials.jsonl", trials),
        "model_contexts": (run_dir / "model_contexts.jsonl", contexts),
        **{
            name: (run_dir / f"{name}.jsonl", values)
            for name, values in {
                **plan.artifact_rows,
                **prepared.dynamic_rows,
            }.items()
        },
    }
    for name, filename in plan.artifact_paths.items():
        if name not in rows:
            raise ValueError(f"artifact path {name!r} has no corresponding rows")
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
    checkpoint = validation.manifest["checkpoint"]
    checkpoint_files = checkpoint["files"]
    for name in (
        "writer_bundle_memories",
        "writer_bundle_evidence",
        "writer_model_contexts",
        "executor_plan",
        "writer_calls",
    ):
        entry = checkpoint_files[name]
        path = run_dir / str(entry["path"])
        if file_hash(path) != entry["sha256"]:
            raise ValueError(f"writer checkpoint artifact changed: {name}")
        files[name] = dict(entry)
        counts[name] = int(entry["rows"])
    for alias, target in plan.file_aliases.items():
        if target not in files:
            raise ValueError(f"file alias {alias!r} refers to missing artifact {target!r}")
        files[alias] = dict(files[target])
    return files, counts


def _validate_resume_configuration(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    manifest: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    config: Any,
    presentation: Any,
    executor_targets: Sequence[str],
    executor_runs: int,
    seed: int,
    executor_task: str,
) -> None:
    _require_equal(manifest.get("domain_id"), domain.domain_id, "domain")
    _require_equal(
        manifest.get("corpus_version"),
        str(options.get("corpus_version") or ""),
        "corpus version",
    )
    _require_equal(
        manifest.get("case_ids"),
        [domain.corpus.case_id(case) for case in cases],
        "case IDs",
    )
    _require_equal(
        manifest.get("presentation_hash"),
        content_hash(presentation.to_dict()),
        "presentation hash",
    )
    _require_equal(manifest.get("seed"), seed, "seed")
    _require_equal(
        manifest.get("capacity_tier"),
        str(options.get("capacity_tier") or "primary"),
        "capacity tier",
    )
    expected_batch_size = options.get("batch_size") or config.batch_size
    _require_equal(manifest.get("batch_size"), expected_batch_size, "batch size")
    executor_manifest = manifest.get("executor")
    if not isinstance(executor_manifest, Mapping):
        raise ValueError("resume manifest has no executor object")
    _require_equal(executor_manifest.get("active"), True, "executor active flag")
    _require_equal(executor_manifest.get("task"), executor_task, "executor task")
    _require_equal(
        executor_manifest.get("targets"),
        list(executor_targets),
        "executor targets",
    )
    _require_equal(executor_manifest.get("runs"), executor_runs, "executor runs")
    _require_equal(
        manifest.get("capacity"),
        calibrate_capacity(
            domain,
            cases,
            corpus_version=str(options["corpus_version"]),
            presentation=presentation,
        ).to_dict(),
        "capacity calibration",
    )
    _require_equal(
        manifest.get("corpus_provenance"),
        dict(domain.corpus.provenance(str(options["corpus_version"]))),
        "corpus provenance",
    )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _read_jsonl_objects(path: Path, label: str) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{label} rows must be objects")
        rows.append(value)
    return rows


def _file_drift(value: Any, root: Path | None) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    changed = []
    for raw_path, expected_hash in value.items():
        path = Path(str(raw_path))
        if root is not None and not path.is_absolute():
            path = root / path
        if not path.is_file() or file_hash(path) != expected_hash:
            changed.append(str(raw_path))
    return tuple(sorted(changed))


def _targets(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    return tuple(str(item) for item in value)


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"resume {label} mismatch")
