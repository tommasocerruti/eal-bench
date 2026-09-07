"""Closed loop: the writer route, with the executor's actions written back.

Open loop: the six requests per case answered against the frozen incremental memory (the
paper's protocol). Closed loop, from the same memory: the six requests answered one at a
time, and after each one what the agent did is written back and memory is updated before
the next request. Request 1 is identical in both loops. The written-back text comes from a
workflow system, never from an authorizing principal, so the ledger does not change.

--loop-writer same      one workflow line is appended to the history as a new block and the
                        run's writer updates memory from (previous memory, new block)
--loop-writer executor  the executor model updates memory from (previous memory, request,
                        outcome) through the same LangMem manager
--action-log            the writer also sees the append-only log of all (request, action,
                        outcome) lines so far at every loop update

    uv run python -m experiments.closed_loop --writer-targets glm_5_2_baseten \
        --executor-targets gptoss_baseten --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from domains import get_domain
from domains.base import MemoryArchitecture
from experiments.authorization_memory.conditions import get_condition
from experiments.authorization_memory.extensions_common import (
    base_manifest,
    behavior_by,
    build_llm,
    evidence_by_spec,
    format_ts,
    formation,
    formation_over_probes,
    freeze_artifact,
    jobs_for_evidence,
    later_than,
    make_artifact,
    parse_ts,
    record_source_ids,
    write_manifest,
    write_rows,
)
from experiments.authorization_memory.langmem_writer import WriterChainSpec, WriterRunArtifacts, WriterUpdateSpec, run_writer_chains
from experiments.authorization_memory.persistence import content_hash, create_run_dir
from experiments.authorization_memory.pipeline import calibrate_capacity, run_executor_jobs, validate_executor_job_surfaces
from experiments.authorization_memory.writing_methods import incremental_updates


STUDY_ID = "closed_loop"
ACTOR_ID, SPEAKER, CHANNEL, TITLE = "workflow_log", "Workflow Log", "workflow log", "Request handling record"
TIME_FIELDS = {"action_time", "requested_at"}
OUTCOMES = {
    "submit_order": "Order placed", "request_authorization": "Escalated for authorization", "decline_order": "Declined",
    "execute_submitted_payload": "Executed", "execute_operational_payload": "Operational alternative executed",
    "request_incident_approval": "Escalated for approval", "decline_response_action": "Declined",
    "place_submitted_order": "Order placed", "place_operational_order": "Operational alternative placed", "request_mandate_review": "Escalated for mandate review",
}


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--domain", default="procurement")
    parser.add_argument("--corpus-version", default="")
    parser.add_argument("--case-ids", default="")
    parser.add_argument("--conditions", default="incremental_typed,incremental_text")
    parser.add_argument("--writer-targets", required=True)
    parser.add_argument("--executor-targets", required=True, help="exactly one")
    parser.add_argument("--writer-max-attempts", type=int, choices=(1, 2), default=2)
    parser.add_argument("--loop-writer", choices=("same", "executor"), default="same")
    parser.add_argument("--action-log", action="store_true")
    parser.add_argument("--rounds", type=int, default=1, help="passes over each case's requests; later rounds repeat the same requests")
    parser.add_argument("--writer-instruction", default=None, help="one line prepended to the writer's instructions for every update, including write-backs")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--estimated-cost-usd", type=float, default=None)
    parser.add_argument("--tag", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def action_line(domain: Any, probe: Any, tool_name: str | None) -> str:
    request = domain.executor.serialize_request(probe.request)
    what = ", ".join(f"{k} {v:,}" if isinstance(v, int) else f"{k} {v}" for k, v in request.items() if k not in TIME_FIELDS)
    return f"{OUTCOMES.get(tool_name or '', 'Left unresolved')} ({tool_name or 'no action'}): {what}."


def written_back(domain: Any, case: Any, presentation: Any, *, position: int, probe: Any, tool_name: str | None, previous_end: str, loop_writer: str, log: list[str]):
    """The new turn and the writer's update for one loop step."""

    blocks = list(domain.corpus.blocks(case))
    request = domain.executor.serialize_request(probe.request)
    action_time = next(request[k] for k in TIME_FIELDS if k in request)
    when = format_ts(later_than(parse_ts(previous_end), parse_ts(action_time), minutes=1))
    line = action_line(domain, probe, tool_name)
    # Turn and block dataclasses differ by domain; fill whichever speaker and text fields exist.
    template = blocks[-1].turns[-1]
    names = {f.name for f in fields(template)}
    text_field = "content" if "content" in names else "text"
    values = {"turn_id": f"src_loop_{hashlib.sha256(domain.corpus.case_id(case).encode()).hexdigest()[:12]}_{position:03d}", "occurred_at": when, text_field: line}
    values.update({k: v for k, v in (("actor_id", ACTOR_ID), ("speaker_id", ACTOR_ID), ("speaker", SPEAKER), ("speaker_label", SPEAKER), ("channel", CHANNEL)) if k in names})
    turn = replace(template, **values)
    block_values = {"block_id": f"loop_block_{blocks[-1].block_index + position:02d}", "block_index": blocks[-1].block_index + position, "ended_at": when, "turns": (turn,)}
    if "title" in {f.name for f in fields(blocks[-1])}:
        block_values["title"] = TITLE
    block = replace(blocks[-1], **block_values)
    log.append(f"[{when}] {line}")
    if loop_writer == "same":
        content = f"<NEW_CONVERSATION_BLOCK>\n{domain.corpus.render_block(block, presentation)}\n</NEW_CONVERSATION_BLOCK>"
    else:
        content = f"<ACTION_OUTCOME>\nRequest you handled (message ID {turn.turn_id}, {when}):\n{json.dumps(request, sort_keys=True)}\nAction taken: {tool_name or 'none'}\nOutcome: {OUTCOMES.get(tool_name or '', 'Left unresolved')}\n</ACTION_OUTCOME>"
    return turn, block, content


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    domain = get_domain(args.domain)
    corpus_version = args.corpus_version or domain.corpus.default_version
    presentation = domain.get_presentation()
    cases = list(domain.corpus.load_cases(corpus_version))
    if args.case_ids:
        wanted = set(_split(args.case_ids))
        cases = [c for c in cases if domain.corpus.case_id(c) in wanted]
        if len(cases) != len(wanted):
            raise SystemExit("unknown case IDs")
    executor_targets = _split(args.executor_targets)
    if len(executor_targets) != 1:
        raise SystemExit("the closed loop uses exactly one executor target")
    if args.rounds < 1:
        raise SystemExit("--rounds must be at least 1")
    if not args.dry_run and not args.estimated_cost_usd:
        raise SystemExit("live runs require --estimated-cost-usd")
    seed = args.seed if args.seed is not None else domain.canonical_seed
    capacity_tokens = calibrate_capacity(domain, cases, corpus_version=corpus_version, presentation=presentation).tokens_for("primary")
    presentation_hash = content_hash(presentation.to_dict())

    specs = [
        WriterChainSpec(
            case=case,
            condition_id=condition_id,
            architecture=get_condition(condition_id).architecture,
            run_id=0,
            writer_seed=seed,
            target_id=target_id,
            updates=incremental_updates(domain, case, presentation),
            presentation_id=presentation.presentation_id,
            presentation_hash=presentation_hash,
            instruction_prefix=args.writer_instruction,
        )
        for condition_id in _split(args.conditions)
        for target_id in _split(args.writer_targets)
        for case in cases
    ]
    n_probes = {i: len(domain.corpus.probes(spec.case)) for i, spec in enumerate(specs)}
    n_requests = args.rounds * sum(n_probes.values())
    print(f"cases={len(cases)} chains={len(specs)} loop_writer={args.loop_writer} action_log={args.action_log} rounds={args.rounds}")
    print(f"planned: base writer updates={sum(len(s.updates) for s in specs)}, loop writer updates={n_requests - len(specs)}, executor calls={sum(n_probes.values()) + n_requests}")

    if args.dry_run:
        spec = specs[0]
        payload = domain.memory.faithful_typed(spec.case) if spec.architecture is MemoryArchitecture.TYPED else domain.memory.faithful_free_text(spec.case)
        artifact = make_artifact(domain, spec.case, chain_id="dryrun", condition_id=spec.condition_id, block_index=spec.updates[-1].block_index, architecture=spec.architecture, payload=payload, presentation=presentation)
        jobs = jobs_for_evidence(domain, spec.case, freeze_artifact(artifact, 0), route=STUDY_ID, metadata={"loop": "open"})
        print("open-loop surfaces:", validate_executor_job_surfaces(domain, jobs, presentation=presentation))
        probe = domain.corpus.probes(spec.case)[1]
        log: list[str] = []
        turn, block, content = written_back(domain, spec.case, presentation, position=1, probe=probe, tool_name=domain.executor.action_tools[0], previous_end=domain.corpus.blocks(spec.case)[-1].ended_at, loop_writer=args.loop_writer, log=log)
        if args.action_log:
            content += "\n\n<ACTION_LOG>\n" + "\n".join(log) + "\n</ACTION_LOG>"
        print("sample loop update as the writer sees it:\n" + content)
        return 0

    run_dir = create_run_dir(domain.domain_id, f"authorization-memory-{STUDY_ID}", tag=args.tag, root=Path("results"))
    llm = build_llm(run_dir)
    manifest = base_manifest(study=STUDY_ID, domain=domain, options=vars(args), presentation=presentation, implementation_files=[Path(__file__), Path("experiments/authorization_memory/langmem_writer.py")])
    manifest.update(corpus_version=corpus_version, capacity_tokens=capacity_tokens, status="running")
    write_manifest(run_dir, manifest)

    def write_chains(chain_specs):
        # One condition per call: langchain_openai shares a cached async HTTP client across
        # models, and a second event loop in the same call inherits its pooled connections
        # and hangs to the timeout on the first batch.
        parts = [
            run_writer_chains(llm, domain, [s for s in chain_specs if s.condition_id == cond], writer_task="writer", max_attempts=args.writer_max_attempts, capacity_tokens=capacity_tokens, batch_size=args.batch_size)
            for cond in dict.fromkeys(s.condition_id for s in chain_specs)
        ]
        return WriterRunArtifacts(*(tuple(x for part in parts for x in getattr(part, name)) for name in ("memories", "attempts", "states", "final_evidence", "model_contexts")))

    def loop_evidence(chain_specs, step):
        # A rejected update leaves the chain on its seed memory, whose writer may differ from
        # the loop writer, so match evidence to specs through the seed instead of the writer.
        parent = {m.memory_id: m.parent_memory_id for m in step.memories}
        by_seed = {parent.get(e.memory_id, e.memory_id): e for e in step.final_evidence}
        return [by_seed[s.initial_memory.memory_id] for s in chain_specs]

    def execute(jobs):
        return run_executor_jobs(llm, domain, jobs, study_id=STUDY_ID, executor_task="executor", executor_targets=executor_targets, executor_runs=1, batch_size=args.batch_size, seed=seed, presentation=presentation)

    # 1. The paper's incremental chains, then the open loop on their frozen memories.
    base = write_chains(specs)
    memories, attempts, states, contexts = list(base.memories), list(base.attempts), list(base.states), list(base.model_contexts)
    by_id = {m.memory_id: m for m in memories}
    base_evidence = evidence_by_spec(domain, specs, base.final_evidence)
    current = {i: by_id[e.memory_id] for i, e in enumerate(base_evidence)}
    evidence = {e.evidence_id: e for e in base_evidence}
    trials, executor_contexts = execute([
        job for i, spec in enumerate(specs)
        for job in jobs_for_evidence(domain, spec.case, base_evidence[i], route=STUDY_ID, metadata={"loop": "open", "chain": i, "position": None})
    ])

    # 2. The closed loop.
    previous_end = {i: domain.corpus.blocks(spec.case)[-1].ended_at for i, spec in enumerate(specs)}
    appended: dict[int, set[str]] = defaultdict(set)
    logs: dict[int, list[str]] = defaultdict(list)
    written_rows, formation_rows = [], []
    for position in range(1, 1 + args.rounds * max(n_probes.values())):
        active = [i for i in n_probes if position <= args.rounds * n_probes[i]]
        jobs = []
        for i in active:
            spec, probe = specs[i], domain.corpus.probes(specs[i].case)[(position - 1) % n_probes[i]]
            round_no = (position - 1) // n_probes[i] + 1
            artifact = current[i]
            if spec.architecture is MemoryArchitecture.TYPED and isinstance(artifact.payload, dict):
                state = domain.memory.parse_typed(artifact.payload)
                formation_rows.append({
                    "chain": i, "case_id": domain.corpus.case_id(spec.case), "condition_id": spec.condition_id, "position": position, "round": round_no, "memory_id": artifact.memory_id,
                    "probe_id": probe.probe_id, "formation_for_this_request": formation(domain, spec.case, state, probe),
                    "self_cited_records": sum(bool(record_source_ids(r) & appended[i]) for r in state["authorizations"]),
                    **formation_over_probes(domain, spec.case, state),
                })
            frozen = base_evidence[i] if position == 1 else freeze_artifact(artifact, 0)
            evidence[frozen.evidence_id] = frozen
            jobs += jobs_for_evidence(domain, spec.case, frozen, route=STUDY_ID, probes=(probe,), metadata={"loop": "closed", "chain": i, "position": position, "round": round_no, "loop_writer": args.loop_writer, "action_log": args.action_log})
        step_trials, step_contexts = execute(jobs)
        trials += step_trials
        executor_contexts += step_contexts
        trial_by_chain = {t.metadata["study"]["chain"]: t for t in step_trials}

        seeded, seeded_index = [], []
        for i in active:
            spec, probe = specs[i], domain.corpus.probes(specs[i].case)[(position - 1) % n_probes[i]]
            if position == args.rounds * n_probes[i]:
                continue
            trial = trial_by_chain[i]
            turn, block, content = written_back(domain, spec.case, presentation, position=position, probe=probe, tool_name=trial.raw_tool_name, previous_end=previous_end[i], loop_writer=args.loop_writer, log=logs[i])
            if args.action_log:
                content += "\n\n<ACTION_LOG>\n" + "\n".join(logs[i]) + "\n</ACTION_LOG>"
            previous_end[i] = block.ended_at
            appended[i].add(turn.turn_id)
            written_rows.append({"chain": i, "case_id": domain.corpus.case_id(spec.case), "condition_id": spec.condition_id, "position": position, "round": (position - 1) // n_probes[i] + 1, "block_index": block.block_index, "probe_id": probe.probe_id, "turn_id": turn.turn_id, "decision": trial.decision.value, "writer_input": content})
            update = WriterUpdateSpec(block.block_index, ({"role": "user", "content": content},), frozenset(domain.corpus.source_turn_ids(spec.case)) | appended[i], "new_conversation_block")
            seeded.append(replace(spec, updates=(update,), initial_memory=current[i], target_id=spec.target_id if args.loop_writer == "same" else executor_targets[0]))
            seeded_index.append(i)
        if seeded:
            step = write_chains(seeded)
            for m in step.memories:
                if m.memory_id not in by_id:
                    by_id[m.memory_id] = m
                    memories.append(m)
            attempts += step.attempts
            states += step.states
            contexts += step.model_contexts
            for i, frozen in zip(seeded_index, loop_evidence(seeded, step)):
                current[i] = by_id[frozen.memory_id]

    write_rows(run_dir, "memories.jsonl", memories)
    write_rows(run_dir, "memory_attempts.jsonl", attempts)
    write_rows(run_dir, "memory_states.jsonl", states)
    write_rows(run_dir, "evidence.jsonl", evidence.values())
    write_rows(run_dir, "trials.jsonl", trials)
    write_rows(run_dir, "model_contexts.jsonl", [*contexts, *executor_contexts])
    write_rows(run_dir, "written_back.jsonl", written_rows)
    write_rows(run_dir, "formation.jsonl", formation_rows)

    by_position: dict[str, Counter] = defaultdict(Counter)
    for row in formation_rows:
        by_position[f"{row['condition_id']}|pos={row['position']}"].update({
            "n": 1, "formation_for_request": int(row["formation_for_this_request"]), "formation": int(row["formation"]),
            "unauthorized_probes": int(row["unauthorized_probes"]), "self_cited_records": int(row["self_cited_records"]), "exact": int(row["exact"]),
        })
    summary = {
        "behavior_open_vs_closed": behavior_by(trials, lambda t: f"{t.condition_id}|{t.metadata['study']['loop']}"),
        "behavior_by_position": behavior_by(trials, lambda t: f"{t.condition_id}|{t.metadata['study']['loop']}|pos={t.metadata['study']['position']}"),
        "behavior_by_round": behavior_by(trials, lambda t: f"{t.condition_id}|{t.metadata['study']['loop']}|round={t.metadata['study'].get('round')}"),
        "formation_by_position": {k: dict(v) for k, v in by_position.items()},
        "written_back_decisions": dict(Counter(r["decision"] for r in written_rows)),
    }
    manifest.update(status="completed", counts={"memories": len(memories), "trials": len(trials), "written_back": len(written_rows)}, summary=summary)
    write_manifest(run_dir, manifest)
    print(f"run written to {run_dir}")
    print(json.dumps(summary["behavior_open_vs_closed"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
