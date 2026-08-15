from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.authorization_memory.langmem_writer import memory_implementation_manifest
from experiments.authorization_memory.persistence import content_hash, file_hash


PACKAGE_DIR = Path(__file__).parent
RELEASE_PATH = PACKAGE_DIR / "release.json"


def validate_release(domain: Any, corpus_version: str = "benchmark_v1") -> dict[str, Any]:
    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    if (
        release.get("schema_version") != "final_v1"
        or release.get("release_id") != "finance_v1"
        or release.get("domain_id") != domain.domain_id
        or release.get("maturity") != domain.maturity
        or release.get("freeze_status") != "claim_frozen"
        or int(release.get("canonical_seed", -1)) != domain.canonical_seed
    ):
        raise ValueError("Finance release identity differs")
    if corpus_version not in {"calibration_v1", "benchmark_v1"}:
        raise ValueError(f"unsupported Finance release corpus: {corpus_version!r}")

    hashed = (
        (release["capacity"], "artifact"),
        (release["presentation"], "source"),
        (release["pressure_profile"], "source"),
        (release["analysis_plan"], "source"),
        (release["run_plan"], "source"),
        (release["run_plan"]["pricing_estimate"], "artifact"),
    )
    for entry, path_key in hashed:
        path = PACKAGE_DIR / entry[path_key]
        if file_hash(path) != entry["sha256"]:
            raise ValueError(f"Finance release hash differs for {path.name}")

    cases = domain.corpus.load_cases("benchmark_v1")
    provenance = domain.corpus.provenance("benchmark_v1")
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
    ):
        raise ValueError("Finance claim corpus differs")

    implementation = memory_implementation_manifest(domain)
    if implementation["memory_implementation_hash"] != release["memory"][
        "implementation_sha256"
    ]:
        raise ValueError("Finance memory implementation differs")
    if content_hash(domain.memory.typed_schema()) != release["memory"]["typed_schema_sha256"]:
        raise ValueError("Finance typed schema differs")
    for filename, expected in release["implementation"].items():
        if file_hash(PACKAGE_DIR / filename) != expected:
            raise ValueError(f"Finance implementation hash differs for {filename}")

    results = release["results"]
    if (
        results.get("status") != "completed_transfer_matrix_canonical_gate_pending"
        or results.get("eligible_to_merge") is not False
        or results.get("outcome_based_resampling") is not False
    ):
        raise ValueError("Finance result status differs")
    for entry in (*results["reports"].values(), *results["run_manifests"].values()):
        path = (PACKAGE_DIR / entry["path"]).resolve()
        if file_hash(path) != entry["sha256"]:
            raise ValueError(f"Finance result hash differs for {path.name}")

    return {
        "status": "passed",
        "release_id": release["release_id"],
        "maturity": release["maturity"],
        "freeze_status": release["freeze_status"],
        "corpus_version": corpus_version,
        "case_count": len(domain.corpus.load_cases(corpus_version)),
        "review_status": release["review"]["status"],
        "results_status": results["status"],
        "eligible_to_merge": results["eligible_to_merge"],
        "manifest_sha256": file_hash(RELEASE_PATH),
    }
