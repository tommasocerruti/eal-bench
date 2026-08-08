from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from domains.base import CapacityPolicy


PACKAGE_DIR = Path(__file__).parent
ARTIFACT_PATH = PACKAGE_DIR / "capacity_calibration_v1.json"
CALIBRATION_VERSION = "calibration_v1"
DEVELOPMENT_VERSION = "benchmark_v1"
PRESENTATION_VERSION = "naturalistic_v1"
MINIMUM_HISTORY_RATIO = 8


def capacity_policy() -> CapacityPolicy:
    if not ARTIFACT_PATH.is_file():
        return CapacityPolicy(minimum_history_ratio=MINIMUM_HISTORY_RATIO)
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    if artifact.get("calibration_corpus") != CALIBRATION_VERSION:
        return CapacityPolicy(minimum_history_ratio=MINIMUM_HISTORY_RATIO)
    primary = int(artifact["primary_tokens"])
    tight = int(artifact["tight_tokens"])
    return CapacityPolicy(
        primary_multiplier=float(artifact["primary_multiplier"]),
        tight_multiplier=float(artifact["tight_multiplier"]),
        minimum_history_ratio=int(artifact["minimum_history_ratio"]),
        minimum_history_ratios={
            CALIBRATION_VERSION: int(artifact["minimum_history_ratio"]),
            DEVELOPMENT_VERSION: int(artifact["minimum_history_ratio"]),
        },
        calibrated_tokens={
            CALIBRATION_VERSION: {"primary": primary, "tight": tight},
            DEVELOPMENT_VERSION: {"primary": primary, "tight": tight},
        },
    )


def build_capacity_calibration(domain: Any) -> dict[str, Any]:
    from experiments.authorization_memory.persistence import canonical_json, content_hash, file_hash

    presentation = domain.get_presentation(PRESENTATION_VERSION)
    calibration_cases = domain.corpus.load_cases(CALIBRATION_VERSION)
    development_cases = domain.corpus.load_cases(DEVELOPMENT_VERSION)
    calibration = _checkpoint_capacity(domain, calibration_cases, presentation)
    development = _checkpoint_capacity(domain, development_cases, presentation)
    source_hashes = {
        str(path.relative_to(PACKAGE_DIR)): file_hash(path)
        for path in domain.corpus.source_files(CALIBRATION_VERSION)
    }
    development_hashes = {
        str(path.relative_to(PACKAGE_DIR)): file_hash(path)
        for path in domain.corpus.source_files(DEVELOPMENT_VERSION)
    }
    largest = max(row["largest_faithful_tokens"] for row in calibration)
    primary_tokens = math.ceil(2.0 * largest)
    minimum_history = min(row["history_tokens"] for row in (*calibration, *development))
    return {
        "schema_version": "3",
        "domain_id": domain.domain_id,
        "calibration_corpus": CALIBRATION_VERSION,
        "calibration_split": "development_capacity",
        "calibration_implementation": "cybersecurity_checkpoint_capacity_v1",
        "freeze_status": "frozen",
        "tokenizer_name": "cl100k_base",
        "tokenizer_version": "tiktoken_reference",
        "typed_schema_version": "4",
        "typed_schema_sha256": content_hash(domain.memory.typed_schema()),
        "free_text_representation": "cybersecurity_current_permissions_v1",
        "calibration_source_sha256": content_hash(source_hashes),
        "calibration_source_files": source_hashes,
        "capacity_basis": "largest faithful text or typed payload at any authorization checkpoint",
        "largest_faithful_tokens": largest,
        "primary_multiplier": 2.0,
        "tight_multiplier": 1.25,
        "primary_tokens": primary_tokens,
        "tight_tokens": math.ceil(1.25 * largest),
        "minimum_history_ratio": MINIMUM_HISTORY_RATIO,
        "minimum_history_tokens": minimum_history,
        "required_history_tokens": MINIMUM_HISTORY_RATIO * primary_tokens,
        "cases": calibration,
        "development_compatibility": {
            "corpus_version": DEVELOPMENT_VERSION,
            "source_sha256": content_hash(development_hashes),
            "source_files": development_hashes,
            "largest_faithful_tokens": max(
                row["largest_faithful_tokens"] for row in development
            ),
            "all_faithful_payloads_fit_primary": all(
                row["largest_faithful_tokens"] <= primary_tokens for row in development
            ),
            "minimum_history_tokens": min(row["history_tokens"] for row in development),
            "required_history_tokens": MINIMUM_HISTORY_RATIO * primary_tokens,
            "cases": development,
        },
        "serialization": {
            "typed": "canonical_json",
            "text": "plain_text",
            "checkpoint_blocks": "all authorization-changing blocks",
            "canonical_json_example_sha256": content_hash(
                canonical_json(domain.memory.faithful_typed(calibration_cases[0], 8))
            ),
        },
    }


def _checkpoint_capacity(domain: Any, cases: Any, presentation: Any) -> list[dict[str, Any]]:
    from experiments.authorization_memory.persistence import canonical_json
    from experiments.authorization_memory.tokens import count_reference_tokens

    from .corpus import replay_case

    rows = []
    for case in cases:
        checkpoints = []
        for block_index in case.metadata["authorization_changing_blocks"]:
            text_tokens = count_reference_tokens(
                domain.memory.faithful_free_text(case, block_index)
            )
            typed_tokens = count_reference_tokens(
                canonical_json(domain.memory.faithful_typed(case, block_index))
            )
            checkpoints.append(
                {
                    "block_index": block_index,
                    "active_grant_count": len(replay_case(case, block_index)),
                    "faithful_text_tokens": text_tokens,
                    "faithful_typed_tokens": typed_tokens,
                    "largest_faithful_tokens": max(text_tokens, typed_tokens),
                }
            )
        rows.append(
            {
                "case_id": case.case_id,
                "history_tokens": count_reference_tokens(
                    domain.corpus.render_full_history(case, presentation)
                ),
                "largest_faithful_tokens": max(
                    row["largest_faithful_tokens"] for row in checkpoints
                ),
                "largest_checkpoint_block_index": max(
                    checkpoints,
                    key=lambda row: row["largest_faithful_tokens"],
                )["block_index"],
                "checkpoints": checkpoints,
            }
        )
    return rows


def write_capacity_calibration(domain: Any) -> None:
    ARTIFACT_PATH.write_text(
        json.dumps(build_capacity_calibration(domain), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def validate_capacity_calibration(domain: Any) -> dict[str, Any]:
    from experiments.authorization_memory.persistence import content_hash, file_hash

    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    rebuilt = build_capacity_calibration(domain)
    if artifact != rebuilt:
        raise ValueError("cybersecurity capacity calibration does not reproduce")
    if artifact["primary_tokens"] != 2 * artifact["largest_faithful_tokens"]:
        raise ValueError("cybersecurity primary capacity is not the required 2x policy")
    if not artifact["development_compatibility"]["all_faithful_payloads_fit_primary"]:
        raise ValueError("development faithful payload exceeds primary capacity")
    if artifact["minimum_history_tokens"] < artifact["required_history_tokens"]:
        raise ValueError("cybersecurity histories are too short for the unchanged capacity policy")
    return {
        "status": "passed",
        "artifact": str(ARTIFACT_PATH),
        "artifact_sha256": file_hash(ARTIFACT_PATH),
        "typed_schema_sha256": content_hash(domain.memory.typed_schema()),
        "primary_tokens": artifact["primary_tokens"],
        "tight_tokens": artifact["tight_tokens"],
        "largest_checkpoint_block_index": max(
            row["largest_checkpoint_block_index"] for row in artifact["cases"]
        ),
        "development_largest_faithful_tokens": artifact["development_compatibility"][
            "largest_faithful_tokens"
        ],
    }


if __name__ == "__main__":
    from domains import get_domain

    write_capacity_calibration(get_domain("cybersecurity"))
