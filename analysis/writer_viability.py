"""Audit whether writer chains created usable initial profiles."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from experiments.authorization_memory.persistence import file_hash

from .common import load_jsonl


def summarize_writer_viability(
    run_dir: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    attempts = _attempt_rows(run_dir, manifest)
    if not attempts:
        return {
            "status": "failed_missing_memory_attempts",
            "conditions": {},
            "one_shot_profile_creation_success": _rate(0, 0),
            "incremental_initial_profile_creation_success": _rate(0, 0),
        }

    by_profile: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in attempts:
        profile_id = row.get("profile_id")
        condition = row.get("condition_id")
        if not isinstance(profile_id, str) or not isinstance(condition, str):
            raise ValueError("memory attempt is missing profile or condition identity")
        by_profile[(condition, profile_id)].append(row)

    conditions: dict[str, dict[str, Any]] = {}
    one_shot_success = 0
    one_shot_profiles = 0
    incremental_success = 0
    incremental_profiles = 0
    for condition in sorted({key[0] for key in by_profile}):
        profiles = [
            rows for (selected, _), rows in by_profile.items() if selected == condition
        ]
        initial_results = [_initial_profile_created(rows) for rows in profiles]
        strategy = "incremental" if condition.startswith("incremental_") else "one_shot"
        architecture = "typed" if condition.endswith("_typed") else "free_text"
        successes = sum(initial_results)
        total = len(initial_results)
        status_counts = Counter(
            str(row.get("status")) for rows in profiles for row in rows
        )
        conditions[condition] = {
            "architecture": architecture,
            "strategy": strategy,
            "profiles": total,
            "initial_profile_creation": _rate(successes, total),
            "attempts": sum(len(rows) for rows in profiles),
            "attempt_statuses": dict(sorted(status_counts.items())),
        }
        if strategy == "one_shot":
            one_shot_success += successes
            one_shot_profiles += total
        else:
            incremental_success += successes
            incremental_profiles += total

    one_shot = _rate(one_shot_success, one_shot_profiles)
    incremental = _rate(incremental_success, incremental_profiles)
    passed = (
        one_shot["value"] == 1.0
        and incremental["value"] == 1.0
    )
    return {
        "status": "passed" if passed else "failed",
        "conditions": conditions,
        "one_shot_profile_creation_success": one_shot,
        "incremental_initial_profile_creation_success": incremental,
    }


def _initial_profile_created(rows: list[dict[str, Any]]) -> bool:
    first_block = min(int(row["block_index"]) for row in rows)
    initial = [row for row in rows if int(row["block_index"]) == first_block]
    logical_updates = {str(row["logical_update_id"]) for row in initial}
    if len(logical_updates) != 1:
        raise ValueError("writer profile has multiple initial logical updates")
    return any(
        row.get("status") in {"accepted", "no_change"}
        and isinstance(row.get("accepted_memory_id"), str)
        for row in initial
    )


def _attempt_rows(
    run_dir: Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    entry = manifest.get("files", {}).get("memory_attempts")
    root = run_dir
    if not isinstance(entry, Mapping):
        entry = (
            manifest.get("release_adoption", {})
            .get("source_files", {})
            .get("memory_attempts")
        )
        root = run_dir / "source"
    if not isinstance(entry, Mapping):
        return []
    path = root / str(entry["path"])
    expected_hash = entry.get("sha256")
    if expected_hash is not None and file_hash(path) != expected_hash:
        raise ValueError("memory-attempt artifact hash mismatch")
    rows = load_jsonl(path)
    expected_rows = entry.get("rows")
    if expected_rows is not None and len(rows) != int(expected_rows):
        raise ValueError("memory-attempt artifact row-count mismatch")
    return rows


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }
