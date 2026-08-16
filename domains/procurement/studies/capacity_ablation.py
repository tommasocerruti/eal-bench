from __future__ import annotations

import json
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from eal_bench.llm import load_config

from experiments.authorization_memory.langmem_writer import (
    _stable_id as _writer_stable_id,
    framework_manifest,
    manager_instructions,
)
from experiments.authorization_memory.persistence import content_hash, file_hash
from experiments.authorization_memory.pipeline import calibrate_capacity
from experiments.authorization_memory.provenance import target_route_manifest
from experiments.authorization_memory.schemas import MemoryArchitecture
from experiments.authorization_memory.study_plan import (
    StudyFinalization,
    StudyPlan,
)
from experiments.authorization_memory.tokens import count_reference_tokens

from .memory import canonical_json
from .route_support import standard_writer_specs
from .routes import _evidence_from_row, _memory_from_row, _ordinary_job


EXPERIMENT_ID = "procurement_typed_incremental_capacity_nonbinding"
WRITER_STUDY_ID = "capacity_nonbinding_writer"
REPLAY_STUDY_ID = "capacity_nonbinding_replay"
WRITER_VISIBLE_EXPERIMENT_ID = (
    "procurement_typed_incremental_capacity_writer_visible_nonbinding"
)
WRITER_VISIBLE_WRITER_STUDY_ID = "capacity_writer_visible_nonbinding"
WRITER_VISIBLE_REPLAY_STUDY_ID = "capacity_writer_visible_nonbinding_replay"
WRITER_VISIBLE_CAPACITY_TOKENS = 8192
PRIMARY_CAPACITY_TIER = "primary"
PRIMARY_EXECUTOR = "gptoss_baseten"
PRIMARY_SEED = 20260719
WRITER_TARGETS = (
    "nemotron_3_ultra_baseten",
    "grok_4_3_openrouter",
    "kimi_baseten",
    "glm_5_2_baseten",
    "qwen_plus_0728_openrouter",
)
BASELINE_RUNS = {
    "nemotron_3_ultra_baseten": Path(
        "results/procurement/"
        "20260809-005257-869522__authorization-memory-writer__"
        "procurement-v1-transfer-nemotron-3-ultra"
    ),
    "grok_4_3_openrouter": Path(
        "results/procurement/"
        "20260809-010130-962971__authorization-memory-writer__"
        "procurement-v1-transfer-grok-4-3"
    ),
    "kimi_baseten": Path(
        "results/procurement/"
        "20260809-112937-803837__authorization-memory-writer__"
        "procurement-v1-transfer-kimi-k2-6-technical-completion"
    ),
    "glm_5_2_baseten": Path(
        "results/procurement/"
        "20260809-011450-878789__authorization-memory-writer__"
        "procurement-v1-transfer-glm-5-2"
    ),
    "qwen_plus_0728_openrouter": Path(
        "results/procurement/"
        "20260809-124843-399194__authorization-memory-writer__"
        "procurement-v1-transfer-qwen-plus-0728"
    ),
}
PREVIOUS_NONBINDING_WRITER_RUN = Path(
    "results/procurement/"
    "20260816-132209-847941__authorization-memory-capacity_nonbinding_writer__"
    "procurement-typed-incremental-capacity-nonbinding"
)
PREVIOUS_NONBINDING_REPLAY_RUN = Path(
    "results/procurement/"
    "20260816-134349-730098__authorization-memory-capacity_nonbinding_replay__"
    "procurement-typed-incremental-capacity-nonbinding-gptoss-replay"
)
PREVIOUS_NONBINDING_ANALYSIS = Path(
    "results/capacity_ablation/"
    "20260816__procurement_typed_incremental_capacity_nonbinding"
)


def validate_writer_options(options: Mapping[str, Any]) -> None:
    _require_fixed_surface(options)
    if str(options.get("source_run") or "").strip():
        raise ValueError(f"{WRITER_STUDY_ID} does not accept --source-run")
    if tuple(options.get("writer_targets") or ()) != WRITER_TARGETS:
        raise ValueError(
            f"{WRITER_STUDY_ID} requires the five frozen writer targets in "
            "their benchmark order"
        )
    if tuple(options.get("executor_targets") or ()):
        raise ValueError(f"{WRITER_STUDY_ID} is writer-only")
    if str(options.get("writer_architecture") or "all") != "typed":
        raise ValueError(f"{WRITER_STUDY_ID} requires --writer-architecture typed")
    if str(options.get("writer_strategy") or "all") != "incremental":
        raise ValueError(f"{WRITER_STUDY_ID} requires --writer-strategy incremental")
    if int(options.get("writer_runs", 1)) != 1:
        raise ValueError(f"{WRITER_STUDY_ID} requires --writer-runs 1")
    if int(options.get("writer_max_attempts", 2)) != 2:
        raise ValueError(f"{WRITER_STUDY_ID} requires --writer-max-attempts 2")
    if str(options.get("writer_task") or "writer") != "writer":
        raise ValueError(f"{WRITER_STUDY_ID} requires the writer task")


def build_writer_plan(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyPlan:
    validate_writer_options(options)
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    specs = tuple(
        spec
        for spec in standard_writer_specs(
            domain,
            cases,
            presentation=presentation,
            target_ids=WRITER_TARGETS,
            writer_runs=1,
            seed=PRIMARY_SEED,
        )
        if spec.condition_id == "incremental_typed"
    )
    if len(specs) != len(WRITER_TARGETS) * len(cases):
        raise ValueError("nonbinding writer plan did not produce 60 trajectories")
    compatibility = _baseline_compatibility(domain, cases, specs, options)
    calibration = calibrate_capacity(
        domain,
        cases,
        corpus_version="benchmark_v1",
        presentation=presentation,
    )
    return StudyPlan(
        study_id=WRITER_STUDY_ID,
        writer_only=True,
        writer_chains=specs,
        artifact_schemas={
            "capacity_attempts": 1,
            "capacity_states": 1,
        },
        persist_empty_artifacts=("capacity_attempts", "capacity_states"),
        finalizer=_capacity_finalizer,
        metadata={
            "route": WRITER_STUDY_ID,
            "experiment_id": EXPERIMENT_ID,
            "conditions": ["incremental_typed"],
            "writer_architecture": "typed",
            "writer_strategy": "incremental",
            "capacity_enforced": False,
            "capacity_condition": {
                "condition_id": "nonbinding",
                "implementation": "capacity_validator_disabled",
                "prompt_capacity_tier": PRIMARY_CAPACITY_TIER,
                "prompt_capacity_tokens": calibration.primary_tokens,
                "validator_capacity_tokens": None,
                "all_other_payload_validators_enabled": True,
                "model_visible_capacity_instruction_changed": False,
            },
            "baseline_compatibility": compatibility,
            "planned_trajectories": len(specs),
            "planned_logical_updates": sum(len(spec.updates) for spec in specs),
            "primary_executor_for_replay": PRIMARY_EXECUTOR,
        },
    )


def validate_writer_visible_options(options: Mapping[str, Any]) -> None:
    validate_writer_options(options)


def build_writer_visible_plan(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyPlan:
    validate_writer_visible_options(options)
    presentation = domain.get_presentation(
        str(options.get("presentation_version") or "") or None
    )
    specs = tuple(
        spec
        for spec in standard_writer_specs(
            domain,
            cases,
            presentation=presentation,
            target_ids=WRITER_TARGETS,
            writer_runs=1,
            seed=PRIMARY_SEED,
        )
        if spec.condition_id == "incremental_typed"
    )
    if len(specs) != len(WRITER_TARGETS) * len(cases):
        raise ValueError("writer-visible plan did not produce 60 trajectories")
    baseline = _baseline_compatibility(domain, cases, specs, options)
    prompt_treatment = _writer_visible_prompt_compatibility(
        domain, specs, PREVIOUS_NONBINDING_WRITER_RUN
    )
    comparator_freeze = {
        "baseline_writer_runs": {
            target: _tree_snapshot(path) for target, path in BASELINE_RUNS.items()
        },
        "enforcement_disabled_writer_run": _tree_snapshot(
            PREVIOUS_NONBINDING_WRITER_RUN
        ),
        "enforcement_disabled_replay_run": _tree_snapshot(
            PREVIOUS_NONBINDING_REPLAY_RUN
        ),
        "enforcement_disabled_analysis": _tree_snapshot(
            PREVIOUS_NONBINDING_ANALYSIS
        ),
    }
    return StudyPlan(
        study_id=WRITER_VISIBLE_WRITER_STUDY_ID,
        writer_only=True,
        writer_chains=specs,
        artifact_schemas={"capacity_attempts": 1, "capacity_states": 1},
        persist_empty_artifacts=("capacity_attempts", "capacity_states"),
        finalizer=_writer_visible_capacity_finalizer,
        metadata={
            "route": WRITER_VISIBLE_WRITER_STUDY_ID,
            "experiment_id": WRITER_VISIBLE_EXPERIMENT_ID,
            "conditions": ["incremental_typed"],
            "writer_architecture": "typed",
            "writer_strategy": "incremental",
            "capacity_enforced": False,
            "writer_visible_capacity_tokens": WRITER_VISIBLE_CAPACITY_TOKENS,
            "capacity_condition": {
                "condition_id": "writer_visible_nonbinding",
                "implementation": (
                    "capacity_validator_disabled_with_high_visible_limit"
                ),
                "calibrated_capacity_tier": PRIMARY_CAPACITY_TIER,
                "calibrated_capacity_tokens": 572,
                "prompt_capacity_tokens": WRITER_VISIBLE_CAPACITY_TOKENS,
                "validator_capacity_tokens": None,
                "writer_output_ceiling_tokens": 4096,
                "all_other_payload_validators_enabled": True,
                "model_visible_capacity_instruction_changed": True,
                "treatment_change": "572_to_8192_numeric_value_only",
            },
            "baseline_compatibility": baseline,
            "prompt_treatment_validation": prompt_treatment,
            "comparator_freeze": comparator_freeze,
            "planned_trajectories": len(specs),
            "planned_logical_updates": sum(len(spec.updates) for spec in specs),
            "primary_executor_for_replay": PRIMARY_EXECUTOR,
        },
    )


def validate_replay_options(options: Mapping[str, Any]) -> None:
    _require_fixed_surface(options)
    if not str(options.get("source_run") or "").strip():
        raise ValueError(f"{REPLAY_STUDY_ID} requires --source-run")
    if tuple(options.get("writer_targets") or ()):
        raise ValueError(f"{REPLAY_STUDY_ID} is executor-only")
    if tuple(options.get("executor_targets") or ()) != (PRIMARY_EXECUTOR,):
        raise ValueError(
            f"{REPLAY_STUDY_ID} requires --executor-targets {PRIMARY_EXECUTOR}"
        )
    if int(options.get("executor_runs", 1)) != 1:
        raise ValueError(f"{REPLAY_STUDY_ID} requires --executor-runs 1")
    if str(options.get("executor_task") or "executor") != "executor":
        raise ValueError(f"{REPLAY_STUDY_ID} requires the executor task")


def build_replay_plan(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyPlan:
    validate_replay_options(options)
    source_path = Path(str(options["source_run"])).expanduser().resolve()
    manifest_path = source_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("status") != "completed"
        or manifest.get("study") != WRITER_STUDY_ID
        or manifest.get("experiment_id") != EXPERIMENT_ID
        or manifest.get("capacity_enforced") is not False
    ):
        raise ValueError("replay source is not the completed nonbinding writer run")
    if manifest.get("case_ids") != [domain.corpus.case_id(case) for case in cases]:
        raise ValueError("replay source case selection changed")
    capacity = manifest.get("capacity_condition")
    if not isinstance(capacity, Mapping) or capacity.get("implementation") != (
        "capacity_validator_disabled"
    ):
        raise ValueError("replay source capacity condition is invalid")
    memories = tuple(
        _memory_from_row(row) for row in _verified_rows(source_path, manifest, "memories")
    )
    evidence = tuple(
        _evidence_from_row(row) for row in _verified_rows(source_path, manifest, "evidence")
    )
    if len(evidence) != len(WRITER_TARGETS) * len(cases):
        raise ValueError("replay source does not contain 60 final trajectories")
    memory_by_id = {item.memory_id: item for item in memories}
    final_memories = []
    case_by_id = {domain.corpus.case_id(case): case for case in cases}
    jobs = []
    lineage = []
    for item in evidence:
        if (
            item.condition_id != "incremental_typed"
            or item.architecture is not MemoryArchitecture.TYPED
            or item.writer is None
            or item.writer.target_id not in WRITER_TARGETS
            or item.memory_id not in memory_by_id
        ):
            raise ValueError("replay source evidence lineage is invalid")
        memory = memory_by_id[str(item.memory_id)]
        final_memories.append(memory)
        case = case_by_id[item.case_id]
        for probe in domain.corpus.probes(case):
            jobs.append(
                _ordinary_job(
                    case,
                    probe,
                    item,
                    route=REPLAY_STUDY_ID,
                    evidence_role="generated_final",
                )
            )
        lineage.append(
            {
                "schema_version": 1,
                "experiment_id": EXPERIMENT_ID,
                "source_run": str(source_path),
                "source_manifest_sha256": file_hash(manifest_path),
                "writer_target": item.writer.target_id,
                "case_id": item.case_id,
                "memory_id": item.memory_id,
                "evidence_id": item.evidence_id,
                "content_hash": item.content_hash,
            }
        )
    return StudyPlan(
        study_id=REPLAY_STUDY_ID,
        executor_only=True,
        jobs=tuple(jobs),
        controlled_memories=tuple(final_memories),
        source_evidence=evidence,
        artifact_schemas={"source_lineage": 1},
        artifact_rows={"source_lineage": tuple(lineage)},
        metadata={
            "route": REPLAY_STUDY_ID,
            "experiment_id": EXPERIMENT_ID,
            "conditions": ["incremental_typed"],
            "capacity_condition": dict(capacity),
            "source_run": str(source_path),
            "source_manifest_sha256": file_hash(manifest_path),
            "source_trajectories": len(evidence),
            "primary_executor": PRIMARY_EXECUTOR,
            "downstream_configuration_changed": False,
        },
    )


def validate_writer_visible_replay_options(options: Mapping[str, Any]) -> None:
    _require_fixed_surface(options)
    if not str(options.get("source_run") or "").strip():
        raise ValueError(f"{WRITER_VISIBLE_REPLAY_STUDY_ID} requires --source-run")
    if tuple(options.get("writer_targets") or ()):
        raise ValueError(f"{WRITER_VISIBLE_REPLAY_STUDY_ID} is executor-only")
    if tuple(options.get("executor_targets") or ()) != (PRIMARY_EXECUTOR,):
        raise ValueError(
            f"{WRITER_VISIBLE_REPLAY_STUDY_ID} requires --executor-targets "
            f"{PRIMARY_EXECUTOR}"
        )
    if int(options.get("executor_runs", 1)) != 1:
        raise ValueError(f"{WRITER_VISIBLE_REPLAY_STUDY_ID} requires --executor-runs 1")
    if str(options.get("executor_task") or "executor") != "executor":
        raise ValueError(f"{WRITER_VISIBLE_REPLAY_STUDY_ID} requires the executor task")


def build_writer_visible_replay_plan(
    domain: Any,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyPlan:
    validate_writer_visible_replay_options(options)
    source_path = Path(str(options["source_run"])).expanduser().resolve()
    manifest_path = source_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("status") != "completed"
        or manifest.get("study") != WRITER_VISIBLE_WRITER_STUDY_ID
        or manifest.get("experiment_id") != WRITER_VISIBLE_EXPERIMENT_ID
        or manifest.get("capacity_enforced") is not False
        or manifest.get("writer_visible_capacity_tokens")
        != WRITER_VISIBLE_CAPACITY_TOKENS
    ):
        raise ValueError(
            "replay source is not the completed writer-visible nonbinding run"
        )
    if manifest.get("case_ids") != [domain.corpus.case_id(case) for case in cases]:
        raise ValueError("replay source case selection changed")
    capacity = manifest.get("capacity_condition")
    if not isinstance(capacity, Mapping) or capacity.get("implementation") != (
        "capacity_validator_disabled_with_high_visible_limit"
    ):
        raise ValueError("replay source capacity condition is invalid")
    memories = tuple(
        _memory_from_row(row) for row in _verified_rows(source_path, manifest, "memories")
    )
    evidence = tuple(
        _evidence_from_row(row)
        for row in _verified_rows(source_path, manifest, "evidence")
    )
    if len(evidence) != len(WRITER_TARGETS) * len(cases):
        raise ValueError("replay source does not contain 60 final trajectories")
    memory_by_id = {item.memory_id: item for item in memories}
    final_memories = []
    case_by_id = {domain.corpus.case_id(case): case for case in cases}
    jobs = []
    lineage = []
    for item in evidence:
        if (
            item.condition_id != "incremental_typed"
            or item.architecture is not MemoryArchitecture.TYPED
            or item.writer is None
            or item.writer.target_id not in WRITER_TARGETS
            or item.memory_id not in memory_by_id
        ):
            raise ValueError("replay source evidence lineage is invalid")
        memory = memory_by_id[str(item.memory_id)]
        final_memories.append(memory)
        case = case_by_id[item.case_id]
        for probe in domain.corpus.probes(case):
            jobs.append(
                _ordinary_job(
                    case,
                    probe,
                    item,
                    route=WRITER_VISIBLE_REPLAY_STUDY_ID,
                    evidence_role="generated_final",
                )
            )
        lineage.append(
            {
                "schema_version": 1,
                "experiment_id": WRITER_VISIBLE_EXPERIMENT_ID,
                "source_run": str(source_path),
                "source_manifest_sha256": file_hash(manifest_path),
                "writer_target": item.writer.target_id,
                "case_id": item.case_id,
                "memory_id": item.memory_id,
                "evidence_id": item.evidence_id,
                "content_hash": item.content_hash,
            }
        )
    return StudyPlan(
        study_id=WRITER_VISIBLE_REPLAY_STUDY_ID,
        executor_only=True,
        jobs=tuple(jobs),
        controlled_memories=tuple(final_memories),
        source_evidence=evidence,
        artifact_schemas={"source_lineage": 1},
        artifact_rows={"source_lineage": tuple(lineage)},
        metadata={
            "route": WRITER_VISIBLE_REPLAY_STUDY_ID,
            "experiment_id": WRITER_VISIBLE_EXPERIMENT_ID,
            "conditions": ["incremental_typed"],
            "capacity_condition": dict(capacity),
            "source_run": str(source_path),
            "source_manifest_sha256": file_hash(manifest_path),
            "source_trajectories": len(evidence),
            "primary_executor": PRIMARY_EXECUTOR,
            "downstream_configuration_changed": False,
        },
    )


def _require_fixed_surface(options: Mapping[str, Any]) -> None:
    if str(options.get("corpus_version") or "") != "benchmark_v1":
        raise ValueError("capacity ablation requires benchmark_v1")
    if str(options.get("presentation_version") or "") != "naturalistic_v1":
        raise ValueError("capacity ablation requires naturalistic_v1")
    if str(options.get("capacity_tier") or PRIMARY_CAPACITY_TIER) != (
        PRIMARY_CAPACITY_TIER
    ):
        raise ValueError("capacity ablation keeps the primary 2x prompt tier")
    if int(options.get("seed", PRIMARY_SEED)) != PRIMARY_SEED:
        raise ValueError(f"capacity ablation requires seed {PRIMARY_SEED}")


def _baseline_compatibility(
    domain: Any,
    cases: Sequence[Any],
    specs: Sequence[Any],
    options: Mapping[str, Any],
) -> dict[str, Any]:
    config = load_config()
    implementation = framework_manifest(domain)
    presentation = domain.get_presentation("naturalistic_v1")
    presentation_hash = content_hash(presentation.to_dict())
    manifests = {}
    prompt_checks = 0
    specs_by_target = {
        target: [spec for spec in specs if spec.target_id == target]
        for target in WRITER_TARGETS
    }
    for target, run_path in BASELINE_RUNS.items():
        manifest_path = run_path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("status") != "completed"
            or manifest.get("corpus_version") != "benchmark_v1"
            or manifest.get("seed") != PRIMARY_SEED
            or manifest.get("capacity_tier") != PRIMARY_CAPACITY_TIER
            or manifest.get("capacity", {}).get("primary_tokens") != 572
            or manifest.get("presentation_hash") != presentation_hash
            or manifest.get("writer", {}).get("memory_implementation_hash")
            != implementation["memory_implementation_hash"]
        ):
            raise ValueError(f"baseline manifest changed: {manifest_path}")
        route = manifest.get("writer", {}).get("target_routes", [None])[0]
        current_route = target_route_manifest(
            config, "writer", target, call_profiles=[]
        )
        for field in (
            "target_id",
            "provider",
            "requested_model",
            "resolved_model",
            "capabilities",
            "max_concurrency",
            "rate_limit",
            "request_parameters",
        ):
            if not isinstance(route, Mapping) or route.get(field) != current_route.get(field):
                raise ValueError(f"writer route changed for {target}: {field}")
        if manifest.get("writer", {}).get("task_parameters") != dict(
            config.task("writer").params
        ):
            raise ValueError(f"writer task parameters changed for {target}")
        contexts = _verified_rows(run_path, manifest, "model_contexts")
        first_contexts = {
            (str(row["case_id"]), int(row["block_index"])): row
            for row in contexts
            if row.get("stage") == "writer"
            and row.get("condition_id") == "incremental_typed"
            and row.get("metadata", {}).get("attempt_index") == 1
        }
        for spec in specs_by_target[target]:
            update = spec.updates[0]
            context = first_contexts.get(
                (domain.corpus.case_id(spec.case), int(update.block_index))
            )
            if context is None:
                raise ValueError(f"baseline first-attempt context missing for {target}")
            chain_id = _writer_stable_id(
                "chain",
                domain.domain_id,
                domain.corpus.case_id(spec.case),
                spec.condition_id,
                str(spec.run_id),
                spec.target_id,
                str(route["provider"]),
                str(route["requested_model"]),
                str(route["resolved_model"]),
                spec.model_override or "",
                spec.chain_instance_id,
                spec.presentation_id,
                spec.presentation_hash or "",
            )
            profile_id = _writer_stable_id("profile", chain_id)
            expected = manager_instructions(
                domain,
                case=spec.case,
                architecture=spec.architecture,
                capacity_tokens=572,
                repair_detail=None,
                presentation_id=spec.presentation_id,
                profile_id=profile_id,
                instruction_prefix=spec.instruction_prefix,
            )
            messages = context.get("messages")
            if (
                not isinstance(messages, list)
                or len(messages) < 2
                or not str(messages[1].get("content") or "").startswith(
                    expected + "\n\n"
                )
            ):
                raise ValueError(f"writer prompt changed for {target}")
            if "nonbinding" in expected.lower() or "unlimited" in expected.lower():
                raise ValueError("nonbinding treatment leaked into the writer prompt")
            prompt_checks += 1
        manifests[target] = {
            "path": str(run_path),
            "manifest_sha256": file_hash(manifest_path),
            "git": manifest.get("git"),
            "implementation_files": manifest.get("implementation_files"),
        }
    if prompt_checks != len(WRITER_TARGETS) * len(cases):
        raise ValueError("baseline prompt compatibility coverage is incomplete")
    return {
        "status": "passed",
        "baseline_capacity_tokens": 572,
        "prompt_checks": prompt_checks,
        "provider_routes_checked": len(WRITER_TARGETS),
        "framework": implementation,
        "baseline_runs": manifests,
        "treatment_difference": "persistent_artifact_capacity_validation_only",
        "command_seed": int(options["seed"]),
    }


def _writer_visible_prompt_compatibility(
    domain: Any,
    specs: Sequence[Any],
    previous_run: Path,
) -> dict[str, Any]:
    config = load_config()
    if dict(config.task("writer").params).get("max_tokens") != 4096:
        raise ValueError("writer output-token ceiling changed from 4096")
    manifest = json.loads((previous_run / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("status") != "completed"
        or manifest.get("study") != WRITER_STUDY_ID
        or manifest.get("experiment_id") != EXPERIMENT_ID
        or manifest.get("capacity_enforced") is not False
        or manifest.get("capacity_condition", {}).get("prompt_capacity_tokens") != 572
    ):
        raise ValueError("previous enforcement-disabled comparator changed")
    contexts = _verified_rows(previous_run, manifest, "model_contexts")
    rendered_contexts = json.dumps(contexts, ensure_ascii=False)
    if rendered_contexts.count("572 reference tokens") != len(contexts):
        raise ValueError(
            "previous enforcement-disabled prompts did not all display 572 tokens"
        )
    low_line = "The serialized profile must fit within 572 reference tokens."
    high_line = (
        "The serialized profile must fit within "
        f"{WRITER_VISIBLE_CAPACITY_TOKENS} reference tokens."
    )
    checks = 0
    representative: dict[str, Any] | None = None
    for spec in specs:
        route = target_route_manifest(
            config, "writer", spec.target_id, call_profiles=[]
        )
        chain_id = _writer_stable_id(
            "chain",
            domain.domain_id,
            domain.corpus.case_id(spec.case),
            spec.condition_id,
            str(spec.run_id),
            spec.target_id,
            str(route["provider"]),
            str(route["requested_model"]),
            str(route["resolved_model"]),
            spec.model_override or "",
            spec.chain_instance_id,
            spec.presentation_id,
            spec.presentation_hash or "",
        )
        profile_id = _writer_stable_id("profile", chain_id)
        common = {
            "domain": domain,
            "case": spec.case,
            "architecture": spec.architecture,
            "repair_detail": None,
            "presentation_id": spec.presentation_id,
            "profile_id": profile_id,
            "instruction_prefix": spec.instruction_prefix,
        }
        low = manager_instructions(capacity_tokens=572, **common)
        high = manager_instructions(
            capacity_tokens=WRITER_VISIBLE_CAPACITY_TOKENS, **common
        )
        if low.count(low_line) != 1 or high.count(high_line) != 1:
            raise ValueError("capacity instruction was not rendered exactly once")
        if low.replace(low_line, high_line) != high:
            raise ValueError("writer-visible treatment changed more than capacity value")
        checks += 1
        if representative is None:
            representative = {
                "writer_target": spec.target_id,
                "case_id": domain.corpus.case_id(spec.case),
                "original_2x_capacity_line": low_line,
                "enforcement_disabled_capacity_line": low_line,
                "writer_visible_nonbinding_capacity_line": high_line,
                "original_and_enforcement_disabled_sha256": content_hash(low),
                "writer_visible_nonbinding_sha256": content_hash(high),
                "normalized_diff": [f"- {low_line}", f"+ {high_line}"],
            }
    if checks != len(WRITER_TARGETS) * 12:
        raise ValueError("writer-visible prompt treatment coverage is incomplete")
    return {
        "status": "passed",
        "control_point": (
            "experiments.authorization_memory.langmem_writer.manager_instructions"
        ),
        "previous_contexts_checked": len(contexts),
        "previous_capacity_instruction_mentions": len(contexts),
        "rendered_trajectory_prompts_checked": checks,
        "comparison": "572_visible_unenforced_vs_8192_visible_unenforced",
        "result": "exact_single_numeric_capacity_change",
        "writer_output_ceiling_tokens": 4096,
        "writer_visible_capacity_tokens": WRITER_VISIBLE_CAPACITY_TOKENS,
        "representative": representative,
    }


def _tree_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        raise ValueError(f"frozen comparator directory is missing: {path}")
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix()
        item_hash = file_hash(item)
        size = item.stat().st_size
        digest.update(f"{relative}\0{size}\0{item_hash}\n".encode())
        file_count += 1
        total_bytes += size
    return {
        "path": str(path),
        "tree_sha256": digest.hexdigest(),
        "file_count": file_count,
        "total_bytes": total_bytes,
    }


def _capacity_finalizer(
    domain: Any,
    cases: Sequence[Any],
    memories: Sequence[Any],
    attempts: Sequence[Any],
    states: Sequence[Any],
    evidence: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyFinalization:
    return _capacity_finalizer_impl(
        domain,
        cases,
        memories,
        attempts,
        states,
        evidence,
        options,
        experiment_id=EXPERIMENT_ID,
        writer_visible_capacity_tokens=572,
    )


def _writer_visible_capacity_finalizer(
    domain: Any,
    cases: Sequence[Any],
    memories: Sequence[Any],
    attempts: Sequence[Any],
    states: Sequence[Any],
    evidence: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyFinalization:
    return _capacity_finalizer_impl(
        domain,
        cases,
        memories,
        attempts,
        states,
        evidence,
        options,
        experiment_id=WRITER_VISIBLE_EXPERIMENT_ID,
        writer_visible_capacity_tokens=WRITER_VISIBLE_CAPACITY_TOKENS,
    )


def _capacity_finalizer_impl(
    domain: Any,
    cases: Sequence[Any],
    memories: Sequence[Any],
    attempts: Sequence[Any],
    states: Sequence[Any],
    evidence: Sequence[Any],
    options: Mapping[str, Any],
    *,
    experiment_id: str,
    writer_visible_capacity_tokens: int,
) -> StudyFinalization:
    del options
    calibration = calibrate_capacity(
        domain,
        cases,
        corpus_version="benchmark_v1",
        presentation=domain.get_presentation("naturalistic_v1"),
    )
    primary = calibration.primary_tokens
    memory_by_id = {memory.memory_id: memory for memory in memories}
    attempt_rows = []
    capacity_failures = 0
    candidate_sizes = []
    for attempt in attempts:
        tokens = _candidate_tokens(attempt.candidate_payload)
        if tokens is not None:
            candidate_sizes.append(tokens)
        capacity_triggered = "capacity is" in attempt.detail.lower()
        capacity_failures += int(capacity_triggered)
        attempt_rows.append(
            {
                "schema_version": 1,
                "experiment_id": experiment_id,
                "writer_target": attempt.writer.target_id,
                "case_id": attempt.case_id,
                "condition_id": attempt.condition_id,
                "block_index": attempt.block_index,
                "logical_update_id": attempt.logical_update_id,
                "attempt_id": attempt.attempt_id,
                "attempt_index": attempt.attempt_index,
                "status": attempt.status,
                "candidate_reference_tokens": tokens,
                "primary_capacity_tokens": primary,
                "writer_visible_capacity_tokens": writer_visible_capacity_tokens,
                "primary_capacity_utilization": (
                    tokens / primary if tokens is not None else None
                ),
                "would_exceed_primary_capacity": (
                    tokens > primary if tokens is not None else None
                ),
                "capacity_validation_applied": False,
                "capacity_triggered": capacity_triggered,
                "detail": attempt.detail,
            }
        )
    if capacity_failures:
        raise ValueError("nonbinding writer run recorded a capacity-triggered failure")
    state_rows = []
    for state in states:
        memory = memory_by_id.get(state.current_memory_id)
        tokens = memory.reference_tokens if memory is not None else 0
        state_rows.append(
            {
                "schema_version": 1,
                "experiment_id": experiment_id,
                "writer_target": memory.writer.target_id if memory and memory.writer else None,
                "case_id": state.case_id,
                "condition_id": state.condition_id,
                "block_index": state.block_index,
                "logical_update_id": state.logical_update_id,
                "state_id": state.state_id,
                "state_status": state.status,
                "changed": state.changed,
                "current_memory_id": state.current_memory_id,
                "memory_reference_tokens": tokens,
                "primary_capacity_tokens": primary,
                "writer_visible_capacity_tokens": writer_visible_capacity_tokens,
                "primary_capacity_utilization": tokens / primary,
                "exceeds_primary_capacity": tokens > primary,
                "capacity_validation_applied": False,
            }
        )
    if len(evidence) != len(WRITER_TARGETS) * len(cases):
        raise ValueError("nonbinding writer run did not finish all 60 trajectories")
    target_counts = {
        target: sum(
            item.writer is not None and item.writer.target_id == target
            for item in evidence
        )
        for target in WRITER_TARGETS
    }
    if any(count != len(cases) for count in target_counts.values()):
        raise ValueError("nonbinding writer trajectory counts differ by target")
    final_memory_ids = {str(item.memory_id) for item in evidence}
    final_sizes = [
        memory.reference_tokens
        for memory in memories
        if memory.memory_id in final_memory_ids
    ]
    state_sizes = [row["memory_reference_tokens"] for row in state_rows]
    thresholds = (572, 1144, 2288)
    return StudyFinalization(
        artifact_rows={
            "capacity_attempts": tuple(attempt_rows),
            "capacity_states": tuple(state_rows),
        },
        manifest_metadata={
            "capacity_audit": {
                "status": "passed",
                "trajectory_count": len(evidence),
                "logical_update_count": len(states),
                "attempt_count": len(attempts),
                "capacity_triggered_validation_failures": capacity_failures,
                "writer_visible_capacity_tokens": writer_visible_capacity_tokens,
                "writer_output_ceiling_tokens": 4096,
                "candidate_writes_above_primary": sum(
                    tokens > primary for tokens in candidate_sizes
                ),
                "accepted_memories_above_primary": sum(
                    memory.reference_tokens > primary for memory in memories
                ),
                "max_candidate_reference_tokens": max(candidate_sizes, default=0),
                "max_accepted_memory_reference_tokens": max(
                    (memory.reference_tokens for memory in memories), default=0
                ),
                "writer_trajectory_counts": target_counts,
                "capacity_was_nonbinding_for_every_write": True,
                "thresholds": {
                    str(threshold): {
                        "candidate_count_above": sum(
                            tokens > threshold for tokens in candidate_sizes
                        ),
                        "candidate_fraction_above": (
                            sum(tokens > threshold for tokens in candidate_sizes)
                            / len(candidate_sizes)
                            if candidate_sizes
                            else None
                        ),
                        "accepted_memory_count_above": sum(
                            memory.reference_tokens > threshold for memory in memories
                        ),
                        "accepted_memory_fraction_above": (
                            sum(
                                memory.reference_tokens > threshold
                                for memory in memories
                            )
                            / len(memories)
                            if memories
                            else None
                        ),
                        "per_update_state_count_above": sum(
                            tokens > threshold for tokens in state_sizes
                        ),
                        "per_update_state_fraction_above": (
                            sum(tokens > threshold for tokens in state_sizes)
                            / len(state_sizes)
                            if state_sizes
                            else None
                        ),
                        "final_memory_count_above": sum(
                            tokens > threshold for tokens in final_sizes
                        ),
                        "final_memory_fraction_above": (
                            sum(tokens > threshold for tokens in final_sizes)
                            / len(final_sizes)
                            if final_sizes
                            else None
                        ),
                    }
                    for threshold in thresholds
                },
            }
        },
    )


def _candidate_tokens(payload: Any) -> int | None:
    if isinstance(payload, str):
        return count_reference_tokens(payload)
    if isinstance(payload, Mapping):
        return count_reference_tokens(canonical_json(payload))
    return None


def _verified_rows(
    run_path: Path,
    manifest: Mapping[str, Any],
    name: str,
) -> list[dict[str, Any]]:
    files = manifest.get("files")
    entry = files.get(name) if isinstance(files, Mapping) else None
    if not isinstance(entry, Mapping):
        raise ValueError(f"manifest is missing {name}")
    path = run_path / str(entry.get("path") or "")
    if not path.is_file() or file_hash(path) != entry.get("sha256"):
        raise ValueError(f"artifact hash failed for {name}: {path}")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != entry.get("rows"):
        raise ValueError(f"artifact row count failed for {name}: {path}")
    return rows
