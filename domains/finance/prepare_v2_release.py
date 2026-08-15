"""Freeze the exact Finance v2 development release manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).parent
RELEASE_PATH = PACKAGE_DIR / "release_v2.json"
SCREEN_VERSIONS = (
    "difficulty_dev_v2_compact",
    "difficulty_dev_v2_equal_cardinality",
    "difficulty_dev_v2_distributed",
)
PROMOTED_VERSION = "difficulty_dev_v2"
RUNNER_UP_VERSION = "difficulty_dev_v2_runner_up"
HELD_OUT_VERSION = "benchmark_v2"


def build_release(domain: Any) -> dict[str, Any]:
    from experiments.authorization_memory.langmem_writer import memory_implementation_manifest
    from experiments.authorization_memory.persistence import content_hash, file_hash

    corpora = {}
    versions = [*SCREEN_VERSIONS]
    for optional in (PROMOTED_VERSION, RUNNER_UP_VERSION, HELD_OUT_VERSION):
        if (PACKAGE_DIR / "data" / f"{optional}.json").is_file():
            versions.append(optional)
    for version in versions:
        cases = domain.corpus.load_cases(version)
        provenance = domain.corpus.provenance(version)
        corpora[version] = {
            "mechanism": str(cases[0].metadata["mechanism_variant"]),
            "sha256": provenance["source_sha256"],
            "case_count": len(cases),
            "family_count": len({case.family for case in cases}),
            "ordinary_authorized_trials_per_pair": len(cases) * 16,
            "ordinary_unauthorized_trials_per_pair": len(cases) * 16,
            "freeze_status": (
                "claim_frozen" if version == HELD_OUT_VERSION else "development_frozen"
            ),
        }
    implementation = memory_implementation_manifest(domain)
    results_root = PACKAGE_DIR.parents[1] / "results" / "finance"
    screen_report_path = results_root / "finance_v2__screen_report.json"
    screen_report = (
        json.loads(screen_report_path.read_text(encoding="utf-8"))
        if screen_report_path.is_file()
        else None
    )
    selected_mechanism = (
        str(screen_report["selected_mechanism"]) if screen_report is not None else None
    )
    rehearsal_report_path = results_root / "finance_v2__rehearsal_report.json"
    rehearsal_report = (
        json.loads(rehearsal_report_path.read_text(encoding="utf-8"))
        if rehearsal_report_path.is_file()
        else None
    )
    result_artifact_names = (
        "screen_report",
        "rehearsal_report",
        "route_summaries",
        "checkpoint_fidelity",
        "witness_repair_report",
        "typed_attribution_report",
        "provider_failures",
        "stability_table",
        "mechanism_report",
        "actual_cost",
    )
    result_artifacts = {}
    for name in result_artifact_names:
        path = results_root / f"finance_v2__{name}.json"
        if path.is_file():
            result_artifacts[name] = {
                "path": f"../../results/finance/{path.name}",
                "sha256": file_hash(path),
            }
    return {
        "schema_version": "finance_v2_development_release_v1",
        "release_id": "finance_v2",
        "domain_id": "finance",
        "maturity": "development",
        "freeze_status": "development_frozen",
        "frozen_on": "2026-08-15",
        "corpora": corpora,
        "reserved_corpora": {
            "promoted_development": "difficulty_dev_v2",
            "held_out_claim": "benchmark_v2",
            "held_out_blueprint_frozen": True,
            "held_out_instantiation_requires_robustness_gate": True,
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
            "freeze_status": "frozen",
        },
        "presentation": {
            "presentation_id": "naturalistic_v2",
            "source": "presentations/naturalistic_v2.json",
            "sha256": file_hash(PACKAGE_DIR / "presentations/naturalistic_v2.json"),
            "freeze_status": "frozen",
        },
        "pressure_profile": {
            "profile_id": "loss_containment_v2",
            "source": "pressure_profiles/loss_containment_v2.json",
            "sha256": file_hash(PACKAGE_DIR / "pressure_profiles/loss_containment_v2.json"),
            "authority_invariant": True,
            "freeze_status": "frozen",
        },
        "memory": {
            "implementation_id": "langmem_profile",
            "implementation_sha256": implementation["memory_implementation_hash"],
            "typed_schema_version": "5",
            "typed_schema_sha256": content_hash(domain.memory.typed_schema()),
            "typed_representation": "flat_scalar_authorization_records",
            "bounded_attempts": 2,
            "invalid_update_policy": "atomic_retention",
            "target_specific_handling": False,
        },
        "analysis_plan": {
            "source": "v2_analysis_plan.json",
            "sha256": file_hash(PACKAGE_DIR / "v2_analysis_plan.json"),
            "freeze_status": "frozen",
        },
        "run_plan": {
            "source": "v2_run_plan.json",
            "sha256": file_hash(PACKAGE_DIR / "v2_run_plan.json"),
            "freeze_status": "frozen",
        },
        "pricing_estimate": {
            "artifact": "v2_pre_run_cost_estimate.json",
            "sha256": file_hash(PACKAGE_DIR / "v2_pre_run_cost_estimate.json"),
            "status": "approved",
        },
        "run_authorization": {
            "development_paid_calls": True,
            "approved_cap_usd": 40.0,
            "deepseek_or_full_matrix": False,
        },
        "selection": {
            "screen_seed": 20260813,
            "status": (
                "winner_and_contingent_runner_up_rehearsals_completed"
                if rehearsal_report is not None
                else "selected_for_two_seed_rehearsal"
                if selected_mechanism is not None
                else "pending_preregistered_screens"
            ),
            "selected_mechanism": selected_mechanism,
            "contingent_runner_up": "compact" if rehearsal_report is not None else None,
            "selection_uses_executor_outcomes": True,
            "witness_selection_uses_executor_outcomes": False,
        },
        "review": {
            "development_screens": "not_required_by_preregistered_plan",
            "held_out_authorization_decisions": 64,
            "held_out_attractiveness_rankings": 32,
            "held_out_status": (
                "not_started_robustness_gate_failed"
                if rehearsal_report is not None
                and rehearsal_report["status"] == "robustness_failed_stop_before_held_out"
                else "gated_on_robustness"
            ),
        },
        "results": {
            "status": (
                str(rehearsal_report["status"])
                if rehearsal_report is not None
                else "screens_completed_winner_selected"
                if screen_report is not None
                else "not_run"
            ),
            "artifacts": result_artifacts,
            "outcome_based_resampling": False,
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
