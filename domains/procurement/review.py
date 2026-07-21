from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .cases import DATA_DIR, current_ledger
from .oracle import evaluate_ledger


PACKAGE_DIR = Path(__file__).parent
BENCHMARK_REVIEW_PATH = PACKAGE_DIR / "reviews" / "benchmark_v1.json"


def review_path() -> Path:
    return BENCHMARK_REVIEW_PATH


def material_paths() -> dict[str, Path]:
    paths = {
        "compiled_corpus_sha256": DATA_DIR / "benchmark_v1.jsonl",
        "naturalistic_presentation_sha256": (
            PACKAGE_DIR / "presentations" / "naturalistic_v1.json"
        ),
        "challenge_module_sha256": PACKAGE_DIR / "challenge.py",
        "challenge_data_sha256": PACKAGE_DIR / "challenge_data.py",
        "presentation_renderer_sha256": PACKAGE_DIR / "presentations.py",
        "prompt_surface_sha256": PACKAGE_DIR / "surface.py",
        "typed_profile_schema_sha256": PACKAGE_DIR / "schemas.py",
        "authorization_review_packet_sha256": (
            PACKAGE_DIR / "reviews" / "benchmark_v1_authorization_blinded.jsonl"
        ),
        "attractiveness_review_packet_sha256": (
            PACKAGE_DIR / "reviews" / "benchmark_v1_attractiveness_blinded.jsonl"
        ),
        "private_review_mapping_sha256": (
            PACKAGE_DIR / "reviews" / "benchmark_v1_private_mapping.json"
        ),
    }
    return paths


def validate_review(
    cases: Sequence[Any],
    *,
    corpus_version: str,
) -> dict[str, Any]:
    if corpus_version != "benchmark_v1":
        raise ValueError(f"unsupported review corpus: {corpus_version!r}")
    selected_path = review_path()
    raw = json.loads(selected_path.read_text(encoding="utf-8"))
    expected_top = {
        "schema_version",
        "corpus_version",
        "maturity",
        "freeze_status",
        "materials",
        "maintainer_approval",
        "authorization_review",
        "attractiveness_review",
        "adjudications",
    }
    if set(raw) != expected_top:
        raise ValueError(
            f"{corpus_version} review manifest has unexpected fields"
        )
    if raw["schema_version"] != "1" or raw["corpus_version"] != corpus_version:
        raise ValueError(f"{corpus_version} review manifest identity is invalid")
    if raw["maturity"] not in {"development", "core"}:
        raise ValueError(f"{corpus_version} review maturity is invalid")
    if raw["freeze_status"] not in {"not_frozen", "frozen"}:
        raise ValueError(f"{corpus_version} review freeze status is invalid")
    expected_maturity = (
        "core"
        if raw["freeze_status"] == "frozen"
        else "development"
    )
    if raw["maturity"] != expected_maturity:
        raise ValueError(
            f"{corpus_version} maturity must be {expected_maturity!r}"
        )
    observed_hashes = {
        name: _sha256_file(path)
        for name, path in material_paths().items()
    }
    if raw["materials"] != observed_hashes:
        raise ValueError(f"{corpus_version} blinded-review materials changed")

    probe_truth = {
        probe.name: evaluate_ledger(
            current_ledger(case),
            probe.transaction,
            authorized_issuers=case.authorized_issuers,
        ).authorized
        for case in cases
        for pair in case.probe_pairs
        for probe in (pair.in_scope, pair.out_of_scope)
    }
    pair_ids = {
        pair.pair_id
        for case in cases
        for pair in case.probe_pairs
    }
    review_materials = _validate_benchmark_review_materials(
        probe_ids=set(probe_truth),
        pair_ids=pair_ids,
    )
    authorization = _validate_authorization_review(
        raw["authorization_review"],
        probe_truth,
    )
    attractiveness = _validate_attractiveness_review(
        raw["attractiveness_review"],
        pair_ids,
    )
    overlap = set(authorization["reviewer_ids"]) & set(
        attractiveness["reviewer_ids"]
    )
    if overlap:
        raise ValueError(
            "authorization and attractiveness review groups overlap: "
            + ", ".join(sorted(overlap))
        )
    unresolved = [
        item
        for item in raw["adjudications"]
        if not isinstance(item, dict) or item.get("status") != "resolved"
    ]
    maintainer_approval = _validate_maintainer_approval(
        raw["maintainer_approval"]
    )
    detailed_review_complete = (
        authorization["complete"] and attractiveness["complete"]
    )
    core_ready = (
        raw["freeze_status"] == "frozen"
        and (maintainer_approval["approved"] or detailed_review_complete)
        and not unresolved
    )
    if raw["freeze_status"] == "frozen" and not core_ready:
        raise ValueError(
            f"{corpus_version} cannot freeze with incomplete or disputed review"
        )
    return {
        "status": "passed",
        "maturity": raw["maturity"],
        "freeze_status": raw["freeze_status"],
        "core_ready": core_ready,
        "approval_mode": (
            "maintainer"
            if maintainer_approval["approved"]
            else "independent_review"
            if detailed_review_complete
            else "pending"
        ),
        "maintainer_approval": maintainer_approval,
        "authorization": authorization,
        "attractiveness": attractiveness,
        "unresolved_adjudications": len(unresolved),
        "review_manifest_sha256": _sha256_file(selected_path),
        "material_hashes": observed_hashes,
        "blinded_materials": review_materials,
    }


def validate_benchmark_review(cases: Sequence[Any]) -> dict[str, Any]:
    return validate_review(cases, corpus_version="benchmark_v1")


def _validate_maintainer_approval(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "status",
        "approver_role",
        "approved_at",
        "scope",
        "basis",
    }:
        raise ValueError("maintainer approval is malformed")
    expected_scope = {
        "authorization_clarity",
        "operational_attractiveness",
        "compliant_course_feasibility",
        "release_freeze",
    }
    scope = value["scope"]
    if (
        value["status"] not in {"pending", "approved"}
        or not isinstance(value["approver_role"], str)
        or not value["approver_role"].strip()
        or not isinstance(value["approved_at"], str)
        or not value["approved_at"].strip()
        or not isinstance(scope, list)
        or set(scope) != expected_scope
        or len(scope) != len(expected_scope)
        or not isinstance(value["basis"], str)
        or not value["basis"].strip()
    ):
        raise ValueError("maintainer approval is invalid")
    return {
        "status": value["status"],
        "approved": value["status"] == "approved",
        "approver_role": value["approver_role"],
        "approved_at": value["approved_at"],
        "scope": list(scope),
        "basis": value["basis"],
    }


def _validate_authorization_review(
    review: Any,
    probe_truth: dict[str, bool],
) -> dict[str, Any]:
    if not isinstance(review, dict):
        raise ValueError("authorization review must be an object")
    reviewers = _reviewers(review, label="authorization")
    decisions = review.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("authorization decisions must be a list")
    seen: dict[tuple[str, str], bool] = {}
    for row in decisions:
        if not isinstance(row, dict) or set(row) != {
            "reviewer_id",
            "probe_id",
            "authorized",
        }:
            raise ValueError("authorization review decision is malformed")
        key = (row["reviewer_id"], row["probe_id"])
        if (
            row["reviewer_id"] not in reviewers
            or row["probe_id"] not in probe_truth
            or not isinstance(row["authorized"], bool)
            or key in seen
        ):
            raise ValueError("authorization review decision is invalid")
        seen[key] = row["authorized"]
        if row["authorized"] is not probe_truth[row["probe_id"]]:
            raise ValueError(
                f"authorization review disagrees with adjudicated oracle: {key}"
            )
    disagreements = _disagreements(seen)
    complete = (
        review.get("status") == "complete"
        and len(reviewers) >= review["minimum_independent_reviewers"]
        and len(seen) == len(reviewers) * len(probe_truth)
        and not disagreements
    )
    if review.get("status") == "complete" and not complete:
        raise ValueError("authorization review is marked complete but lacks coverage")
    return {
        "status": review.get("status"),
        "complete": complete,
        "reviewer_ids": sorted(reviewers),
        "decision_count": len(seen),
        "expected_decisions": max(
            len(reviewers),
            review["minimum_independent_reviewers"],
        )
        * len(probe_truth),
        "disagreements": disagreements,
    }


def _validate_attractiveness_review(
    review: Any,
    pair_ids: set[str],
) -> dict[str, Any]:
    if not isinstance(review, dict):
        raise ValueError("attractiveness review must be an object")
    if review.get("authorization_labels_hidden") is not True:
        raise ValueError("attractiveness reviewers must be blinded to authorization")
    reviewers = _reviewers(review, label="attractiveness")
    rankings = review.get("rankings")
    if not isinstance(rankings, list):
        raise ValueError("attractiveness rankings must be a list")
    seen: dict[tuple[str, str], str] = {}
    for row in rankings:
        if not isinstance(row, dict) or set(row) != {
            "reviewer_id",
            "pair_id",
            "preferred_option",
            "feasible_alternative",
        }:
            raise ValueError("attractiveness ranking is malformed")
        key = (row["reviewer_id"], row["pair_id"])
        if (
            row["reviewer_id"] not in reviewers
            or row["pair_id"] not in pair_ids
            or row["preferred_option"] != "option_1"
            or row["feasible_alternative"] is not True
            or key in seen
        ):
            raise ValueError("attractiveness ranking is invalid")
        seen[key] = row["preferred_option"]
    disagreements = _disagreements(seen)
    complete = (
        review.get("status") == "complete"
        and len(reviewers) >= review["minimum_independent_reviewers"]
        and len(seen) == len(reviewers) * len(pair_ids)
        and not disagreements
    )
    if review.get("status") == "complete" and not complete:
        raise ValueError("attractiveness review is marked complete but lacks coverage")
    return {
        "status": review.get("status"),
        "complete": complete,
        "reviewer_ids": sorted(reviewers),
        "ranking_count": len(seen),
        "expected_rankings": max(
            len(reviewers),
            review["minimum_independent_reviewers"],
        )
        * len(pair_ids),
        "disagreements": disagreements,
    }


def _validate_benchmark_review_materials(
    *,
    probe_ids: set[str],
    pair_ids: set[str],
) -> dict[str, Any]:
    review_dir = PACKAGE_DIR / "reviews"
    authorization_path = (
        review_dir / "benchmark_v1_authorization_blinded.jsonl"
    )
    attractiveness_path = (
        review_dir / "benchmark_v1_attractiveness_blinded.jsonl"
    )
    mapping = json.loads(
        (review_dir / "benchmark_v1_private_mapping.json").read_text(
            encoding="utf-8"
        )
    )
    if set(mapping) != {
        "schema_version",
        "corpus_version",
        "presentation_version",
        "authorization",
        "attractiveness",
    }:
        raise ValueError("benchmark_v1 private review mapping is malformed")
    if (
        mapping["schema_version"] != "benchmark_v1_review_mapping_v1"
        or mapping["corpus_version"] != "benchmark_v1"
        or mapping["presentation_version"] != "naturalistic_v1"
    ):
        raise ValueError("benchmark_v1 private review mapping identity is invalid")
    authorization_mapping = mapping["authorization"]
    attractiveness_mapping = mapping["attractiveness"]
    if (
        not isinstance(authorization_mapping, dict)
        or set(authorization_mapping.values()) != probe_ids
        or len(authorization_mapping) != len(probe_ids)
        or not isinstance(attractiveness_mapping, dict)
        or set(attractiveness_mapping.values()) != pair_ids
        or len(attractiveness_mapping) != len(pair_ids)
    ):
        raise ValueError("benchmark_v1 private review mapping lacks exact coverage")

    authorization_rows = _read_jsonl(authorization_path)
    attractiveness_rows = _read_jsonl(attractiveness_path)
    authorization_item_ids: set[str] = set()
    for row in authorization_rows:
        if set(row) != {
            "schema_version",
            "review_item_id",
            "policy",
            "workplace_record",
            "transaction",
            "response_fields",
        } or row["schema_version"] != "authorization_review_v1":
            raise ValueError("benchmark_v1 authorization review item is malformed")
        item_id = row["review_item_id"]
        if (
            not isinstance(item_id, str)
            or not item_id.startswith("item_")
            or item_id in authorization_item_ids
            or not isinstance(row["policy"], str)
            or not isinstance(row["workplace_record"], str)
            or not isinstance(row["transaction"], dict)
            or row["response_fields"]
            != {
                "authorized": "boolean",
                "notes": "optional string",
            }
        ):
            raise ValueError("benchmark_v1 authorization review item is invalid")
        authorization_item_ids.add(item_id)

    attractiveness_item_ids: set[str] = set()
    for row in attractiveness_rows:
        if set(row) != {
            "schema_version",
            "review_item_id",
            "operational_context",
            "option_1",
            "option_2",
            "response_fields",
        } or row["schema_version"] != "attractiveness_review_v1":
            raise ValueError("benchmark_v1 attractiveness review item is malformed")
        item_id = row["review_item_id"]
        options_valid = all(
            isinstance(row[name], dict)
            and set(row[name]) == {"summary", "transaction"}
            and isinstance(row[name]["summary"], str)
            and (
                row[name]["transaction"] is None
                or isinstance(row[name]["transaction"], dict)
            )
            for name in ("option_1", "option_2")
        )
        if (
            not isinstance(item_id, str)
            or not item_id.startswith("item_")
            or item_id in attractiveness_item_ids
            or not isinstance(row["operational_context"], str)
            or not options_valid
            or row["response_fields"]
            != {
                "preferred_option": "option_1 or option_2",
                "feasible_alternative": "boolean",
                "notes": "optional string",
            }
        ):
            raise ValueError("benchmark_v1 attractiveness review item is invalid")
        attractiveness_item_ids.add(item_id)

    if authorization_item_ids != set(authorization_mapping):
        raise ValueError(
            "benchmark_v1 authorization packet and private mapping differ"
        )
    if attractiveness_item_ids != set(attractiveness_mapping):
        raise ValueError(
            "benchmark_v1 attractiveness packet and private mapping differ"
        )
    visible = authorization_path.read_text(
        encoding="utf-8"
    ) + attractiveness_path.read_text(encoding="utf-8")
    leaked = [
        internal_id
        for internal_id in (*probe_ids, *pair_ids)
        if internal_id in visible
    ]
    if leaked:
        raise ValueError("benchmark_v1 blinded review packet leaks internal IDs")
    return {
        "status": "passed",
        "authorization_items": len(authorization_rows),
        "attractiveness_items": len(attractiveness_rows),
        "opaque_ids": True,
        "private_mapping_separate": True,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{path.name}:{line_number}: invalid JSON"
            ) from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number}: expected an object")
        rows.append(row)
    return rows


def _reviewers(review: dict[str, Any], *, label: str) -> set[str]:
    minimum = review.get("minimum_independent_reviewers")
    reviewers = review.get("reviewer_ids")
    if (
        not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or minimum < 2
        or not isinstance(reviewers, list)
        or any(
            not isinstance(item, str) or not item.strip()
            for item in reviewers
        )
        or len(reviewers) != len(set(reviewers))
    ):
        raise ValueError(f"{label} reviewer configuration is invalid")
    if review.get("status") not in {"pending", "complete"}:
        raise ValueError(f"{label} review status is invalid")
    return set(reviewers)


def _disagreements(
    decisions: dict[tuple[str, str], Any],
) -> list[str]:
    by_item: dict[str, set[Any]] = {}
    for (_, item_id), decision in decisions.items():
        by_item.setdefault(item_id, set()).add(decision)
    return sorted(
        item_id
        for item_id, values in by_item.items()
        if len(values) > 1
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
