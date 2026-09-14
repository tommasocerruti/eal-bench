#!/usr/bin/env python3
"""Paired analysis for bounded-context event-sourced authorization memory."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from analysis.common import load_jsonl, load_run
from domains import get_domain
from experiments.authorization_memory.persistence import (
    canonical_json,
    content_hash,
    file_hash,
    write_json,
    write_jsonl,
)
from experiments.authorization_memory.tokens import count_reference_tokens


SCHEMA_VERSION = "bounded_event_sourcing_analysis_v2"
BOOTSTRAP_SEED = 20260821
BOOTSTRAP_DRAWS = 10_000
EVENT_CONDITION = "bounded_event_sourced_typed"
BASELINE_CONDITION = "incremental_typed"
PAIR_FACTORS = (
    "domain_id",
    "target_id",
    "writer_provider",
    "writer_route_hash",
    "writer_seed",
    "corpus_version",
    "presentation_id",
    "presentation_hash",
    "baseline_implementation_hash",
    "event_implementation_hash",
    "executor_target_id",
    "executor_provider",
    "executor_route_hash",
    "baseline_executor_response_model",
    "event_executor_response_model",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-run", action="append", required=True)
    parser.add_argument("--baseline-run", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-draws", type=int, default=BOOTSTRAP_DRAWS)
    return parser.parse_args()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return load_jsonl(path)


def _load_verified_run(raw_path: str | Path) -> dict[str, Any]:
    path = Path(raw_path).expanduser().resolve()
    manifest_path = path / "manifest.json" if path.is_dir() else path
    if manifest_path.name != "manifest.json" or not manifest_path.is_file():
        raise ValueError(f"run has no manifest: {raw_path}")
    run_dir = manifest_path.parent.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("status") != "completed":
        raise ValueError(f"run is not completed: {manifest_path}")
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise ValueError(f"run has no artifact map: {manifest_path}")
    rows: dict[str, list[dict[str, Any]]] = {}
    verified = {}
    for name, entry in files.items():
        if not isinstance(entry, Mapping):
            raise ValueError(f"invalid artifact entry {name!r}: {manifest_path}")
        relative = entry.get("path")
        expected_hash = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise ValueError(f"incomplete artifact entry {name!r}: {manifest_path}")
        artifact = (run_dir / relative).resolve()
        if not artifact.is_relative_to(run_dir) or not artifact.is_file():
            raise ValueError(f"artifact is missing or escapes its run: {artifact}")
        actual_hash = file_hash(artifact)
        if actual_hash != expected_hash:
            raise ValueError(f"artifact hash mismatch: {artifact}")
        if artifact.suffix == ".jsonl":
            artifact_rows = (
                load_run(manifest_path).rows
                if name == "trials" and manifest.get("study") == "writer"
                else _jsonl(artifact)
            )
            if entry.get("rows") is not None and len(artifact_rows) != int(entry["rows"]):
                raise ValueError(f"artifact row-count mismatch: {artifact}")
            rows[str(name)] = artifact_rows
        verified[str(name)] = {
            "path": str(artifact),
            "sha256": actual_hash,
            **({"rows": int(entry["rows"])} if entry.get("rows") is not None else {}),
        }
    return {
        "run_dir": run_dir,
        "manifest_path": manifest_path.resolve(),
        "manifest_hash": file_hash(manifest_path),
        "manifest": manifest,
        "rows": rows,
        "verified_files": verified,
    }


def _writer_target(row: Mapping[str, Any], manifest: Mapping[str, Any]) -> str:
    writer = row.get("writer")
    if isinstance(writer, Mapping) and writer.get("target_id"):
        return str(writer["target_id"])
    targets = manifest.get("writer", {}).get("targets", ())
    if len(targets) == 1:
        return str(targets[0])
    if row.get("target_id"):
        return str(row["target_id"])
    raise ValueError("cannot resolve writer target")


def _baseline_representation(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    manifest = run["manifest"]
    domain = get_domain(str(manifest["domain_id"]))
    cases = {
        domain.corpus.case_id(case): case
        for case in domain.corpus.load_cases(str(manifest["corpus_version"]))
    }
    target = str(manifest["writer"]["targets"][0])
    seed = int(manifest["seed"])
    memories = {
        row["memory_id"]: row
        for row in run["rows"]["memories"]
        if row.get("condition_id") == BASELINE_CONDITION
    }
    state_rows = [
        row for row in run["rows"]["memory_states"] if row.get("condition_id") == BASELINE_CONDITION
    ]
    result = []
    previous: dict[str, bool] = {}
    for state in sorted(state_rows, key=lambda row: (row["case_id"], int(row["block_index"]))):
        memory = memories.get(state.get("current_memory_id"))
        if memory is None and state.get("current_memory_id") is not None:
            raise ValueError(f"baseline state has no memory: {state.get('state_id')}")
        case = cases[str(state["case_id"])]
        payload = (
            domain.memory.parse_typed(memory["payload"])
            if memory is not None
            else domain.memory.empty_typed()
        )
        report = domain.fidelity.compare(
            case,
            payload,
            through_block_index=int(state["block_index"]),
        )
        semantic = any(field.errors for field in report.fields)
        overgrant = any(field.overgrant for field in report.fields)
        prior = previous.get(str(state["case_id"]))
        result.append(
            {
                "row_type": "state_transition",
                "architecture": "typed_incremental",
                "domain_id": domain.domain_id,
                "case_id": state["case_id"],
                "target_id": target,
                "writer_seed": seed,
                "block_index": int(state["block_index"]),
                "semantic_error": semantic,
                "authority_gaining_error": overgrant,
                "final_state_exact": not semantic,
                "error_introduction": bool(semantic and prior is False),
                "error_persistence": bool(semantic and prior is True),
                "self_repair": bool(not semantic and prior is True),
                "failed_update": str(state.get("status")) not in {"accepted", "no_change"},
            }
        )
        previous[str(state["case_id"])] = semantic

    ordinary_trials = [
        row
        for row in run["rows"]["trials"]
        if row.get("condition_id") == BASELINE_CONDITION
        and row.get("metadata", {}).get("study", {}).get("evidence_role") == "generated_final"
    ]
    evidence_ids = {str(row["evidence_id"]) for row in ordinary_trials}
    evidence = [
        row
        for row in run["rows"]["evidence"]
        if row.get("condition_id") == BASELINE_CONDITION
        and str(row.get("evidence_id")) in evidence_ids
    ]
    by_case: dict[str, dict[str, Any]] = {}
    for row in evidence:
        case_id = str(row["case_id"])
        if case_id in by_case and row["content_hash"] != by_case[case_id]["content_hash"]:
            raise ValueError(f"multiple ordinary baseline memories for {target}/{case_id}")
        by_case[case_id] = row
    if set(by_case) != set(manifest["case_ids"]):
        raise ValueError(f"ordinary baseline evidence is incomplete for {run['run_dir']}")
    for case_id, evidence_row in sorted(by_case.items()):
        case = cases[case_id]
        payload = domain.memory.parse_typed(evidence_row["payload"])
        for probe in domain.corpus.probes(case):
            canonical = domain.executor.oracle(case, probe.request)
            remembered = domain.memory.authorizes(case, payload, probe.request)
            result.append(
                {
                    "row_type": "request_formation",
                    "architecture": "typed_incremental",
                    "domain_id": domain.domain_id,
                    "case_id": case_id,
                    "target_id": target,
                    "writer_seed": seed,
                    "probe_id": probe.probe_id,
                    "pair_id": probe.pair_id,
                    "dimension": probe.dimension,
                    "canonical_authorized": canonical.authorized,
                    "memory_authorized": remembered.authorized,
                    "false_authority": bool(not canonical.authorized and remembered.authorized),
                    "valid_authority_preserved": bool(
                        canonical.authorized and remembered.authorized
                    ),
                    "representation_undergrant": bool(
                        canonical.authorized and not remembered.authorized
                    ),
                }
            )
    return result


def _event_representation(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in run["rows"]["representation_metrics"]:
        rows.append({**row, "architecture": "event_sourced"})
    return rows


def _ordinary_baseline_trials(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    manifest = run["manifest"]
    output = []
    for row in run["rows"]["trials"]:
        if row.get("condition_id") != BASELINE_CONDITION:
            continue
        if row.get("metadata", {}).get("study", {}).get("evidence_role") != "generated_final":
            continue
        output.append(
            {
                **row,
                "architecture": "typed_incremental",
                "target_id": _writer_target(row, manifest),
                "writer_seed": int(row.get("writer_seed", manifest["seed"])),
                "executor_target_id": str(row["executor"]["target_id"]),
            }
        )
    return output


def _event_trials(run: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = run["manifest"]
    ordinary = []
    oracle = []
    for row in run["rows"]["trials"]:
        study = row.get("metadata", {}).get("study", {})
        replay_kind = study.get("replay_kind")
        enriched = {
            **row,
            "target_id": _writer_target(row, manifest),
            "writer_seed": int(row.get("writer_seed", manifest["seed"])),
            "executor_target_id": str(row["executor"]["target_id"]),
        }
        if row.get("condition_id") == EVENT_CONDITION and replay_kind == "event_sourced_full":
            ordinary.append({**enriched, "architecture": "event_sourced"})
        elif replay_kind == "oracle_exact_residual_replacement":
            oracle.append({**enriched, "architecture": "oracle_exact_residual"})
    return ordinary, oracle


def _trajectory_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row["domain_id"],
        row["case_id"],
        row["target_id"],
        int(row["writer_seed"]),
        row.get("writer_route_hash"),
        row.get("presentation_hash"),
        row.get("corpus_version"),
    )


def _paired_representation(
    baseline: Sequence[Mapping[str, Any]],
    event: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    pairs = []
    for row_type in ("request_formation", "state_transition"):
        baseline_rows = [row for row in baseline if row["row_type"] == row_type]
        event_rows = [row for row in event if row["row_type"] == row_type]
        if row_type == "request_formation":

            def key(row: Mapping[str, Any]) -> tuple[Any, ...]:
                return (*_trajectory_key(row), row["probe_id"])

            metrics = (
                "false_authority",
                "valid_authority_preserved",
                "representation_undergrant",
            )
        else:

            def key(row: Mapping[str, Any]) -> tuple[Any, ...]:
                return (*_trajectory_key(row), int(row["block_index"]))

            metrics = (
                "semantic_error",
                "authority_gaining_error",
                "error_introduction",
                "error_persistence",
                "self_repair",
            )
        left = _unique_rows(baseline_rows, key)
        right = _unique_rows(event_rows, key)
        if set(left) != set(right):
            raise ValueError(f"unpaired {row_type} rows: baseline={len(left)} event={len(right)}")
        for identity in sorted(left):
            base = left[identity]
            new = right[identity]
            for metric in metrics:
                eligible = True
                if metric == "false_authority":
                    eligible = not bool(base["canonical_authorized"])
                elif metric in {"valid_authority_preserved", "representation_undergrant"}:
                    eligible = bool(base["canonical_authorized"])
                if eligible:
                    pairs.append(_pair_row(metric, base, new, extra={"row_type": row_type}))
    baseline_final = _last_transition(baseline)
    event_final = _last_transition(event)
    if set(baseline_final) != set(event_final):
        raise ValueError("final trajectory pairing is incomplete")
    for key, base in sorted(baseline_final.items()):
        new = event_final[key]
        pairs.append(
            _pair_row(
                "final_state_error",
                base,
                new,
                baseline_value=bool(base["semantic_error"]),
                event_value=bool(new["semantic_error"]),
                extra={"row_type": "trajectory_final"},
            )
        )
    return pairs


def _last_transition(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[Any, ...], Mapping[str, Any]]:
    result = {}
    for row in rows:
        if row["row_type"] != "state_transition":
            continue
        key = _trajectory_key(row)
        if key not in result or int(row["block_index"]) > int(result[key]["block_index"]):
            result[key] = row
    return result


def _paired_behavior(
    baseline: Sequence[Mapping[str, Any]],
    event: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    def key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            *_trajectory_key(row),
            row["executor_target_id"],
            row.get("executor_route_hash"),
            row["probe_id"],
        )

    left = _unique_rows(baseline, key)
    right = _unique_rows(event, key)
    if set(left) != set(right):
        raise ValueError(f"behavior pairing is incomplete: baseline={len(left)} event={len(right)}")
    result = []
    for identity in sorted(left):
        base = left[identity]
        new = right[identity]
        metric = "authorized_use" if base["request_authorized"] else "unauthorized_submission"
        result.append(
            _pair_row(
                metric,
                base,
                new,
                baseline_value=bool(base["requested_action_taken"]),
                event_value=bool(new["requested_action_taken"]),
                extra={"executor_target_id": base["executor_target_id"], "row_type": "behavior"},
            )
        )
    return result


def _pair_row(
    metric: str,
    baseline: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    baseline_value: bool | None = None,
    event_value: bool | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **{key: baseline.get(key) for key in PAIR_FACTORS},
        "baseline_implementation_hash": baseline.get("memory_implementation_hash"),
        "event_implementation_hash": event.get("memory_implementation_hash"),
        "baseline_executor_response_model": (baseline.get("executor") or {}).get("response_model"),
        "event_executor_response_model": (event.get("executor") or {}).get("response_model"),
        "baseline_provider_error": bool(baseline.get("provider_error")),
        "event_provider_error": bool(event.get("provider_error")),
        "metric": metric,
        "domain_id": baseline["domain_id"],
        "case_id": baseline["case_id"],
        "target_id": baseline["target_id"],
        "writer_seed": int(baseline["writer_seed"]),
        "cluster_id": "|".join(str(value) for value in _trajectory_key(baseline)),
        "baseline_value": bool(baseline[metric] if baseline_value is None else baseline_value),
        "event_value": bool(event[metric] if event_value is None else event_value),
        **dict(extra or {}),
    }


def _summary_row(
    metric: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    stratum: str,
    stratum_value: str,
    draws: int,
) -> dict[str, Any]:
    evaluable = [
        row
        for row in rows
        if not row.get("baseline_provider_error") and not row.get("event_provider_error")
    ]
    baseline_n = sum(bool(row["baseline_value"]) for row in evaluable)
    event_n = sum(bool(row["event_value"]) for row in evaluable)
    denominator = len(evaluable)
    baseline_rate = baseline_n / denominator if denominator else None
    event_rate = event_n / denominator if denominator else None
    difference = event_rate - baseline_rate if denominator else None
    interval = _cluster_bootstrap_interval(evaluable, draws=draws) if denominator else None
    return {
        "schema_version": 1,
        "metric": metric,
        "stratum": stratum,
        "stratum_value": stratum_value,
        "paired_observations": len(rows),
        "behaviorally_evaluable_pairs": denominator,
        "baseline_provider_errors": sum(bool(row.get("baseline_provider_error")) for row in rows),
        "event_provider_errors": sum(bool(row.get("event_provider_error")) for row in rows),
        "denominator_policy": "invalid_and_no_action_retained_provider_failures_reported_separately",
        "trajectory_clusters": len({row["cluster_id"] for row in rows}),
        "typed_incremental": {
            "numerator": baseline_n,
            "denominator": denominator,
            "rate": baseline_rate,
        },
        "event_sourced": {
            "numerator": event_n,
            "denominator": denominator,
            "rate": event_rate,
        },
        "absolute_difference_event_minus_typed": difference,
        "relative_difference": (difference / baseline_rate if baseline_rate else None),
        "cluster_bootstrap_95_interval": interval,
        "bootstrap_draws": draws,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }


def _cluster_bootstrap_interval(
    rows: Sequence[Mapping[str, Any]],
    *,
    draws: int,
) -> list[float]:
    by_cluster: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cluster[str(row["cluster_id"])].append(row)
    clusters = sorted(by_cluster)
    cluster_totals = {
        cluster: (
            sum(float(row["event_value"]) - float(row["baseline_value"]) for row in cluster_rows),
            len(cluster_rows),
        )
        for cluster, cluster_rows in by_cluster.items()
    }
    rng = random.Random(BOOTSTRAP_SEED + sum(ord(char) for char in rows[0]["metric"]))
    values = []
    for _ in range(draws):
        sample = [rng.choice(clusters) for _ in clusters]
        numerator = sum(cluster_totals[cluster][0] for cluster in sample)
        denominator = sum(cluster_totals[cluster][1] for cluster in sample)
        values.append(numerator / denominator)
    values.sort()
    low = values[max(0, math.floor(0.025 * draws) - 1)]
    high = values[min(draws - 1, math.ceil(0.975 * draws) - 1)]
    return [low, high]


def _all_summaries(rows: Sequence[Mapping[str, Any]], *, draws: int) -> list[dict[str, Any]]:
    groups = defaultdict(list)
    for row in rows:
        groups[(row["metric"], *(row.get(key) for key in PAIR_FACTORS))].append(row)
    return [
        {
            **_summary_row(
                identity[0],
                values,
                stratum="full_route_and_presentation",
                stratum_value=canonical_json(dict(zip(PAIR_FACTORS, identity[1:]))),
                draws=draws,
            ),
            "factors": dict(zip(PAIR_FACTORS, identity[1:])),
        }
        for identity, values in sorted(groups.items(), key=lambda item: canonical_json(item[0]))
    ]


def _residual_replay(
    event_runs: Sequence[Mapping[str, Any]],
    ordinary_trials: Sequence[Mapping[str, Any]],
    oracle_trials: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    ordinary_by_key = {}
    oracle_by_key = {}
    for row in ordinary_trials:
        witness = row.get("metadata", {}).get("study", {}).get("residual_witness_id")
        if witness:
            ordinary_by_key[(str(witness), row["executor_target_id"])] = row
    for row in oracle_trials:
        witness = row.get("metadata", {}).get("study", {}).get("residual_witness_id")
        if witness:
            oracle_by_key[(str(witness), row["executor_target_id"])] = row
    output = []
    for run in event_runs:
        for witness in run["rows"].get("residual_witnesses", ()):
            for executor in run["manifest"]["executor"]["targets"]:
                key = (str(witness["witness_id"]), str(executor))
                event = ordinary_by_key.get(key)
                oracle = oracle_by_key.get(key)
                if event is None or oracle is None:
                    raise ValueError(f"residual witness replay is incomplete: {key}")
                output.append(
                    {
                        **witness,
                        "executor_target_id": executor,
                        "event_requested_action_taken": bool(event["requested_action_taken"]),
                        "event_decision": event["decision"],
                        "oracle_requested_action_taken": bool(oracle["requested_action_taken"]),
                        "oracle_decision": oracle["decision"],
                        "causal_replacement_changed_requested_action": bool(
                            event["requested_action_taken"] and not oracle["requested_action_taken"]
                        ),
                    }
                )
    return output


def _token_summary(values: Iterable[int]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": median,
        "mean": fmean(ordered),
        "max": ordered[-1],
    }


def _resource_summary(
    event_runs: Sequence[Mapping[str, Any]],
    baseline_runs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    event_resources = [row for run in event_runs for row in run["rows"]["writer_resources"]]
    baseline_contexts = [
        row
        for run in baseline_runs
        for row in run["rows"]["model_contexts"]
        if row.get("stage") == "writer" and row.get("condition_id") == BASELINE_CONDITION
    ]
    baseline_previous_state_tokens = []
    for run in baseline_runs:
        domain = get_domain(str(run["manifest"]["domain_id"]))
        memories = {
            row["memory_id"]: row
            for row in run["rows"]["memories"]
            if row.get("condition_id") == BASELINE_CONDITION
        }
        states_by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in run["rows"]["memory_states"]:
            if row.get("condition_id") == BASELINE_CONDITION:
                states_by_case[str(row["case_id"])].append(row)
        for states in states_by_case.values():
            previous = domain.memory.serialize_typed(domain.memory.empty_typed())
            for state in sorted(states, key=lambda row: int(row["block_index"])):
                baseline_previous_state_tokens.append(
                    count_reference_tokens(canonical_json(previous))
                )
                previous = (
                    memories[str(state["current_memory_id"])]["payload"]
                    if state.get("current_memory_id") is not None
                    else domain.memory.serialize_typed(domain.memory.empty_typed())
                )
    external_final = []
    external_storage_final = []
    reduced_final = []
    for run in event_runs:
        by_chain: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in run["rows"]["writer_resources"]:
            chain_id = row.get("chain_id") or "|".join(
                (
                    str(row["target_id"]),
                    str(row["case_id"]),
                    str(row["writer_seed"]),
                )
            )
            by_chain[chain_id].append(row)
        for rows in by_chain.values():
            final = max(rows, key=lambda row: (int(row["block_index"]), int(row["attempt_index"])))
            external_final.append(int(final["external_event_log_tokens_after_update"]))
            external_storage_final.append(
                int(final["external_event_log_storage_tokens_after_update"])
            )
            reduced_final.append(int(final["reduced_state_tokens_after_update"]))
    return {
        "writer_visible": {
            "event_previous_state_tokens": _token_summary(
                int(row["previous_state_tokens"]) for row in event_resources
            ),
            "typed_incremental_previous_state_tokens": _token_summary(
                baseline_previous_state_tokens
            ),
            "event_reference_index_tokens": _token_summary(
                int(row["reference_index_tokens"]) for row in event_resources
            ),
            "event_new_block_tokens": _token_summary(
                int(row["new_block_tokens"]) for row in event_resources
            ),
            "event_total_surface_tokens": _token_summary(
                int(row["total_writer_surface_tokens"]) for row in event_resources
            ),
            "event_output_tokens_reference": _token_summary(
                int(row["writer_output_reference_tokens"]) for row in event_resources
            ),
            "typed_incremental_total_surface_tokens": _token_summary(
                count_reference_tokens(
                    canonical_json(
                        {
                            "messages": row["messages"],
                            "tools": row["tools"],
                            "tool_choice": row["tool_choice"],
                        }
                    )
                )
                for row in baseline_contexts
            ),
            "persistent_state_representation": "exact_same_domain_native_typed_state",
            "raw_block_boundaries": "identical",
            "event_log_model_visible": False,
            "padding_or_truncation": False,
        },
        "external_storage": {
            "final_event_log_tokens": _token_summary(external_final),
            "final_event_log_storage_tokens_including_lineage": _token_summary(
                external_storage_final
            ),
            "final_reduced_state_tokens": _token_summary(reduced_final),
            "counted_as_model_visible": False,
        },
    }


def _usage_cost(row: Mapping[str, Any]) -> tuple[float, bool]:
    usage = row.get("usage")
    if not isinstance(usage, Mapping):
        return 0.0, False
    if usage.get("cost") is not None:
        return float(usage["cost"]), True
    return 0.0, False


def _actual_usage(event_runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [row for run in event_runs for row in run["rows"].get("calls", ())]
    by_target = defaultdict(
        lambda: {
            "records": 0,
            "cost": 0.0,
            "missing_cost": 0,
            "failures": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
    )
    by_task = defaultdict(lambda: {"records": 0, "input_tokens": 0, "output_tokens": 0})
    call_ids = Counter()
    for row in rows:
        target = "|".join(
            str(row.get(key) or "unknown") for key in ("provider", "target_id", "resolved_model")
        )
        by_target[target]["records"] += 1
        by_target[target]["failures"] += int(bool(row.get("error")))
        usage = row.get("usage")
        input_tokens = (
            int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            if isinstance(usage, Mapping)
            else 0
        )
        output_tokens = (
            int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
            if isinstance(usage, Mapping)
            else 0
        )
        by_target[target]["input_tokens"] += input_tokens
        by_target[target]["output_tokens"] += output_tokens
        task = str(row.get("task") or "unknown")
        by_task[task]["records"] += 1
        by_task[task]["input_tokens"] += input_tokens
        by_task[task]["output_tokens"] += output_tokens
        cost, available = _usage_cost(row)
        by_target[target]["cost"] += cost
        by_target[target]["missing_cost"] += int(not available)
        if row.get("call_id"):
            call_ids[str(row["call_id"])] += 1
    return {
        "call_records": len(rows),
        "logical_calls": len(call_ids),
        "transport_retries": sum(max(0, count - 1) for count in call_ids.values()),
        "failed_records": sum(bool(row.get("error")) for row in rows),
        "reported_cost_subtotal_usd": sum(value["cost"] for value in by_target.values()),
        "total_cost_usd": None
        if any(value["missing_cost"] for value in by_target.values())
        else sum(value["cost"] for value in by_target.values()),
        "calls_missing_cost_or_usage": sum(value["missing_cost"] for value in by_target.values()),
        "by_target": {
            key: {
                **value,
                "reported_cost_subtotal_usd": value["cost"],
                "cost": None if value["missing_cost"] else value["cost"],
            }
            for key, value in sorted(by_target.items())
        },
        "by_task": dict(sorted(by_task.items())),
        "pricing_basis": "provider-reported usage.cost only; absent costs remain missing",
    }


def _diagnostics(event_runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [row for run in event_runs for row in run["rows"]["event_diagnostics"]]
    failures = Counter(failure for row in rows for failure in row.get("failures", ()))
    return {
        "aligned_or_unmatched_events": len(rows),
        "exact_events": sum(bool(row["exact"]) for row in rows),
        "failure_counts": dict(sorted(failures.items())),
        "ambiguous_alignment_rows": sum(bool(row["alignment_ambiguous"]) for row in rows),
        "alignment_policy": "deterministic chronological position; unmatched tails are explicitly ambiguous",
        "llm_judge_used": False,
    }


def _unique_rows(rows: Sequence[Mapping[str, Any]], key: Any) -> dict[Any, Mapping[str, Any]]:
    result = {}
    for row in rows:
        identity = key(row)
        if identity in result:
            raise ValueError(f"duplicate paired observation: {identity}")
        result[identity] = row
    return result


def _enrich_rows(rows: Sequence[Mapping[str, Any]], run: Mapping[str, Any]) -> list[dict[str, Any]]:
    manifest = run["manifest"]
    enriched = []
    for row in rows:
        target = str(row["target_id"])
        routes = [
            route for route in manifest["writer"]["target_routes"] if route["target_id"] == target
        ]
        if len(routes) != 1:
            raise ValueError(f"analysis requires one writer route for {target}")
        route = routes[0]
        writer = {
            key: route.get(key)
            for key in (
                "target_id",
                "provider",
                "requested_model",
                "resolved_model",
                "request_parameters",
            )
        }
        item = {
            **row,
            "writer_provider": writer["provider"],
            "writer_route_hash": content_hash(writer),
            "corpus_version": manifest["corpus_version"],
            "presentation_id": manifest["presentation"]["presentation_id"],
            "presentation_hash": manifest["presentation_hash"],
            "memory_implementation_hash": row.get("memory_implementation_hash")
            or row.get("metadata", {}).get("core", {}).get("memory_implementation_hash")
            or manifest.get("memory_implementation_hash")
            or manifest["writer"].get("memory_implementation_hash"),
        }
        executor = row.get("executor")
        if executor:
            item["executor_provider"] = executor["provider"]
            item["executor_route_hash"] = content_hash(
                {
                    key: executor.get(key)
                    for key in (
                        "target_id",
                        "provider",
                        "requested_model",
                        "resolved_model",
                        "effective_parameters",
                    )
                }
            )
        enriched.append(item)
    return enriched


def _validate_analysis_sources(
    event_runs: Sequence[Mapping[str, Any]], baseline_runs: Sequence[Mapping[str, Any]]
) -> None:
    available = {run["manifest_hash"] for run in baseline_runs}
    required = {
        source["manifest_sha256"]
        for run in event_runs
        for source in run["manifest"].get("verified_baseline_sources", ())
    }
    if required != available:
        raise ValueError("baseline manifests must match the event runs' frozen sources exactly")
    for run in event_runs:
        manifest = run["manifest"]
        plan = manifest.get("run_plan")
        if plan is not None and content_hash(plan) != manifest.get("run_plan_sha256"):
            raise ValueError("event run plan hash mismatch")


def _stratified_resources(
    event_runs: Sequence[Mapping[str, Any]], baseline_runs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    by_hash = {run["manifest_hash"]: run for run in baseline_runs}
    result = {}
    for run in event_runs:
        for source in run["manifest"]["verified_baseline_sources"]:
            target = source["writer_target_id"]
            selected = {
                **run,
                "rows": {
                    name: [
                        row
                        for row in rows
                        if row.get("target_id") == target
                        or (row.get("writer") or {}).get("target_id") == target
                    ]
                    for name, rows in run["rows"].items()
                },
            }
            key = f"{run['manifest_hash']}|{target}"
            result[key] = _resource_summary([selected], [by_hash[source["manifest_sha256"]]])
    return result


def analyze(
    event_paths: Sequence[str | Path],
    baseline_paths: Sequence[str | Path],
    *,
    output: Path,
    bootstrap_draws: int = BOOTSTRAP_DRAWS,
) -> Path:
    if bootstrap_draws <= 0:
        raise ValueError("bootstrap draws must be positive")
    event_runs = [_load_verified_run(path) for path in event_paths]
    baseline_runs = [_load_verified_run(path) for path in baseline_paths]
    for run in event_runs:
        if run["manifest"].get("study") != "event_sourcing":
            raise ValueError(f"not an event-sourcing run: {run['run_dir']}")
    for run in baseline_runs:
        if BASELINE_CONDITION not in set(run["manifest"].get("conditions") or ()):
            raise ValueError(f"not a typed-incremental baseline: {run['run_dir']}")

    if len({run["manifest_hash"] for run in event_runs}) != len(event_runs) or len(
        {run["manifest_hash"] for run in baseline_runs}
    ) != len(baseline_runs):
        raise ValueError("duplicate input run manifest")
    _validate_analysis_sources(event_runs, baseline_runs)
    baseline_rep = [
        row for run in baseline_runs for row in _enrich_rows(_baseline_representation(run), run)
    ]
    event_rep = [row for run in event_runs for row in _enrich_rows(_event_representation(run), run)]
    baseline_trials, event_trials, oracle_trials = [], [], []
    historical = {run["manifest_hash"]: run for run in baseline_runs}
    for run in event_runs:
        ordinary, oracle = _event_trials(run)
        event_trials.extend(_enrich_rows(ordinary, run))
        oracle_trials.extend(_enrich_rows(oracle, run))
        fresh = _ordinary_baseline_trials(run)
        if run["manifest"].get("baseline_replay"):
            if not fresh:
                raise ValueError("event run has no promised fresh baseline replay trials")
            baseline_trials.extend(_enrich_rows(fresh, run))
        else:
            for source in run["manifest"]["verified_baseline_sources"]:
                baseline = historical[source["manifest_sha256"]]
                selected = [
                    row
                    for row in _ordinary_baseline_trials(baseline)
                    if row["executor_target_id"] in run["manifest"]["executor"]["targets"]
                ]
                baseline_trials.extend(_enrich_rows(selected, baseline))
    paired = [
        *_paired_representation(baseline_rep, event_rep),
        *_paired_behavior(baseline_trials, event_trials),
    ]
    summaries = _all_summaries(paired, draws=bootstrap_draws)
    residual = _residual_replay(event_runs, event_trials, oracle_trials)
    resource = _stratified_resources(event_runs, baseline_runs)
    usage = _actual_usage(event_runs)
    diagnostics = {
        f"{run['manifest_hash']}|{target}": _diagnostics(
            [
                {
                    **run,
                    "rows": {
                        **run["rows"],
                        "event_diagnostics": [
                            row
                            for row in run["rows"]["event_diagnostics"]
                            if row["target_id"] == target
                        ],
                    },
                }
            ]
        )
        for run in event_runs
        for target in run["manifest"]["writer"]["targets"]
    }

    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    artifacts = {
        "paired_observations": paired,
        "paired_metrics": summaries,
        "baseline_representation": baseline_rep,
        "event_representation": event_rep,
        "residual_causal_replay": residual,
    }
    for name, rows in artifacts.items():
        path = output / f"{name}.jsonl"
        count = write_jsonl(path, rows)
        files[name] = {"path": path.name, "sha256": file_hash(path), "rows": count}
    for name, value in {
        "resource_summary": resource,
        "actual_usage": usage,
        "event_diagnostics_summary": diagnostics,
    }.items():
        path = output / f"{name}.json"
        write_json(path, value)
        files[name] = {"path": path.name, "sha256": file_hash(path)}
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "created_at": datetime.now().astimezone().isoformat(),
        "architecture_interpretation": (
            "complete bounded-context event-sourced architecture; component effects are not isolated"
        ),
        "event_log_model_visible": False,
        "event_runs": [
            {"path": str(run["run_dir"]), "manifest_sha256": run["manifest_hash"]}
            for run in event_runs
        ],
        "baseline_runs": [
            {"path": str(run["run_dir"]), "manifest_sha256": run["manifest_hash"]}
            for run in baseline_runs
        ],
        "paired_metric_rows": len(summaries),
        "residual_witness_replays": len(residual),
        "usage": usage,
        "files": files,
    }
    write_json(output / "manifest.json", summary)
    return output


def main() -> None:
    args = _parse_args()
    output = analyze(
        args.event_run,
        args.baseline_run,
        output=args.output,
        bootstrap_draws=args.bootstrap_draws,
    )
    print(canonical_json({"status": "completed", "output": str(output)}))


if __name__ == "__main__":
    main()
