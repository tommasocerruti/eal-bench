from __future__ import annotations

import argparse
import copy
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from domains import get_domain
from experiments.authorization_memory.langmem_writer import framework_manifest
from experiments.authorization_memory.persistence import file_hash, write_json, write_jsonl
from experiments.authorization_memory.pipeline import _study_job_messages
from experiments.authorization_memory.surfaces import model_visible_tools

from .release import validate_release
from .studies import build_controls_plan


ADOPTION_SCHEMA_VERSION = "release_adoption_v1"
ADOPTED_RUNS = {
    "gptoss_baseten": "cybersecurity_v1__adopted__gptoss-controls",
    "deepseek_baseten": "cybersecurity_v1__adopted__deepseek-controls",
}
ADOPTED_PRESSURE_RUN = "cybersecurity_v1__adopted__pressure"


def adopt_controls_run(*, source: Path, output_root: Path) -> dict[str, Any]:
    domain = get_domain("cybersecurity")
    release_validation = validate_release(domain)
    source = source.expanduser().resolve()
    source_manifest_path = source / "manifest.json"
    source_manifest = _load_json(source_manifest_path)
    _validate_source_manifest(domain, source, source_manifest)
    source_files = _validate_source_files(source, source_manifest)

    presentation = domain.get_presentation(domain.default_presentation_id)
    cases = domain.corpus.load_cases(domain.corpus.default_version)
    plan = build_controls_plan(
        domain,
        cases,
        {
            "corpus_version": domain.corpus.default_version,
            "presentation_version": domain.default_presentation_id,
            "capacity_tier": "primary",
        },
    )
    jobs = {job.job_id: job for job in plan.jobs}
    trials = _load_jsonl(source / source_manifest["files"]["trials"]["path"])
    contexts = {
        str(row["trial_id"]): row
        for row in _load_jsonl(
            source / source_manifest["files"]["model_contexts"]["path"]
        )
        if row.get("stage") == "executor" and row.get("trial_id") is not None
    }
    tools = list(model_visible_tools(domain, presentation))
    implementation = framework_manifest(domain)
    adopted: dict[str, Any] = {}
    for target, dirname in ADOPTED_RUNS.items():
        selected = [row for row in trials if row["executor"]["target_id"] == target]
        exact_surfaces, oracle_rescored, action_rescored = _verify_trials(
            domain=domain,
            presentation=presentation,
            jobs=jobs,
            contexts=contexts,
            tools=tools,
            trials=selected,
        )
        destination = output_root / dirname
        manifest = _adopted_manifest(
            domain=domain,
            implementation=implementation,
            release_validation=release_validation,
            source_manifest=source_manifest,
            source_manifest_sha256=file_hash(source_manifest_path),
            source_files=source_files,
            target=target,
            exact_surfaces=exact_surfaces,
            oracle_rescored=oracle_rescored,
            action_rescored=action_rescored,
        )
        _persist(
            destination=destination,
            source=source,
            source_manifest=source_manifest,
            manifest=manifest,
            trials=selected,
        )
        adopted[target] = {
            "path": str(destination.resolve()),
            "manifest_sha256": file_hash(destination / "manifest.json"),
            "trials": len(selected),
            "provider_visible_surfaces_verified": exact_surfaces,
            "oracle_labels_rescored": oracle_rescored,
            "terminal_actions_rescored": action_rescored,
        }

    summary = {
        "schema_version": ADOPTION_SCHEMA_VERSION,
        "status": "passed",
        "network_request_made": False,
        "release_id": release_validation["release_id"],
        "release_manifest_sha256": release_validation["manifest_sha256"],
        "source": str(source),
        "source_manifest_sha256": file_hash(source_manifest_path),
        "runs": adopted,
    }
    write_json(output_root / "cybersecurity_v1__controls_adoption.json", summary)
    return summary


def adopt_pressure_run(
    *,
    source: Path,
    writer: Path,
    output_root: Path,
) -> dict[str, Any]:
    domain = get_domain("cybersecurity")
    release_validation = validate_release(domain)
    source = source.expanduser().resolve()
    writer = writer.expanduser().resolve()
    source_manifest_path = source / "manifest.json"
    writer_manifest_path = writer / "manifest.json"
    source_manifest = _load_json(source_manifest_path)
    writer_manifest = _load_json(writer_manifest_path)
    if (
        source_manifest.get("status") != "completed"
        or source_manifest.get("study") != "pressure"
        or source_manifest.get("domain_id") != domain.domain_id
        or source_manifest.get("corpus_version") != domain.corpus.default_version
        or source_manifest.get("seed") != domain.canonical_seed
    ):
        raise ValueError(f"{source}: source is not the canonical pressure run")
    if (
        writer_manifest.get("status") != "completed"
        or writer_manifest.get("study") != "writer"
        or writer_manifest.get("domain_id") != domain.domain_id
    ):
        raise ValueError(f"{writer}: writer source is invalid")
    writer_hash = file_hash(writer_manifest_path)
    if (
        Path(str(source_manifest.get("source_run"))).resolve() != writer
        or source_manifest.get("source_writer_run_hash") != writer_hash
    ):
        raise ValueError("pressure-to-writer source linkage changed")
    source_files = _validate_source_files(source, source_manifest)
    trials = _load_jsonl(source / source_manifest["files"]["trials"]["path"])
    source_jobs = _load_jsonl(
        source / source_manifest["files"]["source_pressure_jobs"]["path"]
    )
    pressure_pairs = _load_jsonl(
        source / source_manifest["files"]["pressure_pairs"]["path"]
    )
    trial_ids = {
        str(row["metadata"]["core"]["trial_id"])
        for row in trials
    }
    baseline_ids = {
        str(row["metadata"]["core"]["trial_id"])
        for row in _load_jsonl(writer / writer_manifest["files"]["trials"]["path"])
    }
    if (
        len(trials) != len(source_jobs)
        or len(trials) != len(pressure_pairs)
        or {str(row["pressured_trial_id"]) for row in pressure_pairs} != trial_ids
        or {str(row["baseline_trial_id"]) for row in pressure_pairs} != baseline_ids
        or {str(row["baseline_trial_id"]) for row in source_jobs} != baseline_ids
    ):
        raise ValueError("pressure trial pairing changed")

    manifest = copy.deepcopy(source_manifest)
    manifest["source_writer_run"] = str(writer)
    manifest["source_manifest_sha256"] = writer_hash
    manifest["metadata_correction"] = {
        "schema_version": "cybersecurity_pressure_source_alias_v1",
        "source_manifest_sha256": file_hash(source_manifest_path),
        "release_manifest_sha256": release_validation["manifest_sha256"],
        "source_files": source_files,
        "corrected_fields": ["source_writer_run", "source_manifest_sha256"],
        "trial_pairs_verified": len(trials),
        "model_outputs_reused": True,
        "network_request_made": False,
    }
    manifest["files"] = {}
    destination = output_root / ADOPTED_PRESSURE_RUN
    _persist(
        destination=destination,
        source=source,
        source_manifest=source_manifest,
        manifest=manifest,
        trials=trials,
    )
    summary = {
        "schema_version": "cybersecurity_pressure_source_alias_v1",
        "status": "passed",
        "network_request_made": False,
        "release_id": release_validation["release_id"],
        "source": str(source),
        "source_manifest_sha256": file_hash(source_manifest_path),
        "writer": str(writer),
        "writer_manifest_sha256": writer_hash,
        "path": str(destination.resolve()),
        "manifest_sha256": file_hash(destination / "manifest.json"),
        "trial_pairs_verified": len(trials),
    }
    write_json(output_root / "cybersecurity_v1__pressure_adoption.json", summary)
    return summary


def _verify_trials(
    *,
    domain: Any,
    presentation: Any,
    jobs: Mapping[str, Any],
    contexts: Mapping[str, Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
    trials: Sequence[Mapping[str, Any]],
) -> tuple[int, int, int]:
    exact_surfaces = 0
    oracle_rescored = 0
    action_rescored = 0
    for trial in trials:
        trial_id = str(trial["metadata"]["core"]["trial_id"])
        job_id = str(trial["metadata"]["study"]["job_id"])
        job = jobs.get(job_id)
        context = contexts.get(trial_id)
        if job is None or context is None:
            raise ValueError(f"{trial_id}: controls adoption linkage is incomplete")
        if job.evidence.evidence_id != trial["evidence_id"]:
            raise ValueError(f"{trial_id}: controls evidence changed")
        messages = _study_job_messages(
            domain,
            job,
            presentation=presentation,
            pressure=None,
        )
        if (
            messages != context["messages"]
            or list(tools) != context["tools"]
            or context["tool_choice"] != "auto"
            or context["call_id"] != trial["metadata"]["core"]["call_id"]
        ):
            raise ValueError(f"{trial_id}: provider-visible executor surface changed")
        exact_surfaces += 1

        authorized = domain.executor.oracle(
            job.case,
            job.probe.request,
            through_block_index=job.oracle_block_index,
        ).authorized
        if authorized is not bool(trial["request_authorized"]):
            raise ValueError(f"{trial_id}: oracle label changed")
        oracle_rescored += 1

        if trial.get("provider_error") is not None:
            continue
        if int(trial.get("terminal_call_count") or 0) == 0:
            expected = {
                "decision": "no_action",
                "requested_action_taken": False,
                "unauthorized_action_taken": False,
                "action_mismatch": False,
                "compliant": False,
                "parseable": False,
            }
            if {key: trial.get(key) for key in expected} != expected:
                raise ValueError(f"{trial_id}: normalized no-action score changed")
            action_rescored += 1
            continue
        score = domain.executor.score_tool_call(
            job.case,
            job.probe.request,
            str(trial.get("raw_tool_name") or ""),
            dict(trial.get("raw_tool_arguments") or {}),
            through_block_index=job.oracle_block_index,
        )
        expected = {
            "decision": score.decision.value,
            "requested_action_taken": score.decision.value == "execute_requested",
            "unauthorized_action_taken": (
                score.decision.value in {"execute_requested", "execute_other"}
                and score.action_authorized is False
            ),
            "action_mismatch": score.decision.value == "execute_other",
            "compliant": score.compliant,
            "parseable": score.valid_arguments,
        }
        if {key: trial.get(key) for key in expected} != expected:
            raise ValueError(f"{trial_id}: normalized action score changed")
        action_rescored += 1
    return exact_surfaces, oracle_rescored, action_rescored


def _adopted_manifest(
    *,
    domain: Any,
    implementation: Mapping[str, Any],
    release_validation: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    source_manifest_sha256: str,
    source_files: Mapping[str, Any],
    target: str,
    exact_surfaces: int,
    oracle_rescored: int,
    action_rescored: int,
) -> dict[str, Any]:
    manifest = copy.deepcopy(dict(source_manifest))
    target_routes = [
        route
        for route in manifest["executor"]["target_routes"]
        if route["target_id"] == target
    ]
    if len(target_routes) != 1:
        raise ValueError(f"source manifest has no unique route for {target}")
    manifest["executor"]["targets"] = [target]
    manifest["executor"]["target_routes"] = target_routes
    manifest["corpus_provenance"] = dict(
        domain.corpus.provenance(domain.corpus.default_version)
    )
    manifest["memory_implementation_id"] = implementation[
        "memory_implementation_id"
    ]
    manifest["memory_implementation_hash"] = implementation[
        "memory_implementation_hash"
    ]
    manifest["release_adoption"] = {
        "schema_version": ADOPTION_SCHEMA_VERSION,
        "role": "controls",
        "source_manifest_sha256": source_manifest_sha256,
        "source_seed": source_manifest["seed"],
        "release_seed": domain.canonical_seed,
        "release_manifest_sha256": release_validation["manifest_sha256"],
        "source_files": dict(source_files),
        "source_executor_targets": list(source_manifest["executor"]["targets"]),
        "selected_executor_target": target,
        "selection_rule": "all trials for the named executor target",
        "provider_visible_surfaces_verified": exact_surfaces,
        "oracle_labels_rescored": oracle_rescored,
        "terminal_actions_rescored": action_rescored,
        "model_outputs_reused": True,
        "network_request_made": False,
    }
    manifest["files"] = {}
    manifest["counts"] = {
        "trials": oracle_rescored,
        "provider_visible_surfaces_verified": exact_surfaces,
        "oracle_labels_rescored": oracle_rescored,
        "terminal_actions_rescored": action_rescored,
    }
    return manifest


def _persist(
    *,
    destination: Path,
    source: Path,
    source_manifest: Mapping[str, Any],
    manifest: dict[str, Any],
    trials: Sequence[Mapping[str, Any]],
) -> None:
    if destination.exists():
        raise FileExistsError(f"adopted run already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary) / destination.name
        staging.mkdir()
        source_copy = staging / "source"
        source_copy.mkdir()
        shutil.copy2(source / "manifest.json", source_copy / "manifest.json")
        for entry in source_manifest["files"].values():
            path = source / str(entry["path"])
            target = source_copy / str(entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        trials_path = staging / "trials.jsonl"
        write_jsonl(trials_path, trials)
        manifest["files"] = {
            "trials": {
                "path": trials_path.name,
                "rows": len(trials),
                "sha256": file_hash(trials_path),
            }
        }
        write_json(staging / "manifest.json", manifest)
        staging.rename(destination)


def _validate_source_manifest(
    domain: Any,
    source: Path,
    manifest: Mapping[str, Any],
) -> None:
    if (
        manifest.get("status") != "completed"
        or manifest.get("study") != "controls"
        or manifest.get("domain_id") != domain.domain_id
        or manifest.get("corpus_version") != domain.corpus.default_version
        or manifest.get("seed") != domain.canonical_seed
    ):
        raise ValueError(f"{source}: source is not the canonical controls run")
    if set(manifest["executor"]["targets"]) != set(ADOPTED_RUNS):
        raise ValueError(f"{source}: source controls targets differ from the run plan")


def _validate_source_files(
    source: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    observed = {}
    for name, entry in manifest["files"].items():
        path = source / str(entry["path"])
        sha256 = file_hash(path)
        if sha256 != entry["sha256"]:
            raise ValueError(f"{source}: source artifact {name!r} failed hashing")
        observed[name] = {"path": str(entry["path"]), "sha256": sha256}
    return observed


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Adopt a combined cybersecurity controls run into frozen target views."
    )
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--writer-run", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("results/cybersecurity"))
    args = parser.parse_args()
    print(
        json.dumps(
            (
                adopt_pressure_run(
                    source=args.source_run,
                    writer=args.writer_run,
                    output_root=args.output_root,
                )
                if args.writer_run is not None
                else adopt_controls_run(
                    source=args.source_run,
                    output_root=args.output_root,
                )
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
