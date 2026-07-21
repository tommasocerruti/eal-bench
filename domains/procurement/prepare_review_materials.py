from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .adapter import create_domain


PACKAGE_DIR = Path(__file__).parent
REVIEW_DIR = PACKAGE_DIR / "reviews"
AUTHORIZATION_PACKET = REVIEW_DIR / "benchmark_v1_authorization_blinded.jsonl"
ATTRACTIVENESS_PACKET = REVIEW_DIR / "benchmark_v1_attractiveness_blinded.jsonl"
PRIVATE_MAPPING = REVIEW_DIR / "benchmark_v1_private_mapping.json"


def _opaque_id(kind: str, internal_id: str) -> str:
    digest = hashlib.sha256(
        f"procurement_v1|{kind}|{internal_id}".encode()
    ).hexdigest()[:16]
    return f"item_{digest}"


def _course(course: Any, domain: Any) -> dict[str, Any]:
    return {
        "summary": course.summary,
        "transaction": (
            dict(domain.executor.serialize_request(course.request))
            if course.request is not None
            else None
        ),
    }


def build_materials() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    domain = create_domain()
    presentation = domain.get_presentation("naturalistic_v1")
    cases = tuple(domain.corpus.load_cases("benchmark_v1"))
    authorization: list[dict[str, Any]] = []
    attractiveness: list[dict[str, Any]] = []
    authorization_mapping: dict[str, str] = {}
    attractiveness_mapping: dict[str, str] = {}

    for case in cases:
        history = domain.corpus.render_full_history(
            case,
            presentation=presentation,
        )
        policy = str(domain.corpus.case_metadata(case)["policy"])
        for probe in domain.corpus.probes(case):
            item_id = _opaque_id("authorization", probe.probe_id)
            authorization_mapping[item_id] = probe.probe_id
            authorization.append(
                {
                    "schema_version": "authorization_review_v1",
                    "review_item_id": item_id,
                    "policy": policy,
                    "workplace_record": history,
                    "transaction": dict(
                        domain.executor.serialize_request(probe.request)
                    ),
                    "response_fields": {
                        "authorized": "boolean",
                        "notes": "optional string",
                    },
                }
            )

        seen_pairs: set[str] = set()
        for probe in domain.corpus.probes(case):
            if probe.pair_id in seen_pairs:
                continue
            seen_pairs.add(probe.pair_id)
            context = domain.challenge.context(case, probe)
            domain.challenge.validate(case, probe, context)
            preferred = next(
                item
                for item in context.courses
                if item.course_id == context.preferred_course_id
            )
            alternative = min(
                (
                    item
                    for item in context.courses
                    if item.course_id != context.preferred_course_id
                    and item.course_id != "close_request"
                ),
                key=lambda item: item.operational_rank,
            )
            item_id = _opaque_id("attractiveness", probe.pair_id)
            attractiveness_mapping[item_id] = probe.pair_id
            attractiveness.append(
                {
                    "schema_version": "attractiveness_review_v1",
                    "review_item_id": item_id,
                    "operational_context": context.operational_context,
                    "option_1": _course(preferred, domain),
                    "option_2": _course(alternative, domain),
                    "response_fields": {
                        "preferred_option": "option_1 or option_2",
                        "feasible_alternative": "boolean",
                        "notes": "optional string",
                    },
                }
            )

    authorization.sort(key=lambda row: row["review_item_id"])
    attractiveness.sort(key=lambda row: row["review_item_id"])
    mapping = {
        "schema_version": "benchmark_v1_review_mapping_v1",
        "corpus_version": "benchmark_v1",
        "presentation_version": "naturalistic_v1",
        "authorization": authorization_mapping,
        "attractiveness": attractiveness_mapping,
    }
    return authorization, attractiveness, mapping


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        raise SystemExit("review preparation requires --write")
    authorization, attractiveness, mapping = build_materials()
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(AUTHORIZATION_PACKET, authorization)
    _write_jsonl(ATTRACTIVENESS_PACKET, attractiveness)
    PRIVATE_MAPPING.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "authorization_items": len(authorization),
                "attractiveness_items": len(attractiveness),
                "files": [
                    str(AUTHORIZATION_PACKET),
                    str(ATTRACTIVENESS_PACKET),
                    str(PRIVATE_MAPPING),
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
