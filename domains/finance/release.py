from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).parent
V1_RELEASE_PATH = PACKAGE_DIR / "release.json"
V2_RELEASE_PATH = PACKAGE_DIR / "release_v2.json"


def validate_release(domain: Any, corpus_version: str = "benchmark_v1") -> dict[str, Any]:
    if corpus_version.endswith("_v1"):
        return _validate_v1_release(domain)
    return _validate_v2_release(domain, corpus_version)


def _validate_v1_release(domain: Any) -> dict[str, Any]:
    from experiments.authorization_memory.persistence import content_hash, file_hash

    release = json.loads(V1_RELEASE_PATH.read_text(encoding="utf-8"))
    if release.get("release_id") != "finance_v1":
        raise ValueError("Finance v1 release identity differs")
    if release.get("freeze_status") != "claim_frozen":
        raise ValueError("Finance v1 final corpus is not frozen")

    corpus = release["claim_corpus"]
    cases = domain.corpus.load_cases("benchmark_v1")
    if corpus.get("corpus_version") != "benchmark_v1":
        raise ValueError("Finance v1 benchmark identity differs")
    if corpus.get("case_count") != len(cases):
        raise ValueError("Finance v1 benchmark case count differs")
    if corpus.get("ordinary_authorized_trials_per_pair") != len(cases) * 16:
        raise ValueError("Finance v1 authorized trial count differs")
    if corpus.get("ordinary_unauthorized_trials_per_pair") != len(cases) * 16:
        raise ValueError("Finance v1 unauthorized trial count differs")

    capacity = json.loads(
        (PACKAGE_DIR / release["capacity"]["artifact"]).read_text(encoding="utf-8")
    )
    archived_sources = capacity["compatibility"]["benchmark_v1"]["source_files"]
    data_key = "data/benchmark_v1.json"
    if file_hash(PACKAGE_DIR / data_key) != archived_sources[data_key]:
        raise ValueError("Finance v1 frozen benchmark data differs")
    if file_hash(PACKAGE_DIR / release["capacity"]["artifact"]) != release["capacity"]["sha256"]:
        raise ValueError("Finance v1 capacity artifact differs")

    hashed_files = {
        "presentation": ("source", "sha256"),
        "pressure_profile": ("source", "sha256"),
        "analysis_plan": ("source", "sha256"),
    }
    for section, (path_key, hash_key) in hashed_files.items():
        entry = release[section]
        if file_hash(PACKAGE_DIR / entry[path_key]) != entry[hash_key]:
            raise ValueError(f"Finance v1 {section} hash differs")
    pricing = release["run_plan"]["pricing_estimate"]
    if file_hash(PACKAGE_DIR / pricing["artifact"]) != pricing["sha256"]:
        raise ValueError("Finance v1 pricing estimate hash differs")
    run_plan = release["run_plan"]
    if file_hash(PACKAGE_DIR / run_plan["source"]) != run_plan["sha256"]:
        raise ValueError("Finance v1 run plan hash differs")
    equivalence = release["results"]["source_cleanup_equivalence"]
    if file_hash(PACKAGE_DIR / equivalence["path"]) != equivalence["sha256"]:
        raise ValueError("Finance v1 source-cleanup equivalence hash differs")
    if release["memory"].get("typed_schema_sha256") != content_hash(domain.memory.typed_schema()):
        raise ValueError("Finance v1 typed schema differs")
    return {
        "status": "passed",
        "release_id": release["release_id"],
        "case_count": len(cases),
        "historical_implementation_hash": release["memory"]["implementation_sha256"],
        "paid_execution_authorized": corpus["paid_execution_authorized"],
        "eligible_to_merge": release["results"]["eligible_to_merge"],
    }


def _validate_v2_release(domain: Any, corpus_version: str) -> dict[str, Any]:
    from experiments.authorization_memory.langmem_writer import memory_implementation_manifest
    from experiments.authorization_memory.persistence import content_hash, file_hash

    if not V2_RELEASE_PATH.is_file():
        raise ValueError("Finance v2 release has not been frozen")
    release = json.loads(V2_RELEASE_PATH.read_text(encoding="utf-8"))
    if release.get("release_id") != "finance_v2":
        raise ValueError("Finance v2 release identity differs")
    if release.get("freeze_status") not in {"development_frozen", "claim_frozen"}:
        raise ValueError("Finance v2 release is not frozen")
    corpora = release.get("corpora", {})
    if corpus_version not in corpora:
        raise ValueError(f"{corpus_version}: corpus is not part of the Finance v2 release")
    for version, entry in corpora.items():
        cases = domain.corpus.load_cases(version)
        provenance = domain.corpus.provenance(version)
        if entry.get("sha256") != provenance["source_sha256"]:
            raise ValueError(f"{version}: Finance v2 source hash differs")
        if entry.get("case_count") != len(cases):
            raise ValueError(f"{version}: Finance v2 case count differs")

    expected_files = {
        "capacity": ("artifact", "sha256"),
        "blueprint": ("source", "sha256"),
        "presentation": ("source", "sha256"),
        "pressure_profile": ("source", "sha256"),
        "analysis_plan": ("source", "sha256"),
        "run_plan": ("source", "sha256"),
        "pricing_estimate": ("artifact", "sha256"),
    }
    for section, (path_key, hash_key) in expected_files.items():
        entry = release[section]
        if file_hash(PACKAGE_DIR / entry[path_key]) != entry[hash_key]:
            raise ValueError(f"Finance v2 {section} hash differs")
    for name, artifact in release.get("results", {}).get("artifacts", {}).items():
        if file_hash(PACKAGE_DIR / artifact["path"]) != artifact["sha256"]:
            raise ValueError(f"Finance v2 {name} result hash differs")
    implementation = memory_implementation_manifest(domain)
    if release["memory"].get("implementation_sha256") != implementation["memory_implementation_hash"]:
        raise ValueError("Finance v2 memory implementation hash differs")
    if release["memory"].get("typed_schema_sha256") != content_hash(domain.memory.typed_schema()):
        raise ValueError("Finance v2 typed schema hash differs")
    selected = corpora[corpus_version]
    return {
        "status": "passed",
        "release_id": "finance_v2",
        "freeze_status": release["freeze_status"],
        "corpus_version": corpus_version,
        "case_count": selected["case_count"],
        "paid_execution_authorized": release["run_authorization"]["development_paid_calls"],
        "approved_cap_usd": release["run_authorization"]["approved_cap_usd"],
    }
