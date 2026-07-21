#!/usr/bin/env python3
"""Blindly annotate saved free-text memories in a separate immutable child run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from eal_bench.llm import LLM
from eal_bench.llm.logger import JSONLLogger

from domains.procurement.studies.annotations import (
    EXTRACTOR_SYSTEM_PROMPT,
    EXTRACTOR_VERSION,
    EXTRACTION_TOOL,
    EXTRACTION_TOOL_NAME,
    annotation_from_error,
    annotation_from_response,
    extraction_request_for_artifact,
    stratified_human_validation_sample,
)
from domains.procurement.studies.schemas import (
    MemoryArchitecture,
    MemoryArtifact,
)
from experiments.authorization_memory.persistence import (
    content_hash,
    create_run_dir,
    file_hash,
    git_info,
    runtime_info,
    write_json,
    write_jsonl,
)

ANNOTATION_PROTOCOL_ID = "procurement_free_text_annotation_v1"
ANNOTATION_PROMPT_POLICY_ID = "free_text_current_state_prompt_v2"
ANNOTATION_OUTPUT_SCHEMA_ID = (
    "procurement/authorization-state/v3"
)
ANNOTATION_OUTPUT_SCHEMA_VERSION = "3"
ANNOTATION_IMPLEMENTATION_FILES = (
    "config.yaml",
    "pyproject.toml",
    "uv.lock",
    "experiments/annotate_authorization_memories.py",
    "domains/procurement/studies/annotations.py",
    "domains/procurement/studies/schemas.py",
    "src/eal_bench/llm/client.py",
)


def _load_free_text_artifacts(path: Path) -> list[MemoryArtifact]:
    unique: dict[str, MemoryArtifact] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                artifact = MemoryArtifact.from_dict(raw)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid memory artifact at {path}:{line_number}: {exc}"
                ) from exc
            if artifact.architecture is MemoryArchitecture.FREE_TEXT:
                unique.setdefault(artifact.memory_id, artifact)
    return list(unique.values())


def annotate(
    memories_path: Path,
    *,
    output_path: Path | None,
    task: str,
    target: str | None,
    model: str | None,
    batch_size: int | None,
    human_sample_size: int,
    command: str = "",
) -> Path:
    """Run the annotator without writing into the completed source directory."""

    source = _verify_source_run(memories_path)
    artifacts = _load_free_text_artifacts(memories_path)
    if not artifacts:
        raise ValueError(f"no free-text artifacts found in {memories_path}")
    if target is not None and model is not None:
        raise ValueError("pass either --target or --model, not both")

    run_dir, annotations_path = _annotation_paths(
        memories_path,
        output_path,
    )
    calls_path = run_dir / "calls.jsonl"
    manifest_path = run_dir / "manifest.json"
    llm = LLM(logger=JSONLLogger(calls_path))
    route = llm.preflight(
        task,
        target=target,
        model=model,
        required_capabilities=("native_tools", "forced_tool_choice"),
    )
    requests = [extraction_request_for_artifact(artifact) for artifact in artifacts]
    request = requests[0]
    call_ids = [
        "annotation-call-"
        + hashlib.sha256(
            f"{source['manifest_sha256']}|{artifact.memory_id}".encode()
        ).hexdigest()[:24]
        for artifact in artifacts
    ]
    effective_parameters = {
        **dict(llm.config.task(task).params),
        "temperature": 0.0,
        "tool_choice": request["tool_choice"],
        "parallel_tool_calls": request["parallel_tool_calls"],
    }
    manifest = {
        "status": "running",
        "started_at": datetime.now().astimezone().isoformat(),
        "finished_at": None,
        "study": "memory_annotation",
        "domain_id": source["domain_id"],
        "source_run": source,
        "artifact_schema_versions": {"memory_annotations": 1},
        "task": task,
        "extractor": {
            "protocol_id": ANNOTATION_PROTOCOL_ID,
            "extractor_version": EXTRACTOR_VERSION,
            "prompt_policy_id": ANNOTATION_PROMPT_POLICY_ID,
            "system_prompt_sha256": content_hash(EXTRACTOR_SYSTEM_PROMPT),
            "tool_name": EXTRACTION_TOOL_NAME,
            "tool_schema_sha256": content_hash(EXTRACTION_TOOL),
            "output_schema_id": ANNOTATION_OUTPUT_SCHEMA_ID,
            "output_schema_version": ANNOTATION_OUTPUT_SCHEMA_VERSION,
        },
        "route": {
            "target_id": route.target_id,
            "provider": route.provider,
            "requested_model": route.requested_model,
            "resolved_model": route.resolved_model,
            "capabilities": sorted(route.capabilities),
        },
        "effective_parameters": effective_parameters,
        "memory_count": len(artifacts),
        "command": command,
        "git": git_info(),
        "runtime": runtime_info(),
        "implementation_files": _annotation_implementation_files(),
        "files": {},
    }
    write_json(manifest_path, manifest)

    overrides: dict[str, Any] = {
        "tools": request["tools"],
        "tool_choice": request["tool_choice"],
        "parallel_tool_calls": request["parallel_tool_calls"],
        "temperature": 0.0,
    }
    if model is not None:
        overrides["model"] = model
    try:
        responses = llm.batch(
            task,
            [item["messages"] for item in requests],
            target=target,
            call_ids=call_ids,
            batch_size=batch_size,
            return_exceptions=True,
            required_capabilities=("native_tools", "forced_tool_choice"),
            **overrides,
        )

        records = []
        annotation_objects = []
        for artifact, call_id, response in zip(
            artifacts, call_ids, responses
        ):
            if isinstance(response, Exception):
                record = annotation_from_error(
                    artifact,
                    response,
                    extractor_model=route.resolved_model,
                )
                response_model = None
            else:
                record = annotation_from_response(
                    artifact,
                    response,
                    extractor_model=route.resolved_model,
                )
                response_model = (
                    str(response.model)
                    if getattr(response, "model", None)
                    else None
                )
            annotation_objects.append(record)
            records.append(
                {
                    **record.to_dict(),
                    "schema_version": 1,
                    "domain_id": source["domain_id"],
                    "source_manifest_sha256": source["manifest_sha256"],
                    "call_id": call_id,
                    "extractor": {
                        "target_id": route.target_id,
                        "provider": route.provider,
                        "requested_model": route.requested_model,
                        "resolved_model": route.resolved_model,
                        "response_model": response_model,
                        "effective_parameters": effective_parameters,
                    },
                }
            )
        write_jsonl(annotations_path, records)

        files = {
            "memory_annotations": _file_entry(annotations_path),
            "calls": _file_entry(calls_path),
        }
        if human_sample_size:
            accepted = [
                record
                for record in annotation_objects
                if record.status.value == "accepted"
            ]
            if accepted:
                sample_path = run_dir / "human_validation_sample.jsonl"
                memory_text = {
                    artifact.memory_id: str(artifact.payload)
                    for artifact in artifacts
                }
                samples = stratified_human_validation_sample(
                    annotation_objects,
                    memory_text,
                    min(human_sample_size, len(accepted)),
                )
                write_jsonl(
                    sample_path, [sample.to_dict() for sample in samples]
                )
                files["human_validation_sample"] = _file_entry(sample_path)

        accepted_count = sum(
            record.status.value == "accepted"
            for record in annotation_objects
        )
        manifest.update(
            {
                "status": "completed",
                "finished_at": datetime.now().astimezone().isoformat(),
                "counts": {
                    "annotations": len(records),
                    "accepted": accepted_count,
                    "unaccepted": len(records) - accepted_count,
                },
                "files": files,
            }
        )
        write_json(manifest_path, manifest)
        print(
            f"Wrote {len(records)} annotations ({accepted_count} accepted) "
            f"to {annotations_path}"
        )
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


def _verify_source_run(memories_path: Path) -> dict[str, Any]:
    memories_path = memories_path.resolve()
    manifest_path = memories_path.parent / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            "memory annotations require a manifest-backed source run"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError("memory annotation source run must be completed")
    files = manifest.get("files")
    entry = files.get("memories") if isinstance(files, Mapping) else None
    if not isinstance(entry, Mapping):
        raise ValueError("source manifest does not declare memories")
    declared_path = (memories_path.parent / str(entry.get("path"))).resolve()
    if declared_path != memories_path:
        raise ValueError("input path is not the source manifest's memories artifact")
    expected_hash = entry.get("sha256")
    actual_hash = file_hash(memories_path)
    if expected_hash != actual_hash:
        raise ValueError(
            f"source memories hash mismatch: expected {expected_hash}, got "
            f"{actual_hash}"
        )
    domain_id = manifest.get("domain_id", manifest.get("domain"))
    if not isinstance(domain_id, str) or not domain_id:
        raise ValueError("source manifest does not declare a domain")
    return {
        "run_dir": str(memories_path.parent),
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": file_hash(manifest_path),
        "domain_id": domain_id,
        "corpus_version": manifest.get("corpus_version"),
        "memories_path": str(memories_path),
        "memories_sha256": actual_hash,
        "memory_implementation_id": manifest.get("memory_implementation_id"),
    }


def _annotation_paths(
    memories_path: Path,
    output_path: Path | None,
) -> tuple[Path, Path]:
    source_dir = memories_path.resolve().parent
    if output_path is None:
        run_dir = create_run_dir(
            "memory_annotations",
            f"annotations-{source_dir.name}",
        )
        return run_dir, run_dir / "memory_annotations.jsonl"
    annotations_path = output_path.resolve()
    if annotations_path.is_relative_to(source_dir):
        raise ValueError(
            "annotation output must be outside the completed source run"
        )
    run_dir = annotations_path.parent
    if annotations_path.exists():
        raise FileExistsError(
            f"annotation output already exists: {annotations_path}"
        )
    if (run_dir / "manifest.json").exists() or (run_dir / "calls.jsonl").exists():
        raise FileExistsError(
            f"annotation child-run directory is not empty: {run_dir}"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, annotations_path


def _file_entry(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "sha256": file_hash(path),
        "rows": sum(
            1
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ),
    }


def _annotation_implementation_files() -> dict[str, str]:
    repository_root = Path(__file__).resolve().parents[1]
    return {
        relative: file_hash(repository_root / relative)
        for relative in ANNOTATION_IMPLEMENTATION_FILES
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("memories")
    parser.add_argument(
        "--output",
        default=None,
        help="optional child-run JSONL path outside the completed source run",
    )
    parser.add_argument("--task", default="memory_annotator")
    parser.add_argument("--target", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--human-sample-size", type=int, default=0)
    args = parser.parse_args()
    run_dir = annotate(
        Path(args.memories),
        output_path=(Path(args.output) if args.output else None),
        task=args.task,
        target=args.target,
        model=args.model,
        batch_size=args.batch_size,
        human_sample_size=args.human_sample_size,
        command=(
            "python -m experiments.annotate_authorization_memories "
            + " ".join(sys.argv[1:])
        ),
    )
    print(f"Annotation run saved to {run_dir}")


if __name__ == "__main__":
    main()
