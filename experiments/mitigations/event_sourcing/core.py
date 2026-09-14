"""Bounded event sourcing: core."""

from __future__ import annotations

import copy


import re


from collections import defaultdict

from collections.abc import Mapping, Sequence

from dataclasses import dataclass, field


from typing import Any


from domains.base import (
    AuthorizationMemoryDomain,
)


from experiments.authorization_memory.persistence import (
    canonical_json,
    content_hash,
)


from experiments.authorization_memory.tokens import count_reference_tokens


EVENT_SOURCING_STUDY_ID = "event_sourcing"


EVENT_CONDITION_ID = "bounded_event_sourced_typed"


EVENT_SCHEMA_VERSION = "bounded_authorization_event_v1"


EVENT_LOG_SCHEMA_VERSION = 1


EVENT_DELTA_SCHEMA_VERSION = 1


REDUCED_STATE_SCHEMA_VERSION = 1


RESOURCE_SCHEMA_VERSION = 1


DIAGNOSTIC_SCHEMA_VERSION = 1


IMPLEMENTATION_ID = "bounded_event_sourcing_v1"


EVENT_TOOL_NAME = "record_authorization_events"


MAX_EVENTS_PER_BLOCK = 32


_EVENT_ID_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ExtractedEvent:
    """One model-extracted public lifecycle event after system ID assignment."""

    event_id: str
    event_type: str
    target_authorization_id: str | None
    source_turn_ids: tuple[str, ...]
    record: Mapping[str, Any] | None
    changes: Mapping[str, Any] | None
    event_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "target_authorization_id": self.target_authorization_id,
            "source_turn_ids": list(self.source_turn_ids),
            "record": copy.deepcopy(dict(self.record)) if self.record is not None else None,
            "changes": copy.deepcopy(dict(self.changes)) if self.changes is not None else None,
            "event_index": self.event_index,
        }


@dataclass(frozen=True)
class EventBatchValidation:
    events: tuple[ExtractedEvent, ...]
    reduced_state: Mapping[str, Any]
    reducer: "PublicEventReducer"


@dataclass
class PublicEventReducer:
    """Apply extracted events literally using only public lifecycle rules."""

    domain: AuthorizationMemoryDomain
    records: dict[str, dict[str, Any]] = field(default_factory=dict)
    event_log: list[ExtractedEvent] = field(default_factory=list)

    def clone(self) -> "PublicEventReducer":
        return PublicEventReducer(
            domain=self.domain,
            records=copy.deepcopy(self.records),
            event_log=list(self.event_log),
        )

    def apply(self, event: ExtractedEvent) -> None:
        event_type = event.event_type
        source_ids = list(event.source_turn_ids)
        if event_type == "issue":
            assert event.record is not None
            record = copy.deepcopy(dict(event.record))
            record.update(
                _generated_record_fields(
                    self.domain,
                    status="active",
                    supersedes=_record_supersedes(self.domain, record),
                    source_turn_ids=source_ids,
                )
            )
            self.records[str(record["authorization_id"])] = record
        elif event_type == "patch":
            assert event.target_authorization_id is not None
            assert event.changes is not None
            current = copy.deepcopy(self.records[event.target_authorization_id])
            for key, value in event.changes.items():
                if key == "scope" and isinstance(value, Mapping):
                    current["scope"] = {
                        **dict(current.get("scope") or {}),
                        **copy.deepcopy(dict(value)),
                    }
                else:
                    current[key] = copy.deepcopy(value)
            merged_sources = list(
                dict.fromkeys([*_record_source_ids(self.domain, current), *source_ids])
            )
            current.update(
                _generated_record_fields(
                    self.domain,
                    status=str(current["status"]),
                    supersedes=_record_supersedes(self.domain, current),
                    source_turn_ids=merged_sources,
                )
            )
            self.records[event.target_authorization_id] = current
        elif event_type == "revoke":
            assert event.target_authorization_id is not None
            current = copy.deepcopy(self.records[event.target_authorization_id])
            merged_sources = list(
                dict.fromkeys([*_record_source_ids(self.domain, current), *source_ids])
            )
            current.update(
                _generated_record_fields(
                    self.domain,
                    status="revoked",
                    supersedes=_record_supersedes(self.domain, current),
                    source_turn_ids=merged_sources,
                )
            )
            self.records[event.target_authorization_id] = current
        elif event_type == "replace":
            assert event.target_authorization_id is not None
            assert event.record is not None
            current = copy.deepcopy(self.records[event.target_authorization_id])
            merged_sources = list(
                dict.fromkeys([*_record_source_ids(self.domain, current), *source_ids])
            )
            current.update(
                _generated_record_fields(
                    self.domain,
                    status="superseded",
                    supersedes=_record_supersedes(self.domain, current),
                    source_turn_ids=merged_sources,
                )
            )
            self.records[event.target_authorization_id] = current
            replacement = copy.deepcopy(dict(event.record))
            replacement.update(
                _generated_record_fields(
                    self.domain,
                    status="active",
                    supersedes=event.target_authorization_id,
                    source_turn_ids=source_ids,
                )
            )
            self.records[str(replacement["authorization_id"])] = replacement
        else:
            raise ValueError(f"unsupported event type: {event_type!r}")
        self.event_log.append(event)

    def apply_batch(self, events: Sequence[ExtractedEvent]) -> None:
        for event in events:
            self.apply(event)

    def visible_state(self) -> Mapping[str, Any]:
        retain_inactive = self.domain.event_sourcing.retain_inactive_records
        records = [
            copy.deepcopy(record)
            for _, record in sorted(self.records.items())
            if retain_inactive or record.get("status") == "active"
        ]
        empty = dict(self.domain.memory.empty_typed())
        return self.domain.memory.parse_typed(
            {
                "schema_version": empty["schema_version"],
                "authorizations": records,
            }
        )


def _record_source_ids(
    domain: AuthorizationMemoryDomain,
    record: Mapping[str, Any],
) -> list[str]:
    value = record.get("source_turn_ids")
    if domain.event_sourcing.source_id_separator is not None:
        return (
            []
            if not isinstance(value, str)
            else value.split(domain.event_sourcing.source_id_separator)
        )
    return [str(item) for item in (value or ())]


def _record_supersedes(
    domain: AuthorizationMemoryDomain,
    record: Mapping[str, Any],
) -> str | None:
    value = record.get("supersedes")
    if value == domain.event_sourcing.empty_supersedes:
        return None
    return str(value) if value is not None else None


def _generated_record_fields(
    domain: AuthorizationMemoryDomain,
    *,
    status: str,
    supersedes: str | None,
    source_turn_ids: Sequence[str],
) -> dict[str, Any]:
    if domain.event_sourcing.source_id_separator is not None:
        return {
            "status": status,
            "supersedes": supersedes or domain.event_sourcing.empty_supersedes,
            "source_turn_ids": domain.event_sourcing.source_id_separator.join(source_turn_ids),
        }
    return {
        "status": status,
        "supersedes": supersedes,
        "source_turn_ids": list(source_turn_ids),
    }


def event_writer_instruction(
    domain: AuthorizationMemoryDomain,
    case: Any,
    *,
    capacity_tokens: int,
    presentation_id: str,
    repair_detail: str | None = None,
) -> str:
    """Return the exact target-invariant event-writer instruction."""

    presentation = domain.get_presentation(presentation_id)
    policy = domain.get_prompt_policy(presentation)
    parts = [
        "Extract only newly stated authorization-changing events from the CURRENT CONVERSATION BLOCK.",
        (
            "You receive a compact PREVIOUS CURRENT AUTHORIZATION STATE and one new block. "
            "The cumulative event log and earlier conversation blocks are not available."
        ),
        (
            "Use public lifecycle semantics: issue creates a new active record; patch changes "
            "only the named fields of one current record; revoke makes one current record "
            "inactive; replace supersedes one current record and creates one new active record."
        ),
        (
            "For issue and replace, return complete authorization content in record. The system "
            "assigns status, provenance storage, and immutable event IDs; for replace it assigns "
            "the replacement's supersedes field from the selected target. Preserve the schema-native "
            "supersedes field on issue records. For patch, return only changed fields. For revoke, "
            "return neither record nor changes."
        ),
        (
            "Use exact stable authorization and source-turn identifiers visible in the supplied "
            "state or current block. Do not invent opaque event IDs. Preserve schema-native JSON types."
        ),
        (
            "Do not infer an event from discussion, recommendations, stale exports, or other "
            "text that does not itself change authorization. Return an empty "
            "events array when the current block contains no authorization change."
        ),
        policy.writer_source_instruction,
        f"The deterministically reduced current state must fit within {capacity_tokens} reference tokens.",
        "Domain context: " + canonical_json(policy.context_builder(case)),
    ]
    if policy.writer_inference_instruction:
        parts.append(policy.writer_inference_instruction)
    if repair_detail is not None:
        parts.append(
            policy.writer_repair_instruction
            + "Correct only the structural problem in the rejected delta: "
            + repair_detail
        )
    return "\n\n".join(parts)


def event_tool(domain: AuthorizationMemoryDomain) -> dict[str, Any]:
    typed_schema = copy.deepcopy(dict(domain.memory.typed_schema()))
    record_schema = _record_schema(typed_schema)
    content_schema = copy.deepcopy(record_schema)
    content_properties = dict(content_schema.get("properties") or {})
    generated = {"status", "source_turn_ids"}
    content_schema["properties"] = {
        key: value for key, value in content_properties.items() if key not in generated
    }
    content_schema["required"] = [
        key for key in content_schema.get("required", ()) if key not in generated
    ]
    changes_properties = {
        key: copy.deepcopy(value)
        for key, value in content_schema["properties"].items()
        if key != "authorization_id"
    }
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "maxItems": MAX_EVENTS_PER_BLOCK,
                "items": {
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "enum": ["issue", "patch", "revoke", "replace"],
                        },
                        "target_authorization_id": {
                            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}]
                        },
                        "source_turn_ids": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "record": {"anyOf": [content_schema, {"type": "null"}]},
                        "changes": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "properties": changes_properties,
                                    "additionalProperties": False,
                                    "minProperties": 1,
                                },
                                {"type": "null"},
                            ]
                        },
                    },
                    "required": [
                        "event_type",
                        "target_authorization_id",
                        "source_turn_ids",
                        "record",
                        "changes",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["events"],
        "additionalProperties": False,
    }
    if typed_schema.get("$defs"):
        parameters["$defs"] = typed_schema["$defs"]
    return {
        "type": "function",
        "function": {
            "name": EVENT_TOOL_NAME,
            "description": "Record only authorization-changing events newly present in the current block.",
            "parameters": parameters,
        },
    }


def event_writer_messages(
    domain: AuthorizationMemoryDomain,
    case: Any,
    *,
    previous_state: Mapping[str, Any],
    block_text: str,
    capacity_tokens: int,
    presentation_id: str,
    repair_detail: str | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": event_writer_instruction(
                domain,
                case,
                capacity_tokens=capacity_tokens,
                presentation_id=presentation_id,
                repair_detail=repair_detail,
            ),
        },
        {
            "role": "user",
            "content": (
                "PREVIOUS CURRENT AUTHORIZATION STATE\n"
                + canonical_json(previous_state)
                + "\n\nCURRENT CONVERSATION BLOCK\n"
                + block_text
            ),
        },
    ]


def validate_event_arguments(
    domain: AuthorizationMemoryDomain,
    *,
    reducer: PublicEventReducer,
    arguments: Mapping[str, Any],
    visible_source_ids: frozenset[str],
    addressable_authorization_ids: frozenset[str],
    logical_update_id: str,
    capacity_tokens: int,
) -> EventBatchValidation:
    """Perform structural validation only and reduce one batch atomically."""

    raw_events = arguments.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("events must be an array")
    if len(raw_events) > MAX_EVENTS_PER_BLOCK:
        raise ValueError(f"events must contain at most {MAX_EVENTS_PER_BLOCK} entries")
    candidate = reducer.clone()
    parsed: list[ExtractedEvent] = []
    initial_state = candidate.visible_state()
    available_ids = {
        str(record["authorization_id"]) for record in initial_state["authorizations"]
    } | set(addressable_authorization_ids)
    for index, raw in enumerate(raw_events):
        if not isinstance(raw, Mapping):
            raise ValueError(f"event {index} must be an object")
        expected_keys = {
            "event_type",
            "target_authorization_id",
            "source_turn_ids",
            "record",
            "changes",
        }
        if set(raw) != expected_keys:
            raise ValueError(f"event {index} has missing or unexpected fields")
        event_type = raw["event_type"]
        if event_type not in {"issue", "patch", "revoke", "replace"}:
            raise ValueError(f"event {index} has an unsupported event_type")
        target = raw["target_authorization_id"]
        if target is not None and (not isinstance(target, str) or not target.strip()):
            raise ValueError(f"event {index} target must be null or a non-empty string")
        sources = raw["source_turn_ids"]
        if (
            not isinstance(sources, list)
            or not sources
            or any(not isinstance(value, str) or not value.strip() for value in sources)
            or len(sources) != len(set(sources))
        ):
            raise ValueError(f"event {index} source_turn_ids must be unique non-empty strings")
        unseen = sorted(set(sources) - set(visible_source_ids))
        if unseen:
            raise ValueError(
                f"event {index} cites source IDs outside the model-visible state/block: {unseen}"
            )
        record = raw["record"]
        changes = raw["changes"]
        if event_type == "issue":
            if target is not None or not isinstance(record, Mapping) or changes is not None:
                raise ValueError("issue requires null target, complete record, and null changes")
            supersedes = _record_supersedes(domain, record)
            if supersedes is not None and supersedes not in available_ids:
                raise ValueError(
                    "issue supersedes reference does not exist in bounded current state"
                )
        elif event_type == "patch":
            if target not in available_ids:
                raise ValueError("patch target does not exist in bounded current state")
            if record is not None or not isinstance(changes, Mapping) or not changes:
                raise ValueError(
                    "patch requires an existing target, null record, and non-empty changes"
                )
        elif event_type == "revoke":
            if target not in available_ids:
                raise ValueError("revoke target does not exist in bounded current state")
            if record is not None or changes is not None:
                raise ValueError("revoke requires an existing target and null record/changes")
        else:
            if target not in available_ids:
                raise ValueError("replace target does not exist in bounded current state")
            if not isinstance(record, Mapping) or changes is not None:
                raise ValueError(
                    "replace requires an existing target, complete record, and null changes"
                )
        event = ExtractedEvent(
            event_id=_event_id(logical_update_id, index),
            event_type=str(event_type),
            target_authorization_id=target,
            source_turn_ids=tuple(sources),
            record=copy.deepcopy(dict(record)) if isinstance(record, Mapping) else None,
            changes=copy.deepcopy(dict(changes)) if isinstance(changes, Mapping) else None,
            event_index=index,
        )
        candidate.apply(event)
        if event.record is not None:
            available_ids.add(str(event.record["authorization_id"]))
        parsed.append(event)
    reduced = candidate.visible_state()
    tokens = count_reference_tokens(canonical_json(reduced))
    if tokens > capacity_tokens:
        raise ValueError(
            f"reduced state uses {tokens} reference tokens, exceeding capacity {capacity_tokens}"
        )
    return EventBatchValidation(tuple(parsed), reduced, candidate)


def _record_schema(typed_schema: Mapping[str, Any]) -> dict[str, Any]:
    authorizations = typed_schema.get("properties", {}).get("authorizations")
    if not isinstance(authorizations, Mapping):
        raise ValueError("typed schema has no authorizations property")
    items = authorizations.get("items")
    if not isinstance(items, Mapping):
        raise ValueError("typed authorizations schema has no item schema")
    reference = items.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        name = reference.rsplit("/", 1)[-1]
        resolved = typed_schema.get("$defs", {}).get(name)
        if not isinstance(resolved, Mapping):
            raise ValueError("typed authorization item reference cannot be resolved")
        return copy.deepcopy(dict(resolved))
    return copy.deepcopy(dict(items))


def _capacity_tokens(domain: AuthorizationMemoryDomain, corpus_version: str) -> int:
    from experiments.authorization_memory.pipeline import calibrate_capacity

    cases = domain.corpus.load_cases(corpus_version)
    return calibrate_capacity(
        domain,
        cases,
        corpus_version=corpus_version,
        presentation=domain.get_presentation(),
    ).primary_tokens


def _forced_tool_choice() -> dict[str, Any]:
    return {"type": "function", "function": {"name": EVENT_TOOL_NAME}}


def _event_id(logical_update_id: str, event_index: int) -> str:
    safe = _EVENT_ID_SAFE.sub("-", logical_update_id).strip("-")
    return f"evtgen_{safe}_{event_index:02d}"


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{content_hash([prefix, *parts])[:24]}"


def _summary(values: Sequence[int] | Any) -> dict[str, float | int]:
    items = sorted(int(value) for value in values)
    if not items:
        return {"min": 0, "median": 0, "mean": 0.0, "max": 0}
    middle = len(items) // 2
    median = items[middle] if len(items) % 2 else (items[middle - 1] + items[middle]) / 2
    return {
        "min": items[0],
        "median": median,
        "mean": sum(items) / len(items),
        "max": items[-1],
    }


def _raw_events(domain: AuthorizationMemoryDomain, case: Any) -> tuple[Any, ...]:
    if domain.event_sourcing.order_by_effective_at:
        block_positions = {
            str(block.block_id): int(block.block_index) for block in domain.corpus.blocks(case)
        }
        return tuple(
            sorted(
                case.events,
                key=lambda event: (
                    block_positions[str(event.block_id)],
                    str(event.effective_at),
                    str(event.event_id),
                ),
            )
        )
    return tuple(
        sorted(
            case.events,
            key=lambda event: (int(event.block_index), str(event.event_id)),
        )
    )


def _raw_event_block_index(
    event: Any,
    block_positions: Mapping[str, int],
) -> int:
    value = getattr(event, "block_index", None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    block_id = str(getattr(event, "block_id", ""))
    if block_id not in block_positions:
        raise ValueError(f"canonical event references unknown block {block_id!r}")
    return int(block_positions[block_id])


def _canonical_events_by_block(
    domain: AuthorizationMemoryDomain,
    case: Any,
) -> dict[int, tuple[ExtractedEvent, ...]]:
    positions = {
        str(block.block_id): int(block.block_index) for block in domain.corpus.blocks(case)
    }
    grouped: dict[int, list[ExtractedEvent]] = defaultdict(list)
    for index, raw in enumerate(_raw_events(domain, case)):
        block_index = _raw_event_block_index(raw, positions)
        grouped[block_index].append(
            _canonical_event(
                domain,
                case,
                raw,
                event_index=index,
                block_positions=positions,
            )
        )
    return {key: tuple(values) for key, values in grouped.items()}


def _canonical_event(
    domain: AuthorizationMemoryDomain,
    case: Any,
    raw: Any,
    *,
    event_index: int,
    block_positions: Mapping[str, int],
) -> ExtractedEvent:
    event_type = str(raw.event_type)
    raw_record = getattr(raw, "record", None)
    record = _canonical_record_content(domain, raw_record) if raw_record is not None else None
    if event_type == "replace":
        target = str(getattr(raw, domain.event_sourcing.replacement_target_field))
    elif event_type in {"patch", "revoke"}:
        target = str(raw.authorization_id)
    else:
        target = None
    raw_sources = getattr(raw, "source_turn_ids", None)
    sources = (
        tuple(str(value) for value in raw_sources)
        if raw_sources is not None
        else (str(raw.source_turn_id),)
    )
    raw_changes = getattr(raw, "changes", None)
    if raw_changes is None and getattr(raw, "patch", None) is not None:
        raw_changes = raw.patch.to_dict()
    changes = _canonical_changes(domain, raw_changes) if isinstance(raw_changes, Mapping) else None
    return ExtractedEvent(
        event_id=str(raw.event_id),
        event_type=event_type,
        target_authorization_id=target,
        source_turn_ids=sources,
        record=record,
        changes=changes,
        event_index=event_index,
    )


def _canonical_record_content(
    domain: AuthorizationMemoryDomain,
    raw_record: Any,
) -> dict[str, Any]:
    raw = dict(raw_record.to_dict())
    scope_fields = domain.event_sourcing.nested_scope_fields
    if scope_fields and "scope" not in raw:
        raw["scope"] = {name: raw.pop(name) for name in scope_fields}
    empty = dict(domain.memory.empty_typed())
    normalized = domain.memory.parse_typed(
        {
            "schema_version": empty["schema_version"],
            "authorizations": [raw],
        }
    )["authorizations"][0]
    return {
        key: copy.deepcopy(value)
        for key, value in normalized.items()
        if key not in {"status", "source_turn_ids"}
    }


def _canonical_changes(
    domain: AuthorizationMemoryDomain,
    raw_changes: Mapping[str, Any],
) -> dict[str, Any]:
    changes = copy.deepcopy(dict(raw_changes))
    if domain.event_sourcing.nested_scope_fields:
        scope_names = set(domain.event_sourcing.nested_scope_fields)
        scope = {key: changes.pop(key) for key in tuple(changes) if key in scope_names}
        if scope:
            changes["scope"] = scope
    elif domain.event_sourcing.flattened_scope_list_fields and isinstance(
        changes.get("scope"), Mapping
    ):
        scope = dict(changes.pop("scope"))
        changes.update(scope)
        for field_name in domain.event_sourcing.flattened_scope_list_fields:
            value = changes.get(field_name)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                changes[field_name] = domain.event_sourcing.source_id_separator.join(
                    str(item) for item in value
                )
    return changes


def _block_source_ids(domain: AuthorizationMemoryDomain, case: Any, block: Any) -> frozenset[str]:
    del domain, case
    return frozenset(str(getattr(turn, "turn_id")) for turn in block.turns)
