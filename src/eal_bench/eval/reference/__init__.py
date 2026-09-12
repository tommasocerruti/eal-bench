"""Offline reference verification.

Runs from an installed wheel with no repository checkout and no credentials. Each
track adds a fixture directory under `reference/`; this module loads them and
re-derives every recorded value.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib import resources
from typing import Any

from .. import resources as eval_resources

__all__ = ["load_fixture", "verify", "verify_inspect", "verify_resources"]

_ABSENT = object()

_PACKAGE = __name__


def _differing_keys(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> list[str]:
    """Compare by key presence as well as value, so a new field is not read as None."""

    return sorted(
        key
        for key in set(observed) | set(expected)
        if observed.get(key, _ABSENT) != expected.get(key, _ABSENT)
    )


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
            mismatches.append(
                {
                    "domain_id": domain_id,
                    "fields": _differing_keys(observed, recorded),
                }
            )
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
    if found.get("controls", {}).get("status") != "skipped":
        found["inspect"] = verify_inspect()
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
    if sorted(pooled.surfaces) != ["inspect", "native"]:
        raise AssertionError("explicit pooling lost the surface record")
    checked.append("pooling guards")

    return {"status": "passed", "entry_points": checked}


def _controls_fixture_path() -> str:
    return "controls_outcomes.json"


def build_controls_fixture() -> dict[str, Any]:
    """Recorded executor replies covering every outcome class the scorer emits."""

    from ..controls import build_control_trials
    from ..scoring import score_response

    rows: list[dict[str, Any]] = []
    for domain_id in eval_resources.list_domains():
        domain = eval_resources.load_domain(domain_id)
        pairs = build_control_trials(domain_id, check_leakage=False)
        by_pair: dict[str, list[Any]] = {}
        for _, truth in pairs:
            by_pair.setdefault(truth.pair_id, []).append(truth)
        for truth in _fixture_truths(pairs):
            partner = next(
                other
                for other in by_pair[truth.pair_id]
                if other.probe_id != truth.probe_id and other.condition_id == truth.condition_id
            )
            for label, response in _fixture_responses(domain, truth, partner):
                rows.append(
                    {
                        "label": label,
                        "domain_id": domain_id,
                        "trial_id": truth.trial_id,
                        "response": response.to_dict(),
                        "expected": score_response(truth, response).to_dict(),
                    }
                )
    return {"schema_version": 1, "rows": rows}


def _fixture_truths(pairs: list[Any]) -> list[Any]:
    """One authorized and one unauthorized trial per faithful condition."""

    picked: dict[tuple[str, bool], Any] = {}
    for _, truth in pairs:
        picked.setdefault((truth.condition_id, truth.request_authorized), truth)
    return [picked[key] for key in sorted(picked, key=lambda key: (key[0], key[1]))]


def _fixture_responses(domain: Any, truth: Any, partner: Any) -> list[tuple[str, Any]]:
    from ..trials import ModelResponse

    action_tool = domain.action_tools[0]
    arguments = domain.conformance.action_arguments(truth.probe.request, action_tool)
    # Domains with two action tools separate the submitted action from the operational
    # alternative by tool. Procurement has one, so the partner's payload is the other action.
    if len(domain.action_tools) > 1:
        other_tool = domain.action_tools[1]
        other = domain.conformance.action_arguments(truth.probe.request, other_tool)
    else:
        other_tool = action_tool
        other = domain.conformance.action_arguments(partner.probe.request, action_tool)
    escalate, decline = (name for name in domain.terminal_tools if name not in domain.action_tools)
    escalate_arguments = domain.conformance.action_arguments(truth.probe.request, escalate)
    decline_arguments = domain.conformance.action_arguments(truth.probe.request, decline)
    return [
        ("execute_requested", ModelResponse.from_tool_calls([(action_tool, arguments)])),
        ("execute_other", ModelResponse.from_tool_calls([(other_tool, other)])),
        ("escalate", ModelResponse.from_tool_calls([(escalate, escalate_arguments)])),
        ("decline", ModelResponse.from_tool_calls([(decline, decline_arguments)])),
        ("malformed_arguments", ModelResponse.from_tool_calls([(action_tool, "{not json")])),
        (
            "multiple_tool_calls",
            ModelResponse.from_tool_calls([(action_tool, arguments), (decline, decline_arguments)]),
        ),
        ("unknown_tool", ModelResponse.from_tool_calls([("no_such_tool", {})])),
        (
            "missing_tool_call",
            ModelResponse(text="I would need approval first.", finish_reason="stop"),
        ),
        ("provider_error", ModelResponse.provider_error("timeout after 60s")),
    ]


def verify_controls() -> dict[str, Any]:
    """Re-score every recorded reply and require the frozen outcome."""

    from ..controls import build_control_trials
    from ..scoring import score_response
    from ..trials import ModelResponse

    fixture = load_fixture(_controls_fixture_path())
    truths: dict[str, Any] = {}
    mismatches: list[dict[str, Any]] = []
    for row in fixture["rows"]:
        domain_id = row["domain_id"]
        if domain_id not in truths:
            truths[domain_id] = {
                truth.trial_id: truth
                for _, truth in build_control_trials(domain_id, check_leakage=False)
            }
        truth = truths[domain_id].get(row["trial_id"])
        if truth is None:
            mismatches.append({"label": row["label"], "reason": "trial_id not built"})
            continue
        observed = score_response(truth, ModelResponse.from_dict(row["response"])).to_dict()
        if observed != row["expected"]:
            mismatches.append(
                {
                    "label": row["label"],
                    "domain_id": domain_id,
                    "fields": _differing_keys(observed, row["expected"]),
                }
            )
    if mismatches:
        raise AssertionError(f"control outcomes drifted: {mismatches}")
    return {
        "status": "passed",
        "rows_checked": len(fixture["rows"]),
        "labels": sorted({row["label"] for row in fixture["rows"]}),
        "determinism": verify_controls_determinism(),
    }


def verify_controls_determinism() -> dict[str, Any]:
    """Two builds must produce identical trial ids and identical model-visible content."""

    from ..controls import build_control_trials

    checked = 0
    for domain_id in eval_resources.list_domains():
        first = build_control_trials(domain_id, check_leakage=False)
        second = build_control_trials(domain_id, check_leakage=False)
        if len(first) != len(second):
            raise AssertionError(f"{domain_id}: trial count is not deterministic")
        for (trial_a, truth_a), (trial_b, truth_b) in zip(first, second):
            if trial_a.trial_id != trial_b.trial_id:
                raise AssertionError(f"{domain_id}: trial ids are not deterministic")
            if trial_a.to_dict() != trial_b.to_dict():
                raise AssertionError(
                    f"{domain_id}: trial {trial_a.trial_id} content is not deterministic"
                )
            if truth_a.to_dict() != truth_b.to_dict():
                raise AssertionError(
                    f"{domain_id}: truth for {trial_a.trial_id} is not deterministic"
                )
        if len({trial.trial_id for trial, _ in first}) != len(first):
            raise AssertionError(f"{domain_id}: trial ids are not unique")
        checked += len(first)
    return {"status": "passed", "trials_checked": checked}


def _inspect_output(response: dict[str, Any]) -> Any:
    from inspect_ai.model import ChatCompletionChoice, ChatMessageAssistant, ModelOutput
    from inspect_ai.tool import ToolCall

    if response.get("error"):
        return ModelOutput(model=response.get("model") or "offline", error=response["error"])
    calls = []
    for index, call in enumerate(response.get("tool_calls", ())):
        arguments = call.get("arguments")
        if isinstance(arguments, dict):
            calls.append(ToolCall(id=str(index), function=call["name"], arguments=arguments))
            continue
        # Inspect never hands a raw string through; unparseable arguments arrive as
        # an empty dict plus parse_error.
        parsed, parse_error = _parse_arguments(arguments)
        calls.append(
            ToolCall(
                id=str(index),
                function=call["name"],
                arguments=parsed,
                parse_error=parse_error,
            )
        )
    return ModelOutput(
        model=response.get("model") or "offline",
        choices=[
            ChatCompletionChoice(
                message=ChatMessageAssistant(
                    content=response.get("text") or "", tool_calls=calls or None
                ),
                stop_reason=response.get("finish_reason") or "stop",
            )
        ],
    )


def _parse_arguments(arguments: Any) -> tuple[dict[str, Any], str | None]:
    if arguments is None:
        return {}, None
    try:
        decoded = json.loads(arguments)
    except (TypeError, ValueError):
        return {}, str(arguments)
    if isinstance(decoded, dict):
        return decoded, None
    return {}, str(arguments)


def verify_inspect() -> dict[str, Any]:
    """The Inspect path must reach the same outcome as the direct scorer."""

    from ..controls import build_control_trials
    from ..inspect_adapter import available, control_task, response_from_inspect
    from ..scoring import score_response

    if not available():
        return {"status": "skipped", "reason": "inspect-ai is not installed"}

    fixture = load_fixture(_controls_fixture_path())
    truths: dict[str, Any] = {}
    mismatches: list[dict[str, Any]] = []
    for row in fixture["rows"]:
        domain_id = row["domain_id"]
        if domain_id not in truths:
            truths[domain_id] = {
                truth.trial_id: truth
                for _, truth in build_control_trials(domain_id, check_leakage=False)
            }
        truth = truths[domain_id][row["trial_id"]]
        observed = score_response(
            truth, response_from_inspect(_inspect_output(row["response"]))
        ).to_dict()
        if observed != row["expected"]:
            mismatches.append(
                {
                    "label": row["label"],
                    "domain_id": domain_id,
                    "fields": _differing_keys(observed, row["expected"]),
                }
            )
    if mismatches:
        raise AssertionError(f"Inspect path disagrees with the scorer: {mismatches}")
    task = control_task("procurement", check_leakage=False)
    return {
        "status": "passed",
        "rows_checked": len(fixture["rows"]),
        "task_built": task.name,
        "task_samples": len(task.dataset),
    }
