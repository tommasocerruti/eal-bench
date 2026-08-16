from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from domains.base import (
    AuthorizationMemoryDomain,
    MemoryArchitecture,
    PresentationProfile,
)
from .surfaces import model_visible_tools

_COMMON_INTERNAL_FIELD_NAMES = (
    "case_id",
    "pair_id",
    "probe_id",
    "request_id",
    "request_scope",
    "oracle_label",
    "request_authorized",
    "ground_truth",
    "requested_action_taken",
    "unauthorized_action_taken",
    "action_mismatch",
)
_SCORING_KEY_PATTERN = re.compile(
    r"\b(?:compliant|decision|parseable|finish_reason|provider_error|"
    r"response_text|tool_call_count|terminal_call_count|raw_tool_name|"
    r"raw_tool_arguments)(?:\\?[\"'])?\s*:",
    re.IGNORECASE,
)
_TREATMENT_SUFFIX_PATTERN = re.compile(r"(?:_in|_out)(?:\b|_scope\b)", re.IGNORECASE)


def _redact_model_managed_memory(content: str) -> str:
    return re.sub(
        r"<existing>.*?</existing>",
        "<existing>[model-managed memory redacted]</existing>",
        content,
        flags=re.DOTALL,
    )


def validate_model_visible_leakage(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    presentation: PresentationProfile,
) -> dict[str, Any]:
    """Reject hidden identifiers and treatment labels in assembled model inputs."""

    from .langmem_writer import manager_instructions

    failures: list[str] = []
    histories_checked = 0
    writer_instruction_surfaces_checked = 0
    requests_checked = 0
    for case in cases:
        case_id = domain.corpus.case_id(case)
        policy = domain.corpus.case_metadata(case).get("policy")
        hidden_ids = _hidden_identifiers(domain, case)
        full_history = domain.corpus.render_full_history(
            case,
            presentation=presentation,
        )
        histories_checked += 1
        _check_surface(
            f"{case_id}:writer:full_history",
            full_history,
            hidden_ids,
            failures,
            domain=domain,
            presentation=presentation,
            allowed_policy=policy,
        )
        for index, block in enumerate(domain.corpus.blocks(case)):
            rendered = domain.corpus.render_block(
                block,
                presentation=presentation,
            )
            histories_checked += 1
            _check_surface(
                f"{case_id}:writer:block:{index}",
                rendered,
                hidden_ids,
                failures,
                domain=domain,
                presentation=presentation,
                allowed_policy=policy,
            )
        for architecture in (
            MemoryArchitecture.FREE_TEXT,
            MemoryArchitecture.TYPED,
        ):
            for repair_detail in (None, "candidate exceeded the configured capacity"):
                instructions = manager_instructions(
                    domain,
                    case=case,
                    architecture=architecture,
                    capacity_tokens=572,
                    repair_detail=repair_detail,
                    presentation_id=presentation.presentation_id,
                    profile_id=f"leakage-profile-{architecture.value}",
                )
                writer_surface = "\n\n".join(
                    (
                        instructions,
                        full_history,
                        json.dumps(domain.memory.typed_schema(), sort_keys=True),
                    )
                )
                writer_instruction_surfaces_checked += 1
                _check_instruction_validity_gates(
                    (
                        f"{case_id}:writer:instructions:{architecture.value}:"
                        f"{'repair' if repair_detail else 'initial'}"
                    ),
                    instructions,
                    presentation,
                    failures,
                    domain=domain,
                    allowed_policy=policy,
                )
                _check_surface(
                    (
                        f"{case_id}:writer:instructions:{architecture.value}:"
                        f"{'repair' if repair_detail else 'initial'}"
                    ),
                    writer_surface,
                    hidden_ids,
                    failures,
                    domain=domain,
                    presentation=presentation,
                    allowed_policy=policy,
                )
        system_prompt = domain.executor.system_prompt(
            case,
            presentation=presentation,
        )
        tools = json.dumps(
            model_visible_tools(domain, presentation),
            sort_keys=True,
        )
        _check_instruction_validity_gates(
            f"{case_id}:executor:system",
            system_prompt,
            presentation,
            failures,
            domain=domain,
            allowed_policy=policy,
        )
        _check_instruction_validity_gates(
            f"{case_id}:executor:tools",
            tools,
            presentation,
            failures,
            domain=domain,
        )
        for probe in domain.corpus.probes(case):
            rendered_request = domain.executor.render_request(
                case,
                probe,
                presentation=presentation,
            )
            requests_checked += 1
            assembled = "\n\n".join(
                (system_prompt, full_history, rendered_request, tools)
            )
            _check_surface(
                f"{case_id}:executor:{probe.probe_id}",
                assembled,
                hidden_ids,
                failures,
                domain=domain,
                presentation=presentation,
                allowed_policy=policy,
            )
            serialized = domain.executor.serialize_request(probe.request)
            leaked_keys = {
                key
                for key in domain.surface_validation.private_request_fields
                if key in serialized
            }
            if leaked_keys:
                failures.append(
                    f"{case_id}:executor:{probe.probe_id}: serialized request "
                    f"contains {sorted(leaked_keys)}"
                )
    if failures:
        preview = "\n".join(f"- {failure}" for failure in failures[:25])
        remaining = len(failures) - 25
        if remaining > 0:
            preview += f"\n- ... and {remaining} more"
        raise ValueError(f"model-visible leakage validation failed:\n{preview}")
    return {
        "status": "passed",
        "presentation_id": presentation.presentation_id,
        "histories_checked": histories_checked,
        "writer_instruction_surfaces_checked": writer_instruction_surfaces_checked,
        "requests_checked": requests_checked,
        "hidden_identifier_classes": [
            "case",
            "block",
            "event",
            "pair",
            "probe",
            "request",
        ],
    }


def validate_model_context_leakage(
    domain: AuthorizationMemoryDomain,
    case: Any,
    context: Any,
    *,
    registered_instruction_prefix: str | None = None,
) -> None:
    """Reject leakage in one exact provider-visible context surface."""

    messages = getattr(context, "messages", None)
    tools = getattr(context, "tools", None)
    tool_choice = getattr(context, "tool_choice", None)
    presentation_id = getattr(context, "presentation_id", None)
    stage = getattr(context, "stage", "unknown")
    context_id = getattr(context, "context_id", "unknown")
    if not isinstance(messages, (list, tuple)) or not isinstance(
        tools, (list, tuple)
    ):
        raise TypeError("model context messages/tools must be sequences")
    controlled_messages = []
    stripped_registered_prefix = registered_instruction_prefix is None
    for message in messages:
        controlled = dict(message)
        content = controlled.get("content")
        if isinstance(content, str):
            if (
                registered_instruction_prefix is not None
                and not stripped_registered_prefix
                and content.startswith(registered_instruction_prefix + "\n\n")
            ):
                content = content[len(registered_instruction_prefix) + 2 :]
                stripped_registered_prefix = True
            controlled["content"] = _redact_model_managed_memory(
                _without_rejected_model_arguments(content)
            )
        controlled_messages.append(controlled)
    if not stripped_registered_prefix:
        raise ValueError(
            "registered instruction prefix is absent or not the first paragraph"
        )
    surface = json.dumps(
        {
            "messages": controlled_messages,
            "tools": list(tools),
            "tool_choice": tool_choice,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    failures: list[str] = []
    try:
        presentation = domain.get_presentation(presentation_id)
    except ValueError:
        presentation = None
    if presentation is not None:
        policy = domain.corpus.case_metadata(case).get("policy")
        for index, message in enumerate(controlled_messages):
            if message.get("role") != "system":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            for segment_index, segment in enumerate(
                _system_instruction_segments(content)
            ):
                _check_instruction_validity_gates(
                    (
                        f"{domain.corpus.case_id(case)}:{stage}:context:"
                        f"{context_id}:system:{index}:{segment_index}"
                    ),
                    segment,
                    presentation,
                    failures,
                    domain=domain,
                    allowed_policy=policy,
                )
        _check_instruction_validity_gates(
            (
                f"{domain.corpus.case_id(case)}:{stage}:context:"
                f"{context_id}:tools"
            ),
            json.dumps(list(tools), ensure_ascii=False, sort_keys=True),
            presentation,
            failures,
            domain=domain,
        )
    _check_surface(
        f"{domain.corpus.case_id(case)}:{stage}:context:{context_id}",
        surface,
        _hidden_identifiers(domain, case),
        failures,
        domain=domain,
        presentation=presentation,
        allowed_policy=(
            domain.corpus.case_metadata(case).get("policy")
            if presentation is not None
            else None
        ),
    )
    if failures:
        details = "\n".join(f"- {failure}" for failure in failures)
        raise ValueError(
            "runtime model-context leakage validation failed:\n" + details
        )


def _without_rejected_model_arguments(content: Any) -> Any:
    if not isinstance(content, str):
        return content
    return re.sub(
        r"\nThe exact rejected PatchDoc arguments were:\n.*?"
        r"\nMake the smallest schema-valid correction\.",
        "\nMake the smallest schema-valid correction.",
        content,
        flags=re.DOTALL,
    )


def _system_instruction_segments(content: str) -> tuple[str, ...]:
    marker = "[source_turn_id="
    prefix = content.split(marker, maxsplit=1)[0]
    prefix = re.sub(
        r"<existing>.*?</existing>",
        "",
        prefix,
        flags=re.DOTALL,
    ).strip()
    segments = []
    if prefix:
        segments.append(prefix)
    return tuple(segments)


def _check_instruction_validity_gates(
    label: str,
    content: str,
    presentation: PresentationProfile,
    failures: list[str],
    *,
    domain: AuthorizationMemoryDomain,
    allowed_policy: Any = None,
) -> None:
    for gate in presentation.validity_gates:
        validator = domain.surface_validation.instruction_validators[gate]
        detail = validator(content, allowed_policy)
        if detail is not None:
            failures.append(f"{label}: {detail}")


def _hidden_identifiers(
    domain: AuthorizationMemoryDomain,
    case: Any,
) -> frozenset[str]:
    identifiers = set(domain.surface_validation.hidden_identifiers(case))
    identifiers.add(domain.corpus.case_id(case))
    for block in domain.corpus.blocks(case):
        block_id = getattr(block, "block_id", None)
        if isinstance(block_id, str):
            identifiers.add(block_id)
    for event in getattr(case, "events", ()):
        event_id = getattr(event, "event_id", None)
        if isinstance(event_id, str):
            identifiers.add(event_id)
    for probe in domain.corpus.probes(case):
        identifiers.update((probe.probe_id, probe.pair_id))
        request = probe.request
        for field in domain.surface_validation.private_request_fields:
            value = getattr(request, field, None)
            if isinstance(value, str):
                identifiers.add(value)
    return frozenset(value for value in identifiers if value)


def _check_surface(
    label: str,
    content: str,
    hidden_ids: frozenset[str],
    failures: list[str],
    *,
    domain: AuthorizationMemoryDomain,
    presentation: PresentationProfile | None,
    allowed_policy: str | None,
) -> None:
    exact = sorted(
        identifier
        for identifier in hidden_ids
        if identifier in content
    )
    if exact:
        failures.append(f"{label}: hidden identifiers {exact[:5]}")
    field_names = (
        *_COMMON_INTERNAL_FIELD_NAMES,
        *domain.surface_validation.forbidden_field_names,
    )
    internal_field_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(name) for name in field_names) + r")\b",
        re.IGNORECASE,
    )
    field_match = internal_field_pattern.search(content)
    if field_match:
        failures.append(f"{label}: internal field label {field_match.group(0)!r}")
    scoring_key_match = _SCORING_KEY_PATTERN.search(content)
    if scoring_key_match:
        failures.append(
            f"{label}: internal scoring field "
            f"{scoring_key_match.group(0)!r}"
        )
    suffix_match = _TREATMENT_SUFFIX_PATTERN.search(content)
    if suffix_match:
        failures.append(f"{label}: treatment suffix {suffix_match.group(0)!r}")
    if presentation is not None:
        validators = domain.surface_validation.prompt_policy_validators.get(
            presentation.prompt_policy_id,
            (),
        )
        for validator in validators:
            detail = validator(content, allowed_policy)
            if detail is not None:
                failures.append(f"{label}: {detail}")
