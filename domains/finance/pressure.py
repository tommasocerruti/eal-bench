from __future__ import annotations

from .models import FinanceCase


PROFILE_ID = "loss_containment_v1"
V2_PROFILE_ID = "loss_containment_v2"
PRESSURE_ID = "market_opportunity"


def addition(case: FinanceCase) -> str:
    return case.pressure_addition


def profile_id(case: FinanceCase) -> str:
    return profile_id_for_corpus(str(case.metadata.get("corpus_version", "")))


def profile_id_for_corpus(corpus_version: str) -> str:
    if corpus_version in {"calibration_v1", "benchmark_v1"}:
        return PROFILE_ID
    from .corpus_v2 import available_versions

    if corpus_version in available_versions():
        return V2_PROFILE_ID
    raise ValueError(f"unsupported Finance pressure corpus: {corpus_version!r}")
