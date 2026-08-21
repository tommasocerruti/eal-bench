from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from analysis.common import load_jsonl
from analysis.phase2_replication import PRICES, _audit_route, _derived_cost
from domains import get_domain
from domains.finance.studies import (
    _evidence_from_row,
    _memory_from_row,
    _state_from_row,
    _writer_post_builder,
)
from eal_bench.llm import load_config
from experiments.authorization_memory.executor_plan import planned_executor_calls
from experiments.authorization_memory.persistence import content_hash, jsonable
from experiments.authorization_memory.study_plan import WriterRunBundle
from experiments.authorization_memory.surfaces import model_visible_tools


SEEDS = (20260821, 20260822)
WRITERS = (
    "nemotron_3_ultra_baseten",
    "kimi_baseten",
    "glm_5_2_baseten",
    "grok_4_3_openrouter",
    "qwen_plus_0728_openrouter",
)
EXECUTORS = ("gptoss_baseten", "deepseek_baseten")
ROLES = ("natural_error", "natural_exact_repair")
ROLE_LABELS = {
    "natural_error": "generated_memory",
    "natural_exact_repair": "oracle_exact_memory",
}
WRITER_LABELS = {
    "nemotron_3_ultra_baseten": "Nemotron 3 Ultra",
    "kimi_baseten": "Kimi K2.6",
    "glm_5_2_baseten": "GLM 5.2",
    "grok_4_3_openrouter": "Grok 4.3",
    "qwen_plus_0728_openrouter": "Qwen Plus 2025-07-28",
}
EXECUTOR_LABELS = {
    "gptoss_baseten": "GPT-OSS-120B",
    "deepseek_baseten": "DeepSeek V4 Pro",
}


def _canonical(value: Any) -> str:
    return json.dumps(
        jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rows(run: Path, manifest: Mapping[str, Any], name: str) -> list[dict[str, Any]]:
    entry = manifest["files"][name]
    return load_jsonl(run / str(entry["path"]))


def _target(manifest: Mapping[str, Any]) -> str:
    routes = manifest["writer"]["target_routes"]
    if len(routes) != 1:
        raise ValueError("replication writer route must contain one writer target")
    return str(routes[0]["target_id"])


def _mask_memory(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    masked = [dict(row) for row in messages]
    for row in masked:
        content = row.get("content")
        if not isinstance(content, str):
            continue
        start = content.find("<PERSISTENT_MEMORY>\n")
        end = content.find("\n</PERSISTENT_MEMORY>")
        if start < 0 or end < 0 or end < start:
            continue
        prefix = content[: start + len("<PERSISTENT_MEMORY>\n")]
        suffix = content[end:]
        row["content"] = f"{prefix}<MEMORY_VARIANT>{suffix}"
    return masked


def _discover(root: Path) -> dict[tuple[int, str], Path]:
    found: dict[tuple[int, str], Path] = {}
    finance = root / "results" / "finance"
    for seed in SEEDS:
        for run in sorted(finance.glob(f"*phase2-primary-s{seed}-finance-*")):
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            target = _target(manifest)
            key = (seed, target)
            if key in found:
                raise ValueError(f"duplicate replication writer route: {key}")
            found[key] = run.resolve()
    expected = {(seed, target) for seed in SEEDS for target in WRITERS}
    if set(found) != expected:
        raise ValueError(
            f"replication writer routes differ: missing={sorted(expected - set(found))}, "
            f"extra={sorted(set(found) - expected)}"
        )
    return found


def _replay_rows(
    *,
    run: Path,
    manifest: Mapping[str, Any],
    target: str,
    domain: Any,
    cases: Sequence[Any],
    config: Any,
) -> dict[str, Any] | None:
    eligibility = _rows(run, manifest, "substantive_eligibility")
    witnesses = _rows(run, manifest, "witnesses")
    selected = [row for row in eligibility if row.get("selected") is True]
    selected_ids = {str(row["candidate_id"]) for row in selected}
    witness_ids = {str(row["candidate_id"]) for row in witnesses}
    if selected_ids != witness_ids or len(selected_ids) != len(selected):
        raise ValueError(f"{run}: selected eligibility and witness artifacts differ")
    if any(row.get("selection_uses_executor_behavior") is not False for row in eligibility):
        raise ValueError(f"{run}: witness screening is not outcome-blind")
    if any(row.get("selected_before_executor_calls") is not True for row in witnesses):
        raise ValueError(f"{run}: witness freeze timing is not recorded")
    if not selected:
        return None

    bundle = WriterRunBundle(
        memories=tuple(
            _memory_from_row(row) for row in _rows(run, manifest, "memories")
        ),
        states=tuple(
            _state_from_row(row) for row in _rows(run, manifest, "memory_states")
        ),
        evidence=tuple(
            _evidence_from_row(row) for row in _rows(run, manifest, "evidence")
        ),
    )
    seed = int(manifest["seed"])
    executor_targets = tuple(str(row) for row in manifest["executor"]["targets"])
    if executor_targets != EXECUTORS:
        raise ValueError(f"{run}: executor targets differ from the frozen pair")
    options = {
        "corpus_version": "benchmark_v1",
        "presentation_version": "naturalistic_v1",
        "seed": seed,
        "writer_targets": (),
        "writer_runs": 0,
        "executor_targets": executor_targets,
        "executor_runs": int(manifest["executor"]["runs"]),
        "executor_task": str(manifest["executor"]["task"]),
        "validate_only": True,
    }
    expansion = _writer_post_builder(domain, cases, bundle, options)
    for name in ("substantive_eligibility", "witnesses", "interventions"):
        saved = _rows(run, manifest, name)
        rebuilt = list(expansion.artifact_rows[name])
        if _canonical(saved) != _canonical(rebuilt):
            raise ValueError(f"{run}: rebuilt {name} differs from frozen artifact")

    presentation = domain.get_presentation("naturalistic_v1")
    tools = list(model_visible_tools(domain, presentation))
    planned = planned_executor_calls(
        domain,
        expansion.jobs,
        study_id="writer",
        executor_task=str(manifest["executor"]["task"]),
        executor_targets=executor_targets,
        executor_runs=int(manifest["executor"]["runs"]),
        seed=seed,
        presentation=presentation,
        config=config,
        pressure_specs=(),
    )
    trials = _rows(run, manifest, "trials")
    replay_trials = [
        row
        for row in trials
        if row.get("metadata", {}).get("study", {}).get("evidence_role") in ROLES
    ]
    trials_by_call = {
        str(row["metadata"]["core"]["call_id"]): row for row in replay_trials
    }
    contexts = {
        str(row["call_id"]): row
        for row in _rows(run, manifest, "model_contexts")
        if str(row.get("call_id")) in planned
    }
    calls = {
        str(row["call_id"]): row
        for row in _rows(run, manifest, "calls")
        if str(row.get("call_id")) in planned
    }
    planned_ids = set(planned)
    if planned_ids != set(trials_by_call) or planned_ids != set(contexts) or planned_ids != set(calls):
        raise ValueError(f"{run}: planned replay linkage is incomplete")

    surface_hashes = []
    for call_id, item in planned.items():
        context = contexts[call_id]
        call = calls[call_id]
        trial = trials_by_call[call_id]
        messages = list(item.messages)
        visible_hash = content_hash(
            {"messages": messages, "tools": tools, "tool_choice": "auto"}
        )
        if (
            context["content_hash"] != visible_hash
            or context["messages"] != messages
            or context["tools"] != tools
            or context["tool_choice"] != "auto"
        ):
            raise ValueError(f"{run}: model-context hash differs for {call_id}")
        model = context["model"]
        planned_model = item.executor.to_dict()
        for key in (
            "target_id",
            "provider",
            "requested_model",
            "resolved_model",
            "effective_parameters",
        ):
            if _canonical(model.get(key)) != _canonical(planned_model.get(key)):
                raise ValueError(f"{run}: executor {key} differs for {call_id}")
        request = call["request"]
        params = request["params"]
        if (
            request["messages"] != messages
            or params["tools"] != tools
            or params["tool_choice"] != "auto"
            or params["temperature"] != 1.0
            or int(params["seed"]) != item.executor_seed
            or call["target_id"] != item.target_id
            or trial["metadata"]["core"]["model_context_id"] != context["context_id"]
        ):
            raise ValueError(f"{run}: saved provider request differs for {call_id}")
        surface_hashes.append(
            _sha(
                {
                    "target_id": item.target_id,
                    "provider": item.executor.provider,
                    "requested_model": item.executor.requested_model,
                    "resolved_model": item.executor.resolved_model,
                    "effective_parameters": item.executor.effective_parameters,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                }
            )
        )

    by_pair: dict[tuple[str, str], dict[str, tuple[Any, ...]]] = defaultdict(dict)
    job_by_call = {call_id: item.job for call_id, item in planned.items()}
    for call_id, trial in trials_by_call.items():
        study = trial["metadata"]["study"]
        key = (str(study["candidate_id"]), str(trial["executor"]["target_id"]))
        role = str(study["evidence_role"])
        by_pair[key][role] = (
            planned[call_id],
            contexts[call_id],
            trial,
            job_by_call[call_id],
        )
    if len(by_pair) != len(selected) * len(EXECUTORS):
        raise ValueError(f"{run}: causal pair count differs")
    case_by_id = {case.case_id: case for case in cases}
    strict_pairs = 0
    oracle_exact_memories = set()
    for key, pair in by_pair.items():
        if set(pair) != set(ROLES):
            raise ValueError(f"{run}: incomplete causal pair {key}")
        natural_item, natural_context, natural_trial, natural_job = pair["natural_error"]
        repair_item, repair_context, repair_trial, repair_job = pair[
            "natural_exact_repair"
        ]
        if (
            natural_trial["case_id"] != repair_trial["case_id"]
            or natural_trial["probe_id"] != repair_trial["probe_id"]
            or natural_context["block_index"] != repair_context["block_index"]
            or _mask_memory(natural_item.messages) != _mask_memory(repair_item.messages)
            or natural_context["tools"] != repair_context["tools"]
            or natural_context["tool_choice"] != repair_context["tool_choice"]
            or natural_trial["executor"] != repair_trial["executor"]
            or natural_trial["metadata"]["domain"]["challenge"]["choice_set_sha256"]
            != repair_trial["metadata"]["domain"]["challenge"]["choice_set_sha256"]
            or natural_trial["request_authorized"] is not False
            or repair_trial["request_authorized"] is not False
        ):
            raise ValueError(f"{run}: causal invariants differ for {key}")
        case = case_by_id[str(repair_trial["case_id"])]
        block_index = int(repair_context["block_index"])
        exact = domain.memory.faithful_typed(case, block_index)
        if _canonical(repair_job.evidence.payload) != _canonical(exact):
            raise ValueError(f"{run}: repair is not oracle-exact for {key}")
        if natural_job.probe.request.to_dict() != repair_job.probe.request.to_dict():
            raise ValueError(f"{run}: paired request differs for {key}")
        oracle_exact_memories.add(str(repair_job.evidence.memory_id))
        strict_pairs += 1

    condition_by_candidate = {
        str(row["candidate_id"]): str(row["condition_id"]) for row in selected
    }
    analyzed_trials = []
    for row in replay_trials:
        candidate_id = str(row["metadata"]["study"]["candidate_id"])
        analyzed_trials.append(
            {
                **row,
                "_source_writer_target": target,
                "_source_memory_condition": condition_by_candidate[candidate_id],
            }
        )
    return {
        "seed": seed,
        "writer_target": target,
        "writer": WRITER_LABELS[target],
        "source_run": str(run),
        "source_manifest_sha256": _file_hash(run / "manifest.json"),
        "selected_witnesses": len(selected),
        "eligible_candidates": sum(row.get("eligible") is True for row in eligibility),
        "selected_candidate_ids": sorted(selected_ids),
        "selected_witness_ids": sorted(str(row["witness_id"]) for row in witnesses),
        "selected_set_sha256": _sha(sorted(selected_ids)),
        "by_condition": dict(
            sorted(
                {
                    condition: sum(value == condition for value in condition_by_candidate.values())
                    for condition in set(condition_by_candidate.values())
                }.items()
            )
        ),
        "replay_calls": len(planned),
        "strict_causal_pairs": strict_pairs,
        "oracle_exact_witness_variants": len(selected),
        "unique_oracle_exact_memory_artifacts": len(oracle_exact_memories),
        "provider_visible_context_hashes_verified": len(surface_hashes),
        "provider_visible_surface_set_sha256": _sha(sorted(surface_hashes)),
        "trials": analyzed_trials,
        "calls": list(calls.values()),
    }


def analyze(root: Path) -> dict[str, Any]:
    runs = _discover(root)
    domain = get_domain("finance")
    cases = tuple(domain.corpus.load_cases("benchmark_v1"))
    config = load_config()
    audits = []
    replay_sources = []
    selection_rows = []
    all_trials = []
    all_calls = []
    for seed in SEEDS:
        for target in WRITERS:
            run = runs[(seed, target)]
            route_id = f"replication-{seed}-finance-{target}"
            audit = _audit_route(route_id, run)
            if audit["status"] != "passed":
                raise ValueError(f"{run}: artifact audit failed")
            audits.append(audit)
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            eligibility = _rows(run, manifest, "substantive_eligibility")
            selected = [row for row in eligibility if row.get("selected") is True]
            for condition in ("one_shot_typed", "incremental_typed"):
                count = sum(row.get("condition_id") == condition for row in selected)
                selection_rows.append(
                    {
                        "seed": seed,
                        "writer_target": target,
                        "writer": WRITER_LABELS[target],
                        "memory_condition": condition,
                        "selected_witnesses": count,
                    }
                )
            source = _replay_rows(
                run=run,
                manifest=manifest,
                target=target,
                domain=domain,
                cases=cases,
                config=config,
            )
            if source is not None:
                all_trials.extend(source.pop("trials"))
                all_calls.extend(source.pop("calls"))
                replay_sources.append(source)

    for seed in SEEDS:
        if sum(row["selected_witnesses"] for row in selection_rows if row["seed"] == seed) != 6:
            raise ValueError(f"seed {seed}: selected witness count is not six")
    if len(all_trials) != 48 or len(all_calls) != 48:
        raise ValueError("frozen causal replay does not contain exactly 48 calls")

    def outcomes(key_fields: Sequence[str]) -> list[dict[str, Any]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in all_trials:
            values = {
                "seed": int(row["seed"]),
                "executor_target": str(row["executor"]["target_id"]),
                "writer_target": str(row["_source_writer_target"]),
                "memory_condition": str(row["_source_memory_condition"]),
                "memory_role": ROLE_LABELS[
                    str(row["metadata"]["study"]["evidence_role"])
                ],
            }
            grouped[tuple(values[key] for key in key_fields)].append({**row, "_values": values})
        result = []
        for key, rows in sorted(grouped.items()):
            base = dict(zip(key_fields, key))
            result.append(
                {
                    **base,
                    "trials": len(rows),
                    "unauthorized_actions": sum(
                        bool(row["unauthorized_action_taken"]) for row in rows
                    ),
                    "provider_failures": sum(row.get("provider_error") is not None for row in rows),
                }
            )
        return result

    cost_by_target = defaultdict(float)
    attempts_by_target = defaultdict(int)
    failures_by_target = defaultdict(int)
    retries_by_target = defaultdict(int)
    for row in all_calls:
        target = str(row["target_id"])
        attempts = int(row.get("attempts") or 1)
        cost_by_target[target] += _derived_cost(target, row.get("usage") or {})
        attempts_by_target[target] += attempts
        retries_by_target[target] += max(0, attempts - 1)
        failures_by_target[target] += row.get("error") is not None

    exact_request_matches = all(
        bool(row["unauthorized_action_taken"])
        == (row["request_authorized"] is False and row["requested_action_taken"] is True)
        for row in all_trials
    )
    audit_summary = {
        "status": "passed",
        "replication_writer_routes": len(audits),
        "routes_with_selected_witnesses": len(replay_sources),
        "authoritative_artifacts": sum(row["authoritative_artifacts"] for row in audits),
        "authoritative_rows": sum(row["authoritative_rows"] for row in audits),
        "bytes": sum(row["bytes"] for row in audits),
        "manifest_file_maps_complete": all(row["file_map_complete"] for row in audits),
        "manifest_hashes_match": all(row["hashes_match"] for row in audits),
        "manifest_row_counts_match": all(row["row_counts_match"] for row in audits),
        "jsonl_parseable": all(row["jsonl_parseable"] for row in audits),
        "checkpoint_files_verified": sum(
            row["checkpoint"]["verified_files"] for row in audits
        ),
        "checkpoint_hashes_match": all(
            row["checkpoint"]["all_files_verified"] for row in audits
        ),
        "selected_witness_sets_rebuilt_exactly": True,
        "selection_uses_executor_behavior": False,
        "canonical_replay_call_ids_match": True,
        "provider_visible_context_hashes_verified": sum(
            row["provider_visible_context_hashes_verified"] for row in replay_sources
        ),
        "strict_causal_pairs_verified": sum(
            row["strict_causal_pairs"] for row in replay_sources
        ),
        "oracle_exact_witness_variants_verified": sum(
            row["oracle_exact_witness_variants"] for row in replay_sources
        ),
        "unique_oracle_exact_memory_artifacts_verified": sum(
            row["unique_oracle_exact_memory_artifacts"] for row in replay_sources
        ),
        "exact_request_metric_matches_unauthorized_action": exact_request_matches,
        "new_provider_calls": 0,
        "historical_incomplete_finance_run_used": False,
        "writer_memories_rerun": False,
        "routes": audits,
    }
    if not exact_request_matches:
        raise ValueError("intervention action metrics differ")
    total_cost = sum(cost_by_target.values())
    return {
        "schema_version": "finance_seed_natural_error_replay_report_v1",
        "status": "completed_by_strict_reuse",
        "scientific_protocol": {
            "domain": "finance",
            "corpus_version": "benchmark_v1",
            "presentation_version": "naturalistic_v1",
            "seeds": list(SEEDS),
            "executor_targets": list(EXECUTORS),
            "memory_roles": list(ROLE_LABELS.values()),
            "selection": "deterministic, outcome-blind, frozen before executor calls",
            "replay_reuse_basis": (
                "canonical intervention reconstruction reproduced the exact saved call IDs "
                "and provider-visible context hashes"
            ),
        },
        "selection": {
            "by_seed_writer_condition": selection_rows,
            "selected_per_seed": {
                str(seed): sum(
                    row["selected_witnesses"] for row in selection_rows if row["seed"] == seed
                )
                for seed in SEEDS
            },
            "sources": replay_sources,
        },
        "outcomes": {
            "overall": outcomes(("memory_role",)),
            "by_seed": outcomes(("seed", "memory_role")),
            "by_executor": outcomes(("executor_target", "memory_role")),
            "by_seed_executor": outcomes(("seed", "executor_target", "memory_role")),
            "by_seed_writer_condition": outcomes(
                ("seed", "writer_target", "memory_condition", "memory_role")
            ),
        },
        "provider_execution": {
            "call_records": len(all_calls),
            "network_attempts": sum(attempts_by_target.values()),
            "provider_failures": sum(failures_by_target.values()),
            "retries": sum(retries_by_target.values()),
            "by_target": {
                target: {
                    "call_records": sum(row["target_id"] == target for row in all_calls),
                    "network_attempts": attempts_by_target[target],
                    "provider_failures": failures_by_target[target],
                    "retries": retries_by_target[target],
                    "cost_usd": cost_by_target[target],
                }
                for target in EXECUTORS
            },
        },
        "cost": {
            "accounting_policy": (
                "frozen Phase 1 cache-aware Baseten token rates applied to recorded usage"
            ),
            "pricing_usd_per_million_tokens": {
                target: PRICES[target] for target in EXECUTORS
            },
            "replay_calls_actual_cost_usd": total_cost,
            "incremental_cost_this_analysis_usd": 0.0,
            "conservative_incremental_ceiling_usd": 0.0,
        },
        "artifact_audit": audit_summary,
    }


def _outcome(
    rows: Sequence[Mapping[str, Any]], **filters: Any
) -> Mapping[str, Any]:
    return next(
        row
        for row in rows
        if all(row.get(key) == value for key, value in filters.items())
    )


def render_markdown(report: Mapping[str, Any]) -> str:
    selection = [
        row
        for row in report["selection"]["by_seed_writer_condition"]
        if row["selected_witnesses"]
    ]
    overall = report["outcomes"]["overall"]
    generated = _outcome(overall, memory_role="generated_memory")
    exact = _outcome(overall, memory_role="oracle_exact_memory")
    lines = [
        "# Finance natural-error → oracle-exact-memory replay",
        "",
        "## Selected witnesses",
        "",
        "| Seed | Writer | Memory condition | Selected witnesses |",
        "|---:|---|---|---:|",
    ]
    lines.extend(
        f"| {row['seed']} | {row['writer']} | {row['memory_condition']} | "
        f"{row['selected_witnesses']} |"
        for row in selection
    )
    lines.extend(
        [
            "",
            "## Outcomes",
            "",
            "| Scope | Generated-memory unauthorized actions | Oracle-exact unauthorized actions |",
            "|---|---:|---:|",
            f"| Overall | {generated['unauthorized_actions']}/{generated['trials']} | "
            f"{exact['unauthorized_actions']}/{exact['trials']} |",
        ]
    )
    for seed in SEEDS:
        rows = report["outcomes"]["by_seed"]
        natural = _outcome(rows, seed=seed, memory_role="generated_memory")
        repair = _outcome(rows, seed=seed, memory_role="oracle_exact_memory")
        lines.append(
            f"| Seed {seed} | {natural['unauthorized_actions']}/{natural['trials']} | "
            f"{repair['unauthorized_actions']}/{repair['trials']} |"
        )
    lines.extend(
        [
            "",
            "## Executor-specific outcomes",
            "",
            "| Executor | Generated-memory unauthorized actions | Oracle-exact unauthorized actions | Provider failures | Retries |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for target in EXECUTORS:
        rows = report["outcomes"]["by_executor"]
        natural = _outcome(rows, executor_target=target, memory_role="generated_memory")
        repair = _outcome(rows, executor_target=target, memory_role="oracle_exact_memory")
        execution = report["provider_execution"]["by_target"][target]
        lines.append(
            f"| {EXECUTOR_LABELS[target]} | {natural['unauthorized_actions']}/{natural['trials']} | "
            f"{repair['unauthorized_actions']}/{repair['trials']} | "
            f"{execution['provider_failures']} | {execution['retries']} |"
        )
    cost = report["cost"]
    audit = report["artifact_audit"]
    lines.extend(
        [
            "",
            "## Cost and audit",
            "",
            f"- Replay-call cost: ${cost['replay_calls_actual_cost_usd']:.9f}",
            f"- Incremental cost: ${cost['incremental_cost_this_analysis_usd']:.2f}",
            f"- Routes audited: {audit['replication_writer_routes']}",
            f"- Authoritative artifacts: {audit['authoritative_artifacts']}",
            f"- Authoritative rows: {audit['authoritative_rows']}",
            f"- Bytes: {audit['bytes']}",
            f"- Provider-visible context hashes verified: {audit['provider_visible_context_hashes_verified']}",
            f"- Strict causal pairs verified: {audit['strict_causal_pairs_verified']}",
            f"- Oracle-exact witness variants verified: {audit['oracle_exact_witness_variants_verified']}",
            f"- Unique oracle-exact memory artifacts verified: {audit['unique_oracle_exact_memory_artifacts_verified']}",
            f"- Provider failures: {report['provider_execution']['provider_failures']}",
            f"- Retries: {report['provider_execution']['retries']}",
            "- Manifest hashes, row counts, JSONL parsing, checkpoint hashes, frozen witness sets, call IDs, and provider-visible contexts: passed",
            "- New provider calls: 0",
            "- Paper edits: 0",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("results/finance/phase2_seed_witness_replay_report.json"),
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=Path("results/finance/phase2_seed_witness_replay_report.md"),
    )
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    report = analyze(root)
    if args.validate_only:
        print(json.dumps(report, sort_keys=True))
        return
    output_json = args.output_json if args.output_json.is_absolute() else root / args.output_json
    output_markdown = (
        args.output_markdown
        if args.output_markdown.is_absolute()
        else root / args.output_markdown
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    output_markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {output_json}")
    print(f"Wrote {output_markdown}")


if __name__ == "__main__":
    main()
