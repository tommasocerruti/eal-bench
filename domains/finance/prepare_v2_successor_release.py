"""Freeze the Finance v2 frontier-successor claim surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).parent
RELEASE_PATH = PACKAGE_DIR / "release_v2_successor.json"
CORPUS_VERSION = "benchmark_v2"
RELEASE_ID = "finance_v2_frontier_successor_v1"


def build_release(domain: Any) -> dict[str, Any]:
    from experiments.authorization_memory.langmem_writer import memory_implementation_manifest
    from experiments.authorization_memory.persistence import content_hash, file_hash

    cases = domain.corpus.load_cases(CORPUS_VERSION)
    provenance = domain.corpus.provenance(CORPUS_VERSION)
    implementation = memory_implementation_manifest(domain)
    run_plan_path = PACKAGE_DIR / "v2_successor_run_plan.json"
    run_plan = json.loads(run_plan_path.read_text(encoding="utf-8"))
    pricing_path = PACKAGE_DIR / run_plan["pricing_estimate"]["artifact"]
    results_root = PACKAGE_DIR.parents[1] / "results" / "finance"
    controls_report_path = results_root / "finance_v2_successor__controls_report.json"
    matrix_estimate_path = PACKAGE_DIR / "v2_successor_matrix_estimate.json"
    result_artifacts = {}
    if controls_report_path.is_file():
        result_artifacts["controls_report"] = {
            "path": "../../results/finance/finance_v2_successor__controls_report.json",
            "sha256": file_hash(controls_report_path),
        }
    if matrix_estimate_path.is_file():
        result_artifacts["matrix_estimate"] = {
            "path": "v2_successor_matrix_estimate.json",
            "sha256": file_hash(matrix_estimate_path),
        }
    return {
        "schema_version": "finance_v2_frontier_successor_release_v1",
        "release_id": RELEASE_ID,
        "domain_id": "finance",
        "maturity": "core",
        "freeze_status": "claim_frozen",
        "frozen_on": "2026-08-15",
        "relationship_to_prior_release": {
            "release_id": "finance_v2",
            "manifest": "release_v2.json",
            "manifest_sha256": file_hash(PACKAGE_DIR / "release_v2.json"),
            "original_robustness_gate": "failed",
            "original_result_preserved": True,
            "successor_is_not_retroactive_gate_passage": True,
        },
        "claim_corpus": {
            "corpus_version": CORPUS_VERSION,
            "mechanism": "equal_cardinality",
            "source_release_id": provenance["release_id"],
            "sha256": provenance["source_sha256"],
            "case_count": len(cases),
            "family_count": len({case.family for case in cases}),
            "ordinary_authorized_trials_per_writer_executor_pair": len(cases) * 16,
            "ordinary_unauthorized_trials_per_writer_executor_pair": len(cases) * 16,
            "held_out_during_finance_v2_development": True,
            "freeze_status": "claim_frozen",
        },
        "capacity": {
            "corpus_version": "calibration_v1",
            "artifact": "capacity_calibration.json",
            "sha256": file_hash(PACKAGE_DIR / "capacity_calibration.json"),
            "primary_tokens": 5860,
            "policy": "reuse_frozen_v1_2x_primary_capacity",
            "freeze_status": "frozen_unchanged",
        },
        "blueprint": {
            "source": "v2_blueprint.json",
            "sha256": file_hash(PACKAGE_DIR / "v2_blueprint.json"),
            "held_out_families_reserved_before_development": True,
            "freeze_status": "frozen",
        },
        "presentation": {
            "presentation_id": "naturalistic_v2",
            "source": "presentations/naturalistic_v2.json",
            "sha256": file_hash(PACKAGE_DIR / "presentations/naturalistic_v2.json"),
            "freeze_status": "frozen_unchanged",
        },
        "pressure_profile": {
            "profile_id": "loss_containment_frontier_v1",
            "source": "pressure_profiles/loss_containment_frontier_v1.json",
            "sha256": file_hash(
                PACKAGE_DIR / "pressure_profiles/loss_containment_frontier_v1.json"
            ),
            "analysis_status": "prospective_for_successor_post_hoc_relative_to_finance_v2",
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
            "source": "v2_successor_analysis_plan.json",
            "sha256": file_hash(PACKAGE_DIR / "v2_successor_analysis_plan.json"),
            "freeze_status": "frozen",
        },
        "run_plan": {
            "source": "v2_successor_run_plan.json",
            "sha256": file_hash(run_plan_path),
            "freeze_status": "frozen",
            "route_authorizations": run_plan["route_authorizations"],
            "pricing_estimate": {
                "artifact": pricing_path.name,
                "sha256": file_hash(pricing_path),
                "status": "approved",
                "approved_cap_usd": 30.0,
            },
        },
        "review": {
            "status": "approved_with_owner_waiver",
            "owner_approved_on": "2026-08-15",
            "independent_blinded_review": "not_collected_for_successor",
        },
        "results": {
            "status": (
                "controls_passed_matrix_approval_pending"
                if controls_report_path.is_file()
                else "controls_pending"
            ),
            "outcome_based_resampling": False,
            "artifacts": result_artifacts,
        },
    }


def write_release(domain: Any) -> None:
    RELEASE_PATH.write_text(
        json.dumps(build_release(domain), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    from domains import get_domain

    write_release(get_domain("finance"))
