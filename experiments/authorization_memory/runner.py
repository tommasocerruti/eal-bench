from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from eal_bench.llm import LLM
from eal_bench.llm.logger import JSONLLogger

from domains.base import AuthorizationMemoryDomain

from .challenges import validate_challenge_construction
from .conformance import validate_domain_conformance
from .conditions import condition_ids, get_condition
from .langmem_writer import framework_manifest
from .leakage import validate_model_visible_leakage
from .persistence import (
    content_hash,
    create_run_dir,
    file_hash,
    git_info,
    runtime_info,
    write_json,
    write_jsonl,
)
from .pipeline import run_core, validate_core_construction
from .provenance import (
    effective_behavioral_parameters,
    target_route_manifest,
)
from .schemas import ARTIFACT_SCHEMA_VERSIONS, LANGMEM_IMPLEMENTATION_ID


def validate_domain(
    domain: AuthorizationMemoryDomain,
    *,
    corpus_version: str,
    requested_case_ids: Sequence[str] = (),
    selected_conditions: Sequence[str] = (),
    presentation_version: str | None = None,
) -> dict[str, Any]:
    presentation = domain.get_presentation(presentation_version)
    cases = _select_cases(
        domain,
        domain.corpus.load_cases(corpus_version),
        requested_case_ids,
    )
    result = validate_core_construction(
        domain,
        cases,
        corpus_version=corpus_version,
        condition_ids=selected_conditions or None,
        presentation=presentation,
    )
    result["source_files"] = {
        str(path): file_hash(path)
        for path in domain.corpus.source_files(corpus_version)
    }
    result["corpus_provenance"] = dict(
        domain.corpus.provenance(corpus_version)
    )
    result["studies"] = list(domain.study_ids)
    result["presentation"] = presentation.to_dict()
    result["presentation_hash"] = content_hash(presentation.to_dict())
    result["model_visible_leakage"] = validate_model_visible_leakage(
        domain,
        cases,
        presentation,
    )
    result["conformance"] = validate_domain_conformance(domain, cases)
    result["challenges"] = validate_challenge_construction(
        domain,
        tuple(cases),
    )
    result["domain_offline_checks"] = {
        check_id: check(
            domain,
            cases,
            {
                "corpus_version": corpus_version,
                "presentation_version": presentation.presentation_id,
            },
        )
        for check_id, check in domain.offline_checks.items()
    }
    return result


def run_core_experiment(
    domain: AuthorizationMemoryDomain,
    *,
    corpus_version: str,
    writer_task: str,
    executor_task: str,
    writer_targets: Sequence[str],
    executor_targets: Sequence[str],
    requested_case_ids: Sequence[str] = (),
    selected_conditions: Sequence[str] = (),
    writer_runs: int = 1,
    executor_runs: int = 1,
    writer_max_attempts: int = 2,
    capacity_tier: str = "primary",
    batch_size: int | None = None,
    seed: int = 20260715,
    tag: str | None = None,
    command: str = "",
    presentation_version: str | None = None,
) -> Path:
    presentation = domain.get_presentation(presentation_version)
    cases = _select_cases(
        domain,
        domain.corpus.load_cases(corpus_version),
        requested_case_ids,
    )
    selected = tuple(selected_conditions) or condition_ids()
    writer_label = "-".join(writer_targets)
    executor_label = "-".join(executor_targets)
    run_dir = create_run_dir(
        domain.domain_id,
        f"authorization-memory-{capacity_tier}-w{writer_label}-e{executor_label}",
        tag=tag,
    )
    calls_path = run_dir / "calls.jsonl"
    manifest_path = run_dir / "manifest.json"
    llm = LLM(logger=JSONLLogger(calls_path))
    manifest = _manifest(
        domain,
        config=llm.config,
        corpus_version=corpus_version,
        cases=cases,
        selected_conditions=selected,
        writer_task=writer_task,
        executor_task=executor_task,
        writer_targets=writer_targets,
        executor_targets=executor_targets,
        writer_runs=writer_runs,
        executor_runs=executor_runs,
        writer_max_attempts=writer_max_attempts,
        capacity_tier=capacity_tier,
        batch_size=batch_size or llm.config.batch_size,
        seed=seed,
        command=command,
        presentation=presentation,
    )
    write_json(manifest_path, manifest)
    try:
        artifacts = run_core(
            llm,
            domain,
            cases,
            corpus_version=corpus_version,
            writer_task=writer_task,
            executor_task=executor_task,
            writer_targets=writer_targets,
            executor_targets=executor_targets,
            writer_runs=writer_runs,
            executor_runs=executor_runs,
            writer_max_attempts=writer_max_attempts,
            condition_ids=selected,
            capacity_tier=capacity_tier,
            batch_size=batch_size,
            seed=seed,
            presentation=presentation,
        )
        rows = {
            "memories": (run_dir / "memories.jsonl", artifacts.memories),
            "memory_attempts": (
                run_dir / "memory_attempts.jsonl",
                artifacts.attempts,
            ),
            "memory_states": (
                run_dir / "memory_states.jsonl",
                artifacts.states,
            ),
            "evidence": (run_dir / "evidence.jsonl", artifacts.evidence),
            "trials": (run_dir / "trials.jsonl", artifacts.trials),
            "model_contexts": (
                run_dir / "model_contexts.jsonl",
                artifacts.model_contexts,
            ),
        }
        files: dict[str, dict[str, Any]] = {}
        for name, (path, values) in rows.items():
            count = write_jsonl(path, values)
            files[name] = {
                "path": path.name,
                "sha256": file_hash(path),
                "rows": count,
            }
        if calls_path.exists():
            files["calls"] = {
                "path": calls_path.name,
                "sha256": file_hash(calls_path),
                "rows": sum(
                    1
                    for line in calls_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ),
            }
        manifest.update(
            {
                "capacity": artifacts.calibration.to_dict(),
                "files": files,
                "counts": {
                    "memories": len(artifacts.memories),
                    "memory_attempts": len(artifacts.attempts),
                    "memory_states": len(artifacts.states),
                    "evidence": len(artifacts.evidence),
                    "trials": len(artifacts.trials),
                    "model_contexts": len(artifacts.model_contexts),
                },
            }
        )
        _record_response_models(
            manifest["writer"]["target_routes"],
            (attempt.writer for attempt in artifacts.attempts),
        )
        _record_response_models(
            manifest["executor"]["target_routes"],
            (trial.executor for trial in artifacts.trials),
        )
        write_json(manifest_path, manifest)
        _validate_model_context_call_log(
            artifacts.model_contexts,
            calls_path,
        )
        manifest.update(
            {
                "status": "completed",
                "finished_at": datetime.now().astimezone().isoformat(),
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


def _validate_model_context_call_log(
    contexts: Sequence[Any],
    calls_path: Path,
) -> None:
    if not contexts:
        return
    if not calls_path.is_file():
        raise ValueError("model contexts were produced without a call log")
    records = [
        json.loads(line)
        for line in calls_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_call_id: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("call log rows must be objects")
        call_id = record.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("core call log row is missing its logical call ID")
        by_call_id.setdefault(call_id, []).append(record)

    contexts_by_call_id: dict[str, list[Any]] = {}
    for context in contexts:
        contexts_by_call_id.setdefault(context.call_id, []).append(context)
    context_call_ids = set(contexts_by_call_id)
    if set(by_call_id) != context_call_ids:
        raise ValueError("model contexts and call-log IDs do not match")

    writer_contexts_by_run_id: dict[str, Any] = {}
    for call_id, call_contexts in contexts_by_call_id.items():
        if len(call_contexts) > 1 and any(
            not context.framework_run_id for context in call_contexts
        ):
            raise ValueError(
                f"logical call {call_id!r} has duplicate non-writer contexts"
            )
        for context in call_contexts:
            framework_run_id = context.framework_run_id
            if not framework_run_id:
                continue
            if framework_run_id in writer_contexts_by_run_id:
                raise ValueError(
                    f"duplicate writer framework run ID {framework_run_id!r}"
                )
            writer_contexts_by_run_id[framework_run_id] = context

    for context in contexts:
        framework_run_id = context.framework_run_id
        matching_records = by_call_id[context.call_id]
        if framework_run_id:
            matching_records = [
                record
                for record in matching_records
                if record.get("langchain_run_id") == framework_run_id
            ]
            if len(matching_records) != 1:
                raise ValueError(
                    f"writer context {context.context_id} does not have exactly "
                    "one framework call-log row"
                )
        matching_hashes = {
            _call_record_context_hash(record) for record in matching_records
        }
        if matching_hashes != {context.content_hash}:
            raise ValueError(
                f"model context {context.context_id} does not match its call log"
            )

    for record in records:
        framework_run_id = record.get("langchain_run_id")
        if not isinstance(framework_run_id, str) or not framework_run_id:
            continue
        context = writer_contexts_by_run_id.get(framework_run_id)
        if context is None or context.call_id != record["call_id"]:
            raise ValueError(
                f"writer call-log row {framework_run_id!r} has no model context"
            )


def _call_record_context_hash(record: Mapping[str, Any]) -> str:
    request = record.get("request")
    if not isinstance(request, Mapping):
        raise ValueError("call log row has no request object")
    messages = request.get("messages")
    if not isinstance(messages, list):
        raise ValueError("call log request has no single message sequence")
    params = request.get("params")
    tools = request.get("tools")
    if tools is None and isinstance(params, Mapping):
        tools = params.get("tools")
    if tools is None:
        tools = []
    if not isinstance(tools, list):
        raise ValueError("call log request tools must be an array")
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


def _manifest(
    domain: AuthorizationMemoryDomain,
    *,
    config: Any,
    corpus_version: str,
    cases: Sequence[Any],
    selected_conditions: Sequence[str],
    writer_task: str,
    executor_task: str,
    writer_targets: Sequence[str],
    executor_targets: Sequence[str],
    writer_runs: int,
    executor_runs: int,
    writer_max_attempts: int,
    capacity_tier: str,
    batch_size: int,
    seed: int,
    command: str,
    presentation: Any = None,
) -> dict[str, Any]:
    presentation = presentation or domain.get_presentation()
    source_files = domain.corpus.source_files(corpus_version)
    implementation_files = _implementation_files(domain)
    writer_profiles = _writer_call_profiles(
        domain,
        config,
        task=writer_task,
        selected_conditions=selected_conditions,
        runs=writer_runs,
        seed=seed,
    )
    writer_active = any(
        get_condition(condition_id).writer_required
        for condition_id in selected_conditions
    )
    implementation = framework_manifest(domain)
    memory_implementation_id = LANGMEM_IMPLEMENTATION_ID
    memory_implementation_hash = implementation[
        "memory_implementation_hash"
    ]
    writer_framework = implementation if writer_active else None
    profile_schema = (
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
    )
    executor_profiles = _executor_call_profiles(
        domain,
        config,
        task=executor_task,
        runs=executor_runs,
        seed=seed,
    )
    return {
        "status": "running",
        "started_at": datetime.now().astimezone().isoformat(),
        "finished_at": None,
        "domain_id": domain.domain_id,
        "domain_adapter_version": domain.adapter_version,
        "domain_maturity": domain.maturity,
        "memory_implementation_id": memory_implementation_id,
        "memory_implementation_hash": memory_implementation_hash,
        "artifact_schema_versions": ARTIFACT_SCHEMA_VERSIONS,
        "corpus_version": corpus_version,
        "corpus_provenance": dict(
            domain.corpus.provenance(corpus_version)
        ),
        "presentation": presentation.to_dict(),
        "presentation_hash": content_hash(presentation.to_dict()),
        "case_ids": [domain.corpus.case_id(case) for case in cases],
        "conditions": list(selected_conditions),
        "study": "core",
        "writer": {
            "active": writer_active,
            "task": writer_task,
            "targets": list(writer_targets),
            "memory_implementation_id": memory_implementation_id,
            "memory_implementation_hash": memory_implementation_hash,
            "framework": writer_framework,
            "profile_schema": profile_schema,
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
            "runs": writer_runs,
            "max_attempts": writer_max_attempts,
        },
        "executor": {
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
            "runs": executor_runs,
        },
        "capacity_tier": capacity_tier,
        "batch_size": batch_size,
        "seed": seed,
        "source_files": {
            str(path): file_hash(path) for path in source_files
        },
        "implementation_files": {
            str(path.relative_to(_repository_root())): file_hash(path)
            for path in implementation_files
        },
        "command": command,
        "git": git_info(),
        "runtime": runtime_info(),
        "files": {},
    }


def _implementation_files(
    domain: AuthorizationMemoryDomain,
) -> tuple[Path, ...]:
    root = _repository_root()
    paths = {
        root / "config.yaml",
        root / "pyproject.toml",
        root / "uv.lock",
        root / "experiments" / "run.py",
        root / "domains" / "__init__.py",
        root / "domains" / "base.py",
    }
    paths.update((root / "experiments" / "authorization_memory").glob("*.py"))
    paths.update((root / "src" / "eal_bench" / "llm").glob("*.py"))
    paths.update(
        (root / "domains" / domain.domain_id).glob("**/*.py")
    )
    return tuple(sorted(path for path in paths if path.is_file()))


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _writer_call_profiles(
    domain: AuthorizationMemoryDomain,
    config: Any,
    *,
    task: str,
    selected_conditions: Sequence[str],
    runs: int,
    seed: int,
) -> list[dict[str, Any]]:
    architectures = sorted(
        {
            condition.architecture
            for condition_id in selected_conditions
            if (condition := get_condition(condition_id)).writer_required
        },
        key=lambda architecture: architecture.value,
    )
    profiles: list[dict[str, Any]] = []
    for architecture in architectures:
        for run_id in range(runs):
            profiles.append(
                {
                    "architecture": architecture.value,
                    "run_id": run_id,
                    "manager": framework_manifest(domain)["manager"],
                    "effective_parameters": effective_behavioral_parameters(
                        config,
                        task,
                        overrides={
                            "temperature": 1.0,
                            "seed": seed + run_id,
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
    *,
    task: str,
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


def _record_response_models(
    routes: Sequence[dict[str, Any]],
    provenances: Any,
) -> None:
    observed: dict[str, set[str]] = {}
    for provenance in provenances:
        if provenance.target_id is None or provenance.response_model is None:
            continue
        observed.setdefault(provenance.target_id, set()).add(
            provenance.response_model
        )
    for route in routes:
        response_models = sorted(observed.get(route["target_id"], set()))
        route["response_model"] = (
            response_models[0] if len(response_models) == 1 else None
        )
        route["response_models_observed"] = response_models


def _select_cases(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    requested: Sequence[str],
) -> tuple[Any, ...]:
    available = {
        domain.corpus.case_id(case): case
        for case in cases
    }
    if not requested:
        return tuple(cases)
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise ValueError(f"unknown case IDs: {', '.join(unknown)}")
    return tuple(available[case_id] for case_id in requested)


def print_validation(result: dict[str, Any]) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))
