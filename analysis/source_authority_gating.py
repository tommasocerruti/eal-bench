"""Offline source-authority contract checks and frozen-memory formation report."""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from analysis.source_authority_results import formation_factors
from domains import get_domain
from domains.source_authority import cited_source_authority_adapter
from experiments.authorization_memory.persistence import content_hash
from experiments.mitigations.source_authority.gate import (
    apply_cited_source_authority_gate,
    evaluate_cited_sources,
)
from experiments.mitigations.source_authority.sources import load_writer_source, source_paths


def validate_gate_contract(domain: Any, cases: Sequence[Any]) -> dict[str, Any]:
    """Exercise the literal citation rule, including unrelated authoritative chatter."""
    counts: Counter[str] = Counter()
    resolver = cited_source_authority_adapter(domain)
    for case in cases:
        sources = resolver.resolve(case, None)
        if frozenset(sources) != domain.corpus.source_turn_ids(case, None):
            raise ValueError("source-authority resolver omitted source turns")
        blocks = tuple(domain.corpus.blocks(case))
        final_block = max(int(block.block_index) for block in blocks)
        for block in blocks:
            index = int(block.block_index)
            if frozenset(resolver.resolve(case, index)) != domain.corpus.source_turn_ids(case, index):
                raise ValueError("source-authority resolver violated source visibility")
        counts["cases"] += 1
        counts["source_turns"] += len(sources)
        capable = [key for key, value in sources.items() if value.authorization_capable]
        noncapable = [key for key, value in sources.items() if not value.authorization_capable]
        counts["authority_capable_sources"] += len(capable)
        counts["non_authority_capable_sources"] += len(noncapable)
        for citations, expected in (((), "missing_provenance"), (("",), "missing_provenance")):
            passed, reason, _ = evaluate_cited_sources(
                citations, visible_sources=sources, all_sources=sources,
            )
            if passed or reason != expected:
                raise ValueError("missing citations must fail closed")
            counts["missing_provenance"] += 1
        canonical = domain.memory.serialize_typed(domain.memory.faithful_typed(case, None))
        if not canonical["authorizations"]:
            continue
        fixtures = [(case, ("source_authority_unknown_fixture",), final_block, "unknown_provenance")]
        if capable:
            fixtures.append((case, (capable[0],), final_block, "all_cited_sources_authority_capable"))
            chatter_case = _replace_source_content(case, capable[0])
            fixtures.append((chatter_case, (capable[0],), final_block, "all_cited_sources_authority_capable"))
            counts["unrelated_authority_chatter"] += 1
        if noncapable:
            fixtures.append((case, (noncapable[0],), final_block, "source_not_authority_capable"))
        if capable and noncapable:
            fixtures.append((case, (capable[0], noncapable[0]), final_block, "source_not_authority_capable"))
            counts["mixed_citations"] += 1
        first = min(int(block.block_index) for block in blocks)
        future = next((str(turn.turn_id) for block in blocks if int(block.block_index) > first for turn in block.turns), None)
        if future:
            fixtures.append((case, (future,), first, "future_provenance"))
        for fixture_case, citations, through, reason in fixtures:
            payload = copy.deepcopy(canonical)
            record = payload["authorizations"][0]
            record["source_turn_ids"] = (
                " | ".join(citations) if isinstance(record["source_turn_ids"], str)
                else list(citations)
            )
            payload["authorizations"] = [record]
            before = content_hash(payload)
            gated = apply_cited_source_authority_gate(
                domain, fixture_case, domain.memory.parse_typed(payload),
                through_block_index=through,
            )
            if gated.decisions[0].reason != reason or content_hash(payload) != before:
                raise ValueError(f"source-authority fixture failed: {reason}")
            retained = int(reason == "all_cited_sources_authority_capable")
            if gated.retained_record_count != retained:
                raise ValueError("gate kept the wrong record count")
            expected = dict(payload, authorizations=[record] if retained else [])
            if gated.gated_state != domain.memory.serialize_typed(domain.memory.parse_typed(expected)):
                raise ValueError("gate modified data other than removing records")
            counts[reason] += 1
    required = {"all_cited_sources_authority_capable", "source_not_authority_capable",
                "unknown_provenance", "future_provenance", "mixed_citations",
                "unrelated_authority_chatter", "missing_provenance"}
    if any(not counts[name] for name in required):
        raise ValueError("corpus does not exercise the complete source-authority contract")
    return {"status": "passed", "domain_id": domain.domain_id, **dict(counts),
            "gate_uses_oracle": False, "gate_uses_turn_content": False}


def _replace_source_content(case: Any, source_id: str) -> Any:
    blocks = list(case.blocks)
    for block_index, block in enumerate(blocks):
        turns = list(block.turns)
        for turn_index, turn in enumerate(turns):
            if str(turn.turn_id) == source_id:
                field = "content" if hasattr(turn, "content") else "text"
                turns[turn_index] = replace(turn, **{field: "The routine team meeting starts at 09:30."})
                blocks[block_index] = replace(block, turns=tuple(turns))
                return replace(case, blocks=tuple(blocks))
    raise ValueError("source-authority chatter fixture has no source turn")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--corpus-version", default="benchmark_v1")
    parser.add_argument("--presentation-version", default="naturalistic_v1")
    parser.add_argument("--source-run", action="append", default=[])
    parser.add_argument("--writer-strategy", choices=("all", "one_shot", "incremental"), default="all")
    args = parser.parse_args()
    domain = get_domain(args.domain)
    cases = domain.corpus.load_cases(args.corpus_version)
    report = {"contract": validate_gate_contract(domain, cases), "sources": []}
    if args.source_run:
        options = {**vars(args), "source_runs": args.source_run}
        by_id = {domain.corpus.case_id(case): case for case in cases}
        for path in source_paths(options):
            source = load_writer_source(path, domain, cases, options)
            summaries = {}
            strata = {}
            for item in source.evidence:
                factors = formation_factors({
                    "source_manifest_sha256": source.manifest_hash,
                    "condition_id": item.condition_id,
                    "source_writer": item.writer.to_dict(),
                    "source_writer_seed": item.writer_seed,
                    "source_writer_run_id": item.memory_run_id,
                    "source_memory_implementation_id": item.memory_implementation_id,
                    "source_memory_implementation_hash": item.memory_implementation_hash,
                    "source_presentation_id": item.presentation_id,
                    "source_presentation_hash": item.presentation_hash,
                })
                group_id = content_hash(factors)
                strata[group_id] = factors
                group = summaries.setdefault(group_id, Counter())
                gate = apply_cited_source_authority_gate(
                    domain, by_id[item.case_id], domain.memory.parse_typed(item.payload),
                    through_block_index=max(int(block.block_index) for block in domain.corpus.blocks(by_id[item.case_id])),
                )
                group["memories"] += 1
                group["input_records"] += gate.input_record_count
                group["retained_records"] += gate.retained_record_count
                group["changed_memories"] += int(content_hash(gate.gated_state) != item.content_hash)
                group.update(decision.reason for decision in gate.decisions)
            report["sources"].append({**source.provenance(), "formation": [
                {"factors": strata[key], **dict(values)} for key, values in summaries.items()
            ]})
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
