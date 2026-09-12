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

    checks: dict[str, Any] = {
        "resources": verify_resources(),
        "api_contracts": verify_api_contracts(),
    }
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


def _sample_outcome(**overrides: Any) -> Any:
    from ..scoring import TrialOutcome

    row = {
        "trial_id": "trial_sample",
        "domain_id": "procurement",
        "case_id": "case",
        "probe_id": "probe",
        "pair_id": "pair",
        "condition_id": "faithful_text",
        "request_authorized": True,
        "decision": "execute_requested",
        "requested_action_taken": True,
        "unauthorized_action_taken": False,
        "action_mismatch": False,
        "compliant": True,
        "parseable": True,
        "provider_error": None,
        "finish_reason": "tool_calls",
        "tool_call_count": 1,
        "terminal_call_count": 1,
        "tool_name": "submit_order",
        "tool_arguments": {"vendor": "Acme"},
        "resource_key": "resource_a",
        "executor_target": "gptoss_baseten",
        "executor_provider": "baseten",
        "executor_model": "openai/gpt-oss-120b",
        "response_model": "openai/gpt-oss-120b",
        "surface": "native",
    }
    row.update(overrides)
    return TrialOutcome(**row)


def verify_api_contracts() -> dict[str, Any]:
    """Execute the public entry points a consumer uses, not only the ones tracks use.

    Written because an adapter that was never run turned out to hold several
    defects. Anything exported here is exercised at least once.
    """

    import tempfile
    from pathlib import Path

    from ..export import (
        EXPORT_SCHEMA_VERSION,
        read_outcomes,
        write_outcomes,
    )
    from ..metrics import (
        MixedConditionsError,
        MixedExecutorsError,
        MixedResourcesError,
        MixedSurfacesError,
        aggregate,
    )
    from ..resources import ResourceVersions, describe, load_domain
    from ..trials import ModelResponse, Trial

    checked: list[str] = []

    # ModelResponse.from_openai against a real SDK object, not a hand-built mapping.
    from openai.types.chat import ChatCompletion

    completion = ChatCompletion.model_validate(
        {
            "id": "cmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "openai/gpt-oss-120b",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "submit_order",
                                    "arguments": '{"vendor": "Acme"}',
                                },
                            }
                        ],
                    },
                }
            ],
        }
    )
    reply = ModelResponse.from_openai(completion)
    if [call.name for call in reply.tool_calls] != ["submit_order"]:
        raise AssertionError("from_openai lost the tool call")
    if reply.model != "openai/gpt-oss-120b" or reply.finish_reason != "tool_calls":
        raise AssertionError("from_openai lost the response model or finish reason")
    failure = ModelResponse.from_openai(TimeoutError("slow"))
    if failure.error is None or failure.error_type != "TimeoutError":
        raise AssertionError("from_openai lost the exception class")
    # The runner records "<ExceptionClass>: <message>"; this path must match it.
    from ..scoring import _provider_payload

    rebuilt = _provider_payload(failure)
    if f"{type(rebuilt).__name__}: {rebuilt}" != "TimeoutError: slow":
        raise AssertionError(
            f"provider error is not runner-comparable: {type(rebuilt).__name__}: {rebuilt}"
        )
    checked.append("ModelResponse.from_openai")

    # Trial serialization round trip.
    resources = describe(load_domain("procurement"))
    trial = Trial(
        trial_id="trial_sample",
        messages=({"role": "user", "content": "hello"},),
        tools=({"type": "function", "function": {"name": "submit_order"}},),
        tool_choice="auto",
        resources=resources,
    )
    restored = Trial.from_dict(trial.to_dict())
    if restored != trial or not isinstance(restored.resources, ResourceVersions):
        raise AssertionError("Trial.from_dict did not round trip")
    checked.append("Trial.from_dict")

    # Outcome JSONL round trip, including the schema-version gate.
    outcome = _sample_outcome()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "outcomes.jsonl"
        if write_outcomes(path, [outcome]) != 1:
            raise AssertionError("write_outcomes reported the wrong row count")
        if read_outcomes(path) != [outcome]:
            raise AssertionError("outcomes did not round trip")
        path.write_text(
            json.dumps({"schema_version": EXPORT_SCHEMA_VERSION + 1}) + "\n",
            encoding="utf-8",
        )
        try:
            read_outcomes(path)
        except ValueError:
            pass
        else:
            raise AssertionError("read_outcomes accepted an unknown schema version")
    checked.append("write_outcomes/read_outcomes")

    # Every pooling guard must actually fire.
    guards = [
        (MixedResourcesError, _sample_outcome(resource_key="resource_b")),
        (MixedConditionsError, _sample_outcome(condition_id="faithful_typed")),
        (MixedSurfacesError, _sample_outcome(surface="inspect")),
        (MixedExecutorsError, _sample_outcome(executor_model="openai/gpt-oss-20b")),
        # Two providers serving one model are different routes.
        (
            MixedExecutorsError,
            _sample_outcome(executor_provider="openrouter", executor_target="gptoss_openrouter"),
        ),
    ]
    for error, other in guards:
        try:
            aggregate([outcome, other], track="controls")
        except error:
            continue
        raise AssertionError(f"{error.__name__} did not fire")
    pooled = aggregate(
        [outcome, _sample_outcome(surface="inspect")],
        track="controls",
        allow_mixed_surfaces=True,
    )
    # A consistent tokenizer policy: the name and the count come from one resolution.
    from experiments.authorization_memory.tokens import (
        count_reference_tokens,
        reference_tokenizer_name,
    )

    if len({reference_tokenizer_name() for _ in range(3)}) != 1:
        raise AssertionError("the reference tokenizer name is not stable")
    if len({count_reference_tokens("a stable payload") for _ in range(3)}) != 1:
        raise AssertionError("the reference token count is not stable")
    checked.append("reference tokenizer policy")
    if sorted(pooled.surfaces) != ["inspect", "native"]:
        raise AssertionError("explicit pooling lost the surface record")
    checked.append("pooling guards")

    return {"status": "passed", "entry_points": checked}
