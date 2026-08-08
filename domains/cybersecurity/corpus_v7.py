"""Cybersecurity v7 action-tool wrapper over the frozen v3 state-swap corpus."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from domains.base import BenchmarkProbe

from . import corpus_v3 as v3
from .models import CybersecurityCase, ResponseRequest


VERSIONS = ("calibration_v7", "difficulty_dev_v7")
_V3_VERSION = {
    "calibration_v7": "calibration_v3",
    "difficulty_dev_v7": "difficulty_dev_v3",
}


def load_cases(version: str) -> tuple[CybersecurityCase, ...]:
    if version not in VERSIONS:
        raise ValueError(f"unsupported Cybersecurity v7 corpus version: {version!r}")
    return tuple(_decorate_case(case, version) for case in v3.load_cases(_V3_VERSION[version]))


def source_files(version: str) -> tuple[Path, ...]:
    if version not in VERSIONS:
        raise ValueError(f"unsupported Cybersecurity v7 corpus version: {version!r}")
    return (*v3.source_files(_V3_VERSION[version]), Path(__file__))


def validate_case(case: CybersecurityCase) -> None:
    v3.validate_case(case)
    for probe in case.probes:
        expected = case.preferred_requests[probe.pair_id]
        if probe.request.execution_course != "submitted_payload":
            raise ValueError(f"{probe.probe_id}: submitted request has the wrong v7 identity")
        if probe.request.operational_near_match != expected.to_dict():
            raise ValueError(f"{probe.probe_id}: operational payload differs")
        if expected.execution_course != "operational_payload":
            raise ValueError(f"{probe.pair_id}: preferred request has the wrong v7 identity")


def _decorate_case(case: CybersecurityCase, version: str) -> CybersecurityCase:
    preferred = {
        pair_id: _with_identity(
            request,
            course="operational_payload",
            operational=request,
        )
        for pair_id, request in case.preferred_requests.items()
    }
    probes: list[BenchmarkProbe] = []
    for probe in case.probes:
        request = _with_identity(
            probe.request,
            course="submitted_payload",
            operational=case.preferred_requests[probe.pair_id],
        )
        probes.append(replace(probe, request=request))
    decorated = replace(
        case,
        probes=tuple(probes),
        preferred_request=preferred[next(iter(preferred))],
        preferred_requests=preferred,
        metadata={
            **case.metadata,
            "corpus_version": version,
            "execution_protocol": "dedicated_fixed_confirmation_actions_v7",
            "content_source_release": "cybersecurity_v3",
            "failed_protocol_predecessor": "cybersecurity_v6",
        },
    )
    validate_case(decorated)
    return decorated


def _with_identity(
    request: ResponseRequest,
    *,
    course: str,
    operational: ResponseRequest,
) -> ResponseRequest:
    return replace(
        request,
        execution_course=course,
        operational_near_match=operational.to_dict(),
    )
