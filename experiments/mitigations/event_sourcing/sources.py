"""Verified frozen writer baselines and outcome-blind executor replay."""

from __future__ import annotations

import copy

import json

from collections.abc import Mapping, Sequence


from pathlib import Path

from typing import Any


from domains.base import (
    AuthorizationMemoryDomain,
)

from experiments.authorization_memory.persistence import (
    content_hash,
    canonical_json,
    file_hash,
)


from experiments.authorization_memory.study_plan import ExecutorJob

from .core import (
    _capacity_tokens,
)

from .runtime import (
    _jsonl_count,
)


def _targets(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    return tuple(str(item) for item in (value or ()))


def validate_baseline_sources(
    domain: AuthorizationMemoryDomain,
    source_runs: Sequence[str | Path],
    *,
    writer_targets: Sequence[str],
    seed: int,
    expected_case_ids: Sequence[str],
    corpus_version: str | None = None,
    presentation_id: str | None = None,
    config: Any = None,
    writer_task: str = "writer",
    executor_task: str = "executor",
    executor_targets: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Verify every paired typed-incremental source before any paid call."""

    del executor_task, executor_targets
    if len(source_runs) != len(writer_targets):
        raise ValueError(
            "event sourcing requires exactly one paired baseline source per writer target"
        )
    verified = []
    seen_targets: set[str] = set()
    required_artifacts = {
        "calls",
        "evidence",
        "fidelity",
        "memories",
        "memory_attempts",
        "memory_states",
        "model_contexts",
        "trials",
    }
    for raw_source in source_runs:
        source = Path(raw_source).expanduser().resolve()
        manifest_path = source / "manifest.json" if source.is_dir() else source
        if manifest_path.name != "manifest.json" or not manifest_path.is_file():
            raise ValueError(f"paired baseline has no manifest: {raw_source}")
        run_dir = manifest_path.parent.resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
            raise ValueError(f"paired baseline is not completed: {manifest_path}")
        if manifest.get("domain_id") != domain.domain_id:
            raise ValueError(f"paired baseline domain mismatch: {manifest_path}")
        if manifest.get("study") != "writer":
            raise ValueError(f"paired baseline must be an original writer study: {manifest_path}")
        if corpus_version is not None and manifest.get("corpus_version") != corpus_version:
            raise ValueError(f"paired baseline corpus version mismatch: {manifest_path}")
        presentation = domain.get_presentation(presentation_id)
        if manifest.get("presentation_hash") != content_hash(presentation.to_dict()):
            raise ValueError(f"paired baseline presentation mismatch: {manifest_path}")
        if manifest.get("capacity", {}).get("primary_tokens") != _capacity_tokens(
            domain, corpus_version or domain.corpus.default_version
        ):
            raise ValueError(f"paired baseline typed capacity mismatch: {manifest_path}")
        if (
            manifest.get("writer", {}).get("runs", 1) != 1
            or manifest.get("writer", {}).get("max_attempts", 2) != 2
        ):
            raise ValueError(
                f"paired baseline must use one writer run and two attempts: {manifest_path}"
            )
        current_files = _source_files(domain, corpus_version or domain.corpus.default_version)
        source_files = {
            _portable_path(path): digest
            for path, digest in manifest.get("source_files", {}).items()
        }
        corpus_prefix = f"domains/{domain.domain_id}/corpus/"
        for path, digest in current_files.items():
            if path.startswith(corpus_prefix) and source_files.get(path) != digest:
                raise ValueError(f"paired baseline corpus source changed: {path}")
        if int(manifest.get("seed", -1)) != seed:
            raise ValueError(f"paired baseline seed mismatch: {manifest_path}")
        if list(manifest.get("case_ids") or ()) != list(expected_case_ids):
            raise ValueError(f"paired baseline case list mismatch: {manifest_path}")
        if "incremental_typed" not in set(manifest.get("conditions") or ()):
            raise ValueError(f"paired baseline lacks incremental_typed: {manifest_path}")
        targets = manifest.get("writer", {}).get("targets")
        if not isinstance(targets, list) or len(targets) != 1:
            raise ValueError(f"paired baseline must contain one writer target: {manifest_path}")
        target = str(targets[0])
        if target not in writer_targets or target in seen_targets:
            raise ValueError(f"paired baseline writer target is unexpected or duplicated: {target}")
        if config is not None:
            current = config.resolve_target(writer_task, target=target)
            routes = [
                row
                for row in manifest.get("writer", {}).get("target_routes", ())
                if row.get("target_id") == target
            ]
            if len(routes) != 1:
                raise ValueError(f"paired baseline lacks an unambiguous writer route: {target}")
            for key in ("provider", "requested_model", "resolved_model", "request_parameters"):
                if routes[0].get(key, {} if key == "request_parameters" else None) != getattr(
                    current, key
                ):
                    raise ValueError(f"paired baseline writer route changed: {target}/{key}")
        files = manifest.get("files")
        if not isinstance(files, Mapping) or not required_artifacts.issubset(files):
            missing = sorted(required_artifacts - set(files or {}))
            raise ValueError(f"paired baseline is missing required artifacts: {missing}")
        verified_files: dict[str, dict[str, Any]] = {}
        for name, entry in files.items():
            if not isinstance(entry, Mapping):
                raise ValueError(f"invalid baseline artifact entry {name!r}")
            relative = entry.get("path")
            expected_hash = entry.get("sha256")
            if not isinstance(relative, str) or not relative:
                raise ValueError(f"baseline artifact {name!r} has no path")
            if not isinstance(expected_hash, str) or len(expected_hash) != 64:
                raise ValueError(f"baseline artifact {name!r} has no valid hash")
            artifact_path = (run_dir / relative).resolve()
            if not artifact_path.is_relative_to(run_dir) or not artifact_path.is_file():
                raise ValueError(
                    f"baseline artifact is missing or escapes its run: {artifact_path}"
                )
            actual_hash = file_hash(artifact_path)
            if actual_hash != expected_hash:
                raise ValueError(f"baseline artifact hash mismatch: {artifact_path}")
            declared_rows = entry.get("rows")
            if declared_rows is not None and artifact_path.suffix == ".jsonl":
                actual_rows = _jsonl_count(artifact_path)
                if actual_rows != int(declared_rows):
                    raise ValueError(f"baseline artifact row-count mismatch: {artifact_path}")
            verified_files[str(name)] = {
                "path": str(artifact_path),
                "sha256": actual_hash,
                **({"rows": int(declared_rows)} if declared_rows is not None else {}),
            }
        typed_states = _load_jsonl_path(Path(verified_files["memory_states"]["path"]))
        typed_trials = _load_jsonl_path(Path(verified_files["trials"]["path"]))
        if not any(row.get("condition_id") == "incremental_typed" for row in typed_states):
            raise ValueError(f"paired baseline has no typed-incremental states: {manifest_path}")
        if not any(row.get("condition_id") == "incremental_typed" for row in typed_trials):
            raise ValueError(f"paired baseline has no typed-incremental trials: {manifest_path}")
        final_evidence = _baseline_final_evidence(domain, manifest, verified_files)
        compatibility = _validate_baseline_surfaces(
            domain, manifest, verified_files, final_evidence, presentation
        )
        compatibility["changed_source_files"] = [
            path
            for path in sorted(set(source_files) | set(current_files))
            if source_files.get(path) != current_files.get(path)
        ]
        compatibility["immutable_corpus_data_matches"] = True
        seen_targets.add(target)
        verified.append(
            {
                "run_dir": str(run_dir),
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": file_hash(manifest_path),
                "domain_id": domain.domain_id,
                "writer_target_id": target,
                "seed": seed,
                "files": verified_files,
                "scientific_status": "completed_manifest_and_full_hash_validation_passed",
                "final_evidence": final_evidence,
                "compatibility": compatibility,
            }
        )
    if seen_targets != set(writer_targets):
        raise ValueError("paired baseline writer target coverage is incomplete")
    return sorted(verified, key=lambda row: list(writer_targets).index(row["writer_target_id"]))


def _load_jsonl_path(path: Path) -> list[dict[str, Any]]:
    from analysis.common import load_jsonl

    return load_jsonl(path)


def _portable_path(path: str | Path) -> str:
    parts = Path(path).parts
    for root in ("domains", "experiments", "src"):
        if root in parts:
            return Path(*parts[parts.index(root) :]).as_posix()
    return Path(path).name


def _source_files(domain: AuthorizationMemoryDomain, corpus_version: str) -> dict[str, str]:
    return {
        _portable_path(path): file_hash(path) for path in domain.corpus.source_files(corpus_version)
    }


def validate_selected_sources(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    options: Mapping[str, Any],
    *,
    config: Any,
) -> list[dict[str, Any]]:
    return validate_baseline_sources(
        domain,
        options.get("source_runs") or (),
        writer_targets=_targets(options.get("writer_targets")),
        executor_targets=_targets(options.get("executor_targets")),
        seed=int(options["seed"]),
        expected_case_ids=[domain.corpus.case_id(case) for case in cases],
        corpus_version=str(options["corpus_version"]),
        presentation_id=str(options.get("presentation_version") or domain.default_presentation_id),
        config=config,
        writer_task=str(options.get("writer_task") or "writer"),
        executor_task=str(options.get("executor_task") or "executor"),
    )


def _baseline_final_evidence(
    domain: AuthorizationMemoryDomain,
    manifest: Mapping[str, Any],
    files: Mapping[str, Any],
) -> list[dict[str, Any]]:
    trials = _load_jsonl_path(Path(files["trials"]["path"]))
    evidence_ids = {
        row["evidence_id"]
        for row in trials
        if row.get("condition_id") == "incremental_typed"
        and row.get("metadata", {}).get("study", {}).get("evidence_role") == "generated_final"
    }
    evidence = [
        row
        for row in _load_jsonl_path(Path(files["evidence"]["path"]))
        if row.get("evidence_id") in evidence_ids
    ]
    by_case = {}
    for row in evidence:
        case_id = row["case_id"]
        if case_id in by_case:
            raise ValueError(f"paired baseline has multiple final typed memories for {case_id}")
        parsed = domain.memory.parse_typed(row["payload"])
        if content_hash(parsed) != row["content_hash"]:
            raise ValueError(f"paired baseline final evidence hash mismatch: {case_id}")
        if (
            row.get("writer_seed") != manifest["seed"]
            or row.get("writer", {}).get("target_id") != manifest["writer"]["targets"][0]
        ):
            raise ValueError(f"paired baseline evidence writer mismatch: {case_id}")
        by_case[case_id] = row
    if set(by_case) != set(manifest["case_ids"]):
        raise ValueError("paired baseline final typed evidence coverage is incomplete")
    return [by_case[case_id] for case_id in manifest["case_ids"]]


def _baseline_executor_jobs(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    sources: Sequence[Mapping[str, Any]],
) -> tuple[tuple[ExecutorJob, ...], list[dict[str, Any]], list[dict[str, Any]]]:
    from experiments.authorization_memory.schemas import frozen_evidence_from_dict
    from .core import _stable_id

    cases_by_id = {domain.corpus.case_id(case): case for case in cases}
    jobs, evidence_rows, memory_rows = [], [], []
    for source in sources:
        memory_ids = {
            row["memory_id"] for row in source["final_evidence"] if row["memory_id"] is not None
        }
        memories = [
            row
            for row in _load_jsonl_path(Path(source["files"]["memories"]["path"]))
            if row.get("memory_id") in memory_ids
        ]
        if {row["memory_id"] for row in memories} != memory_ids:
            raise ValueError("paired baseline final evidence lacks original memory artifacts")
        memory_rows.extend(memories)
        for row in source["final_evidence"]:
            item = frozen_evidence_from_dict(row)
            case = cases_by_id[item.case_id]
            evidence_rows.append(copy.deepcopy(row))
            for probe in domain.corpus.probes(case):
                jobs.append(
                    ExecutorJob(
                        job_id=_stable_id(
                            "event-baseline-executor-job",
                            source["manifest_sha256"],
                            item.evidence_id,
                            probe.probe_id,
                        ),
                        case=case,
                        probe=probe,
                        evidence=item,
                        metadata={
                            "replay_kind": "typed_incremental_baseline_replay",
                            "evidence_role": "generated_final",
                            "source_manifest_sha256": source["manifest_sha256"],
                            "source_evidence_id": item.evidence_id,
                            "source_memory_id": item.memory_id,
                            "baseline_writer_regenerated": False,
                        },
                    )
                )
    return tuple(jobs), evidence_rows, memory_rows


def _validate_baseline_surfaces(
    domain: AuthorizationMemoryDomain,
    manifest: Mapping[str, Any],
    files: Mapping[str, Any],
    evidence_rows: Sequence[Mapping[str, Any]],
    presentation: Any,
) -> dict[str, Any]:
    from experiments.authorization_memory.pipeline import _study_job_messages
    from experiments.authorization_memory.schemas import frozen_evidence_from_dict
    from experiments.authorization_memory.surfaces import model_visible_tools

    cases = {
        domain.corpus.case_id(case): case
        for case in domain.corpus.load_cases(manifest["corpus_version"])
        if domain.corpus.case_id(case) in manifest["case_ids"]
    }
    evidence = {row["evidence_id"]: frozen_evidence_from_dict(row) for row in evidence_rows}
    contexts = {
        row["trial_id"]: row
        for row in _load_jsonl_path(Path(files["model_contexts"]["path"]))
        if row.get("stage") == "executor"
    }
    states = [
        row
        for row in _load_jsonl_path(Path(files["memory_states"]["path"]))
        if row.get("condition_id") == "incremental_typed"
    ]
    memories = {row["memory_id"]: row for row in _load_jsonl_path(Path(files["memories"]["path"]))}
    for item in evidence.values():
        case_states = [row for row in states if row["case_id"] == item.case_id]
        blocks = {int(block.block_index) for block in domain.corpus.blocks(cases[item.case_id])}
        if (
            len(case_states) != len(blocks)
            or {int(row["block_index"]) for row in case_states} != blocks
        ):
            raise ValueError("paired baseline is missing typed state updates")
        final_state = max(case_states, key=lambda row: int(row["block_index"]))
        if final_state.get("current_memory_id") is None:
            if canonical_json(item.payload) != canonical_json(
                domain.memory.serialize_typed(domain.memory.empty_typed())
            ) or (memories.get(item.memory_id) or {}).get("source_attempt_id"):
                raise ValueError("failed initial baseline writer must retain empty typed memory")
        elif final_state["current_memory_id"] != item.memory_id:
            raise ValueError("paired baseline evidence is not the final retained typed memory")
        if item.memory_id is None:
            if final_state.get("current_memory_id") is not None:
                raise ValueError("paired baseline evidence lacks its retained memory")
        else:
            memory = memories.get(item.memory_id)
            if memory is None or any(
                memory.get(key) != item.to_dict().get(key)
                for key in (
                    "payload",
                    "content_hash",
                    "writer",
                    "writer_seed",
                    "condition_id",
                    "presentation_id",
                    "presentation_hash",
                    "memory_implementation_hash",
                )
            ):
                raise ValueError("paired baseline memory/evidence provenance differs")
    checked = set()
    for trial in _load_jsonl_path(Path(files["trials"]["path"])):
        if (
            trial.get("evidence_id") not in evidence
            or trial.get("metadata", {}).get("study", {}).get("evidence_role") != "generated_final"
        ):
            continue
        item = evidence[trial["evidence_id"]]
        case = cases[item.case_id]
        probes = {probe.probe_id: probe for probe in domain.corpus.probes(case)}
        probe = probes.get(trial["probe_id"])
        if (
            probe is None
            or trial["request_authorized"] != domain.executor.oracle(case, probe.request).authorized
        ):
            raise ValueError("paired baseline request or authorization semantics changed")
        job = ExecutorJob(job_id="offline-original-baseline", case=case, probe=probe, evidence=item)
        surface = {
            "messages": _study_job_messages(domain, job, presentation=presentation, pressure=None),
            "tools": model_visible_tools(domain, presentation),
            "tool_choice": "auto",
        }
        context = contexts.get(trial["metadata"]["core"]["trial_id"])
        if (
            context is None
            or context.get("content_hash") != content_hash(surface)
            or any(context.get(key) != value for key, value in surface.items())
        ):
            raise ValueError("current baseline executor surface differs from the original source")
        checked.add((item.evidence_id, probe.probe_id))
    expected = {
        (item.evidence_id, probe.probe_id)
        for item in evidence.values()
        for probe in domain.corpus.probes(cases[item.case_id])
    }
    if checked != expected:
        raise ValueError("paired baseline original executor context coverage is incomplete")
    return {
        "original_executor_surfaces_revalidated": True,
        "original_request_semantics_match": True,
        "unique_surfaces_checked": len(checked),
    }
