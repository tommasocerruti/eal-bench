"""Freeze the public Finance v1 release and completed transfer results."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).parent
RELEASE_PATH = PACKAGE_DIR / "release.json"
RESULTS_ROOT = PACKAGE_DIR.parents[1] / "results" / "finance"
EQUIVALENCE_PATH = RESULTS_ROOT / "finance_v1__release_equivalence.json"
RELEASE_ID = "finance_v1"
CORPUS_VERSION = "benchmark_v1"


def build_release(domain: Any) -> dict[str, Any]:
    from experiments.authorization_memory.langmem_writer import memory_implementation_manifest
    from experiments.authorization_memory.persistence import content_hash, file_hash

    cases = domain.corpus.load_cases(CORPUS_VERSION)
    provenance = domain.corpus.provenance(CORPUS_VERSION)
    implementation = memory_implementation_manifest(domain)
    run_plan_path = PACKAGE_DIR / "run_plan.json"
    pricing_path = PACKAGE_DIR / "pre_run_cost_estimate.json"
    run_plan = _object(run_plan_path)
    pricing = _object(pricing_path)
    index = _object(RESULTS_ROOT / "finance_v1__matrix_run_index.json")
    _write_equivalence(domain)

    reports = {}
    for name in (
        "controls_report",
        "matrix_run_index",
        "matrix_report",
        "matrix_results.md",
        "actual_cost",
        "provider_failures",
        "route_summaries",
        "transfer_agreement",
        "condition_results",
        "witness_repair_report",
        "mechanism_extension",
        "release_equivalence",
        "acceptance",
    ):
        filename = f"finance_v1__{name}"
        if "." not in name:
            filename += ".json"
        path = RESULTS_ROOT / filename
        reports[name.replace(".md", "")] = {
            "path": os.path.relpath(path, PACKAGE_DIR),
            "sha256": file_hash(path),
        }

    run_manifests = {}
    controls = _object(RESULTS_ROOT / "finance_v1__controls_report.json")["isolation_gate"]
    run_manifests["controls_gptoss"] = _manifest_entry(
        controls["gptoss_baseten"]["run"], file_hash
    )
    run_manifests["controls_deepseek_initial"] = _manifest_entry(
        controls["deepseek_baseten"]["source_run"], file_hash
    )
    run_manifests["controls_deepseek_final"] = _manifest_entry(
        controls["deepseek_baseten"]["final_run"], file_hash
    )
    for writer, entry in index["writers_in_frozen_order"].items():
        label = writer.removesuffix("_baseten").removesuffix("_openrouter")
        run_manifests[f"{label}_writer"] = _manifest_entry(entry["writer_run"], file_hash)
        run_manifests[f"{label}_pressure"] = _manifest_entry(entry["pressure_run"], file_hash)
        if entry["pressure_network_source_run"] != entry["pressure_run"]:
            run_manifests[f"{label}_pressure_initial"] = _manifest_entry(
                entry["pressure_network_source_run"], file_hash
            )

    implementation_files = (
        "adapter.py",
        "capacity.py",
        "compile_corpus.py",
        "compile_v2.py",
        "corpus.py",
        "corpus_v2.py",
        "finalize_results.py",
        "models.py",
        "pressure.py",
        "release.py",
        "semantics.py",
        "studies.py",
    )
    return {
        "schema_version": "final_v1",
        "release_id": RELEASE_ID,
        "domain_id": "finance",
        "maturity": "core",
        "freeze_status": "claim_frozen",
        "canonical_seed": domain.canonical_seed,
        "capacity": {
            "corpus_version": "calibration_v1",
            "artifact": "capacity_calibration.json",
            "sha256": file_hash(PACKAGE_DIR / "capacity_calibration.json"),
            "primary_tokens": 5860,
            "primary_policy": "2x_largest_faithful_payload_at_any_checkpoint",
            "freeze_status": "frozen",
        },
        "claim_corpus": {
            "corpus_version": CORPUS_VERSION,
            "status": "completed",
            "source_files": provenance["source_files"],
            "sha256": provenance["source_sha256"],
            "case_count": len(cases),
            "family_count": len({case.family for case in cases}),
            "authorization_decisions": sum(len(case.probes) for case in cases),
            "attractiveness_rankings": 4 * len(cases),
            "ordinary_authorized_trials_per_writer_executor_pair": len(cases) * 16,
            "ordinary_unauthorized_trials_per_writer_executor_pair": len(cases) * 16,
            "freeze_status": "frozen",
            "paid_execution_authorized": True,
        },
        "presentation": {
            "presentation_id": "naturalistic_v1",
            "source": "presentations/naturalistic_v1.json",
            "sha256": file_hash(PACKAGE_DIR / "presentations" / "naturalistic_v1.json"),
            "freeze_status": "frozen",
        },
        "pressure_profile": {
            "profile_id": "loss_containment_v1",
            "source": "pressure_profiles/loss_containment_v1.json",
            "sha256": file_hash(
                PACKAGE_DIR / "pressure_profiles" / "loss_containment_v1.json"
            ),
            "authority_invariant": True,
            "freeze_status": "frozen",
        },
        "memory": {
            "implementation_id": "langmem_profile",
            "implementation_sha256": implementation["memory_implementation_hash"],
            "typed_schema_version": "5",
            "typed_schema_sha256": content_hash(domain.memory.typed_schema()),
            "bounded_attempts": 2,
            "invalid_update_policy": "atomic_retention",
            "target_specific_handling": False,
        },
        "analysis_plan": {
            "source": "analysis_plan.json",
            "sha256": file_hash(PACKAGE_DIR / "analysis_plan.json"),
            "freeze_status": "frozen",
        },
        "implementation": {
            name: file_hash(PACKAGE_DIR / name) for name in implementation_files
        },
        "review": {
            "status": "approved_with_owner_waiver",
            "approved_on": "2026-08-15",
            "independent_blinded_review": "not_collected",
        },
        "run_plan": {
            "source": run_plan_path.name,
            "sha256": file_hash(run_plan_path),
            "status": run_plan["status"],
            "freeze_status": "frozen",
            "route_authorizations": run_plan["route_authorizations"],
            "pricing_estimate": {
                "artifact": pricing_path.name,
                "sha256": file_hash(pricing_path),
                "status": pricing["status"],
                "approved_cap_usd": float(pricing["estimated_cost_usd"]["approved_hard_cap"]),
            },
        },
        "results": {
            "status": "completed_claim_release",
            "eligible_to_merge": True,
            "outcome_based_resampling": False,
            "technical_execution_identifiers_retained": True,
            "reports": reports,
            "run_manifests": run_manifests,
        },
    }


def _write_equivalence(domain: Any) -> None:
    from experiments.authorization_memory.persistence import content_hash, file_hash

    from . import corpus, pressure

    payload = _object(PACKAGE_DIR / "data" / "benchmark_v2.json")
    technical = tuple(corpus._case_from_dict(item) for item in payload["cases"])
    public = domain.corpus.load_cases("benchmark_v1")
    before = _surface_payload(domain, technical)
    after = _surface_payload(domain, public)
    if before != after:
        raise ValueError("Finance public-release alias changes a model-visible surface")
    digest = content_hash(before)
    value = {
        "schema_version": "finance_release_equivalence_v1",
        "release_id": RELEASE_ID,
        "status": "passed",
        "technical_execution_identity": {
            "corpus_version": "benchmark_v2",
            "presentation_version": "naturalistic_v2",
            "pressure_profile": "loss_containment_frontier_v1",
            "source_sha256": file_hash(PACKAGE_DIR / "data" / "benchmark_v2.json"),
        },
        "public_release_identity": {
            "corpus_version": "benchmark_v1",
            "presentation_version": "naturalistic_v1",
            "pressure_profile": pressure.PROFILE_ID,
        },
        "model_surface_equivalence": {
            "status": "byte_identical",
            "combined_sha256_before": digest,
            "combined_sha256_after": content_hash(after),
            "components": [
                "rendered full histories",
                "rendered incremental blocks",
                "faithful free-text memories",
                "faithful typed memories",
                "serialized probe requests",
                "baseline pressure additions",
                "loss-containment pressure additions",
                "organization and portfolio labels",
            ],
        },
        "non_surface_changes": [
            "public release ID",
            "public corpus and presentation IDs",
            "source layout and provenance hashes",
        ],
        "paid_result_applicability": "preserved",
    }
    EQUIVALENCE_PATH.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _surface_payload(domain: Any, cases: tuple[Any, ...]) -> list[dict[str, Any]]:
    from experiments.authorization_memory.persistence import canonical_json

    from . import pressure

    rows = []
    for case in cases:
        checkpoints = tuple(case.metadata["authorization_changing_blocks"])
        rows.append(
            {
                "case_id": case.case_id,
                "history": domain.corpus.render_full_history(case, None),
                "blocks": [domain.corpus.render_block(block, None) for block in case.blocks],
                "faithful_text": [
                    domain.memory.faithful_free_text(case, block) for block in checkpoints
                ],
                "faithful_typed": [
                    canonical_json(domain.memory.faithful_typed(case, block))
                    for block in checkpoints
                ],
                "requests": [
                    canonical_json(probe.request.to_dict()) for probe in case.probes
                ],
                "baseline_pressure": case.pressure_addition,
                "loss_containment_pressure": pressure.addition(case),
                "organization": case.organization,
                "portfolio": case.portfolio_name,
            }
        )
    return rows


def _manifest_entry(run: str, file_hash: Any) -> dict[str, Any]:
    path = RESULTS_ROOT / run / "manifest.json"
    return {
        "path": os.path.relpath(path, PACKAGE_DIR),
        "sha256": file_hash(path),
    }


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected JSON object")
    return value


def write_release(domain: Any) -> None:
    RELEASE_PATH.write_text(
        json.dumps(build_release(domain), indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    from domains import get_domain

    write_release(get_domain("finance"))
