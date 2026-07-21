from __future__ import annotations

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from typing import Any

from .cases import load_cases
from .studies.pipeline import (
    PRIMARY_CAPACITY_MULTIPLIER,
    TIGHT_CAPACITY_MULTIPLIER,
    calibrate_capacity_budgets,
)


PACKAGE_DIR = Path(__file__).parent
REPO_ROOT = PACKAGE_DIR.parents[1]
CALIBRATION_PATH = PACKAGE_DIR / "capacity_calibration.json"
SOURCE_PATHS = (
    "domains/procurement/data/calibration_v1.jsonl",
    "domains/procurement/corpus/calibration_v1/01_calibration_v1_issue_only.yaml",
    "domains/procurement/corpus/calibration_v1/02_calibration_v1_amount_narrowing.yaml",
    "domains/procurement/corpus/calibration_v1/03_calibration_v1_time_narrowing.yaml",
    "domains/procurement/corpus/calibration_v1/04_calibration_v1_category_narrowing.yaml",
    "domains/procurement/corpus/calibration_v1/05_calibration_v1_revoke_replace.yaml",
)
REPRESENTATION_PATHS = (
    "domains/procurement/cases.py",
    "domains/procurement/schemas.py",
    "domains/procurement/studies/memory.py",
    "domains/procurement/studies/pipeline.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    without_hash = {
        key: value
        for key, value in payload.items()
        if key != "payload_sha256"
    }
    canonical = json.dumps(
        without_hash,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_capacity_calibration() -> dict[str, Any]:
    cases = tuple(load_cases("calibration_v1"))
    calibration = calibrate_capacity_budgets(cases)
    payload: dict[str, Any] = {
        "schema_version": "1",
        "domain_id": "procurement",
        "calibration_corpus_version": "calibration_v1",
        "calibration_split": "calibration",
        "reference_tokenizer": {
            "name": calibration.reference_tokenizer,
            "package": "tiktoken",
            "package_version": version("tiktoken"),
        },
        "implementation_version": "procurement_capacity_calibration_v1",
        "source_hashes": {
            path: _sha256(REPO_ROOT / path) for path in SOURCE_PATHS
        },
        "representation_hashes": {
            path: _sha256(REPO_ROOT / path) for path in REPRESENTATION_PATHS
        },
        "cases": [
            {
                "case_id": row.case_id,
                "history_tokens": row.history_tokens,
                "faithful_text_tokens": row.faithful_text_tokens,
                "faithful_typed_tokens": row.faithful_typed_tokens,
            }
            for row in calibration.cases
        ],
        "largest_faithful_tokens": calibration.largest_faithful_tokens,
        "primary_multiplier": PRIMARY_CAPACITY_MULTIPLIER,
        "tight_multiplier": TIGHT_CAPACITY_MULTIPLIER,
        "primary_tokens": calibration.primary_tokens,
        "tight_tokens": calibration.tight_tokens,
        "minimum_history_to_primary_ratio": calibration.minimum_history_ratio,
        "minimum_required_history_tokens": (
            calibration.minimum_history_ratio * calibration.primary_tokens
        ),
    }
    payload["payload_sha256"] = _payload_hash(payload)
    return payload


def write_capacity_calibration() -> None:
    CALIBRATION_PATH.write_text(
        json.dumps(build_capacity_calibration(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def validate_capacity_calibration(capacity_policy: Any) -> dict[str, Any]:
    raw = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version",
        "domain_id",
        "calibration_corpus_version",
        "calibration_split",
        "reference_tokenizer",
        "implementation_version",
        "source_hashes",
        "representation_hashes",
        "cases",
        "largest_faithful_tokens",
        "primary_multiplier",
        "tight_multiplier",
        "primary_tokens",
        "tight_tokens",
        "minimum_history_to_primary_ratio",
        "minimum_required_history_tokens",
        "payload_sha256",
    }
    if set(raw) != expected_keys:
        raise ValueError("procurement capacity calibration fields changed")
    if (
        raw["schema_version"] != "1"
        or raw["domain_id"] != "procurement"
        or raw["calibration_corpus_version"] != "calibration_v1"
        or raw["calibration_split"] != "calibration"
        or raw["implementation_version"]
        != "procurement_capacity_calibration_v1"
        or raw["payload_sha256"] != _payload_hash(raw)
    ):
        raise ValueError("procurement capacity calibration identity is invalid")

    tokenizer = raw["reference_tokenizer"]
    if tokenizer != {
        "name": "cl100k_base",
        "package": "tiktoken",
        "package_version": version("tiktoken"),
    }:
        raise ValueError("procurement capacity tokenizer version changed")
    for group in ("source_hashes", "representation_hashes"):
        recorded = raw[group]
        observed = {
            relative_path: _sha256(REPO_ROOT / relative_path)
            for relative_path in recorded
        }
        if recorded != observed:
            raise ValueError(
                f"procurement capacity {group.replace('_', ' ')} changed"
            )

    cases = tuple(load_cases("calibration_v1"))
    if any(case.benchmark.split != "calibration" for case in cases):
        raise ValueError("capacity calibration corpus contains a non-calibration case")
    calibration = calibrate_capacity_budgets(cases)
    if raw["cases"] != [
        {
            "case_id": row.case_id,
            "history_tokens": row.history_tokens,
            "faithful_text_tokens": row.faithful_text_tokens,
            "faithful_typed_tokens": row.faithful_typed_tokens,
        }
        for row in calibration.cases
    ]:
        raise ValueError("procurement capacity case counts changed")
    expected_numbers = {
        "largest_faithful_tokens": calibration.largest_faithful_tokens,
        "primary_multiplier": capacity_policy.primary_multiplier,
        "tight_multiplier": capacity_policy.tight_multiplier,
        "primary_tokens": calibration.primary_tokens,
        "tight_tokens": calibration.tight_tokens,
        "minimum_history_to_primary_ratio": calibration.minimum_history_ratio,
        "minimum_required_history_tokens": (
            calibration.minimum_history_ratio * calibration.primary_tokens
        ),
    }
    if any(raw[key] != value for key, value in expected_numbers.items()):
        raise ValueError("procurement capacity policy or derived budget changed")
    for corpus_version in ("calibration_v1", "benchmark_v1"):
        if (
            capacity_policy.calibrated_for(corpus_version, "primary")
            != raw["primary_tokens"]
            or capacity_policy.calibrated_for(corpus_version, "tight")
            != raw["tight_tokens"]
        ):
            raise ValueError(
                f"{corpus_version} does not reuse the frozen capacity budget"
            )
    return {
        "status": "passed",
        "artifact_sha256": _sha256(CALIBRATION_PATH),
        "payload_sha256": raw["payload_sha256"],
        "calibration_corpus_version": raw[
            "calibration_corpus_version"
        ],
        "reference_tokenizer": tokenizer,
        **expected_numbers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        raise ValueError("capacity calibration generation requires --write")
    write_capacity_calibration()


if __name__ == "__main__":
    main()
