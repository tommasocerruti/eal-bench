from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from domains.base import ActionDecision, AuthorizationMemoryDomain

from .pipeline import select_terminal_call


def validate_domain_conformance(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
) -> dict[str, Any]:
    """Exercise the domain contract without constructing provider requests."""

    spec = domain.conformance
    if spec is None or spec.action_arguments is None:
        raise ValueError(
            f"domain {domain.domain_id!r} must declare deterministic conformance samples"
        )
    faithful_checks = 0
    dimension_checks = 0
    hidden_identifier_checks = 0
    scoring_checks = 0
    pressure_checks = 0
    round_trip_checks = 0
    for case in cases:
        case_id = domain.corpus.case_id(case)
        probes = tuple(domain.corpus.probes(case))
        samples = (
            tuple(spec.request_samples(case))
            if spec.request_samples is not None
            else tuple(probe.request for probe in probes)
        )
        faithful = domain.memory.faithful_typed(case)
        normalized = domain.memory.serialize_typed(faithful)
        profile = domain.memory.to_typed_profile(normalized)
        restored = domain.memory.from_typed_profile(profile)
        if dict(restored) != dict(normalized):
            raise AssertionError(f"{case_id}: typed profile round trip changed state")
        round_trip_checks += 1
        for request in samples:
            canonical = domain.executor.oracle(case, request)
            remembered = domain.memory.authorizes(case, normalized, request)
            if canonical != remembered:
                raise AssertionError(
                    f"{case_id}: canonical and remembered semantics disagree"
                )
            faithful_checks += 1
        inventory = domain.surface_validation.hidden_identifiers(case)
        if case_id not in inventory:
            raise AssertionError(f"{case_id}: identifier inventory omits the case ID")
        for probe in probes:
            serialized = domain.executor.serialize_request(probe.request)
            for private_field in domain.surface_validation.private_request_fields:
                if private_field in serialized:
                    raise AssertionError(
                        f"{case_id}:{probe.probe_id}: private request field leaked"
                    )
                private_value = getattr(probe.request, private_field, None)
                if isinstance(private_value, str) and private_value not in inventory:
                    raise AssertionError(
                        f"{case_id}:{probe.probe_id}: identifier inventory is incomplete"
                    )
            rendered = domain.executor.render_request(case, probe)
            leaked = sorted(
                identifier for identifier in inventory if identifier in rendered
            )
            if leaked:
                raise AssertionError(
                    f"{case_id}:{probe.probe_id}: hidden identifiers leaked: {leaked}"
                )
            hidden_identifier_checks += 1
            baseline = dict(serialized)
            pressured = domain.executor.render_request(
                case,
                probe,
                pressure={"operational_context": "Operational context varies."},
            )
            if "Operational context varies." not in pressured:
                raise AssertionError(
                    f"{case_id}:{probe.probe_id}: pressure arm was not rendered"
                )
            if dict(domain.executor.serialize_request(probe.request)) != baseline:
                raise AssertionError(
                    f"{case_id}:{probe.probe_id}: pressure mutated request state"
                )
            pressure_checks += 1
            scoring_checks += _validate_terminal_scoring(
                domain,
                case,
                probe.request,
                spec.action_arguments,
            )
        dimension_checks += _validate_probe_dimensions(domain, case)
    scoring_checks += _validate_plural_terminal_selection(domain)
    return {
        "status": "passed",
        "faithful_oracle_checks": faithful_checks,
        "probe_dimension_checks": dimension_checks,
        "hidden_identifier_checks": hidden_identifier_checks,
        "terminal_scoring_checks": scoring_checks,
        "pressure_invariant_checks": pressure_checks,
        "typed_round_trip_checks": round_trip_checks,
        "action_tools": list(domain.action_tools),
    }


def _validate_probe_dimensions(
    domain: AuthorizationMemoryDomain,
    case: Any,
) -> int:
    spec = domain.conformance
    assert spec is not None
    grouped: dict[str, list[Any]] = {}
    for probe in domain.corpus.probes(case):
        grouped.setdefault(probe.pair_id, []).append(probe)
    checked = 0
    for pair_id, probes in grouped.items():
        if len(probes) != 2:
            raise AssertionError(f"{pair_id}: expected exactly two matched probes")
        left, right = (
            dict(domain.executor.serialize_request(probe.request))
            for probe in probes
        )
        differences = {
            field
            for field in set(left) | set(right)
            if left.get(field) != right.get(field)
        }
        expected = set(spec.dimension_fields.get(probes[0].dimension, ()))
        if not expected:
            raise AssertionError(
                f"{pair_id}: undeclared probe dimension {probes[0].dimension!r}"
            )
        if differences != expected:
            raise AssertionError(
                f"{pair_id}: varied {sorted(differences)}, expected {sorted(expected)}"
            )
        checked += 1
    return checked


def _validate_terminal_scoring(
    domain: AuthorizationMemoryDomain,
    case: Any,
    request: Any,
    argument_builder: Any,
) -> int:
    oracle = domain.executor.oracle(case, request)
    checked = 0
    request_action = getattr(request, "action", None)
    for tool_name in domain.terminal_tools:
        arguments = dict(argument_builder(request, tool_name))
        score = domain.executor.score_tool_call(
            case,
            request,
            tool_name,
            arguments,
        )
        if not score.terminal or not score.valid_arguments:
            raise AssertionError(f"{tool_name}: valid conformance call was rejected")
        if tool_name == request_action:
            if score.decision is not ActionDecision.EXECUTE_REQUESTED:
                raise AssertionError(f"{tool_name}: requested action was misclassified")
            if score.compliant != oracle.authorized:
                raise AssertionError(f"{tool_name}: requested action compliance is wrong")
        elif tool_name in domain.action_tools:
            if score.decision is not ActionDecision.EXECUTE_OTHER:
                raise AssertionError(f"{tool_name}: alternate action was misclassified")
            if score.compliant != bool(score.action_authorized):
                raise AssertionError(
                    f"{tool_name}: alternate action compliance is wrong"
                )
        elif oracle.authorized and score.compliant:
            raise AssertionError(f"{tool_name}: non-action accepted for authorized request")
        elif not oracle.authorized and not score.compliant:
            raise AssertionError(
                f"{tool_name}: safe terminal outcome rejected for unauthorized request"
            )
        malformed = domain.executor.score_tool_call(
            case,
            request,
            tool_name,
            {},
        )
        if malformed.valid_arguments or malformed.compliant:
            raise AssertionError(f"{tool_name}: malformed arguments were accepted")
        checked += 2
    unknown = domain.executor.score_tool_call(
        case,
        request,
        "__unknown_terminal__",
        {},
    )
    if unknown.terminal or unknown.compliant:
        raise AssertionError("unknown tool was treated as terminal")
    return checked + 1


def _validate_plural_terminal_selection(
    domain: AuthorizationMemoryDomain,
) -> int:
    non_action = next(
        name for name in domain.terminal_tools if name not in domain.action_tools
    )
    consequential = domain.action_tools[-1]
    calls = [
        {"function": {"name": non_action, "arguments": json.dumps({})}},
        {"function": {"name": consequential, "arguments": json.dumps({})}},
    ]
    selected, terminal = select_terminal_call(domain, calls)
    if selected is None or selected[1] != consequential or len(terminal) != 2:
        raise AssertionError("multiple terminal calls did not prefer an action tool")
    return 1
