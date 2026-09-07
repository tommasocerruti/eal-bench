from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.authorization_memory.langmem_writer import memory_implementation_manifest
from experiments.authorization_memory.persistence import content_hash, file_hash


PACKAGE_DIR = Path(__file__).parent
RELEASE_PATH = PACKAGE_DIR / "release.json"
RELEASE_ID = "finance_redesign_v1"
EVALUATION_SEEDS = [20260816, 20260821, 20260822]


def validate_release(domain: Any, corpus_version: str = "benchmark_v1") -> dict[str, Any]:
    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    if (
        release.get("schema_version") != "finance_redesign_release_v1"
        or release.get("release_id") != RELEASE_ID
        or release.get("domain_id") != domain.domain_id
        or release.get("maturity") != domain.maturity
        or release.get("freeze_status") != "claim_frozen"
        or release.get("evaluation_seeds") != EVALUATION_SEEDS
        or int(release.get("canonical_seed", -1)) != domain.canonical_seed
    ):
        raise ValueError("Finance redesign release identity differs")
    if corpus_version not in domain.corpus.versions:
        raise ValueError(f"unsupported Finance redesign release corpus: {corpus_version!r}")

    hashed = (
        (release["capacity"], "artifact"),
        (release["presentation"], "source"),
        (release["pressure_profile"], "source"),
        (release["analysis_plan"], "source"),
        (release["run_plan"], "source"),
        (release["run_plan"]["pricing_estimate"], "artifact"),
        (release["final_precommit"], "path"),
        (release["offline_validation"], "report"),
        (release["legacy_archive"], "manifest"),
    )
    for entry, path_key in hashed:
        path = PACKAGE_DIR / entry[path_key]
        if file_hash(path) != entry["sha256"]:
            raise ValueError(f"Finance redesign release hash differs for {path.name}")

    provenance = domain.corpus.provenance("benchmark_v1")
    cases = domain.corpus.load_cases("benchmark_v1")
    claim = release["claim_corpus"]
    if (
        claim.get("corpus_version") != "benchmark_v1"
        or claim.get("case_count") != len(cases)
        or claim.get("family_count") != len({case.family for case in cases})
        or claim.get("authorization_decisions") != sum(len(case.probes) for case in cases)
        or claim.get("source_files") != provenance["source_files"]
        or claim.get("sha256") != provenance["source_sha256"]
        or claim.get("freeze_status") != "frozen"
        or claim.get("paid_execution_authorized") is not True
        or claim.get("development_iteration") != "finance_redesign_dev_014"
    ):
        raise ValueError("Finance redesign claim corpus differs")

    memory = memory_implementation_manifest(domain)
    if memory["memory_implementation_hash"] != release["memory"]["implementation_sha256"]:
        raise ValueError("Finance redesign memory implementation differs")
    if content_hash(domain.memory.typed_schema()) != release["memory"]["typed_schema_sha256"]:
        raise ValueError("Finance redesign typed schema differs")
    for filename, expected in release["implementation"].items():
        if file_hash(PACKAGE_DIR / filename) != expected:
            raise ValueError(f"Finance redesign implementation hash differs for {filename}")

    review = release["review"]
    pricing = release["run_plan"]["pricing_estimate"]
    if (
        review.get("status") != "approved"
        or pricing.get("status") != "approved"
        or float(pricing.get("approved_complete_project_ceiling_usd", 0)) != 300
        or release["run_plan"].get("route_authorizations")
        != {"controls": True, "writer": True, "pressure": True, "witness_replay": False}
    ):
        raise ValueError("Finance redesign execution approval differs")

    results = release.get("results", {})
    if results.get("status") not in {
        "held_out_evaluation_pending",
        "completed_held_out_evaluation",
    }:
        raise ValueError("Finance redesign result lifecycle differs")
    if results.get("status") == "completed_held_out_evaluation":
        if (
            results.get("outcome_based_resampling") is not False
            or results.get("complete_artifact_audit") is not True
        ):
            raise ValueError("Finance redesign completed-result contract differs")
        for entry in (*results.get("reports", {}).values(), *results.get("run_manifests", {}).values()):
            path = (PACKAGE_DIR / entry["path"]).resolve()
            if file_hash(path) != entry["sha256"]:
                raise ValueError(f"Finance redesign result hash differs for {path.name}")

    return {
        "status": "passed",
        "release_id": release["release_id"],
        "maturity": release["maturity"],
        "freeze_status": release["freeze_status"],
        "corpus_version": corpus_version,
        "case_count": len(domain.corpus.load_cases(corpus_version)),
        "review_status": review["status"],
        "pricing_status": pricing["status"],
        "results_status": results["status"],
        "manifest_sha256": file_hash(RELEASE_PATH),
        "legacy_archive_active": False,
    }
