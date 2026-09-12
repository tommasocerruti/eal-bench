"""Offline reference verification.

Runs from an installed wheel with no repository checkout and no credentials. Each
track adds a fixture directory under `reference/`; this module loads them and
re-derives every recorded value.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from .. import resources as eval_resources

__all__ = ["load_fixture", "verify", "verify_resources"]

_PACKAGE = __name__


def load_fixture(name: str) -> Any:
    handle = resources.files(_PACKAGE).joinpath(name)
    if not handle.is_file():
        raise FileNotFoundError(f"missing reference fixture {name!r}")
    return json.loads(handle.read_text(encoding="utf-8"))


def verify_resources() -> dict[str, Any]:
    """Resource identity must match the recorded snapshot for every domain."""

    expected = load_fixture("resource_versions.json")
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for domain_id, recorded in sorted(expected["domains"].items()):
        domain = eval_resources.load_domain(domain_id)
        observed = eval_resources.describe(domain).to_dict()
        checked += 1
        if observed != recorded:
            differing = sorted(
                key
                for key in set(observed) | set(recorded)
                if observed.get(key) != recorded.get(key)
            )
            mismatches.append({"domain_id": domain_id, "fields": differing})
    if mismatches:
        raise AssertionError(f"resource identity drifted: {mismatches}")
    return {
        "status": "passed",
        "domains_checked": checked,
        "protocol_id": eval_resources.PROTOCOL_ID,
        "scorer_id": eval_resources.SCORER_ID,
    }


def verify() -> dict[str, Any]:
    checks: dict[str, Any] = {"resources": verify_resources()}
    checks.update(_optional_track_checks())
    return {
        "status": "passed",
        "network_request_made": False,
        "checks": checks,
    }


def _optional_track_checks() -> dict[str, Any]:
    """Track verifiers register here as each track lands."""

    found: dict[str, Any] = {}
    try:
        from ..controls import verify_reference as verify_controls
    except ImportError:
        pass
    else:
        found["controls"] = verify_controls()
    try:
        from ..preservation import verify_reference as verify_preservation
    except ImportError:
        pass
    else:
        found["preservation"] = verify_preservation()
    return found
