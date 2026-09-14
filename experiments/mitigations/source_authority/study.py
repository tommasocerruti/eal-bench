"""Paired original/gated execution through the shared study engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from domains.base import AuthorizationMemoryDomain, StudyProfile
from domains.source_authority import cited_source_authority_adapter
from experiments.authorization_memory.persistence import canonical_json, content_hash, file_hash
from experiments.authorization_memory.schemas import MemoryOrigin
from experiments.authorization_memory.study_plan import ExecutorJob, StudyPlan
from experiments.authorization_memory.tokens import count_reference_tokens, reference_tokenizer_name

from .gate import GATE_SCHEMA_VERSION, apply_cited_source_authority_gate
from .sources import load_writer_source, source_paths

STUDY_ID = "source_authority"
PROTOCOL_VERSION = "source_authority_paired_replay_v1"


def shared_study_profile() -> StudyProfile:
    return StudyProfile(
        study_id=STUDY_ID,
        description="Paired original and cited-source-authority-gated frozen typed memories.",
        required_capabilities=("native_tools", "seed"),
        validator=validate_options,
        builder=build_plan,
    )


def validate_options(options: Mapping[str, Any]) -> None:
    source_paths(options)
    if options.get("writer_targets"):
        raise ValueError("source_authority reuses frozen writers and rejects --writer-targets")
    if not options.get("executor_targets"):
        raise ValueError("source_authority requires configured executor targets")
    if str(options.get("writer_strategy") or "all") not in {"all", "one_shot", "incremental"}:
        raise ValueError("source_authority writer strategy must be all, one_shot, or incremental")
    if str(options.get("writer_architecture") or "all") not in {"all", "typed"}:
        raise ValueError("source_authority requires typed source memories")


def build_plan(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> StudyPlan:
    validate_options(options)
    case_by_id = {domain.corpus.case_id(case): case for case in cases}
    sources = tuple(
        load_writer_source(path, domain, cases, options)
        for path in source_paths(options)
    )
    if len({source.manifest_hash for source in sources}) != len(sources):
        raise ValueError("source_authority cannot count a copied source run twice")
    jobs = []
    memories = {}
    evidence = {}
    decisions = []
    population = []
    source_rows = []
    resolver = cited_source_authority_adapter(domain)
    implementation = implementation_hashes()
    for source in sources:
        source_memories = {item.memory_id: item for item in source.memories}
        for original in source.evidence:
            if original.evidence_id in evidence or original.memory_id in memories:
                raise ValueError("source_authority sources contain overlapping final memories")
            case = case_by_id[original.case_id]
            original_memory = source_memories[original.memory_id]
            final_block = max(int(block.block_index) for block in domain.corpus.blocks(case))
            gate = apply_cited_source_authority_gate(
                domain, case, domain.memory.parse_typed(original.payload),
                through_block_index=final_block,
            )
            gate_id = stable_id("gate", source.manifest_hash, original.evidence_id, gate.to_dict())
            payload = dict(gate.gated_state)
            memory_id = stable_id("memory", gate_id, payload)
            gated_memory = replace(
                original_memory,
                memory_id=memory_id,
                parent_memory_id=original.memory_id,
                origin=MemoryOrigin.CONTROLLED,
                payload=payload,
                content_hash=content_hash(payload),
                reference_tokens=count_reference_tokens(canonical_json(payload)),
                reference_tokenizer=reference_tokenizer_name(),
                source_attempt_id=None,
                framework_run_ids=(),
                framework={
                    "source_writer_framework": dict(original_memory.framework),
                    "deterministic_transform": {
                        "gate_id": gate_id, "schema_version": GATE_SCHEMA_VERSION,
                        "source_memory_id": original.memory_id,
                        "source_attempt_id": original.source_attempt_id,
                        "implementation_files": implementation,
                    },
                },
            )
            gated = replace(
                original,
                evidence_id=stable_id("evidence", gate_id, memory_id),
                memory_id=memory_id,
                payload=payload,
                content_hash=gated_memory.content_hash,
                source_attempt_id=None,
            )
            evidence[original.evidence_id] = original
            evidence[gated.evidence_id] = gated
            memories[original.memory_id] = original_memory
            memories[gated_memory.memory_id] = gated_memory
            provenance = {
                "source_run": str(source.path),
                "source_manifest_sha256": source.manifest_hash,
                "source_evidence_id": original.evidence_id,
                "source_memory_id": original.memory_id,
                "source_memory_hash": original.content_hash,
                "source_memory_block_index": original_memory.block_index,
                "source_writer_seed": original.writer_seed,
                "source_writer_run_id": original.memory_run_id,
                "source_writer": original.writer.to_dict(),
                "source_profile_id": original.profile_id,
                "source_memory_implementation_id": original.memory_implementation_id,
                "source_memory_implementation_hash": original.memory_implementation_hash,
                "source_corpus_version": source.manifest["corpus_version"],
                "source_corpus_provenance_hash": content_hash(source.manifest["corpus_provenance"]),
                "source_presentation_id": original.presentation_id,
                "source_presentation_hash": original.presentation_hash,
            }
            decisions.append({
                "schema_version": 1,
                "gate_id": gate_id,
                "case_id": original.case_id,
                "condition_id": original.condition_id,
                **provenance,
                "gated_evidence_id": gated.evidence_id,
                "gated_memory_id": gated.memory_id,
                "gated_memory_hash": gated.content_hash,
                "immutable_authority_metadata": [
                    item.to_dict() for item in resolver.resolve(case, final_block).values()
                ],
                "result": gate.to_dict(),
            })
            for probe in domain.corpus.probes(case):
                pair_id = stable_id("pair", source.manifest_hash, original.evidence_id, probe.probe_id)
                job_ids = {}
                for variant, item in (("ORIGINAL", original), ("GATED", gated)):
                    job_id = stable_id("job", pair_id, variant)
                    job_ids[variant] = job_id
                    jobs.append(ExecutorJob(
                        job_id=job_id,
                        case=case,
                        probe=probe,
                        evidence=item,
                        metadata={
                            "route": STUDY_ID,
                            "source_authority_protocol": PROTOCOL_VERSION,
                            "variant": variant,
                            "pair_id": pair_id,
                            "gate_id": gate_id,
                            "evidence_role": "generated_final",
                            "gate_changed": original.content_hash != gated.content_hash,
                            "source_request_hash": content_hash(probe.request.to_dict()),
                            "source_final_block_index": final_block,
                            **provenance,
                        },
                    ))
                population.append({
                    "schema_version": 1,
                    "pair_id": pair_id,
                    "gate_id": gate_id,
                    "case_id": original.case_id,
                    "probe_id": probe.probe_id,
                    "condition_id": original.condition_id,
                    "request": probe.request.to_dict(),
                    "request_hash": content_hash(probe.request.to_dict()),
                    "original_job_id": job_ids["ORIGINAL"],
                    "gated_job_id": job_ids["GATED"],
                    "original_evidence_id": original.evidence_id,
                    "gated_evidence_id": gated.evidence_id,
                    "selected_before_executor_calls": True,
                    **provenance,
                })
        source_rows.extend(
            {"source_manifest_sha256": source.manifest_hash, **dict(row)}
            for row in source.baseline_jobs
        )
    return StudyPlan(
        study_id=STUDY_ID,
        executor_only=True,
        jobs=tuple(jobs),
        source_evidence=tuple(evidence.values()),
        controlled_memories=tuple(memories.values()),
        artifact_schemas={"source_authority_decisions": 1, "source_authority_pairs": 1,
                          "source_authority_baselines": 1},
        artifact_rows={
            "source_authority_decisions": tuple(decisions),
            "source_authority_pairs": tuple(population),
            "source_authority_baselines": tuple(source_rows),
        },
        persist_empty_artifacts=("source_authority_baselines",),
        metadata={
            "route": STUDY_ID,
            "source_authority_protocol": PROTOCOL_VERSION,
            "source_authority_gate_schema": GATE_SCHEMA_VERSION,
            "source_authority_sources": [source.provenance() for source in sources],
            "source_authority_implementation_files": implementation,
            "source_authority_implementation_hash": content_hash(implementation),
            "source_authority_population": population,
            "source_authority_population_hash": content_hash(population),
            "source_authority_decisions_hash": content_hash(decisions),
            "source_authority_variants": ["ORIGINAL", "GATED"],
            "source_authority_selected_memory_count": len(decisions),
            "source_authority_pair_count": len(population),
            "source_authority_source_strategy": str(options.get("writer_strategy") or "all"),
            "selection_uses_executor_behavior": False,
            "source_authority_gate_uses_oracle": False,
            "source_authority_fresh_writer_calls": 0,
            "source_authority_original_reexecuted": True,
            "planned_ordinary_executor_jobs": len(jobs),
            "planned_dynamic_executor_jobs_min": 0,
            "planned_dynamic_executor_jobs_max": 0,
        },
    )


def implementation_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    paths = [*Path(__file__).parent.glob("*.py"), root / "domains/base.py",
             root / "domains/source_authority.py"]
    return {str(path.relative_to(root)): file_hash(path) for path in sorted(paths)}


def stable_id(prefix: str, *values: Any) -> str:
    return f"{prefix}_{content_hash(values)}"
