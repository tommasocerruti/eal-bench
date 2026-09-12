"""Export the published cross-domain tables and verify their saved provenance offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from itertools import product
from pathlib import Path

from analysis.common import load_run

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ("procurement", "cybersecurity", "finance")
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


def checked_json(root: Path, reference: dict) -> dict:
    path = root / reference["path"]
    if sha256(path) != reference["sha256"]:
        raise ValueError(f"Source hash differs: {path}")
    return read_json(path)


def summarize(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    groups = defaultdict(lambda: dict.fromkeys(COUNTS, 0))
    for row in rows:
        for field in COUNTS:
            groups[tuple(row[key] for key in keys)][field] += row[field]
    return [dict(zip(keys, key), **counts) for key, counts in sorted(groups.items())]


def trial_counts(rows: list[dict]) -> dict:
    authorized = [r for r in rows if r["request_authorized"] is True]
    unauthorized = [r for r in rows if r["request_authorized"] is False]
    return {
        "trials": len(rows),
        "provider_error_trials": sum(r.get("provider_error") is not None for r in rows),
        "authorized_trials": len(authorized),
        "authorized_use": sum(bool(r["requested_action_taken"]) for r in authorized),
        "unauthorized_trials": len(unauthorized),
        "unauthorized_submissions": sum(bool(r["requested_action_taken"]) for r in unauthorized),
    }


def from_trials(run: Path, domain: str) -> dict:
    loaded = load_run(run, domain=domain)
    if not loaded.hash_verified:
        raise ValueError(f"Trials lack a verified manifest hash: {run}")
    rows = [r for r in loaded.rows
            if r["metadata"]["study"].get("evidence_role") == "generated_final"]
    pairs = defaultdict(list)
    for row in rows:
        pairs[tuple(row[k] for k in ("case_id", "condition_id", "probe_id", "memory_id"))].append(row)
    executors = loaded.manifest["executor"]["targets"]
    if any(len(v) != 2 or {r["executor"]["target_id"] for r in v} != set(executors)
           for v in pairs.values()):
        raise ValueError(f"Incomplete executor pairing: {run}")
    return {
        "by_condition": {c: trial_counts([r for r in rows if r["condition_id"] == c])
                         for c in CONDITIONS},
        "by_executor": {e: trial_counts([r for r in rows if r["executor"]["target_id"] == e])
                        for e in executors},
        "agreement": {
            "pairs": len(pairs),
            "matches": sum(v[0]["requested_action_taken"] == v[1]["requested_action_taken"]
                           for v in pairs.values()),
        },
    }


def from_report(report: dict, source: dict, route: dict) -> dict:
    """Normalize historical report formats without changing their frozen files."""
    if source["format"] == "grouped_route_counts_v1":
        row = report["replication"]["raw_route_results"][route["source_row"]]
        if (row["seed"], row["writer_target"], row["domain_id"], row["manifest_sha256"]) != (
            route["seed"], route["writer_target"], route["domain_id"], route["manifest"]["sha256"],
        ):
            raise ValueError("Report route does not match its manifest selection")

        def counts(value: dict) -> dict:
            aliases = {"trials": "n", "provider_error_trials": "provider_errors"}
            return {k: value[aliases.get(k, k)] for k in COUNTS}

        agreement = row["executor_transfer"]
        return {
            "by_condition": {k: counts(v) for k, v in row["by_condition"].items()},
            "by_executor": {k: counts(v) for k, v in row["by_executor"].items()},
            "agreement": {"pairs": agreement["matched_memory_request_pairs"],
                          "matches": agreement["requested_action_outcome_matches"]},
        }
    if source["format"] == "factorial_matrix_counts_v1":
        rows = [r for r in report["ordinary_matrix"]
                if (r["seed"], r["writer_target"]) == (route["seed"], route["writer_target"])]
        cells = [(r["memory_condition"], r["executor_target"]) for r in rows]
        expected = set(product(CONDITIONS, route["executor_targets"]))
        if set(cells) != expected or len(cells) != len(expected):
            raise ValueError("Incomplete or duplicated factorial cells")
        agreements = [r for r in report["executor_transfer"]
                      if (r["seed"], r["writer_target"]) == (route["seed"], route["writer_target"])]
        if len(agreements) != 1:
            raise ValueError("Incomplete or duplicated agreement cells")
        agreement = agreements[0]
        return {
            "by_condition": {r["memory_condition"]: {k: r[k] for k in COUNTS}
                             for r in summarize(rows, ("memory_condition",))},
            "by_executor": {r["executor_target"]: {k: r[k] for k in COUNTS}
                            for r in summarize(rows, ("executor_target",))},
            "agreement": {"pairs": agreement["matched_fixed_memory_request_pairs"],
                          "matches": agreement["requested_action_matches"]},
        }
    raise ValueError(f"Unsupported report format: {source['format']}")


def validate_counts(value: dict, specification: dict) -> None:
    if set(value["by_condition"]) != set(CONDITIONS):
        raise ValueError("Unexpected memory conditions")
    if set(value["by_executor"]) != set(specification["executor_targets"]):
        raise ValueError("Unexpected executor targets")
    for group in ("by_condition", "by_executor"):
        for counts in value[group].values():
            if any(type(counts[k]) is not int or counts[k] < 0 for k in COUNTS):
                raise ValueError("Counts must be nonnegative integers")
            if counts["authorized_trials"] + counts["unauthorized_trials"] != counts["trials"]:
                raise ValueError("Authorization denominators do not sum to trials")
            for numerator, denominator in (("authorized_use", "authorized_trials"),
                                           ("unauthorized_submissions", "unauthorized_trials"),
                                           ("provider_error_trials", "trials")):
                if counts[numerator] > counts[denominator]:
                    raise ValueError("Outcome exceeds its denominator")
    condition_total = summarize(list(value["by_condition"].values()), ())[0]
    if condition_total != summarize(list(value["by_executor"].values()), ())[0]:
        raise ValueError("Condition and executor totals differ")
    expected = specification["authorized_trials_per_writer_condition"]
    if any((r["authorized_trials"], r["unauthorized_trials"]) != (expected, expected)
           for r in value["by_condition"].values()):
        raise ValueError("Condition denominators differ from the registered design")
    agreement = value["agreement"]
    if any(type(agreement[k]) is not int for k in ("matches", "pairs")):
        raise ValueError("Agreement counts must be integers")
    if not 0 <= agreement["matches"] <= agreement["pairs"] == condition_total["trials"] // 2:
        raise ValueError("Agreement denominator differs from paired ordinary trials")


def build(root: Path, domain: str, raw_root: Path) -> tuple[dict, dict]:
    spec = read_json(root / f"results/{domain}/paper/manifest.json")
    if spec["schema_version"] != "paper_result_manifest_v1" or spec["domain_id"] != domain:
        raise ValueError("Unexpected result manifest")
    checked_json(root, spec["release"])
    for reference in spec["dataset_sources"]:
        if sha256(root / reference["path"]) != reference["sha256"]:
            raise ValueError(f"Dataset source hash differs: {reference['path']}")
    snapshot = checked_json(root, spec["counts"])
    sources = {key: checked_json(root, ref) for key, ref in spec["sources"].items()
               if ref["format"] != "trials_v5"}
    expected = set(product(spec["seeds"], spec["writer_targets"]))
    actual = [(r["seed"], r["writer_target"]) for r in spec["routes"]]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("Missing, duplicate, or unexpected writer routes")
    if set(snapshot) != {r["route_id"] for r in spec["routes"]}:
        raise ValueError("Count snapshot and route inventory differ")
    condition_rows, executor_rows, agreement_rows, inventory = [], [], [], []
    verified_trials = 0
    for route in spec["routes"]:
        manifest = checked_json(root, route["manifest"])
        if (manifest["domain_id"], manifest["seed"], manifest["status"], manifest["route"]) != (
            domain, route["seed"], "completed", "writer",
        ) or manifest["writer"]["targets"] != [route["writer_target"]]:
            raise ValueError("Run identity differs from the registered route")
        for key, expected_value in spec["treatment"].items():
            if manifest[key] != expected_value:
                raise ValueError(f"Treatment differs across routes: {key}")
        if sorted(manifest["executor"]["targets"]) != sorted(spec["executor_targets"]):
            raise ValueError("Run uses different executor targets")
        value = snapshot[route["route_id"]]
        validate_counts(value, spec)
        source = spec["sources"][route["source_id"]]
        if source["format"] != "trials_v5":
            if from_report(sources[route["source_id"]], source, route) != value:
                raise ValueError("Saved counts differ from the frozen report")
        run_relative = Path(route["manifest"]["path"]).parent
        run = raw_root / run_relative
        for kind, entry in manifest["files"].items():
            path = run / entry["path"]
            status = "missing"
            if path.is_file():
                if sha256(path) != entry["sha256"]:
                    raise ValueError(f"Raw artifact hash differs: {path}")
                with path.open(encoding="utf-8") as handle:
                    count = 0
                    for line in handle:
                        if line.strip():
                            if not isinstance(json.loads(line), dict):
                                raise ValueError(f"Non-object JSONL row: {path}")
                            count += 1
                if count != entry["rows"]:
                    raise ValueError(f"Raw artifact row count differs: {path}")
                status = "hash_and_rows_verified"
            inventory.append({"domain_id": domain, "route_id": route["route_id"],
                              "artifact": kind, "path": str(run_relative / entry["path"]),
                              "expected_sha256": entry["sha256"], "expected_rows": entry["rows"],
                              "status": status})
        if (run / manifest["files"]["trials"]["path"]).is_file():
            # The checked manifest is authoritative even when raw files live elsewhere.
            checked_json(raw_root, route["manifest"])
            if from_trials(run, domain) != value:
                raise ValueError(f"Raw trial counts differ from the snapshot: {run}")
            verified_trials += 1
        identity = {k: route[k] for k in ("seed", "writer_target")}
        for condition, counts in value["by_condition"].items():
            condition_rows.append({"domain_id": domain, **identity,
                                   "memory_condition": condition, **counts})
        for executor, counts in value["by_executor"].items():
            executor_rows.append({"domain_id": domain, **identity,
                                  "executor_target": executor, **counts})
        agreement_rows.append({"domain_id": domain, **identity, **value["agreement"]})
    missing = sum(r["status"] == "missing" for r in inventory)
    summary = {
        "schema_version": "paper_result_summary_v1", "domain_id": domain,
        "release_id": spec["release_id"], "paper": spec["paper"],
        "seeds": spec["seeds"], "treatment": spec["treatment"],
        "writer_routes": len(actual), "raw_trial_routes_verified": verified_trials,
        "ordinary_pooled": summarize(condition_rows, ())[0],
        "requested_action_agreement": {k: sum(r[k] for r in agreement_rows)
                                       for k in ("matches", "pairs")},
        "raw_artifacts": {"expected": len(inventory), "verified": len(inventory) - missing,
                          "missing": missing},
        "evidence_basis": "Hash-linked saved counts; available raw trials are recounted.",
        "limits": "Count verification does not rerun the oracle or recreate missing bootstrap inputs.",
    }
    tables = {
        "writer_conditions": condition_rows,
        "writer_executors": executor_rows,
        "seed_conditions": summarize(condition_rows, ("domain_id", "seed", "memory_condition")),
        "memory_design": summarize(condition_rows, ("domain_id", "memory_condition")),
        "executor_transfer": summarize(executor_rows, ("domain_id", "executor_target")),
        "executor_agreement": agreement_rows,
        "artifact_inventory": inventory,
    }
    return summary, tables


def render(summary: dict, tables: dict) -> str:
    lines = [f"# {summary['domain_id'].title()} paper results", "",
             "| Memory condition | Authorized use | Unauthorized submission |",
             "|---|---:|---:|"]
    for condition in CONDITIONS:
        row = next(r for r in tables["memory_design"] if r["memory_condition"] == condition)
        values = []
        for n, d in (("authorized_use", "authorized_trials"),
                     ("unauthorized_submissions", "unauthorized_trials")):
            values.append(f"{row[n]}/{row[d]} ({100 * row[n] / row[d]:.1f}%)")
        lines.append(f"| {condition} | {' | '.join(values)} |")
    agreement, raw = summary["requested_action_agreement"], summary["raw_artifacts"]
    lines += ["", f"Executor agreement: {agreement['matches']}/{agreement['pairs']}.",
              f"Raw artifacts: {raw['verified']}/{raw['expected']} verified; {raw['missing']} missing.",
              f"Raw trial routes recounted: {summary['raw_trial_routes_verified']}/{summary['writer_routes']}.",
              summary["limits"], ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=(*DOMAINS, "all"), default="all")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--raw-root", type=Path, help="repository-shaped archive containing original raw files")
    parser.add_argument("--output-dir", type=Path, help="export the same CSV/JSON/Markdown layout per domain")
    parser.add_argument("--require-raw", action="store_true", help="exit 2 if any inventoried raw file is missing")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    domains = DOMAINS if args.domain == "all" else (args.domain,)
    if args.output_dir:
        output = args.output_dir.resolve()
        if output == root or any(p == output or p in output.parents for p in (root / "domains", root / "results")):
            parser.error("Use an output directory outside frozen domains/ and results/")
    missing = 0
    for domain in domains:
        summary, tables = build(root, domain, (args.raw_root or root).resolve())
        markdown = render(summary, tables)
        print(markdown)
        missing += summary["raw_artifacts"]["missing"]
        if args.output_dir:
            destination = output / domain
            destination.mkdir(parents=True, exist_ok=True)
            for name, rows in tables.items():
                with (destination / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
            (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            (destination / "tables.md").write_text(markdown, encoding="utf-8")
    if args.require_raw and missing:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
