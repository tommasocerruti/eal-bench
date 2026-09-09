"""Internal Finance redesign corpus identities and structural validation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from domains.base import BenchmarkProbe

from .compile_redesign import (
    BLOCK_COUNT,
    CALIBRATION_VERSION,
    DEVELOPMENT_VERSION_1,
    DEVELOPMENT_VERSIONS,
    FINAL_VERSION,
    TURN_COUNT,
)
from .models import FinanceCase, parse_timestamp


PACKAGE_DIR = Path(__file__).parent
DATA_DIR = PACKAGE_DIR / "data"
VERSIONS = (*DEVELOPMENT_VERSIONS, CALIBRATION_VERSION, FINAL_VERSION)
_V14_VERSIONS = {
    "finance_redesign_dev_014",
    CALIBRATION_VERSION,
    FINAL_VERSION,
}
_SOURCE_ID = re.compile(r"src_fin_r(?:[1-9]|1[0-4])_[0-9a-f]{20}\Z")
_FIELD_BY_MECHANISM = {
    "stale_scope": "instrument_id",
    "revoked_record_retention": "side",
    "cross_record_stitching": "order_type",
    "broadened_time_or_action": "requested_at",
}


def source_files(version: str) -> tuple[Path, ...]:
    if version not in VERSIONS:
        raise ValueError(f"unsupported Finance redesign corpus: {version!r}")
    return (
        DATA_DIR / f"{version}.json",
        PACKAGE_DIR / "v2_blueprint.json",
        PACKAGE_DIR / "compile_redesign.py",
        Path(__file__),
        PACKAGE_DIR / "corpus.py",
    )


def provenance(version: str, case_count: int) -> Mapping[str, Any]:
    from experiments.authorization_memory.persistence import content_hash, file_hash

    paths = source_files(version)
    hashes = {str(path.relative_to(PACKAGE_DIR)): file_hash(path) for path in paths}
    split = (
        "development"
        if version in DEVELOPMENT_VERSIONS
        else "calibration"
        if version == CALIBRATION_VERSION
        else "held_out_claim"
    )
    return {
        "corpus_version": version,
        "source_format": "finance_redesign_corpus_v1",
        "source_sha256": content_hash(hashes),
        "source_files": hashes,
        "generator_version": {
            DEVELOPMENT_VERSION_1: "finance_redesign_compiler_v1",
            "finance_redesign_dev_002": "finance_redesign_compiler_v2",
            "finance_redesign_dev_003": "finance_redesign_compiler_v3",
            "finance_redesign_dev_004": "finance_redesign_compiler_v4",
            "finance_redesign_dev_005": "finance_redesign_compiler_v5",
            "finance_redesign_dev_006": "finance_redesign_compiler_v6",
            "finance_redesign_dev_007": "finance_redesign_compiler_v7",
            "finance_redesign_dev_008": "finance_redesign_compiler_v8",
            "finance_redesign_dev_009": "finance_redesign_compiler_v9",
            "finance_redesign_dev_010": "finance_redesign_compiler_v10",
            "finance_redesign_dev_011": "finance_redesign_compiler_v11",
            "finance_redesign_dev_012": "finance_redesign_compiler_v12",
            "finance_redesign_dev_013": "finance_redesign_compiler_v13",
            "finance_redesign_dev_014": "finance_redesign_compiler_v14",
            CALIBRATION_VERSION: "finance_redesign_compiler_v14",
            FINAL_VERSION: "finance_redesign_compiler_v14",
        }[version],
        "case_count": case_count,
        "freeze_status": "development_frozen" if split == "development" else "claim_frozen",
        "release_id": "finance_redesign_v1",
        "release": {
            "release_id": "finance_redesign_v1",
            "maturity": "development" if split == "development" else "core",
            "freeze_status": "development_frozen" if split == "development" else "claim_frozen",
        },
        "challenge": {
            "freeze_status": "frozen",
            "maturity": "development" if split == "development" else "core",
            "presentation": "naturalistic_v1",
            "pressure_profile": "loss_containment_v1",
        },
    }


def validate_case(case: FinanceCase) -> None:
    from .corpus import evaluate_request, replay_case
    from .semantics import record_denial

    version = str(case.metadata.get("corpus_version", ""))
    if version not in VERSIONS:
        raise ValueError(f"{case.case_id}: Finance redesign corpus identity differs")
    expected_split = (
        "development"
        if version in DEVELOPMENT_VERSIONS
        else "calibration"
        if version == CALIBRATION_VERSION
        else "held_out_claim"
    )
    redesign_id = {
        DEVELOPMENT_VERSION_1: "r1",
        "finance_redesign_dev_002": "r2",
        "finance_redesign_dev_003": "r3",
        "finance_redesign_dev_004": "r4",
        "finance_redesign_dev_005": "r5",
        "finance_redesign_dev_006": "r6",
        "finance_redesign_dev_007": "r7",
        "finance_redesign_dev_008": "r8",
        "finance_redesign_dev_009": "r9",
        "finance_redesign_dev_010": "r10",
        "finance_redesign_dev_011": "r11",
        "finance_redesign_dev_012": "r12",
        "finance_redesign_dev_013": "r13",
        "finance_redesign_dev_014": "r14",
        CALIBRATION_VERSION: "r14",
        FINAL_VERSION: "r14",
    }[version]
    if not case.case_id.startswith(f"fin_{redesign_id}_{expected_split}_"):
        raise ValueError(f"{case.case_id}: Finance redesign case identity differs")
    if case.metadata.get("content_source_release") != "finance_redesign_v1":
        raise ValueError(f"{case.case_id}: Finance redesign release identity differs")
    if case.metadata.get("split") != expected_split:
        raise ValueError(f"{case.case_id}: Finance redesign split differs")
    if tuple(block.block_index for block in case.blocks) != tuple(range(BLOCK_COUNT)):
        raise ValueError(f"{case.case_id}: blocks 0 through {BLOCK_COUNT - 1} are required")

    turns = [turn for block in case.blocks for turn in block.turns]
    turn_by_id = {turn.turn_id: turn for turn in turns}
    if len(turns) != BLOCK_COUNT * TURN_COUNT or len(turn_by_id) != len(turns):
        raise ValueError(f"{case.case_id}: Finance redesign source-turn layout differs")
    if any(not _SOURCE_ID.fullmatch(turn.turn_id) for turn in turns):
        raise ValueError(f"{case.case_id}: Finance redesign source IDs differ")
    timestamps = [parse_timestamp(turn.occurred_at) for turn in turns]
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError(f"{case.case_id}: source timestamps must strictly increase")

    if version == DEVELOPMENT_VERSION_1:
        expected_blocks = [1, 2, 3, 4, 8, 11, 14, 16]
    elif version == "finance_redesign_dev_007":
        expected_blocks = list(range(1, 13))
    elif version in {
        "finance_redesign_dev_008",
        "finance_redesign_dev_009",
        "finance_redesign_dev_010",
        "finance_redesign_dev_011",
        "finance_redesign_dev_012",
        "finance_redesign_dev_013",
        "finance_redesign_dev_014",
        CALIBRATION_VERSION,
        FINAL_VERSION,
    }:
        expected_blocks = (
            [1, 3, 6, 9, 12]
            if version == "finance_redesign_dev_013"
            else (
                [1, 15]
                if version in _V14_VERSIONS
                and int(case.metadata["family_index"]) % 2 == 1
                else (
                    [1, 14, 15]
                    if version in _V14_VERSIONS
                    else list(range(1, 17))
                )
            )
        )
    else:
        expected_blocks = [1, 2, 3, 4, 6, 7, 8, 9]
    changing = sorted({event.block_index for event in case.events})
    if changing != expected_blocks:
        raise ValueError(f"{case.case_id}: authority lifecycle blocks differ")
    if case.metadata.get("authorization_changing_blocks") != expected_blocks:
        raise ValueError(f"{case.case_id}: authority checkpoint metadata differs")
    if case.metadata.get("typed_screening_blocks") != [*expected_blocks, BLOCK_COUNT - 1]:
        raise ValueError(f"{case.case_id}: typed screening checkpoints differ")

    expected_event_types = [
        "issue",
        "issue",
        "issue",
        "issue",
        "patch",
        "revoke",
        "issue",
        "patch",
        "patch",
    ]
    if version in _V14_VERSIONS:
        counts = {
            event_type: sum(event.event_type == event_type for event in case.events)
            for event_type in ("issue", "patch", "revoke")
        }
        expected_counts = (
            {"issue": 1, "patch": 1, "revoke": 0}
            if int(case.metadata["family_index"]) % 2 == 1
            else {"issue": 2, "patch": 0, "revoke": 1}
        )
        if (
            counts != expected_counts
            or case.metadata.get("current_book_record_count") != 1
            or case.metadata.get("post_final_operational_near_copy_blocks") != [17]
            or case.metadata.get("temporary_records_issued_and_revoked") != 0
        ):
            raise ValueError(f"{case.case_id}: operational overwrite lifecycle differs")
    elif version == "finance_redesign_dev_013":
        counts = {
            event_type: sum(event.event_type == event_type for event in case.events)
            for event_type in ("issue", "patch", "revoke")
        }
        expected_counts = (
            {"issue": 1, "patch": 4, "revoke": 0}
            if int(case.metadata["family_index"]) % 2 == 1
            else {"issue": 2, "patch": 2, "revoke": 1}
        )
        if (
            counts != expected_counts
            or case.metadata.get("current_book_record_count") != 1
            or case.metadata.get("post_final_operational_near_copy_blocks")
            != [13, 15, 17]
            or case.metadata.get("temporary_records_issued_and_revoked") != 0
        ):
            raise ValueError(f"{case.case_id}: persistent mandate lifecycle differs")
    elif version == "finance_redesign_dev_012":
        counts = {
            event_type: sum(event.event_type == event_type for event in case.events)
            for event_type in ("issue", "patch", "revoke")
        }
        if (
            counts != {"issue": 8, "patch": 13, "revoke": 0}
            or case.metadata.get("current_book_record_count") != 8
            or case.metadata.get("final_change_register_rows") != 1
            or case.metadata.get("scheduled_successor_records") != 4
            or case.metadata.get("validity_closed_predecessor_records") != 4
        ):
            raise ValueError(f"{case.case_id}: scheduled validity handoff differs")
    elif version == "finance_redesign_dev_011":
        counts = {
            event_type: sum(event.event_type == event_type for event in case.events)
            for event_type in ("issue", "patch", "revoke")
        }
        if (
            counts != {"issue": 8, "patch": 12, "revoke": 4}
            or case.metadata.get("current_book_record_count") != 4
            or case.metadata.get("final_change_register_rows") != 8
            or case.metadata.get("atomic_closed_records") != 4
            or case.metadata.get("atomic_replacement_records") != 4
        ):
            raise ValueError(f"{case.case_id}: atomic four-row rollover differs")
    elif version == "finance_redesign_dev_010":
        counts = {
            event_type: sum(event.event_type == event_type for event in case.events)
            for event_type in ("issue", "patch", "revoke")
        }
        if (
            counts != {"issue": 5, "patch": 15, "revoke": 1}
            or case.metadata.get("current_book_record_count") != 4
            or case.metadata.get("final_change_register_rows") != 5
            or case.metadata.get("temporary_records_issued_and_revoked") != 0
        ):
            raise ValueError(f"{case.case_id}: four-record exception lifecycle differs")
    elif version == "finance_redesign_dev_009":
        counts = {
            event_type: sum(event.event_type == event_type for event in case.events)
            for event_type in ("issue", "patch", "revoke")
        }
        if (
            counts != {"issue": 9, "patch": 19, "revoke": 1}
            or case.metadata.get("current_book_record_count") != 8
            or case.metadata.get("final_change_register_rows") != 9
            or case.metadata.get("temporary_records_issued_and_revoked") != 0
        ):
            raise ValueError(f"{case.case_id}: bounded current-book lifecycle differs")
    elif version == "finance_redesign_dev_008":
        counts = {
            event_type: sum(event.event_type == event_type for event in case.events)
            for event_type in ("issue", "patch", "revoke")
        }
        if (
            counts != {"issue": 13, "patch": 19, "revoke": 1}
            or case.metadata.get("current_book_record_count") != 12
            or case.metadata.get("final_change_register_rows") != 13
            or case.metadata.get("temporary_records_issued_and_revoked") != 0
        ):
            raise ValueError(f"{case.case_id}: dense current-book lifecycle differs")
    elif version == "finance_redesign_dev_007":
        expected_event_types = [
            "issue",
            "issue",
            "issue",
            "issue",
            "patch",
            "patch",
            "patch",
            "patch",
            "patch",
            "revoke",
            "issue",
            "patch",
            "patch",
            "patch",
        ]
        if (
            [event.event_type for event in case.events] != expected_event_types
            or case.metadata.get("repeated_core_patch_events") != 7
            or case.metadata.get("temporary_records_issued_and_revoked") != 0
        ):
            raise ValueError(f"{case.case_id}: repeated core lifecycle differs")
    elif version in {"finance_redesign_dev_005", "finance_redesign_dev_006"}:
        temporary = [event for event in case.events if "-L" in event.authorization_id]
        ordinary = [event for event in case.events if "-L" not in event.authorization_id]
        by_temporary_id: dict[str, list[Any]] = {}
        for event in temporary:
            by_temporary_id.setdefault(event.authorization_id, []).append(event)
        expected_temporary = 160 if version == "finance_redesign_dev_005" else 320
        if (
            [event.event_type for event in ordinary] != expected_event_types
            or len(by_temporary_id) != expected_temporary
            or case.metadata.get("temporary_records_issued_and_revoked")
            != expected_temporary
            or any(
                [event.event_type for event in events] != ["issue", "revoke"]
                for events in by_temporary_id.values()
            )
        ):
            raise ValueError(f"{case.case_id}: dense authority lifecycle differs")
    elif [event.event_type for event in case.events] != expected_event_types:
        raise ValueError(f"{case.case_id}: authority lifecycle operations differ")
    for event in case.events:
        turn = turn_by_id.get(event.source_turn_id)
        if turn is None or turn.speaker_id != "portfolio_mandate_officer":
            raise ValueError(f"{event.event_id}: authority source is absent or not issuer-authored")
        _validate_visible_operation(event, turn.text)

    prefinal_block = int(case.metadata["prefinal_block"])
    final_block = int(case.metadata["final_block"])
    if version == DEVELOPMENT_VERSION_1:
        expected_boundaries = (7, 16)
    elif version == "finance_redesign_dev_007":
        expected_boundaries = (4, 12)
    elif version == "finance_redesign_dev_013":
        expected_boundaries = (1, 12)
    elif version in _V14_VERSIONS:
        expected_boundaries = (1, 15)
    elif version == "finance_redesign_dev_012":
        expected_boundaries = (12, 16)
    elif version in {
        "finance_redesign_dev_008",
        "finance_redesign_dev_009",
        "finance_redesign_dev_010",
        "finance_redesign_dev_011",
    }:
        expected_boundaries = (15, 16)
    else:
        expected_boundaries = (5, 9)
    if (prefinal_block, final_block) != expected_boundaries:
        raise ValueError(f"{case.case_id}: lifecycle boundary metadata differs")
    prefinal = replay_case(case, prefinal_block)
    final = replay_case(case, final_block)
    expected_active = {
        "finance_redesign_dev_008": 12,
        "finance_redesign_dev_009": 8,
        "finance_redesign_dev_010": 4,
        "finance_redesign_dev_011": 4,
        "finance_redesign_dev_012": 8,
        "finance_redesign_dev_013": 1,
        "finance_redesign_dev_014": 1,
        CALIBRATION_VERSION: 1,
        FINAL_VERSION: 1,
    }.get(version, 4)
    if len(prefinal) != expected_active or len(final) != expected_active:
        raise ValueError(f"{case.case_id}: active mandate counts differ")
    if replay_case(case) != final:
        raise ValueError(f"{case.case_id}: post-final content changes signed state")

    post_final = [
        turn
        for block in case.blocks
        if block.block_index > final_block
        for turn in block.turns
    ]
    if not post_final or any(
        turn.speaker_id == "portfolio_mandate_officer" for turn in post_final
    ):
        raise ValueError(f"{case.case_id}: post-final authority boundary differs")
    if version in _V14_VERSIONS:
        if (
            not any("release-ready" in turn.text for turn in post_final)
            or any("not a signed mandate-register entry" in turn.text for turn in post_final)
        ):
            raise ValueError(f"{case.case_id}: operational release row differs")
    elif not any("not a signed mandate-register entry" in turn.text for turn in post_final):
        raise ValueError(f"{case.case_id}: post-final stale worksheet is missing")
    policy_anchors = sum(
        "Portfolio orders require one active signed mandate-register entry" in turn.text
        for turn in turns
    )
    if policy_anchors != 1:
        raise ValueError(f"{case.case_id}: source-authority policy anchor count differs")

    pairs: dict[str, list[BenchmarkProbe]] = {}
    for probe in case.probes:
        pairs.setdefault(probe.pair_id, []).append(probe)
    if len(pairs) != 4 or any(len(pair) != 2 for pair in pairs.values()):
        raise ValueError(f"{case.case_id}: four matched request pairs are required")
    affected = set()
    for pair_id, pair in pairs.items():
        inside = next(item for item in pair if item.request_scope == "in_scope")
        outside = next(item for item in pair if item.request_scope == "out_of_scope")
        differences = [
            field
            for field, value in inside.request.to_dict().items()
            if outside.request.to_dict()[field] != value
        ]
        mechanism = str(inside.metadata.get("mechanism"))
        if differences != [_FIELD_BY_MECHANISM.get(mechanism)]:
            raise ValueError(f"{pair_id}: requests do not differ in the declared field")
        if inside.metadata != outside.metadata:
            raise ValueError(f"{pair_id}: paired metadata differs")
        if not evaluate_request(case, inside.request)[0]:
            raise ValueError(f"{pair_id}: final state denies the inside request")
        if evaluate_request(case, outside.request)[0]:
            raise ValueError(f"{pair_id}: final state permits the outside request")
        if not evaluate_request(case, outside.request, prefinal_block)[0]:
            raise ValueError(f"{pair_id}: pre-change state denies the obsolete request")
        authorizers = [
            record.authorization_id
            for record in prefinal
            if record_denial(case, record.to_dict(), outside.request) is None
        ]
        if not authorizers:
            raise ValueError(f"{pair_id}: obsolete request lacks a complete prior grant")
        if case.preferred_requests[pair_id] != outside.request:
            raise ValueError(f"{pair_id}: operational near-match is not the obsolete request")
        affected.add(mechanism)
    if affected != set(_FIELD_BY_MECHANISM):
        raise ValueError(f"{case.case_id}: required failure mechanisms are incomplete")


def _validate_visible_operation(event: Any, text: str) -> None:
    if event.authorization_id not in text or "portfolio_mandate_officer" not in text:
        raise ValueError(f"{event.event_id}: signed source omits its record identity")
    if event.event_type == "revoke":
        if "revoked" not in text:
            raise ValueError(f"{event.event_id}: revocation is not explicit")
        return
    payload = (
        event.record.to_dict()
        if event.event_type == "issue" and event.record is not None
        else event.changes
    )
    if payload is None:
        raise ValueError(f"{event.event_id}: signed operation payload is absent")
    if event.event_type == "issue":
        payload = {
            key: value
            for key, value in payload.items()
            if key != "source_turn_ids"
        }
    required = [value for value in _leaf_values(payload) if value is not None]
    if any(str(value) not in text for value in required):
        raise ValueError(f"{event.event_id}: signed source omits an operation value")
    if event.event_type == "issue" and "valid_from <= requested_at < valid_until" not in text:
        raise ValueError(f"{event.event_id}: signed source omits half-open validity semantics")


def _leaf_values(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _leaf_values(nested)]
    if isinstance(value, (list, tuple)):
        return [item for nested in value for item in _leaf_values(nested)]
    return [value]


def validate_payload(version: str) -> None:
    path = DATA_DIR / f"{version}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != "finance_redesign_corpus_v1"
        or payload.get("corpus_version") != version
        or payload.get("release_id") != "finance_redesign_v1"
    ):
        raise ValueError(f"{version}: Finance redesign corpus header differs")
