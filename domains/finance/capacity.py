from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from domains.base import CapacityPolicy


PACKAGE_DIR = Path(__file__).parent
ARTIFACT_PATH = PACKAGE_DIR / "capacity_calibration.json"
CALIBRATION_VERSION = "calibration_v1"
BENCHMARK_VERSION = "benchmark_v1"
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
    from .corpus import _versions

    versions = _versions()
    return CapacityPolicy(
        primary_multiplier=float(artifact["primary_multiplier"]),
        tight_multiplier=float(artifact["tight_multiplier"]),
        minimum_history_ratio=int(artifact["minimum_history_ratio"]),
        minimum_history_ratios={
            version: int(artifact["minimum_history_ratio"]) for version in versions
        },
        calibrated_tokens={
            version: {"primary": primary, "tight": tight} for version in versions
        },
    )


def build_capacity_calibration(domain: Any) -> dict[str, Any]:
    from experiments.authorization_memory.persistence import canonical_json, content_hash, file_hash

    presentation = domain.get_presentation(PRESENTATION_VERSION)
    rows_by_version = {
        version: _checkpoint_capacity(domain, domain.corpus.load_cases(version), presentation)
        for version in (CALIBRATION_VERSION, BENCHMARK_VERSION)
    }
    source_hashes = {
        str(path.relative_to(PACKAGE_DIR)): file_hash(path)
        for path in domain.corpus.source_files(CALIBRATION_VERSION)
    }
    largest = max(row["largest_faithful_tokens"] for row in rows_by_version[CALIBRATION_VERSION])
    primary_tokens = math.ceil(2.0 * largest)
    compatibility = {}
    for version in (BENCHMARK_VERSION,):
        paths = domain.corpus.source_files(version)
        hashes = {str(path.relative_to(PACKAGE_DIR)): file_hash(path) for path in paths}
        rows = rows_by_version[version]
        compatibility[version] = {
            "source_sha256": content_hash(hashes),
            "source_files": hashes,
            "largest_faithful_tokens": max(row["largest_faithful_tokens"] for row in rows),
            "all_faithful_payloads_fit_primary": all(row["largest_faithful_tokens"] <= primary_tokens for row in rows),
            "minimum_history_tokens": min(row["history_tokens"] for row in rows),
            "required_history_tokens": MINIMUM_HISTORY_RATIO * primary_tokens,
            "cases": rows,
        }
    all_rows = tuple(row for rows in rows_by_version.values() for row in rows)
    return {
        "schema_version": "1",
        "domain_id": domain.domain_id,
        "calibration_corpus": CALIBRATION_VERSION,
        "calibration_split": "development_capacity",
        "calibration_implementation": "finance_checkpoint_capacity_v1",
        "freeze_status": "frozen",
        "tokenizer_name": "cl100k_base",
        "tokenizer_version": "tiktoken_reference",
        "typed_schema_version": "5",
        "typed_schema_sha256": content_hash(domain.memory.typed_schema()),
        "free_text_representation": "finance_current_mandates_v1",
        "calibration_source_sha256": content_hash(source_hashes),
        "calibration_source_files": source_hashes,
        "capacity_basis": "largest faithful text or typed payload at any authorization checkpoint",
        "largest_faithful_tokens": largest,
        "primary_multiplier": 2.0,
        "tight_multiplier": 1.25,
        "primary_tokens": primary_tokens,
        "tight_tokens": math.ceil(1.25 * largest),
        "minimum_history_ratio": MINIMUM_HISTORY_RATIO,
        "minimum_history_tokens": min(row["history_tokens"] for row in all_rows),
        "required_history_tokens": MINIMUM_HISTORY_RATIO * primary_tokens,
        "cases": rows_by_version[CALIBRATION_VERSION],
        "compatibility": compatibility,
        "serialization": {
            "typed": "canonical_json",
            "text": "plain_text",
            "checkpoint_blocks": "all authorization-changing blocks",
            "canonical_json_example_sha256": content_hash(
                canonical_json(domain.memory.faithful_typed(domain.corpus.load_cases(CALIBRATION_VERSION)[0], 9))
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
            text_tokens = count_reference_tokens(domain.memory.faithful_free_text(case, block_index))
            typed_tokens = count_reference_tokens(canonical_json(domain.memory.faithful_typed(case, block_index)))
            checkpoints.append({
                "block_index": block_index,
                "active_mandate_count": len(replay_case(case, block_index)),
                "faithful_text_tokens": text_tokens,
                "faithful_typed_tokens": typed_tokens,
                "largest_faithful_tokens": max(text_tokens, typed_tokens),
            })
        rows.append({
            "case_id": case.case_id,
            "history_tokens": count_reference_tokens(domain.corpus.render_full_history(case, presentation)),
            "largest_faithful_tokens": max(item["largest_faithful_tokens"] for item in checkpoints),
            "largest_checkpoint_block_index": max(checkpoints, key=lambda item: item["largest_faithful_tokens"])["block_index"],
            "checkpoints": checkpoints,
        })
    return rows


def write_capacity_calibration(domain: Any) -> None:
    ARTIFACT_PATH.write_text(
        json.dumps(build_capacity_calibration(domain), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def validate_capacity_calibration(
    domain: Any,
    cases: Any | None = None,
    presentation: Any | None = None,
) -> dict[str, Any]:
    from experiments.authorization_memory.persistence import content_hash, file_hash

    if not ARTIFACT_PATH.is_file():
        raise ValueError("Finance capacity artifact has not been generated")
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    release = json.loads((PACKAGE_DIR / "release.json").read_text(encoding="utf-8"))
    if file_hash(ARTIFACT_PATH) != release["capacity"]["sha256"]:
        raise ValueError("Finance v1 capacity artifact differs from its frozen release")
    if artifact["primary_tokens"] != 2 * artifact["largest_faithful_tokens"]:
        raise ValueError("Finance primary capacity is not the required 2x policy")
    for version, entry in artifact["compatibility"].items():
        if not entry["all_faithful_payloads_fit_primary"]:
            raise ValueError(f"{version}: faithful payload exceeds primary capacity")
        if entry["minimum_history_tokens"] < entry["required_history_tokens"]:
            raise ValueError(f"{version}: source history is too short")
    if artifact["minimum_history_tokens"] < artifact["required_history_tokens"]:
        raise ValueError("Finance calibration history is too short")
    selected_rows = []
    if cases is not None:
        if presentation is None:
            raise ValueError("Finance capacity compatibility requires a presentation")
        selected_rows = _checkpoint_capacity(domain, cases, presentation)
        for row in selected_rows:
            if row["largest_faithful_tokens"] > artifact["primary_tokens"]:
                raise ValueError(
                    f"{row['case_id']}: faithful payload exceeds frozen primary capacity"
                )
            if row["history_tokens"] < artifact["required_history_tokens"]:
                raise ValueError(
                    f"{row['case_id']}: source history is too short for frozen capacity"
                )
    return {
        "status": "passed",
        "artifact": str(ARTIFACT_PATH),
        "artifact_sha256": file_hash(ARTIFACT_PATH),
        "typed_schema_sha256": content_hash(domain.memory.typed_schema()),
        "primary_tokens": artifact["primary_tokens"],
        "tight_tokens": artifact["tight_tokens"],
        "minimum_history_tokens": artifact["minimum_history_tokens"],
        "selected_case_count": len(selected_rows),
        "selected_largest_faithful_tokens": max(
            (row["largest_faithful_tokens"] for row in selected_rows),
            default=artifact["largest_faithful_tokens"],
        ),
        "selected_minimum_history_tokens": min(
            (row["history_tokens"] for row in selected_rows),
            default=artifact["minimum_history_tokens"],
        ),
    }


if __name__ == "__main__":
    from domains import get_domain

    write_capacity_calibration(get_domain("finance"))
