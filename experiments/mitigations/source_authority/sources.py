"""Verify completed writer artifacts and select their final typed population."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from analysis.common import load_jsonl, load_memory_artifacts
from domains.base import AuthorizationMemoryDomain, MemoryArchitecture
from experiments.authorization_memory.persistence import content_hash, file_hash
from experiments.authorization_memory.schemas import (
    FrozenEvidence,
    MemoryArtifact,
    frozen_evidence_from_dict,
    memory_artifact_from_dict,
)

TYPED_CONDITIONS = ("one_shot_typed", "incremental_typed")


@dataclass(frozen=True)
class WriterSource:
    path: Path
    manifest_hash: str
    manifest: Mapping[str, Any]
    files: Mapping[str, Any]
    evidence: tuple[FrozenEvidence, ...]
    memories: tuple[MemoryArtifact, ...]
    baseline_jobs: tuple[Mapping[str, Any], ...]
    compatibility: Mapping[str, Any]

    def provenance(self) -> dict[str, Any]:
        return {
            "source_run": str(self.path),
            "manifest_sha256": self.manifest_hash,
            "files": dict(self.files),
            "domain_id": self.manifest["domain_id"],
            "domain_adapter_version": self.manifest["domain_adapter_version"],
            "corpus_version": self.manifest["corpus_version"],
            "corpus_provenance": self.manifest["corpus_provenance"],
            "source_files": self.manifest["source_files"],
            "compatibility": dict(self.compatibility),
            "presentation": self.manifest["presentation"],
            "presentation_hash": self.manifest["presentation_hash"],
            "source_seed": self.manifest["seed"],
            "writer": self.manifest["writer"],
            "original_executor": self.manifest.get("executor"),
            "memory_implementation_id": self.manifest["memory_implementation_id"],
            "memory_implementation_hash": self.manifest["memory_implementation_hash"],
            "selected_evidence_ids": [item.evidence_id for item in self.evidence],
            "selected_memory_ids": [item.memory_id for item in self.evidence],
            "selected_case_ids": sorted({item.case_id for item in self.evidence}),
            "selected_conditions": sorted({item.condition_id for item in self.evidence}),
            "selected_writer_seeds": sorted({item.writer_seed for item in self.evidence}),
        }


def source_paths(options: Mapping[str, Any]) -> tuple[Path, ...]:
    values = options.get("source_runs") or (options.get("source_run"),)
    if isinstance(values, (str, Path)):
        values = (values,)
    paths = tuple(Path(str(value)).expanduser().resolve() for value in values if value)
    if not paths:
        raise ValueError("source_authority requires at least one --source-run")
    paths = tuple(path.parent if path.name == "manifest.json" else path for path in paths)
    if len(paths) != len(set(paths)):
        raise ValueError("source_authority source runs must be distinct")
    return paths


def verify_files(path: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    path = path.expanduser().resolve()
    files = manifest.get("files")
    if not isinstance(files, Mapping) or not {"memories", "evidence"} <= set(files):
        raise ValueError(f"{path}: source needs declared memories and evidence artifacts")
    verified = {}
    for name, entry in files.items():
        if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
            raise ValueError(f"{path}: malformed artifact entry {name!r}")
        artifact = (path / entry["path"]).resolve()
        if not artifact.is_relative_to(path) or not artifact.is_file():
            raise ValueError(f"{path}: missing or external source artifact {name!r}")
        if file_hash(artifact) != entry.get("sha256"):
            raise ValueError(f"{path}: source artifact {name!r} hash mismatch")
        with artifact.open(encoding="utf-8") as handle:
            count = sum(bool(line.strip()) for line in handle)
        if type(entry.get("rows")) is not int or count != entry["rows"]:
            raise ValueError(f"{path}: source artifact {name!r} row count mismatch")
        verified[name] = dict(entry)
    return verified


def load_writer_source(
    path: Path,
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> WriterSource:
    path = path.expanduser().resolve()
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"{path}: missing source manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = file_hash(manifest_path)
    if manifest.get("status") != "completed" or manifest.get("study") != "writer":
        raise ValueError(f"{path}: source must be a completed writer study")
    presentation = domain.get_presentation(str(options["presentation_version"]))
    expected = {
        "domain_id": domain.domain_id,
        "domain_adapter_version": domain.adapter_version,
        "corpus_version": str(options["corpus_version"]),
        "presentation": presentation.to_dict(),
        "presentation_hash": content_hash(presentation.to_dict()),
        "corpus_provenance": dict(domain.corpus.provenance(str(options["corpus_version"]))),
        "memory_implementation_id": "langmem_profile",
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ValueError(f"{path}: incompatible source {field}")
    case_by_id = {domain.corpus.case_id(case): case for case in cases}
    source_cases = manifest.get("case_ids")
    if (
        not isinstance(source_cases, list)
        or len(source_cases) != len(set(source_cases))
        or not set(case_by_id) <= set(source_cases)
    ):
        raise ValueError(f"{path}: source does not cover selected cases")
    compatibility = _verify_corpus_files(path, domain, manifest, str(options["corpus_version"]))
    files = verify_files(path, manifest)
    memories = {
        row["memory_id"]: memory_artifact_from_dict(row)
        for row in load_memory_artifacts(path, domain=domain.domain_id)
    }
    if len(memories) != files["memories"]["rows"]:
        raise ValueError(f"{path}: duplicate source memory IDs")
    all_evidence = tuple(
        frozen_evidence_from_dict(row)
        for row in load_jsonl(path / files["evidence"]["path"])
    )
    if len({item.evidence_id for item in all_evidence}) != len(all_evidence):
        raise ValueError(f"{path}: duplicate source evidence IDs")
    strategy = str(options.get("writer_strategy") or "all")
    declared = manifest.get("conditions")
    if not isinstance(declared, list):
        raise ValueError(f"{path}: source must declare its writer conditions")
    conditions = tuple(
        item for item in TYPED_CONDITIONS
        if item in declared and (strategy == "all" or item == f"{strategy}_typed")
    )
    if not conditions:
        raise ValueError(f"{path}: source has no selected typed writer strategy")
    writer = manifest.get("writer")
    if not isinstance(writer, Mapping) or writer.get("active") is not True:
        raise ValueError(f"{path}: source writer route is missing")
    runs = writer.get("runs")
    targets = writer.get("targets")
    if type(runs) is not int or runs < 1 or not isinstance(targets, list) or not targets:
        raise ValueError(f"{path}: source writer population is incomplete")
    if len(set(targets)) != len(targets):
        raise ValueError(f"{path}: duplicate source writer targets")
    routes = {row["target_id"]: row for row in writer.get("target_routes", ())}
    if set(routes) != set(targets):
        raise ValueError(f"{path}: source writer route provenance is incomplete")
    selected = []
    keys = set()
    for item in all_evidence:
        if item.case_id not in case_by_id or item.condition_id not in conditions:
            continue
        memory = memories.get(item.memory_id)
        if memory is None:
            raise ValueError(f"{path}: evidence has no linked memory: {item.evidence_id}")
        # LangMem's final freeze identity separates final evidence from checkpoint repairs.
        final_id = "evidence_" + content_hash("\0".join((
            item.domain_id, item.case_id, item.condition_id,
            str(item.memory_run_id), memory.memory_id,
        )))[:24]
        if item.evidence_id != final_id:
            continue
        _verify_evidence(path, item, memory, manifest, routes)
        key = (item.case_id, item.condition_id, item.writer.target_id, item.memory_run_id)
        if key in keys:
            raise ValueError(f"{path}: duplicate final typed population cell {key}")
        keys.add(key)
        selected.append(item)
    expected_keys = {
        (case_id, condition, target, run_id)
        for case_id in case_by_id for condition in conditions
        for target in targets for run_id in range(runs)
    }
    if keys != expected_keys:
        raise ValueError(
            f"{path}: incomplete final typed population; "
            f"missing={len(expected_keys - keys)}, unexpected={len(keys - expected_keys)}"
        )
    _verify_final_states(path, files, selected, memories, case_by_id, domain)
    baseline_jobs = _verify_baseline_jobs(
        path, files, selected, case_by_id, domain,
        presentation=presentation,
        verify_surfaces=not compatibility["all_source_files_match"],
    )
    compatibility["original_executor_surfaces_revalidated"] = not compatibility["all_source_files_match"]
    if file_hash(manifest_path) != manifest_hash:
        raise ValueError(f"{path}: source manifest changed during validation")
    return WriterSource(
        path=path, manifest_hash=manifest_hash, manifest=manifest, files=files,
        evidence=tuple(selected),
        memories=tuple(memories[item.memory_id] for item in selected),
        baseline_jobs=baseline_jobs, compatibility=compatibility,
    )


def _verify_corpus_files(
    path: Path, domain: AuthorizationMemoryDomain,
    manifest: Mapping[str, Any], corpus_version: str,
) -> dict[str, Any]:
    def portable(value: str) -> str:
        parts = Path(value).parts
        if "domains" not in parts:
            raise ValueError(f"{path}: corpus file lacks a portable domains path")
        return Path(*parts[parts.index("domains"):]).as_posix()

    source_files = manifest.get("source_files")
    if not isinstance(source_files, Mapping):
        raise ValueError(f"{path}: source corpus file hashes are missing")
    recorded = {portable(str(name)): digest for name, digest in source_files.items()}
    current = {
        portable(str(source)): file_hash(source)
        for source in domain.corpus.source_files(corpus_version)
    }
    data_suffixes = {".json", ".jsonl", ".yaml", ".yml", ".csv", ".txt"}
    recorded_data = {name: digest for name, digest in recorded.items() if Path(name).suffix in data_suffixes}
    current_data = {name: digest for name, digest in current.items() if Path(name).suffix in data_suffixes}
    if not recorded_data or recorded_data != current_data:
        raise ValueError(f"{path}: immutable source corpus data differs from this checkout")
    return {
        "all_source_files_match": recorded == current,
        "immutable_corpus_data_matches": True,
        "corpus_provenance_matches": True,
        "presentation_matches": True,
        "current_source_files": current,
        "changed_or_added_code_files": [
            name for name in sorted(set(recorded) | set(current))
            if recorded.get(name) != current.get(name)
        ],
    }


def _verify_evidence(
    path: Path, item: FrozenEvidence, memory: MemoryArtifact,
    manifest: Mapping[str, Any], routes: Mapping[str, Any],
) -> None:
    if item.architecture is not MemoryArchitecture.TYPED or memory.origin.value != "writer":
        raise ValueError(f"{path}: selected evidence must be generated typed memory")
    fields = (
        "domain_id", "case_id", "condition_id", "writer_seed", "writer", "architecture",
        "payload", "content_hash", "presentation_id", "presentation_hash", "profile_id",
        "memory_implementation_id", "memory_implementation_hash", "source_attempt_id",
    )
    if any(getattr(item, name) != getattr(memory, name) for name in fields):
        raise ValueError(f"{path}: memory/evidence linkage differs for {item.evidence_id}")
    if (
        item.source_history is not None
        or type(item.memory_run_id) is not int
        or item.memory_run_id != memory.writer_run_id
        or item.content_hash != content_hash(item.payload)
        or item.presentation_hash != manifest["presentation_hash"]
        or item.presentation_id != manifest["presentation"]["presentation_id"]
        or item.domain_id != manifest["domain_id"]
        or item.memory_implementation_hash != manifest.get("memory_implementation_hash")
        or type(item.writer_seed) is not int
        or not item.profile_id
        or item.writer is None
    ):
        raise ValueError(f"{path}: invalid frozen evidence provenance for {item.evidence_id}")
    route = routes.get(item.writer.target_id)
    if route is None or any(
        getattr(item.writer, name) != route.get(name)
        for name in ("provider", "requested_model", "resolved_model")
    ):
        raise ValueError(f"{path}: evidence writer route differs from manifest")
    parameters = item.writer.effective_parameters
    if parameters.get("temperature") != 1.0 or parameters.get("seed") != item.writer_seed:
        raise ValueError(f"{path}: inconsistent source writer parameters")


def _verify_final_states(
    path: Path, files: Mapping[str, Any], selected: Sequence[FrozenEvidence],
    memories: Mapping[str, MemoryArtifact], cases: Mapping[str, Any],
    domain: AuthorizationMemoryDomain,
) -> None:
    if "memory_states" not in files:
        raise ValueError(f"{path}: final population requires memory_states provenance")
    rows = load_jsonl(path / files["memory_states"]["path"])
    states = {}
    for row in rows:
        key = (row["profile_id"], row["block_index"])
        if key in states:
            raise ValueError(f"{path}: duplicate writer profile checkpoint")
        states[key] = row
    for item in selected:
        final_block = max(int(block.block_index) for block in domain.corpus.blocks(cases[item.case_id]))
        state = states.get((item.profile_id, final_block))
        if state is None:
            raise ValueError(f"{path}: final writer checkpoint is missing")
        for name in (
            "domain_id", "case_id", "condition_id", "writer_seed", "presentation_id",
            "presentation_hash", "memory_implementation_id", "memory_implementation_hash",
        ):
            if state.get(name) != getattr(item, name):
                raise ValueError(f"{path}: final writer checkpoint {name} differs")
        if state.get("writer_run_id") != item.memory_run_id:
            raise ValueError(f"{path}: final writer checkpoint run differs")
        if state["current_memory_id"] is None:
            if item.payload.get("authorizations") or memories[item.memory_id].source_attempt_id:
                raise ValueError(f"{path}: failed initial writer must retain empty final memory")
        elif state["current_memory_id"] != item.memory_id:
            raise ValueError(f"{path}: evidence does not link to the final retained memory")


def _verify_baseline_jobs(
    path: Path, files: Mapping[str, Any], selected: Sequence[FrozenEvidence],
    cases: Mapping[str, Any], domain: AuthorizationMemoryDomain,
    *, presentation: Any, verify_surfaces: bool,
) -> tuple[Mapping[str, Any], ...]:
    evidence = {item.evidence_id: item for item in selected}
    probes = {
        (case_id, probe.probe_id): probe
        for case_id, case in cases.items() for probe in domain.corpus.probes(case)
    }
    rows = tuple(
        row for row in (
            load_jsonl(path / files["pressure_source_jobs"]["path"])
            if "pressure_source_jobs" in files else ()
        )
        if row.get("evidence_role") == "generated_final" and row.get("evidence_id") in evidence
    )
    if not rows and "trials" in files:
        rows = tuple(
            {
                "case_id": trial["case_id"], "probe_id": trial["probe_id"],
                "condition_id": trial["condition_id"],
                "memory_id": trial["memory_id"], "evidence_id": trial["evidence_id"],
                "evidence_hash": evidence[trial["evidence_id"]].content_hash,
                "request": probes[(trial["case_id"], trial["probe_id"])].request.to_dict(),
                "oracle_block_index": None,
                "baseline_job_id": trial["metadata"]["study"]["job_id"],
                "baseline_trial_id": trial["metadata"]["core"]["trial_id"],
                "baseline_call_id": trial["metadata"]["core"]["call_id"],
                "executor_target_id": trial["executor"]["target_id"],
                "executor_run_id": trial["executor_run_id"],
                "executor_seed": trial["seed"],
                "evidence_role": "generated_final",
            }
            for trial in load_jsonl(path / files["trials"]["path"])
            if trial.get("evidence_id") in evidence
            and trial.get("metadata", {}).get("study", {}).get("evidence_role") == "generated_final"
            and (trial["case_id"], trial["probe_id"]) in probes
        )
    if not rows:
        if verify_surfaces:
            raise ValueError(f"{path}: changed source code requires frozen baseline contexts")
        return ()
    seen = set()
    contexts = {}
    if verify_surfaces:
        if "model_contexts" not in files:
            raise ValueError(f"{path}: changed source code requires model_contexts")
        contexts = {
            row["trial_id"]: row
            for row in load_jsonl(path / files["model_contexts"]["path"])
            if row.get("stage") == "executor"
        }
    for row in rows:
        item = evidence[row["evidence_id"]]
        probe = probes.get((item.case_id, row["probe_id"]))
        if (
            probe is None or row["case_id"] != item.case_id
            or row["condition_id"] != item.condition_id
            or row["memory_id"] != item.memory_id
            or row["evidence_hash"] != item.content_hash
            or row["request"] != probe.request.to_dict()
            or row.get("oracle_block_index") is not None
        ):
            raise ValueError(f"{path}: incompatible original generated-final request")
        if verify_surfaces:
            from experiments.authorization_memory.pipeline import _study_job_messages
            from experiments.authorization_memory.surfaces import model_visible_tools
            from experiments.authorization_memory.study_plan import ExecutorJob

            context = contexts.get(row["baseline_trial_id"])
            job = ExecutorJob(job_id=row["baseline_job_id"], case=cases[item.case_id], probe=probe, evidence=item)
            visible = {
                "messages": _study_job_messages(domain, job, presentation=presentation, pressure=None),
                "tools": list(model_visible_tools(domain, presentation)),
                "tool_choice": "auto",
            }
            if context is None or any(context.get(key) != value for key, value in visible.items()):
                raise ValueError(f"{path}: current original-memory executor surface differs from source")
            if context["evidence_id"] != item.evidence_id or context["memory_id"] != item.memory_id:
                raise ValueError(f"{path}: original executor context evidence linkage differs")
        seen.add((item.evidence_id, probe.probe_id))
    expected = {
        (item.evidence_id, probe.probe_id)
        for item in selected for probe in domain.corpus.probes(cases[item.case_id])
    }
    if seen != expected:
        raise ValueError(f"{path}: generated-final request population is incomplete")
    return rows
