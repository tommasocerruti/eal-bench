from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).parent
RELEASE_PATH = PACKAGE_DIR / "release.json"


def validate_release(domain: Any) -> dict[str, Any]:
    from experiments.authorization_memory.langmem_writer import (
        memory_implementation_manifest,
    )
    from experiments.authorization_memory.persistence import content_hash, file_hash

    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    if release.get("release_id") != "finance_v1":
        raise ValueError("Finance release identity differs")
    if release.get("freeze_status") != "claim_frozen":
        raise ValueError("Finance final corpus is not frozen")

    corpus = release["claim_corpus"]
    provenance = domain.corpus.provenance("benchmark_v1")
    if corpus.get("corpus_version") != "benchmark_v1":
        raise ValueError("Finance benchmark identity differs")
    if corpus.get("sha256") != provenance["source_sha256"]:
        raise ValueError("Finance benchmark source hash differs")
    cases = domain.corpus.load_cases("benchmark_v1")
    if corpus.get("case_count") != len(cases):
        raise ValueError("Finance benchmark case count differs")
    if corpus.get("ordinary_authorized_trials_per_pair") != len(cases) * 16:
        raise ValueError("Finance authorized trial count differs")
    if corpus.get("ordinary_unauthorized_trials_per_pair") != len(cases) * 16:
        raise ValueError("Finance unauthorized trial count differs")

    hashed_files = {
        "capacity": ("artifact", "sha256"),
        "presentation": ("source", "sha256"),
        "pressure_profile": ("source", "sha256"),
        "analysis_plan": ("source", "sha256"),
    }
    for section, (path_key, hash_key) in hashed_files.items():
        entry = release[section]
        if file_hash(PACKAGE_DIR / entry[path_key]) != entry[hash_key]:
            raise ValueError(f"Finance {section} hash differs")
    pricing = release["run_plan"]["pricing_estimate"]
    if file_hash(PACKAGE_DIR / pricing["artifact"]) != pricing["sha256"]:
        raise ValueError("Finance pricing estimate hash differs")
    run_plan = release["run_plan"]
    if file_hash(PACKAGE_DIR / run_plan["source"]) != run_plan["sha256"]:
        raise ValueError("Finance run plan hash differs")
    equivalence = release["results"]["source_cleanup_equivalence"]
    if file_hash(PACKAGE_DIR / equivalence["path"]) != equivalence["sha256"]:
        raise ValueError("Finance source-cleanup equivalence hash differs")

    implementation = memory_implementation_manifest(domain)
    memory = release["memory"]
    if memory.get("implementation_sha256") != implementation["memory_implementation_hash"]:
        raise ValueError("Finance memory implementation hash differs")
    if memory.get("typed_schema_sha256") != content_hash(domain.memory.typed_schema()):
        raise ValueError("Finance typed schema hash differs")
    return {
        "status": "passed",
        "release_id": release["release_id"],
        "case_count": len(cases),
        "paid_execution_authorized": corpus["paid_execution_authorized"],
        "eligible_to_merge": release["results"]["eligible_to_merge"],
    }
