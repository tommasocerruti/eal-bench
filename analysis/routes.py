"""Summarize one canonical controls, writer, or pressure run."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .common import load_jsonl


def summarize(run_dir: Path) -> dict[str, Any]:
    path = run_dir.expanduser().resolve()
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "completed":
        raise ValueError("route analysis requires a completed run")
    route = str(manifest.get("study"))
    if route not in {"controls", "writer", "pressure"}:
        raise ValueError(f"unsupported canonical route: {route!r}")
    trials = _artifact(path, manifest, "trials")
    if route == "controls":
        summary = _controls(trials)
    elif route == "writer":
        summary = _writer(path, manifest, trials)
    else:
        summary = _pressure(path, manifest, trials)
    return {
        "route": route,
        "run": str(path),
        "domain_id": manifest["domain_id"],
        "corpus_version": manifest["corpus_version"],
        "presentation_id": manifest["presentation"]["presentation_id"],
        "presentation_hash": manifest["presentation_hash"],
        "executor_targets": manifest["executor"]["targets"],
        "summary": summary,
    }


def _controls(trials: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in trials:
        grouped[
            (
                str(_study(row).get("evidence_role")),
                str(_core(row).get("dimension")),
            )
        ].append(row)
    outcomes = {
        f"{role}:{dimension}": _rates(rows)
        for (role, dimension), rows in sorted(grouped.items())
    }
    return {
        "overall": _rates(trials),
        "outcomes_by_evidence_role_and_dimension": outcomes,
        "broadening_to_repair": _matched_role_contrast(
            trials, "controlled_broadening", "exact_repair"
        ),
        "faithful_to_sham": _matched_role_contrast(
            trials, "faithful_sham_control", "semantic_sham"
        ),
    }


def _writer(
    path: Path,
    manifest: Mapping[str, Any],
    trials: list[dict[str, Any]],
) -> dict[str, Any]:
    fidelity = _artifact(path, manifest, "fidelity")
    eligibility = _artifact(path, manifest, "substantive_eligibility")
    selected_conditions = tuple(
        str(value) for value in manifest.get("conditions", ())
    )
    error_fields: dict[str, int] = defaultdict(int)
    scored_states: dict[str, set[str]] = defaultdict(set)
    for row in fidelity:
        condition = str(row["condition_id"])
        scored_states[condition].add(str(row["state_id"]))
        if not row.get("exact"):
            error_fields[condition] += 1
    memory_errors = {}
    for condition in selected_conditions:
        architecture = (
            "typed" if condition.endswith("_typed") else "free_text"
        )
        strategy = (
            "incremental"
            if condition.startswith("incremental_")
            else "one_shot"
        )
        key = f"{architecture}:{strategy}"
        memory_errors[key] = (
            {
                "error_field_count": error_fields[condition],
                "scored_states": len(scored_states[condition]),
                "status": "scored",
            }
            if architecture == "typed"
            else {
                "error_field_count": None,
                "scored_states": 0,
                "status": "not_scored_without_accepted_annotations",
            }
        )
    selected = [
        row for row in eligibility if row.get("selected_for_executor") is True
    ]
    witness_trials = [
        row
        for row in trials
        if _study(row).get("request_role") == "witness"
        and _study(row).get("evidence_role")
        in {"natural_error", "exact_repair"}
    ]
    return {
        "memory_errors_by_architecture_and_strategy": memory_errors,
        "ordinary_baseline": _rates(
            [
                row
                for row in trials
                if _study(row).get("evidence_role") == "generated_final"
            ]
        ),
        "ordinary_baseline_by_condition": {
            condition: _rates(
                [
                    row
                    for row in trials
                    if _study(row).get("evidence_role")
                    == "generated_final"
                    and row.get("condition_id") == condition
                ]
            )
            for condition in selected_conditions
        },
        "substantive_overgrant_exposure": {
            "screened": len(eligibility),
            "eligible": sum(row.get("eligible") is True for row in eligibility),
            "selected": len(selected),
            "status": (
                "estimable"
                if selected
                else "inconclusive_no_natural_overgrant"
            ),
        },
        "witness_behavior": {
            role: _rates(
                [
                    row
                    for row in witness_trials
                    if _study(row).get("evidence_role") == role
                ]
            )
            for role in ("natural_error", "exact_repair")
        },
    }


def _pressure(
    path: Path,
    manifest: Mapping[str, Any],
    pressured: list[dict[str, Any]],
) -> dict[str, Any]:
    pairs = _artifact(path, manifest, "pressure_pairs")
    source_path = Path(str(manifest["source_writer_run"]))
    source_manifest = json.loads(
        (source_path / "manifest.json").read_text(encoding="utf-8")
    )
    baseline = {
        _core(row)["trial_id"]: row
        for row in _artifact(source_path, source_manifest, "trials")
    }
    pressured_by_id = {
        _core(row)["trial_id"]: row for row in pressured
    }
    factorial: list[
        tuple[dict[str, Any], dict[str, Any], dict[str, Any]]
    ] = []
    targeted: dict[
        str,
        list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    ] = defaultdict(list)
    for pair in pairs:
        baseline_id = str(pair["baseline_trial_id"])
        pressured_id = str(pair["pressured_trial_id"])
        if baseline_id not in baseline or pressured_id not in pressured_by_id:
            raise ValueError(
                f"pressure pair {pair.get('pressure_pair_id')!r} has "
                "missing baseline or pressured trial"
            )
        base = baseline[baseline_id]
        strong = pressured_by_id[pressured_id]
        family = str(
            pair.get("analysis_family") or "natural_error_repair"
        )
        row = (pair, base, strong)
        if family == "writer_factorial":
            factorial.append(row)
        elif family == "natural_error_repair":
            targeted[str(pair["evidence_role"])].append(row)
        else:
            raise ValueError(f"unknown pressure analysis family {family!r}")
    factorial_by_condition: dict[
        str,
        list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    ] = defaultdict(list)
    for row in factorial:
        factorial_by_condition[str(row[0]["condition_id"])].append(row)
    effects = {}
    for role in ("natural_error", "exact_repair"):
        rows = targeted.get(role, [])
        effects[role] = (
            {
                "pairs": len(rows),
                "baseline_unauthorized_action_rate": _mean(
                    base["unauthorized_action_taken"]
                    for _, base, _ in rows
                ),
                "pressured_unauthorized_action_rate": _mean(
                    strong["unauthorized_action_taken"]
                    for _, _, strong in rows
                ),
                "pressure_effect": _mean(
                    int(strong["unauthorized_action_taken"])
                    - int(base["unauthorized_action_taken"])
                    for _, base, strong in rows
                ),
            }
            if rows
            else {"pairs": 0, "status": "association_not_estimable"}
        )
    interaction = "association_not_estimable"
    if all(effects[role].get("pairs", 0) for role in effects):
        interaction = (
            effects["natural_error"]["pressure_effect"]
            - effects["exact_repair"]["pressure_effect"]
        )
    return {
        "writer_factorial": {
            "overall": _pressure_pair_summary(factorial),
            "by_condition": {
                condition: _pressure_pair_summary(rows)
                for condition, rows in sorted(
                    factorial_by_condition.items()
                )
            },
        },
        "targeted_natural_error_repair": {
            "effects": effects,
            "memory_error_x_pressure_interaction": interaction,
        },
        "effects": effects,
        "memory_error_x_pressure_interaction": interaction,
    }


def _pressure_pair_summary(
    rows: list[
        tuple[dict[str, Any], dict[str, Any], dict[str, Any]]
    ],
) -> dict[str, Any]:
    if not rows:
        return {"pairs": 0, "status": "association_not_estimable"}
    baseline = [base for _, base, _ in rows]
    pressured = [strong for _, _, strong in rows]
    authorized = [
        (base, strong)
        for _, base, strong in rows
        if base["request_authorized"]
    ]
    unauthorized = [
        (base, strong)
        for _, base, strong in rows
        if not base["request_authorized"]
    ]
    if any(
        base["request_authorized"] != strong["request_authorized"]
        for _, base, strong in rows
    ):
        raise ValueError("pressure pair changed the oracle authorization label")
    return {
        "pairs": len(rows),
        "baseline": _rates(baseline),
        "strong_pressure": _rates(pressured),
        "authorized_use_pressure_effect": (
            _mean(
                int(strong["requested_action_taken"])
                - int(base["requested_action_taken"])
                for base, strong in authorized
            )
            if authorized
            else "association_not_estimable"
        ),
        "unauthorized_action_pressure_effect": (
            _mean(
                int(strong["unauthorized_action_taken"])
                - int(base["unauthorized_action_taken"])
                for base, strong in unauthorized
            )
            if unauthorized
            else "association_not_estimable"
        ),
        "all_request_unauthorized_action_pressure_effect": _mean(
            int(strong["unauthorized_action_taken"])
            - int(base["unauthorized_action_taken"])
            for _, base, strong in rows
        ),
    }


def _rates(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    selected = list(rows)
    if not selected:
        return {"n": 0, "status": "no_events"}
    authorized = [row for row in selected if row["request_authorized"]]
    unauthorized = [row for row in selected if not row["request_authorized"]]
    return {
        "n": len(selected),
        "authorized_use_rate": _mean(
            row["requested_action_taken"] for row in authorized
        ),
        "unauthorized_action_rate": _mean(
            row["unauthorized_action_taken"] for row in unauthorized
        ),
        "provider_errors": sum(
            row.get("provider_error") is not None for row in selected
        ),
    }


def _matched_role_contrast(
    trials: list[dict[str, Any]],
    left: str,
    right: str,
) -> dict[str, Any]:
    left_rows = [
        row for row in trials if _study(row).get("evidence_role") == left
    ]
    right_rows = [
        row for row in trials if _study(row).get("evidence_role") == right
    ]
    left_by_key = {
        _comparison_key(row): row for row in left_rows
    }
    right_by_key = {
        _comparison_key(row): row for row in right_rows
    }
    if len(left_by_key) != len(left_rows) or len(right_by_key) != len(
        right_rows
    ):
        raise ValueError("control contrast contains duplicate comparison rows")
    shared = sorted(set(left_by_key) & set(right_by_key))
    return {
        left: _rates(left_rows),
        right: _rates(right_rows),
        "matched_pairs": len(shared),
        "unmatched_left": len(left_by_key) - len(shared),
        "unmatched_right": len(right_by_key) - len(shared),
        "paired_unauthorized_action_effect": _mean(
            int(right_by_key[key]["unauthorized_action_taken"])
            - int(left_by_key[key]["unauthorized_action_taken"])
            for key in shared
        ),
        "paired_requested_action_effect": _mean(
            int(right_by_key[key]["requested_action_taken"])
            - int(left_by_key[key]["requested_action_taken"])
            for key in shared
        ),
    }


def _comparison_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    study = _study(row)
    executor = row.get("executor", {})
    return (
        row.get("case_id"),
        study.get("comparison_id"),
        study.get("request_role"),
        (
            executor.get("target_id")
            if isinstance(executor, Mapping)
            else None
        ),
        row.get("executor_run_id"),
        row.get("seed"),
    )


def _artifact(
    path: Path,
    manifest: Mapping[str, Any],
    name: str,
) -> list[dict[str, Any]]:
    entry = manifest.get("files", {}).get(name)
    if not isinstance(entry, Mapping):
        return []
    return load_jsonl(path / str(entry["path"]))


def _core(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return row.get("metadata", {}).get("core", {})


def _study(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return row.get("metadata", {}).get("study", {})


def _mean(values: Iterable[Any]) -> float | None:
    selected = [float(value) for value in values]
    return sum(selected) / len(selected) if selected else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.run_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
