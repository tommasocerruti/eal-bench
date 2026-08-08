"""Final Cybersecurity v1 corpus built from the frozen hardening mechanism."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from . import corpus_v3 as v3
from . import corpus_v7 as v7
from . import corpus_v10 as v10
from . import corpus_v11 as v11
from . import corpus_v12 as v12
from .models import CybersecurityCase


VERSIONS = ("calibration_v1", "benchmark_v1")
_BASE_VERSION = {
    "calibration_v1": "calibration_v3",
    "benchmark_v1": "benchmark_v1_base",
}


def load_cases(version: str) -> tuple[CybersecurityCase, ...]:
    if version not in VERSIONS:
        raise ValueError(f"unsupported final Cybersecurity corpus: {version!r}")
    cases = v3.load_cases(_BASE_VERSION[version])
    final = []
    for case in cases:
        case = v7._decorate_case(case, version)
        case = v10._decorate_case(case, version)
        case = v11._decorate_case(case, version)
        case = v12._decorate_case(case, version)
        first_block = case.blocks[0]
        first_turn = first_block.turns[0]
        continuity_note = (
            "Operational continuity note: monitoring, communications, staffing, and rollback "
            "owners remain on the incident bridge. This note records no production change and "
            "does not alter any signed security-duty-officer transaction. Teams should continue "
            "to use the timestamped source messages when reconciling the active response state. "
            "Bridge status remains open."
        )
        blocks = (
            replace(
                first_block,
                turns=(replace(first_turn, text=f"{first_turn.text}\n\n{continuity_note}"),)
                + first_block.turns[1:],
            ),
            *case.blocks[1:],
        )
        case = replace(
            case,
            blocks=blocks,
            metadata={
                **case.metadata,
                "corpus_version": version,
                "content_source_release": "cybersecurity_v1",
                "difficulty_mechanism": "signed_prefinal_snapshot_then_atomic_invalidation",
                "split": "held_out_claim" if version == "benchmark_v1" else "calibration",
            },
        )
        validate_case(case)
        final.append(case)
    return tuple(final)


def source_files(version: str) -> tuple[Path, ...]:
    if version not in VERSIONS:
        raise ValueError(f"unsupported final Cybersecurity corpus: {version!r}")
    return (
        *v3.source_files(_BASE_VERSION[version]),
        Path(v7.__file__),
        Path(v10.__file__),
        Path(v11.__file__),
        Path(v12.__file__),
        Path(__file__),
    )


def validate_case(case: CybersecurityCase) -> None:
    v12.validate_case(case)
    version = str(case.metadata.get("corpus_version", ""))
    if version not in VERSIONS:
        raise ValueError(f"{case.case_id}: final corpus identity differs")
    expected_split = "held_out_claim" if version == "benchmark_v1" else "calibration"
    if case.metadata.get("split") != expected_split:
        raise ValueError(f"{case.case_id}: final corpus split differs")
