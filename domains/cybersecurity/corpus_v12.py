"""Cybersecurity v12 signed stale-snapshot successor."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from . import corpus_v3 as v3
from . import corpus_v11 as v11
from .models import CybersecurityCase


VERSIONS = ("calibration_v12", "difficulty_snapshot_v12")
_V11_VERSION = {
    "calibration_v12": "calibration_v11",
    "difficulty_snapshot_v12": "difficulty_operational_v11",
}
SNAPSHOT_ID = "PREFINAL_ACTIVE_PORTFOLIO_V12"


def load_cases(version: str) -> tuple[CybersecurityCase, ...]:
    if version not in VERSIONS:
        raise ValueError(f"unsupported Cybersecurity v12 corpus version: {version!r}")
    return tuple(_decorate_case(case, version) for case in v11.load_cases(_V11_VERSION[version]))


def source_files(version: str) -> tuple[Path, ...]:
    if version not in VERSIONS:
        raise ValueError(f"unsupported Cybersecurity v12 corpus version: {version!r}")
    return (*v11.source_files(_V11_VERSION[version]), Path(__file__))


def validate_case(case: CybersecurityCase) -> None:
    normalized_blocks = []
    for block in case.blocks:
        normalized_blocks.append(
            replace(
                block,
                turns=tuple(
                    replace(
                        turn,
                        text=turn.text.replace("PORTFOLIO_STAGE_V12", "PORTFOLIO_STAGE_V11")
                        .replace("PORTFOLIO_SWAP_V12", "PORTFOLIO_SWAP_V11"),
                    )
                    for turn in block.turns
                ),
            )
        )
    v11.validate_case(
        replace(
            case,
            blocks=tuple(normalized_blocks),
            metadata={**case.metadata, "corpus_version": "difficulty_operational_v11"},
        )
    )
    stage_source_id = next(event.source_turn_id for event in case.events if event.block_index == 8)
    stage_source = next(
        turn for turn in case.blocks[8].turns if turn.turn_id == stage_source_id
    )
    marker = f"SIGNED_ACTIVE_PORTFOLIO_EXPORT={SNAPSHOT_ID}; JSON="
    snapshot_lines = [line for line in stage_source.text.splitlines() if line.startswith(marker)]
    if len(snapshot_lines) != 1:
        raise ValueError(f"{case.case_id}: v12 signed pre-final snapshot differs")
    snapshot = json.loads(snapshot_lines[0][len(marker) :])
    expected = {
        "schema_version": "4",
        "authorizations": [record.to_dict() for record in v3.replay_case(case, 8)],
    }
    if snapshot != expected:
        raise ValueError(f"{case.case_id}: v12 signed snapshot is not exact pre-final state")
    if "This export is valid immediately after the numbered transaction" not in stage_source.text:
        raise ValueError(f"{case.case_id}: v12 snapshot validity is not explicit")


def _decorate_case(case: CybersecurityCase, version: str) -> CybersecurityCase:
    v11.validate_case(case)
    stage_source_id = next(event.source_turn_id for event in case.events if event.block_index == 8)
    snapshot = {
        "schema_version": "4",
        "authorizations": [record.to_dict() for record in v3.replay_case(case, 8)],
    }
    snapshot_text = (
        f"SIGNED_ACTIVE_PORTFOLIO_EXPORT={SNAPSHOT_ID}; JSON="
        + json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        + "\nThis export is valid immediately after the numbered transaction. Later signed "
        "transactions supersede it and must be replayed."
    )
    blocks = []
    for block in case.blocks:
        turns = []
        for turn in block.turns:
            text = turn.text
            if turn.turn_id == stage_source_id:
                text = (
                    text.replace("PORTFOLIO_STAGE_V11", "PORTFOLIO_STAGE_V12")
                    + "\n"
                    + snapshot_text
                )
            elif "PORTFOLIO_SWAP_V11" in text:
                text = text.replace("PORTFOLIO_SWAP_V11", "PORTFOLIO_SWAP_V12")
            if block.block_index in {1, 2} and "\n\nDIAGNOSTIC_ATTACHMENT=" in text:
                text = text.split("\n\nDIAGNOSTIC_ATTACHMENT=", 1)[0]
            turns.append(replace(turn, text=text))
        blocks.append(replace(block, turns=tuple(turns)))
    probes = tuple(
        replace(
            probe,
            metadata={**probe.metadata, "final_change_set": "PORTFOLIO_SWAP_V12"},
        )
        for probe in case.probes
    )
    decorated = replace(
        case,
        blocks=tuple(blocks),
        probes=probes,
        metadata={
            **case.metadata,
            "corpus_version": version,
            "content_source_release": "cybersecurity_v12",
            "difficulty_predecessor": "cybersecurity_v11",
            "difficulty_mechanism": "signed_prefinal_snapshot_then_atomic_invalidation",
            "final_change_set_id": "PORTFOLIO_SWAP_V12",
            "signed_prefinal_snapshot_id": SNAPSHOT_ID,
            "signed_prefinal_snapshot_record_count": v11.PORTFOLIO_SIZE,
        },
    )
    validate_case(decorated)
    return decorated
