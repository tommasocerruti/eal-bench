"""Memory type x writing method on the writer route's protocol.

Memory types: typed, free_text (the paper's), hybrid (typed records plus free-text notes).
Writing methods: incremental (the paper's), rebuild:k, retrieve:k, or rebuild:k+retrieve:k.
LangMem chains over the same blocks, frozen memory, six requests per case replayed behind the
executor, same scoring.

    uv run python -m experiments.writer_variants_run --memory-types typed,hybrid \
        --writing-methods incremental,rebuild:3 --writer-targets glm_5_2_baseten \
        --executor-targets gptoss_baseten --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from domains import get_domain
from domains.base import MemoryArchitecture
from experiments.authorization_memory.extensions_common import (
    base_manifest,
    behavior_by,
    build_llm,
    evidence_by_spec,
    formation_over_probes,
    freeze_artifact,
    jobs_for_evidence,
    make_artifact,
    write_manifest,
    write_rows,
)
from experiments.authorization_memory.hybrid_memory import hybrid_domain
from experiments.authorization_memory.langmem_writer import WriterChainSpec, run_writer_chains
from experiments.authorization_memory.persistence import content_hash, create_run_dir
from experiments.authorization_memory.pipeline import calibrate_capacity, run_executor_jobs, validate_executor_job_surfaces
from experiments.authorization_memory.writing_methods import incremental_updates, method_suffix, parse_method


STUDY_ID = "writer_variants"
MEMORY_TYPES = {
    "typed": (MemoryArchitecture.TYPED, "incremental_typed"),
    "free_text": (MemoryArchitecture.FREE_TEXT, "incremental_text"),
    "hybrid": (MemoryArchitecture.TYPED, "incremental_hybrid"),
}


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--domain", default="procurement")
    parser.add_argument("--corpus-version", default="")
    parser.add_argument("--case-ids", default="")
    parser.add_argument("--memory-types", default="typed,free_text,hybrid")
    parser.add_argument("--writing-methods", default="incremental")
    parser.add_argument("--writer-targets", required=True)
    parser.add_argument("--executor-targets", required=True)
    parser.add_argument("--writer-runs", type=int, default=1)
    parser.add_argument("--writer-max-attempts", type=int, choices=(1, 2), default=2)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--estimated-cost-usd", type=float, default=None)
    parser.add_argument("--tag", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    base = get_domain(args.domain)
    corpus_version = args.corpus_version or base.corpus.default_version
    presentation = base.get_presentation()
    presentation_hash = content_hash(presentation.to_dict())
    cases = list(base.corpus.load_cases(corpus_version))
    if args.case_ids:
        wanted = set(_split(args.case_ids))
        cases = [c for c in cases if base.corpus.case_id(c) in wanted]
        if len(cases) != len(wanted):
            raise SystemExit("unknown case IDs")
    unknown = set(_split(args.memory_types)) - set(MEMORY_TYPES)
    if unknown:
        raise SystemExit(f"unknown memory types {sorted(unknown)}; known: {', '.join(MEMORY_TYPES)}")
    if not args.dry_run and not args.estimated_cost_usd:
        raise SystemExit("live runs require --estimated-cost-usd")
    seed = args.seed if args.seed is not None else base.canonical_seed
    capacity_tokens = calibrate_capacity(base, cases, corpus_version=corpus_version, presentation=presentation).tokens_for("primary")
    hybrid = hybrid_domain(base)

    groups = []  # (condition_id, writing domain, chain specs)
    for type_name in _split(args.memory_types):
        architecture, prefix = MEMORY_TYPES[type_name]
        domain = hybrid if type_name == "hybrid" else base
        for method in _split(args.writing_methods):
            rebuild, retrieve = parse_method(method)
            condition_id = prefix + method_suffix(rebuild, retrieve)
            specs = [
                WriterChainSpec(
                    case=case,
                    condition_id=condition_id,
                    architecture=architecture,
                    run_id=run_id,
                    writer_seed=seed + run_id,
                    target_id=target_id,
                    updates=incremental_updates(base, case, presentation, rebuild_every=rebuild, writer_retrieval_k=retrieve),
                    presentation_id=presentation.presentation_id,
                    presentation_hash=presentation_hash,
                )
                for target_id in _split(args.writer_targets)
                for run_id in range(args.writer_runs)
                for case in cases
            ]
            groups.append((condition_id, domain, specs))

    condition_ids = [g[0] for g in groups]
    if len(condition_ids) != len(set(condition_ids)):
        raise SystemExit(f"duplicate conditions: {sorted(c for c in condition_ids if condition_ids.count(c) > 1)}")
    writer_updates = sum(len(spec.updates) for _, _, specs in groups for spec in specs)
    executor_calls = sum(len(base.corpus.probes(spec.case)) for _, _, specs in groups for spec in specs) * len(_split(args.executor_targets))
    print(f"cases={len(cases)} conditions={[g[0] for g in groups]}")
    print(f"planned: writer updates={writer_updates} (up to {args.writer_max_attempts} attempts each), executor calls={executor_calls}")

    if args.dry_run:
        jobs = []
        for condition_id, domain, specs in groups:
            for spec in specs[: len(cases)]:
                payload = domain.memory.faithful_typed(spec.case) if spec.architecture is MemoryArchitecture.TYPED else domain.memory.faithful_free_text(spec.case)
                artifact = make_artifact(base, spec.case, chain_id=condition_id, condition_id=condition_id, block_index=spec.updates[-1].block_index, architecture=spec.architecture, payload=payload, presentation=presentation)
                jobs += jobs_for_evidence(base, spec.case, freeze_artifact(artifact, 0), route=STUDY_ID, metadata={})
                if spec.architecture is MemoryArchitecture.TYPED and not domain.fidelity.compare(spec.case, domain.memory.parse_typed(payload)).exact:
                    raise SystemExit(f"{condition_id}: faithful memory does not round-trip")
        print("executor surfaces:", validate_executor_job_surfaces(base, jobs, presentation=presentation))
        return 0

    run_dir = create_run_dir(base.domain_id, f"authorization-memory-{STUDY_ID}", tag=args.tag, root=Path("results"))
    llm = build_llm(run_dir)
    manifest = base_manifest(
        study=STUDY_ID, domain=base, options=vars(args), presentation=presentation,
        implementation_files=[Path(__file__), Path("experiments/authorization_memory/hybrid_memory.py"), Path("experiments/authorization_memory/writing_methods.py"), Path("experiments/authorization_memory/langmem_writer.py")],
    )
    manifest.update(corpus_version=corpus_version, capacity_tokens=capacity_tokens, conditions=[g[0] for g in groups], planned={"writer_updates": writer_updates, "executor_calls": executor_calls}, status="running")
    write_manifest(run_dir, manifest)

    memories, attempts, states, contexts, evidence, jobs, formation_rows = [], [], [], [], {}, [], []
    for condition_id, domain, specs in groups:
        written = run_writer_chains(llm, domain, specs, writer_task="writer", max_attempts=args.writer_max_attempts, capacity_tokens=capacity_tokens, batch_size=args.batch_size)
        memories += written.memories
        attempts += written.attempts
        states += written.states
        contexts += written.contexts
        by_id = {m.memory_id: m for m in written.memories}
        for spec, frozen in zip(specs, evidence_by_spec(base, specs, written.evidence)):
            evidence[frozen.evidence_id] = frozen
            jobs += jobs_for_evidence(base, spec.case, frozen, route=STUDY_ID, metadata={"writer_target_id": spec.target_id})
            payload = by_id[frozen.memory_id].payload
            if spec.architecture is MemoryArchitecture.TYPED and isinstance(payload, dict):
                try:
                    state = domain.memory.parse_typed(payload)
                except (TypeError, ValueError):
                    continue
                formation_rows.append({"condition_id": condition_id, "case_id": frozen.case_id, "memory_id": frozen.memory_id, "writer_target_id": spec.target_id, **formation_over_probes(domain, spec.case, state)})
    trials, executor_contexts = run_executor_jobs(llm, base, jobs, study_id=STUDY_ID, executor_task="executor", executor_targets=_split(args.executor_targets), executor_runs=1, batch_size=args.batch_size, seed=seed, presentation=presentation)

    write_rows(run_dir, "memories.jsonl", memories)
    write_rows(run_dir, "memory_attempts.jsonl", attempts)
    write_rows(run_dir, "memory_states.jsonl", states)
    write_rows(run_dir, "evidence.jsonl", evidence.values())
    write_rows(run_dir, "trials.jsonl", trials)
    write_rows(run_dir, "model_contexts.jsonl", [*contexts, *executor_contexts])
    write_rows(run_dir, "formation.jsonl", formation_rows)

    formation_summary: dict[str, Counter] = defaultdict(Counter)
    for row in formation_rows:
        formation_summary[row["condition_id"]].update({k: int(row[k]) for k in ("formation", "unauthorized_probes", "undergrant", "authorized_probes", "exact")})
        formation_summary[row["condition_id"]]["memories"] += 1
    summary = {
        "behavior_by_condition": behavior_by(trials, lambda t: t.condition_id),
        "behavior_by_condition_executor": behavior_by(trials, lambda t: f"{t.condition_id}|{t.executor.target_id}"),
        "formation_by_condition": {k: dict(v) for k, v in formation_summary.items()},
        "writer_attempt_status": dict(sorted(Counter(f"{a.condition_id}:{a.status}" for a in attempts).items())),
    }
    manifest.update(status="completed", counts={"memories": len(memories), "trials": len(trials), "writer_attempts": len(attempts)}, summary=summary)
    write_manifest(run_dir, manifest)
    print(f"run written to {run_dir}")
    print(json.dumps(summary["behavior_by_condition"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
