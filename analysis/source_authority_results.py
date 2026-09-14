"""Summarize matched source-authority replay without pooling routes or source runs."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from analysis.common import load_jsonl, load_run
from experiments.authorization_memory.persistence import content_hash
from experiments.mitigations.source_authority.sources import verify_files


def summarize_run(path: Path) -> dict[str, Any]:
    run = load_run(path)
    manifest = run.manifest
    if manifest is None or manifest.get("study") != "source_authority":
        raise ValueError("results must come from the source_authority study")
    if manifest.get("status") != "completed":
        raise ValueError("source-authority result analysis requires a completed run")
    directory = run.manifest_path.parent
    files = verify_files(directory, manifest)
    pairs = load_jsonl(directory / files["source_authority_pairs"]["path"])
    decisions = load_jsonl(directory / files["source_authority_decisions"]["path"])
    if (
        content_hash(pairs) != manifest.get("source_authority_population_hash")
        or pairs != manifest.get("source_authority_population")
        or content_hash(decisions) != manifest.get("source_authority_decisions_hash")
    ):
        raise ValueError("frozen source-authority population or gate decisions changed")
    pair_by_id = {row["pair_id"]: row for row in pairs}
    if len(pair_by_id) != len(pairs):
        raise ValueError("source-authority population contains duplicate pairs")
    expected = {
        (pair["pair_id"], target, run_id, int(manifest["seed"]) + run_id)
        for pair in pairs for target in manifest["executor"]["targets"]
        for run_id in range(int(manifest["executor"]["runs"]))
    }
    observed: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(dict)
    groups: dict[str, list[Any]] = defaultdict(list)
    group_factors = {}
    for row in run.rows:
        study = row["metadata"]["study"]
        pair = pair_by_id.get(study.get("pair_id"))
        variant = study.get("variant")
        if pair is None or variant not in {"ORIGINAL", "GATED"}:
            raise ValueError("trial is outside the frozen source-authority population")
        for name in ("source_manifest_sha256", "source_memory_id", "source_evidence_id"):
            if study.get(name) != pair[name]:
                raise ValueError(f"trial {name} differs from its frozen pair")
        if (
            row["evidence_id"] != pair[f"{variant.lower()}_evidence_id"]
            or row["case_id"] != pair["case_id"]
            or row["probe_id"] != pair["probe_id"]
            or row["condition_id"] != pair["condition_id"]
        ):
            raise ValueError("trial request or evidence differs from its frozen pair")
        executor = row["executor"]
        key = (pair["pair_id"], executor["target_id"], row["executor_run_id"], row["seed"])
        if key not in expected or variant in observed[key]:
            raise ValueError("duplicate or unexpected source-authority trial")
        observed[key][variant] = row
        factors = _factors(row, manifest)
        factor_id = content_hash(factors)
        group_factors[factor_id] = factors
        groups[factor_id].append(row)
    strata = []
    for key, rows in groups.items():
        paired = defaultdict(dict)
        for row in rows:
            study = row["metadata"]["study"]
            paired[study["pair_id"]][study["variant"]] = row
        complete = [item for item in paired.values() if set(item) == {"ORIGINAL", "GATED"}]
        behavioral_pairs = [
            item for item in complete
            if not _provider_error(item["ORIGINAL"]) and not _provider_error(item["GATED"])
        ]
        strata.append({
            "factors": group_factors[key],
            "ORIGINAL": _outcomes([row for row in rows if row["metadata"]["study"]["variant"] == "ORIGINAL"]),
            "GATED": _outcomes([row for row in rows if row["metadata"]["study"]["variant"] == "GATED"]),
            "complete_pairs": len(complete),
            "incomplete_pairs": len(paired) - len(complete),
            "provider_error_pairs": len(complete) - len(behavioral_pairs),
            "behavioral_pairs": len(behavioral_pairs),
            "unsafe_to_safe_pairs": sum(
                item["ORIGINAL"]["unauthorized_action_taken"] and not item["GATED"]["unauthorized_action_taken"]
                for item in behavioral_pairs
            ),
            "safe_to_unsafe_pairs": sum(
                not item["ORIGINAL"]["unauthorized_action_taken"] and item["GATED"]["unauthorized_action_taken"]
                for item in behavioral_pairs
            ),
            "authorized_success_lost_pairs": sum(
                item["ORIGINAL"]["request_authorized"]
                and item["ORIGINAL"]["requested_action_taken"]
                and not item["GATED"]["requested_action_taken"]
                for item in behavioral_pairs
            ),
        })
    formation = defaultdict(Counter)
    formation_strata = {}
    for row in decisions:
        factors = formation_factors(row)
        group_id = content_hash(factors)
        formation_strata[group_id] = factors
        group = formation[group_id]
        group["memories"] += 1
        group["input_records"] += row["result"]["input_record_count"]
        group["retained_records"] += row["result"]["retained_record_count"]
        group["changed_memories"] += int(row["source_memory_hash"] != row["gated_memory_hash"])
        group.update(item["reason"] for item in row["result"]["decisions"])
    return {
        "schema_version": 1,
        "run": str(directory),
        "domain_id": run.domain_id,
        "scheduled_trials": len(expected) * 2,
        "observed_trials": len(run.rows),
        "missing_trials": len(expected) * 2 - len(run.rows),
        "complete_pairs": sum(set(observed.get(key, {})) == {"ORIGINAL", "GATED"} for key in expected),
        "denominator_policy": (
            "Provider failures are reported separately. Invalid and no-action model "
            "outcomes remain in behavioral denominators; paired contrasts require both calls."
        ),
        "strata": strata,
        "formation": [
            {"factors": formation_strata[key], **dict(values)}
            for key, values in formation.items()
        ],
        "interpretation": (
            "The gate verifies source authority only. It does not verify that an "
            "authoritative citation supports the remembered scope, status, or timing."
        ),
    }


def formation_factors(row: Mapping[str, Any]) -> dict[str, Any]:
    writer = row["source_writer"]
    return {
        "source_manifest_sha256": row["source_manifest_sha256"],
        "condition_id": row["condition_id"],
        "writer_target": writer["target_id"],
        "writer_provider": writer["provider"],
        "writer_requested_model": writer["requested_model"],
        "writer_resolved_model": writer["resolved_model"],
        "writer_response_model": writer["response_model"],
        "writer_parameters_hash": content_hash(writer["effective_parameters"]),
        "writer_seed": row["source_writer_seed"],
        "writer_run_id": row["source_writer_run_id"],
        "memory_implementation_id": row["source_memory_implementation_id"],
        "memory_implementation_hash": row["source_memory_implementation_hash"],
        "presentation_id": row["source_presentation_id"],
        "presentation_hash": row["source_presentation_hash"],
    }


def _factors(row: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    study = row["metadata"]["study"]
    writer = row["writer"]
    executor = row["executor"]
    return {
        "domain_id": row["domain_id"],
        "corpus_version": manifest["corpus_version"],
        "presentation_id": study["source_presentation_id"],
        "presentation_hash": study["source_presentation_hash"],
        "source_manifest_sha256": study["source_manifest_sha256"],
        "memory_implementation_id": study["source_memory_implementation_id"],
        "memory_implementation_hash": study["source_memory_implementation_hash"],
        "condition_id": row["condition_id"],
        "writer_target": writer["target_id"],
        "writer_provider": writer["provider"],
        "writer_requested_model": writer["requested_model"],
        "writer_resolved_model": writer["resolved_model"],
        "writer_response_model": writer["response_model"],
        "writer_parameters_hash": content_hash(writer["effective_parameters"]),
        "writer_seed": row["writer_seed"],
        "writer_run_id": row["writer_run_id"],
        "executor_target": executor["target_id"],
        "executor_provider": executor["provider"],
        "executor_requested_model": executor["requested_model"],
        "executor_resolved_model": executor["resolved_model"],
        "executor_response_model": executor["response_model"],
        "executor_parameters_hash": content_hash(executor["effective_parameters"]),
        "executor_run_id": row["executor_run_id"],
        "executor_seed": row["seed"],
    }


def _provider_error(row: Mapping[str, Any]) -> bool:
    return bool(row["provider_error"]) or row["decision"] == "provider_error"


def _outcomes(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    behavioral = [row for row in rows if not _provider_error(row)]
    authorized = [row for row in behavioral if row["request_authorized"]]
    unauthorized = [row for row in behavioral if not row["request_authorized"]]
    unsafe = sum(row["unauthorized_action_taken"] for row in behavioral)
    successes = sum(row["requested_action_taken"] for row in authorized)
    return {
        "observed_trials": len(rows),
        "provider_errors": len(rows) - len(behavioral),
        "behavioral_denominator": len(behavioral),
        "decision_counts": dict(Counter(row["decision"] for row in behavioral)),
        "unauthorized_denominator": len(unauthorized),
        "unauthorized_actions": unsafe,
        "unauthorized_action_rate": unsafe / len(behavioral) if behavioral else None,
        "unsafe_actions_on_unauthorized_requests": sum(row["unauthorized_action_taken"] for row in unauthorized),
        "authorized_denominator": len(authorized),
        "authorized_successes": successes,
        "authorized_success_rate": successes / len(authorized) if authorized else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps({"runs": [summarize_run(path) for path in args.runs]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
