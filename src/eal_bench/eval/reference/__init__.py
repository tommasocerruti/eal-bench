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
    from experiments.authorization_memory.tokens import reference_tokenizer_name

    checks: dict[str, Any] = {"resources": verify_resources()}
    checks.update(_optional_track_checks())
    return {
        "status": "passed",
        "network_request_made": False,
        # cl100k_base needs a download on first use. An offline install falls back to
        # the regex counter, which changes token counts, so name it in the output.
        "reference_tokenizer": reference_tokenizer_name(),
        "checks": checks,
    }


_TRACK_MODULES = ("controls", "preservation")


def _optional_track_checks() -> dict[str, Any]:
    """Run every track verifier that is installed.

    A track that is absent is reported as skipped. A track that is present but fails
    to import is an error, not a silent pass.
    """

    from importlib import import_module, util

    package = __package__.rsplit(".", 1)[0]
    found: dict[str, Any] = {}
    for name in _TRACK_MODULES:
        qualified = f"{package}.{name}"
        if util.find_spec(qualified) is None:
            found[name] = {
                "status": "skipped",
                "reason": f"{qualified} is not installed",
            }
            continue
        found[name] = import_module(qualified).verify_reference()
    return found
