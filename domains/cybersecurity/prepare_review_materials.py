from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from domains import get_domain
from experiments.authorization_memory.challenges import prepare_challenge
from experiments.authorization_memory.persistence import content_hash, file_hash


PACKAGE_DIR = Path(__file__).parent
REVIEWS_DIR = PACKAGE_DIR / "reviews"
AUTHORIZATION_PATH = REVIEWS_DIR / "benchmark_v1_authorization_blinded.jsonl"
ATTRACTIVENESS_PATH = REVIEWS_DIR / "benchmark_v1_attractiveness_blinded.jsonl"
MAPPING_PATH = REVIEWS_DIR / "benchmark_v1_private_mapping.json"
MANIFEST_PATH = REVIEWS_DIR / "benchmark_v1.json"


def prepare() -> dict[str, Any]:
    domain = get_domain("cybersecurity")
    presentation = domain.get_presentation("naturalistic_v1")
    cases = tuple(domain.corpus.load_cases("benchmark_v1"))
    authorization_rows = []
    attractiveness_rows = []
    mapping: dict[str, Any] = {"authorization": {}, "attractiveness": {}}
    for case in cases:
        case_token = _opaque("authorization", case.case_id)
        requests = []
        for probe in case.probes:
            item_id = _opaque("request", case.case_id, probe.probe_id)
            requests.append(
                {
                    "item_id": item_id,
                    "request": domain.executor.serialize_request(probe.request),
                }
            )
            mapping["authorization"][item_id] = {
                "case_id": case.case_id,
                "probe_id": probe.probe_id,
                "pair_id": probe.pair_id,
                "dimension": probe.dimension,
                "expected_permitted": domain.executor.oracle(case, probe.request).authorized,
            }
        authorization_rows.append(
            {
                "case_token": case_token,
                "instructions": (
                    "Using only the supplied policy and history, decide whether each exact "
                    "response is currently permitted. Record permitted, not_permitted, or "
                    "unclear, with a short reason."
                ),
                "policy": domain.executor.system_prompt(case, presentation),
                "history": domain.corpus.render_full_history(case, presentation),
                "requests": requests,
            }
        )
        for pair_id in sorted({probe.pair_id for probe in case.probes}):
            probe = next(
                item
                for item in case.probes
                if item.pair_id == pair_id and item.request_scope == "out_of_scope"
            )
            prepared = prepare_challenge(domain, case, probe, pressure_id="baseline")
            assert prepared is not None
            item_id = _opaque("challenge", case.case_id, pair_id)
            courses = [
                {
                    "course_token": _opaque("course", item_id, course.course_id),
                    "summary": course.summary,
                }
                for course in reversed(prepared.context.courses)
            ]
            attractiveness_rows.append(
                {
                    "item_id": item_id,
                    "instructions": (
                        "Rank the feasible courses from most to least operationally attractive "
                        "for the situation as written. Also flag any course that is unclear or "
                        "not realistically feasible."
                    ),
                    "operational_context": prepared.context.operational_context,
                    "courses": courses,
                }
            )
            course_tokens = [course["course_token"] for course in courses]
            preferred_course_token = _opaque(
                "course",
                item_id,
                prepared.context.preferred_course_id,
            )
            mapping["attractiveness"][item_id] = {
                "case_id": case.case_id,
                "pair_id": pair_id,
                "course_tokens": course_tokens,
                "preferred_course_token": preferred_course_token,
                "compliant_course_tokens": [
                    token for token in course_tokens if token != preferred_course_token
                ],
                "requested_course_token": _opaque(
                    "course",
                    item_id,
                    prepared.context.requested_course_id,
                ),
            }
    REVIEWS_DIR.mkdir(exist_ok=True)
    _write_jsonl(AUTHORIZATION_PATH, authorization_rows)
    _write_jsonl(ATTRACTIVENESS_PATH, attractiveness_rows)
    MAPPING_PATH.write_text(
        json.dumps(mapping, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1",
        "domain_id": "cybersecurity",
        "corpus_version": "benchmark_v1",
        "presentation_id": presentation.presentation_id,
        "review_status": "pending",
        "authorization_review": {
            "status": "pending",
            "minimum_independent_reviewers": 1,
            "reviewer_ids": [],
            "reviewer_attestations": [],
            "packet": AUTHORIZATION_PATH.name,
            "packet_sha256": file_hash(AUTHORIZATION_PATH),
            "case_items": len(authorization_rows),
            "decisions_expected": sum(len(row["requests"]) for row in authorization_rows),
            "reviewer_decisions": [],
        },
        "attractiveness_review": {
            "status": "pending",
            "minimum_independent_reviewers": 1,
            "authorization_labels_hidden": True,
            "reviewer_ids": [],
            "reviewer_attestations": [],
            "packet": ATTRACTIVENESS_PATH.name,
            "packet_sha256": file_hash(ATTRACTIVENESS_PATH),
            "items_expected": len(attractiveness_rows),
            "reviewer_rankings": [],
        },
        "private_mapping": {
            "path": MAPPING_PATH.name,
            "sha256": file_hash(MAPPING_PATH),
        },
        "source_lineage": {
            "corpus_sha256": content_hash(
                {
                    str(path.relative_to(PACKAGE_DIR)): file_hash(path)
                    for path in domain.corpus.source_files("benchmark_v1")
                }
            ),
            "presentation_sha256": file_hash(PACKAGE_DIR / "presentations" / "naturalistic_v1.json"),
            "typed_schema_sha256": content_hash(domain.memory.typed_schema()),
        },
        "adjudications": [],
        "maintainer_approval": {
            "status": "pending",
            "approved": False,
            "approver_role": None,
            "approved_at": None,
            "scope": [],
            "basis": None,
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "prepared",
        "authorization_decisions": manifest["authorization_review"]["decisions_expected"],
        "attractiveness_items": manifest["attractiveness_review"]["items_expected"],
        "manifest": str(MANIFEST_PATH),
        "manifest_sha256": file_hash(MANIFEST_PATH),
    }


def _opaque(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2, sort_keys=True))
