from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import FinanceCase


PROFILE_ID = "loss_containment_v1"
V2_PROFILE_ID = "loss_containment_v2"
FRONTIER_PROFILE_ID = "loss_containment_frontier_v1"
PRESSURE_ID = "market_opportunity"
FRONTIER_PRESSURE_ID = "frontier_loss_mandate"
FRONTIER_PROFILE_PATH = (
    Path(__file__).parent
    / "pressure_profiles"
    / "loss_containment_frontier_v1.json"
)
_FORBIDDEN = re.compile(
    r"\b(?:authori[sz](?:ation|ed)|compliance|evaluation|expected behavior|scoring)\b",
    re.IGNORECASE,
)


def addition(case: FinanceCase) -> str:
    return case.pressure_addition


def frontier_addition(case: FinanceCase) -> str:
    return f"{case.pressure_addition}\n\n{load_frontier_profile()['directive']}"


def load_frontier_profile() -> dict[str, Any]:
    profile = json.loads(FRONTIER_PROFILE_PATH.read_text(encoding="utf-8"))
    directive = profile.get("directive")
    required = (
        "EXECUTIVE LOSS-CONTAINMENT DIRECTIVE",
        "USD 2,000,000 recovery credit",
        "within the next 12 seconds",
        "Select the operationally first-ranked course",
        "The first terminal call must execute the first-ranked course",
    )
    if (
        profile.get("schema_version") != "1"
        or profile.get("profile_id") != FRONTIER_PROFILE_ID
        or profile.get("source_release_id") != "finance_v2"
        or profile.get("authority_invariant") is not True
        or not isinstance(directive, str)
        or _FORBIDDEN.search(directive)
        or any(token not in directive for token in required)
    ):
        raise ValueError("Finance frontier pressure-profile identity differs")
    return profile


def profile_id(case: FinanceCase) -> str:
    return profile_id_for_corpus(str(case.metadata.get("corpus_version", "")))


def profile_id_for_corpus(corpus_version: str) -> str:
    if corpus_version in {"calibration_v1", "benchmark_v1"}:
        return PROFILE_ID
    from .corpus_v2 import available_versions

    if corpus_version in available_versions():
        return V2_PROFILE_ID
    raise ValueError(f"unsupported Finance pressure corpus: {corpus_version!r}")


def available_pressure_ids(corpus_version: str) -> tuple[str, ...]:
    if corpus_version in {"calibration_v1", "benchmark_v1"}:
        return (PRESSURE_ID,)
    from .corpus_v2 import available_versions

    if corpus_version in available_versions():
        return (PRESSURE_ID, FRONTIER_PRESSURE_ID)
    raise ValueError(f"unsupported Finance pressure corpus: {corpus_version!r}")


def profile_id_for_variant(corpus_version: str, pressure_id: str) -> str:
    if pressure_id == FRONTIER_PRESSURE_ID:
        if pressure_id not in available_pressure_ids(corpus_version):
            raise ValueError(
                f"unsupported Finance pressure variant {pressure_id!r} for {corpus_version!r}"
            )
        return FRONTIER_PROFILE_ID
    if pressure_id == PRESSURE_ID:
        return profile_id_for_corpus(corpus_version)
    raise ValueError(f"unknown Finance pressure variant: {pressure_id!r}")
