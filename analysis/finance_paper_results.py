"""Rebuild Finance paper tables from frozen aggregates and audit raw-file availability."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from itertools import product
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ("one_shot_text", "incremental_text", "one_shot_typed", "incremental_typed")
COUNTS = (
    "trials", "provider_error_trials", "authorized_trials", "authorized_use",
    "unauthorized_trials", "unauthorized_submissions",
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_json(base: Path, entry: dict, path_key: str = "path") -> dict:
    path = base / entry[path_key]
    if sha256(path) != entry["sha256"]:
        raise ValueError(f"Frozen file hash differs: {path}")
    return read_json(path)


def summarize(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    groups = defaultdict(lambda: dict.fromkeys(COUNTS, 0))
    for row in rows:
        for field in COUNTS:
            groups[tuple(row[key] for key in keys)][field] += row[field]
    return [dict(zip(keys, key), **counts) for key, counts in sorted(groups.items())]


def audit_artifacts(root: Path, package: Path, release: dict) -> list[dict]:
    inventory = []
    for route_id, reference in release["results"]["run_manifests"].items():
        manifest = checked_json(package, reference)
        run = (package / reference["path"]).resolve().parent
        if manifest["status"] != "completed" or manifest["domain_id"] != "finance":
            raise ValueError(f"Not a completed Finance manifest: {route_id}")
        for kind, entry in manifest["files"].items():
            path = run / entry["path"]
            status = "missing"
            if path.is_file():
                if sha256(path) != entry["sha256"]:
                    raise ValueError(f"Raw artifact hash differs: {path}")
                count = 0
                with path.open(encoding="utf-8") as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        if not isinstance(json.loads(line), dict):
                            raise ValueError(f"Raw artifact contains a non-object row: {path}")
                        count += 1
                if count != entry["rows"]:
                    raise ValueError(f"Raw artifact rows differ: {path}")
                status = "hash_and_rows_verified"
            inventory.append({
                "route_id": route_id, "artifact": kind,
                "path": str(path.relative_to(root)), "expected_rows": entry["rows"],
                "expected_sha256": entry["sha256"], "status": status,
            })
    return inventory


def build(root: Path) -> tuple[dict, dict[str, list[dict]]]:
    package = root / "domains/finance"
    release = read_json(package / "release.json")
    if release["release_id"] != "finance_redesign_v1":
        raise ValueError("This command requires finance_redesign_v1, the paper's Finance release")
    for name, expected in release["claim_corpus"]["source_files"].items():
        if sha256(package / name) != expected:
            raise ValueError(f"Frozen corpus source hash differs: {name}")
    for name, expected in release["implementation"].items():
        if sha256(package / name) != expected:
            raise ValueError(f"Frozen Finance implementation hash differs: {name}")
    for section, path_key in (
        (release["capacity"], "artifact"), (release["presentation"], "source"),
        (release["pressure_profile"], "source"), (release["analysis_plan"], "source"),
        (release["run_plan"], "source"), (release["offline_validation"], "report"),
    ):
        checked_json(package, section, path_key)
    reports = release["results"]["reports"]
    report = checked_json(package, reports["final_json"])
    audit = checked_json(package, reports["artifact_audit"])
    markdown = package / reports["final_markdown"]["path"]
    if sha256(markdown) != reports["final_markdown"]["sha256"]:
        raise ValueError("Frozen Markdown report hash differs")
    precommit = checked_json(package, release["final_precommit"])
    lock = precommit["scientific_lock"]
    if report["metric_lock"]["paper_facing_metric"] != "exact_request_unauthorized_submission":
        raise ValueError("Report uses a different behavioral metric")
    matrix = report["ordinary_matrix"]
    keys = ("seed", "writer_target", "memory_condition", "executor_target")
    expected = set(product(
        lock["seeds"], lock["writer_targets_in_order"],
        lock["memory_conditions"], lock["executor_targets"],
    ))
    actual = [tuple(row[k] for k in keys) for row in matrix]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("Ordinary matrix has missing, duplicate, or unexpected cells")
    for row in matrix:
        if any(type(row[k]) is not int or row[k] < 0 for k in COUNTS):
            raise ValueError("Matrix counts must be nonnegative integers")
        if (row["authorized_trials"], row["unauthorized_trials"], row["trials"]) != (32, 32, 64):
            raise ValueError("Matrix cell denominators differ from the frozen 32+32 design")
        if row["authorized_use"] > 32 or row["unauthorized_submissions"] > 32:
            raise ValueError("An outcome count exceeds its denominator")
    condition_rows = summarize(matrix, ("memory_condition",))
    for row in condition_rows:
        saved = next(r["behavior"] for r in report["memory_design"]
                     if r["memory_condition"] == row["memory_condition"])
        if any(row[k] != saved[k] for k in COUNTS):
            raise ValueError("Recomputed condition counts differ from the frozen aggregate")
    total = summarize(matrix, ())[0]
    if any(total[k] != report["ordinary_pooled"][k] for k in COUNTS):
        raise ValueError("Recomputed total counts differ from the frozen aggregate")
    transfers = report["executor_transfer"]
    transfer_keys = [(r["seed"], r["writer_target"]) for r in transfers]
    expected_transfer = set(product(lock["seeds"], lock["writer_targets_in_order"]))
    if set(transfer_keys) != expected_transfer or len(transfers) != len(expected_transfer):
        raise ValueError("Executor agreement matrix is incomplete or duplicated")
    inventory = audit_artifacts(root, package, release)
    missing = sum(row["status"] == "missing" for row in inventory)
    summary = {
        "schema_version": "finance_paper_tables_v1",
        "release_id": release["release_id"],
        "corpus_sha256": release["claim_corpus"]["sha256"],
        "report_sha256": reports["final_json"]["sha256"],
        "paper": "https://arxiv.org/html/2609.01836v1#A2.SS2",
        "evidence_basis": "frozen aggregate cells; no raw trial reconstruction",
        "seeds": lock["seeds"], "ordinary_matrix_cells": len(matrix),
        "ordinary_pooled": total,
        "requested_action_agreement": {
            "matches": sum(r["requested_action_matches"] for r in transfers),
            "pairs": sum(r["matched_fixed_memory_request_pairs"] for r in transfers),
        },
        "raw_artifacts": {
            "expected": len(inventory), "verified": len(inventory) - missing,
            "missing": missing,
        },
        "historical_audit_status": audit["status"],
        "current_raw_files_complete": missing == 0,
        "limits": "Aggregate checks do not independently verify scoring or recreate bootstrap inputs.",
    }
    tables = {
        "ordinary_matrix": [{k: r[k] for k in (*keys, *COUNTS)} for r in matrix],
        "seed_conditions": summarize(matrix, ("seed", "memory_condition")),
        "memory_design": condition_rows,
        "executor_transfer": summarize(matrix, ("executor_target",)),
        "executor_agreement": transfers,
        "artifact_inventory": inventory,
    }
    return summary, tables


def render(summary: dict, tables: dict) -> str:
    lines = [
        "# Finance paper results", "",
        "Source: frozen aggregate cells from `finance_redesign_v1`.",
        "These counts reproduce the Finance rows of paper Appendix B.2, Tables 11–13.", "",
        "| Condition | Authorized use | Unauthorized submission |",
        "|---|---:|---:|",
    ]
    for condition in CONDITIONS:
        row = next(r for r in tables["memory_design"] if r["memory_condition"] == condition)
        values = []
        for numerator, denominator in (
            ("authorized_use", "authorized_trials"),
            ("unauthorized_submissions", "unauthorized_trials"),
        ):
            n, d = row[numerator], row[denominator]
            values.append(f"{n}/{d} ({100 * n / d:.1f}%)")
        lines.append(f"| {condition} | {' | '.join(values)} |")
    raw = summary["raw_artifacts"]
    agreement = summary["requested_action_agreement"]
    lines += [
        "", f"Executor requested-action agreement: {agreement['matches']}/{agreement['pairs']}.",
        f"Raw artifacts: {raw['verified']}/{raw['expected']} verified; {raw['missing']} missing.",
        "The historical completion audit does not establish present-day raw-file availability.",
        summary["limits"], "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, help="write derived CSV, JSON, and Markdown files")
    parser.add_argument("--require-raw", action="store_true", help="exit 2 if original files are missing")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    summary, tables = build(root)
    markdown = render(summary, tables)
    if args.output_dir:
        output = args.output_dir.resolve()
        frozen = (root / "domains", root / "results")
        if output == root or any(p == output or p in output.parents for p in frozen):
            parser.error("Use a separate output directory, outside frozen domains/ and results/")
        output.mkdir(parents=True, exist_ok=True)
        for name, rows in tables.items():
            with (output / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        (output / "tables.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    if args.require_raw and not summary["current_raw_files_complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
