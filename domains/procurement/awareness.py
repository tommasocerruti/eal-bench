from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from domains.base import AuthorizationMemoryDomain, AwarenessProtocolSpec


def _run(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> Path:
    from experiments.authorization_memory.evaluation_awareness import (
        run_evaluation_awareness,
    )

    return run_evaluation_awareness(domain, cases, options)


def _validate(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> None:
    from experiments.authorization_memory.evaluation_awareness import (
        validate_evaluation_awareness,
    )

    validate_evaluation_awareness(domain, cases, options)


def protocols() -> dict[str, AwarenessProtocolSpec]:
    core = AwarenessProtocolSpec(
        protocol_id="v1",
        description=(
            "Core procurement awareness protocol over matched benchmark "
            "and deployment-like controls."
        ),
        core_protocol=True,
        expected_contexts=72,
        expected_jobs=216,
        control_match_count=12,
        runner=_run,
        offline_validator=_validate,
        minimum_control_authors=4,
        maximum_controls_per_author=3,
        benchmark_corpus_version="benchmark_v1",
        presentation_id="naturalistic_v1",
    )
    smoke = AwarenessProtocolSpec(
        protocol_id="smoke_v1",
        description=(
            "Six-call, non-core procurement diagnostic plumbing check."
        ),
        core_protocol=False,
        expected_contexts=2,
        expected_jobs=6,
        control_match_count=1,
        runner=_run,
        offline_validator=_validate,
    )
    return {
        core.protocol_id: core,
        smoke.protocol_id: smoke,
    }
