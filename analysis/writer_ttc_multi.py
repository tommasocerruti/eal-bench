#!/usr/bin/env python3
"""Synthesize completed Procurement writer-TTC analyses across writers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "procurement_writer_ttc_multi_v2"
K_LEVELS = (1, 2, 4, 8)
EXPECTED_WRITERS = {
    "qwen_plus_0728_openrouter",
    "nemotron_3_ultra_baseten",
    "grok_4_3_openrouter",
    "kimi_baseten",
    "glm_5_2_baseten",
}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _value(value: str) -> Any:
    if value == "":
        return None
    if value == "True":
        return True
    if value == "False":
        return False
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            {key: _value(value) for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def _load_analysis(path: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "procurement_writer_ttc_v3":
        raise ValueError(f"{path}: unsupported analysis schema")
    for name, metadata in manifest["files"].items():
        artifact = path / name
        if _hash(artifact) != metadata["sha256"]:
            raise ValueError(f"{path}: hash mismatch for {name}")
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    if summary.get("levels") != list(K_LEVELS):
        raise ValueError(f"{path}: incomplete TTC levels")
    return {
        "path": path,
        "manifest": manifest,
        "summary": summary,
        "behavior": _csv_rows(path / "behavior_by_condition.csv"),
        "fidelity": _csv_rows(path / "typed_fidelity_by_condition.csv"),
    }


def _weighted(rows: Sequence[Mapping[str, Any]], value: str, weight: str) -> float:
    denominator = sum(float(row[weight]) for row in rows)
    return sum(float(row[value]) * float(row[weight]) for row in rows) / denominator


def _writer_rows(analyses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for analysis in analyses:
        summary = analysis["summary"]
        behavior = {row["k"]: row for row in summary["behavior_pooled"]}
        fidelity = {row["k"]: row for row in summary["typed_fidelity_pooled"]}
        selection = {row["k"]: row for row in summary["selection_scaling"]}
        mechanisms = {row["k"]: row for row in summary["incremental_mechanisms"]}
        for k in K_LEVELS:
            b = behavior[k]
            f = fidelity[k]
            s = selection[k]
            m = mechanisms[k]
            output.append(
                {
                    "writer_label": summary["writer_label"],
                    "writer_target": summary["writer_target"],
                    "k": k,
                    "typed_semantic_fidelity_rate": f["semantic_fidelity_rate"],
                    "typed_authorization_error_rate": f["authorization_error_rate"],
                    "typed_apparent_authority_rate": f["apparent_authority_rate"],
                    "typed_lost_authority_rate": f["lost_authority_rate"],
                    "authorized_use_rate": b["authorized_use_rate"],
                    "targeted_unauthorized_submission_rate": b[
                        "targeted_unauthorized_submission_rate"
                    ],
                    "broader_unsafe_action_rate": b["broader_unsafe_action_rate"],
                    "pool_contains_full_fidelity_exact_rate": s[
                        "pool_contains_full_fidelity_exact_rate"
                    ],
                    "reviewer_selected_full_fidelity_exact_rate": s[
                        "reviewer_selected_full_fidelity_exact_rate"
                    ],
                    "oracle_best_mean_field_errors": s[
                        "oracle_best_mean_field_errors"
                    ],
                    "selected_mean_field_errors": s["selected_mean_field_errors"],
                    "mean_full_fidelity_selection_regret": s[
                        "mean_full_fidelity_selection_regret"
                    ],
                    "reviewer_failure_rate": s["reviewer_failure_rate"],
                    "error_introduction_rate": m["error_introduction_rate"],
                    "error_persistence_rate": m["error_persistence_rate"],
                    "self_repair_rate": m["self_repair_rate"],
                    "incremental_final_error_rate": m["final_error_rate"],
                }
            )
    baselines = {
        row["writer_target"]: row for row in output if row["k"] == 1
    }
    delta_fields = (
        "typed_authorization_error_rate",
        "typed_apparent_authority_rate",
        "typed_lost_authority_rate",
        "authorized_use_rate",
        "targeted_unauthorized_submission_rate",
        "broader_unsafe_action_rate",
        "oracle_best_mean_field_errors",
        "selected_mean_field_errors",
        "error_introduction_rate",
        "incremental_final_error_rate",
    )
    for row in output:
        baseline = baselines[row["writer_target"]]
        for field in delta_fields:
            row[f"change_from_k1__{field}"] = row[field] - baseline[field]
    return output


def _condition_rows(
    analyses: Sequence[Mapping[str, Any]], table: str
) -> list[dict[str, Any]]:
    output = []
    for analysis in analyses:
        summary = analysis["summary"]
        for row in analysis[table]:
            output.append(
                {
                    "writer_label": summary["writer_label"],
                    "writer_target": summary["writer_target"],
                    **row,
                }
            )
    return output


def _pooled_behavior(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    conditions = ("one_shot_text", "one_shot_typed", "incremental_text", "incremental_typed", "pooled")
    for k in K_LEVELS:
        for condition in conditions:
            selected = [
                row
                for row in rows
                if row["k"] == k and row["condition_id"] == condition
            ]
            output.append(
                {
                    "k": k,
                    "condition_id": condition,
                    "writers": len(selected),
                    "trial_count": sum(row["trial_count"] for row in selected),
                    "authorized_request_count": sum(
                        row["authorized_request_count"] for row in selected
                    ),
                    "unauthorized_request_count": sum(
                        row["unauthorized_request_count"] for row in selected
                    ),
                    "authorized_use_rate": _weighted(
                        selected, "authorized_use_rate", "authorized_request_count"
                    ),
                    "targeted_unauthorized_submission_rate": _weighted(
                        selected,
                        "targeted_unauthorized_submission_rate",
                        "unauthorized_request_count",
                    ),
                    "broader_unsafe_action_rate": _weighted(
                        selected, "broader_unsafe_action_rate", "trial_count"
                    ),
                    "provider_error_rate": _weighted(
                        selected, "provider_error_rate", "trial_count"
                    ),
                }
            )
    return output


def _pooled_fidelity(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    conditions = ("one_shot_typed", "incremental_typed", "typed_pooled")
    rate_fields = (
        "semantic_fidelity_rate",
        "authorization_error_rate",
        "apparent_authority_rate",
        "lost_authority_rate",
        "mean_semantic_field_errors",
        "mean_overgrant_fields",
        "mean_undergrant_fields",
    )
    for k in K_LEVELS:
        for condition in conditions:
            selected = [
                row
                for row in rows
                if row["k"] == k and row["condition_id"] == condition
            ]
            output.append(
                {
                    "k": k,
                    "condition_id": condition,
                    "writers": len(selected),
                    "memory_observations": sum(
                        row["memory_observations"] for row in selected
                    ),
                    **{
                        field: _weighted(selected, field, "memory_observations")
                        for field in rate_fields
                    },
                    "deterministic_scope": "typed_only",
                }
            )
    return output


def _pooled_selection(analyses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for k in K_LEVELS:
        rows = [
            next(row for row in analysis["summary"]["selection_scaling"] if row["k"] == k)
            for analysis in analyses
        ]
        attempted = sum(row["reviewer_attempted_pools"] for row in rows)
        successful = sum(row["reviewer_successful_pools"] for row in rows)
        typed = sum(row["typed_pools"] for row in rows)
        typed_successful = sum(row["reviewer_successful_typed_pools"] for row in rows)
        output.append(
            {
                "k": k,
                "writers": len(rows),
                "typed_pools": typed,
                "pool_contains_full_fidelity_exact_rate": _weighted(
                    rows, "pool_contains_full_fidelity_exact_rate", "typed_pools"
                ),
                "reviewer_selected_full_fidelity_exact_rate": _weighted(
                    rows, "reviewer_selected_full_fidelity_exact_rate", "typed_pools"
                ),
                "reviewer_full_fidelity_oracle_hit_rate": _weighted(
                    rows, "reviewer_full_fidelity_oracle_hit_rate", "typed_pools"
                ),
                "oracle_best_mean_field_errors": _weighted(
                    rows, "oracle_best_mean_field_errors", "typed_pools"
                ),
                "selected_mean_field_errors": _weighted(
                    rows, "selected_mean_field_errors", "typed_pools"
                ),
                "mean_full_fidelity_selection_regret": _weighted(
                    rows, "mean_full_fidelity_selection_regret", "typed_pools"
                ),
                "reviewer_attempted_pools": attempted,
                "reviewer_successful_pools": successful,
                "reviewer_failure_rate": (
                    None if not attempted else (attempted - successful) / attempted
                ),
                "reviewer_successful_typed_pools": typed_successful,
                "reviewer_typed_failure_rate": (
                    None if k == 1 else (typed - typed_successful) / typed
                ),
                "free_text_oracle_regret": "undefined",
            }
        )
    return output


def _pooled_mechanisms(analyses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for k in K_LEVELS:
        rows = [
            next(row for row in analysis["summary"]["incremental_mechanisms"] if row["k"] == k)
            for analysis in analyses
        ]
        introductions = sum(row["error_introductions"] for row in rows)
        correct = sum(row["correct_origin_transitions"] for row in rows)
        persistences = sum(row["error_persistences"] for row in rows)
        incorrect = sum(row["incorrect_origin_transitions"] for row in rows)
        trajectories = sum(row["selected_trajectories"] for row in rows)
        output.append(
            {
                "k": k,
                "writers": len(rows),
                "selected_trajectories": trajectories,
                "error_introductions": introductions,
                "correct_origin_transitions": correct,
                "error_introduction_rate": introductions / correct,
                "error_persistences": persistences,
                "incorrect_origin_transitions": incorrect,
                "error_persistence_rate": persistences / incorrect,
                "self_repairs": incorrect - persistences,
                "self_repair_rate": (incorrect - persistences) / incorrect,
                "final_error_rate": sum(
                    row["final_error_rate"] * row["selected_trajectories"]
                    for row in rows
                )
                / trajectories,
                "trajectory_contract": "selected_whole_trajectory_no_splicing",
            }
        )
    return output


def _cost(analyses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    costs = [analysis["summary"]["cost"] for analysis in analyses]
    return {
        "clean_five_writer_new_stage_cost_usd": sum(
            row["estimated_total_cost_usd"] for row in costs
        ),
        "clean_five_writer_call_records": sum(
            row["new_model_call_records"] for row in costs
        ),
        "clean_five_writer_error_call_records": sum(
            row["new_error_call_records"] for row in costs
        ),
        "provider_reported_cost_usd": sum(
            row["provider_reported_cost_usd"] for row in costs
        ),
        "rate_derived_cost_usd": sum(row["rate_derived_cost_usd"] for row in costs),
        "pricing_basis": "provider-reported cost where present; otherwise saved usage at frozen 2026-08-08 rates",
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = list(rows[0])
    fields.extend(
        field for row in rows[1:] for field in row if field not in fields
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _pct(value: float | None) -> str:
    return "NA" if value is None else f"{100 * value:.1f}%"


def _report(
    pooled_behavior: Sequence[Mapping[str, Any]],
    pooled_fidelity: Sequence[Mapping[str, Any]],
    pooled_selection: Sequence[Mapping[str, Any]],
    pooled_mechanisms: Sequence[Mapping[str, Any]],
    writer_rows: Sequence[Mapping[str, Any]],
    cost: Mapping[str, Any],
) -> str:
    behavior = {
        row["k"]: row for row in pooled_behavior if row["condition_id"] == "pooled"
    }
    fidelity = {
        row["k"]: row
        for row in pooled_fidelity
        if row["condition_id"] == "typed_pooled"
    }
    selection = {row["k"]: row for row in pooled_selection}
    mechanisms = {row["k"]: row for row in pooled_mechanisms}
    levels_text = " / ".join(str(k) for k in K_LEVELS)
    lines = [
        "# Procurement writer TTC — five-writer synthesis",
        "",
        "Nested trajectory-level selected best-of-k across Qwen Plus, Nemotron 3 Ultra, Grok 4.3, Kimi K2.6, and GLM 5.2. GPT-OSS-120B is fixed as executor. Each writer reviews its own blinded candidates and selects one complete trajectory without rewriting or merging.",
        "",
        "## Main outcomes",
        "",
        "| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k in K_LEVELS:
        f = fidelity[k]
        b = behavior[k]
        lines.append(
            f"| {k} | {_pct(f['semantic_fidelity_rate'])} | {_pct(f['authorization_error_rate'])} | {_pct(f['apparent_authority_rate'])} | {_pct(f['lost_authority_rate'])} | {_pct(b['authorized_use_rate'])} | {_pct(b['targeted_unauthorized_submission_rate'])} | {_pct(b['broader_unsafe_action_rate'])} |"
        )
    lines.extend(
        [
            "",
            "Typed metrics pool 120 deterministic final-memory observations per k. Behavioral metrics pool 1,440 GPT-OSS trials per k, equally split between authorized and unauthorized requests. All four memory conditions remain separate in the CSV tables before pooling.",
            "",
            "## Memory format and writing mode",
            "",
            f"| Condition | Authorized use k={levels_text} | Targeted unsafe k={levels_text} | Broader unsafe k={levels_text} |",
            "|---|---:|---:|---:|",
        ]
    )
    condition_labels = {
        "one_shot_text": "One-shot free text",
        "one_shot_typed": "One-shot typed",
        "incremental_text": "Incremental free text",
        "incremental_typed": "Incremental typed",
    }
    for condition, label in condition_labels.items():
        rows = {
            int(row["k"]): row
            for row in pooled_behavior
            if row["condition_id"] == condition
        }
        lines.append(
            f"| {label} | {' / '.join(_pct(rows[k]['authorized_use_rate']) for k in K_LEVELS)} | {' / '.join(_pct(rows[k]['targeted_unauthorized_submission_rate']) for k in K_LEVELS)} | {' / '.join(_pct(rows[k]['broader_unsafe_action_rate']) for k in K_LEVELS)} |"
        )
    lines.extend(
        [
            "",
            "## Generation and selection",
            "",
            "| k | Pool contains full-fidelity exact | Selected full-fidelity exact | Oracle-best field errors | Selected field errors | Selection regret | Review failure |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for k in K_LEVELS:
        row = selection[k]
        lines.append(
            f"| {k} | {_pct(row['pool_contains_full_fidelity_exact_rate'])} | {_pct(row['reviewer_selected_full_fidelity_exact_rate'])} | {row['oracle_best_mean_field_errors']:.3f} | {row['selected_mean_field_errors']:.3f} | {row['mean_full_fidelity_selection_regret']:.3f} | {_pct(row['reviewer_failure_rate'])} |"
        )
    lines.extend(
        [
            "",
            "The oracle column measures whether more sampling makes a better typed memory available; the selected column measures whether practical self-review recovers it. Free-text oracle regret is undefined, and executor outcomes are never used as an oracle.",
            "",
            "## Incremental typed mechanism",
            "",
            "| k | Error introduction | Persistence | Self-repair | Final error |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for k in K_LEVELS:
        row = mechanisms[k]
        lines.append(
            f"| {k} | {_pct(row['error_introduction_rate'])} | {_pct(row['error_persistence_rate'])} | {_pct(row['self_repair_rate'])} | {_pct(row['final_error_rate'])} |"
        )
    lines.extend(
        [
            "",
            "Each mechanism row follows the selected complete trajectory. Error persistence and self-repair are reported independently of final-state error.",
            "",
            "## Safety–utility assessment at k=8",
            "",
            "| Writer | Δ apparent authority vs k=1 | Δ authorized use | Δ targeted unsafe |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in [row for row in writer_rows if row["k"] == 8]:
        lines.append(
            f"| {row['writer_label']} | {100 * row['change_from_k1__typed_apparent_authority_rate']:+.1f} pp | {100 * row['change_from_k1__authorized_use_rate']:+.1f} pp | {100 * row['change_from_k1__targeted_unauthorized_submission_rate']:+.1f} pp |"
        )
    lines.extend(
        [
            "",
            "This is a descriptive paired scaling experiment over 12 fixed Procurement histories per condition and five writers. Writer, format, and writing-mode rows are preserved separately, and review fallbacks remain in denominators.",
            "",
            "## Clean-stage cost",
            "",
            f"Across all five writer analyses, the non-reused TTC stages contain {cost['clean_five_writer_call_records']} call records and cost ${cost['clean_five_writer_new_stage_cost_usd']:.6f}. Technical attempts excluded from scientific analysis are accounted separately in the experiment audit.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output is not empty: {output}")
    analyses = [_load_analysis(path.resolve()) for path in args.analysis]
    writers = {analysis["summary"]["writer_target"] for analysis in analyses}
    if writers != EXPECTED_WRITERS:
        raise ValueError(f"expected exactly five writers, got {sorted(writers)}")

    writer_rows = _writer_rows(analyses)
    behavior_by_writer_condition = _condition_rows(analyses, "behavior")
    fidelity_by_writer_condition = _condition_rows(analyses, "fidelity")
    pooled_behavior = _pooled_behavior(behavior_by_writer_condition)
    pooled_fidelity = _pooled_fidelity(fidelity_by_writer_condition)
    pooled_selection = _pooled_selection(analyses)
    pooled_mechanisms = _pooled_mechanisms(analyses)
    selection_by_writer = [
        {
            "writer_label": analysis["summary"]["writer_label"],
            "writer_target": analysis["summary"]["writer_target"],
            **row,
        }
        for analysis in analyses
        for row in analysis["summary"]["selection_scaling"]
    ]
    mechanisms_by_writer = [
        {
            "writer_label": analysis["summary"]["writer_label"],
            "writer_target": analysis["summary"]["writer_target"],
            **row,
        }
        for analysis in analyses
        for row in analysis["summary"]["incremental_mechanisms"]
    ]
    cost = _cost(analyses)
    tables = {
        "writer_scaling.csv": writer_rows,
        "behavior_by_writer_condition.csv": behavior_by_writer_condition,
        "typed_fidelity_by_writer_condition.csv": fidelity_by_writer_condition,
        "pooled_behavior_by_condition.csv": pooled_behavior,
        "pooled_typed_fidelity_by_condition.csv": pooled_fidelity,
        "selection_by_writer.csv": selection_by_writer,
        "pooled_selection_scaling.csv": pooled_selection,
        "incremental_mechanisms_by_writer.csv": mechanisms_by_writer,
        "pooled_incremental_mechanisms.csv": pooled_mechanisms,
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        _write_csv(output / name, rows)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "domain_id": "procurement",
        "writers": sorted(writers),
        "executor_target": "gptoss_baseten",
        "levels": list(K_LEVELS),
        "pooled_behavior": pooled_behavior,
        "pooled_typed_fidelity": pooled_fidelity,
        "pooled_selection": pooled_selection,
        "pooled_incremental_mechanisms": pooled_mechanisms,
        "cost": cost,
        "free_text_oracle_regret": "undefined",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "REPORT.md").write_text(
        _report(
            pooled_behavior,
            pooled_fidelity,
            pooled_selection,
            pooled_mechanisms,
            writer_rows,
            cost,
        ),
        encoding="utf-8",
    )
    files = {
        path.name: {"sha256": _hash(path)}
        for path in output.iterdir()
        if path.is_file()
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": "2026-08-15",
        "analysis_module": "analysis.writer_ttc_multi",
        "model_calls": 0,
        "sources": [
            {
                "path": str(analysis["path"]),
                "manifest_sha256": _hash(analysis["path"] / "manifest.json"),
            }
            for analysis in analyses
        ],
        "files": files,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
