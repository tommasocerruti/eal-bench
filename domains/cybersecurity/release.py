from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.authorization_memory.langmem_writer import framework_manifest
from experiments.authorization_memory.persistence import content_hash, file_hash


PACKAGE_DIR = Path(__file__).parent
RELEASE_PATH = PACKAGE_DIR / "release.json"


def validate_release(domain: Any) -> dict[str, Any]:
    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    if (
        release.get("schema_version") != "final_v1"
        or release.get("release_id") != "cybersecurity_v1"
        or release.get("domain_id") != domain.domain_id
        or release.get("maturity") != domain.maturity
        or release.get("freeze_status") != "claim_frozen"
        or int(release.get("canonical_seed", -1)) != domain.canonical_seed
    ):
        raise ValueError("Cybersecurity release identity differs")

    hashed = (
        (release["capacity"], "artifact"),
        (release["presentation"], "source"),
        (release["pressure_profile"], "source"),
        (release["analysis_plan"], "source"),
        (release["run_plan"], "source"),
        (release["review"], "manifest"),
        (release["run_plan"]["pricing_estimate"], "artifact"),
    )
    for entry, path_key in hashed:
        path = PACKAGE_DIR / entry[path_key]
        if file_hash(path) != entry["sha256"]:
            raise ValueError(f"Cybersecurity release hash differs for {path.name}")

    source_hashes = {
        str(path.relative_to(PACKAGE_DIR)): file_hash(path)
        for path in domain.corpus.source_files("benchmark_v1")
    }
    claim = release["claim_corpus"]
    if (
        claim.get("corpus_version") != "benchmark_v1"
        or claim.get("case_count") != 16
        or claim.get("family_count") != 16
        or claim.get("authorization_decisions") != 128
        or claim.get("attractiveness_rankings") != 64
        or claim.get("source_files") != source_hashes
        or claim.get("sha256") != content_hash(source_hashes)
        or claim.get("freeze_status") != "frozen"
        or claim.get("paid_execution_authorized") is not True
    ):
        raise ValueError("Cybersecurity claim corpus differs")

    if content_hash(domain.memory.typed_schema()) != release["memory"]["typed_schema_sha256"]:
        raise ValueError("Cybersecurity typed schema differs")
    implementation = framework_manifest(domain)
    if implementation["memory_implementation_hash"] != release["memory"]["implementation_sha256"]:
        raise ValueError("Cybersecurity memory implementation differs")
    for filename, expected in release["implementation"].items():
        if file_hash(PACKAGE_DIR / filename) != expected:
            raise ValueError(f"Cybersecurity implementation hash differs for {filename}")
    if (
        release["review"].get("status") != "approved_with_owner_waiver"
        or release["run_plan"]["pricing_estimate"].get("status") != "approved"
        or float(release["run_plan"]["pricing_estimate"].get("approved_cap_usd", 0)) != 12.0
    ):
        raise ValueError("Cybersecurity approval gate differs")

    results = release.get("results")
    if results is not None:
        if (
            results.get("status") != "completed_official_pass_aggressive_miss"
            or results.get("eligible_to_merge") is not True
            or results.get("outcome_based_resampling") is not False
        ):
            raise ValueError("Cybersecurity completed-results status differs")
        for entry in (
            results["bundle"],
            *results["run_manifests"].values(),
            *results["reports"].values(),
        ):
            path = (PACKAGE_DIR / entry["path"]).resolve()
            if file_hash(path) != entry["sha256"]:
                raise ValueError(f"Cybersecurity result hash differs for {path.name}")

    return {
        "status": "passed",
        "release_id": release["release_id"],
        "maturity": release["maturity"],
        "freeze_status": release["freeze_status"],
        "review_status": release["review"]["status"],
        "claim_corpus_status": claim["status"],
        "pricing_status": release["run_plan"]["pricing_estimate"]["status"],
        "results_status": results["status"] if results else "not_attached",
        "manifest_sha256": file_hash(RELEASE_PATH),
    }


def validate_review(domain: Any) -> dict[str, Any]:
    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    review_path = PACKAGE_DIR / release["review"]["manifest"]
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if (
        review.get("schema_version") != "final_v1"
        or review.get("domain_id") != domain.domain_id
        or review.get("corpus_version") != "benchmark_v1"
        or review.get("presentation_id") != "naturalistic_v1"
        or review.get("review_status") != "approved_with_owner_waiver"
        or review.get("maintainer_approval", {}).get("approved") is not True
    ):
        raise ValueError("Cybersecurity review identity differs")
    for section, expected in (("authorization_review", 128), ("attractiveness_review", 64)):
        entry = review[section]
        packet = PACKAGE_DIR / "reviews" / entry["packet"]
        count = entry.get("decisions_expected", entry.get("items_expected", -1))
        if (
            file_hash(packet) != entry["packet_sha256"]
            or entry.get("status") != "approved_with_owner_waiver"
            or int(count) != expected
        ):
            raise ValueError(f"Cybersecurity {section} differs")
    mapping_path = PACKAGE_DIR / "reviews" / review["private_mapping"]["path"]
    if file_hash(mapping_path) != review["private_mapping"]["sha256"]:
        raise ValueError("Cybersecurity private review mapping differs")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if len(mapping.get("authorization", {})) != 128 or len(mapping.get("attractiveness", {})) != 64:
        raise ValueError("Cybersecurity private review coverage differs")
    expected_lineage = {
        "corpus_sha256": release["claim_corpus"]["sha256"],
        "presentation_sha256": release["presentation"]["sha256"],
        "typed_schema_sha256": content_hash(domain.memory.typed_schema()),
    }
    if review.get("source_lineage") != expected_lineage:
        raise ValueError("Cybersecurity review lineage differs")
    return {
        "status": "passed",
        "review_status": review["review_status"],
        "complete": True,
        "authorization": {"complete": True, "decisions": 128},
        "attractiveness": {"complete": True, "rankings": 64},
        "maintainer_approval": review["maintainer_approval"],
    }
