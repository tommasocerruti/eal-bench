from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .cases import DATA_DIR, validate_case
from .schemas import AuthorizationCase


CORPUS_DIR = Path(__file__).with_name("corpus")
_REF_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_NAMESPACE_PATTERN = re.compile(r"^[0-9a-f]{8}$")
_FIVE_MINUTES = timedelta(minutes=5)


def _timestamp(value: object, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO-8601 UTC timestamp") from exc
    else:
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp ending in Z")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")
    return parsed


def _format_timestamp(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    if utc.microsecond:
        return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return utc.isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _ref(value: object, name: str) -> str:
    ref = _text(value, name)
    if not _REF_PATTERN.fullmatch(ref):
        raise ValueError(f"{name} must match {_REF_PATTERN.pattern}")
    return ref


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be a mapping with string keys")
    return value


def _sequence(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    name: str,
) -> None:
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise ValueError(f"{name} is missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{name} has unexpected fields: {sorted(unknown)}")


def _normalized_for_hash(value: object) -> object:
    if isinstance(value, datetime):
        return _format_timestamp(value)
    if isinstance(value, dict):
        return {
            key: _normalized_for_hash(item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        return [_normalized_for_hash(item) for item in value]
    return value


def _authoring_hash(source: dict[str, Any]) -> str:
    canonical = json.dumps(
        _normalized_for_hash(source),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _turn_times(
    blocks: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, str]:
    explicit: dict[str, datetime] = {}
    turn_to_block: dict[str, str] = {}
    block_turns: dict[str, list[str]] = {}
    for block_index, block in enumerate(blocks):
        block_ref = _ref(block.get("ref"), f"blocks[{block_index}].ref")
        if block_ref in block_turns:
            raise ValueError(f"duplicate block ref {block_ref!r}")
        refs: list[str] = []
        for turn_index, turn_value in enumerate(
            _sequence(block.get("turns"), f"{block_ref}.turns")
        ):
            turn = _mapping(turn_value, f"{block_ref}.turns[{turn_index}]")
            turn_ref = _ref(turn.get("ref"), f"{block_ref}.turns[{turn_index}].ref")
            if turn_ref in turn_to_block:
                raise ValueError(f"duplicate turn ref {turn_ref!r}")
            turn_to_block[turn_ref] = block_ref
            refs.append(turn_ref)
            if turn.get("occurred_at") is not None:
                explicit[turn_ref] = _timestamp(
                    turn["occurred_at"], f"{turn_ref}.occurred_at"
                )
        block_turns[block_ref] = refs

    anchors = dict(explicit)
    for event_index, event in enumerate(events):
        event_name = f"events[{event_index}]"
        effective_at = _timestamp(event.get("effective_at"), f"{event_name}.effective_at")
        block_ref = _ref(event.get("block_ref"), f"{event_name}.block_ref")
        if block_ref not in block_turns:
            raise ValueError(f"{event_name} references unknown block {block_ref!r}")
        for turn_ref_value in _sequence(
            event.get("source_turn_refs"), f"{event_name}.source_turn_refs"
        ):
            turn_ref = _ref(turn_ref_value, f"{event_name}.source_turn_refs item")
            if turn_to_block.get(turn_ref) != block_ref:
                raise ValueError(
                    f"{event_name} source {turn_ref!r} must belong to {block_ref!r}"
                )
            if turn_ref not in explicit:
                previous = anchors.get(turn_ref)
                if previous is not None and previous != effective_at:
                    raise ValueError(
                        f"{turn_ref!r} is an implicit source for events at different times"
                    )
                anchors[turn_ref] = effective_at

    resolved: dict[str, str] = {}
    previous_block_end: datetime | None = None
    for block_index, block in enumerate(blocks):
        block_ref = _ref(block.get("ref"), f"blocks[{block_index}].ref")
        ended_at = _timestamp(block.get("ended_at"), f"{block_ref}.ended_at")
        refs = block_turns[block_ref]
        if not refs:
            raise ValueError(f"{block_ref}.turns must not be empty")
        indexed_anchors = {
            index: anchors[turn_ref]
            for index, turn_ref in enumerate(refs)
            if turn_ref in anchors
        }
        times: list[datetime | None] = [None] * len(refs)
        if not indexed_anchors:
            for index in range(len(refs)):
                times[index] = ended_at - _FIVE_MINUTES * (len(refs) - 1 - index)
        else:
            anchor_indices = sorted(indexed_anchors)
            for index in anchor_indices:
                times[index] = indexed_anchors[index]
            first = anchor_indices[0]
            for index in range(first - 1, -1, -1):
                times[index] = indexed_anchors[first] - _FIVE_MINUTES * (first - index)
            for left, right in zip(anchor_indices, anchor_indices[1:]):
                required = (
                    _FIVE_MINUTES * (right - left - 1)
                    + timedelta(microseconds=1)
                )
                if indexed_anchors[left] + required > indexed_anchors[right]:
                    raise ValueError(
                        f"{block_ref} has insufficient time between anchored turns "
                        f"{refs[left]!r} and {refs[right]!r}"
                    )
                for index in range(left + 1, right):
                    times[index] = indexed_anchors[left] + _FIVE_MINUTES * (index - left)
            last = anchor_indices[-1]
            for index in range(last + 1, len(refs)):
                times[index] = indexed_anchors[last] + _FIVE_MINUTES * (index - last)

        concrete = [time for time in times if time is not None]
        if len(concrete) != len(refs):
            raise AssertionError("timestamp derivation left unresolved turns")
        if any(previous >= current for previous, current in zip(concrete, concrete[1:])):
            raise ValueError(f"{block_ref} turn timestamps must be strictly increasing")
        if concrete[-1] > ended_at:
            raise ValueError(f"{block_ref} has a turn after ended_at")
        if previous_block_end is not None and concrete[0] <= previous_block_end:
            raise ValueError(
                f"{block_ref} must begin after the previous block ended"
            )
        previous_block_end = ended_at
        resolved.update(
            (turn_ref, _format_timestamp(time))
            for turn_ref, time in zip(refs, concrete)
        )
    return resolved


def _record(
    value: object,
    *,
    source_ids: dict[str, str],
    name: str,
) -> dict[str, Any]:
    record = dict(_mapping(value, name))
    _keys(
        record,
        required={
            "authorization_ref",
            "issuer",
            "grantee",
            "effect",
            "action",
            "vendor",
            "allowed_categories",
            "max_amount",
            "currency",
            "valid_from",
            "valid_until",
            "status",
            "source_turn_refs",
        },
        optional={"supersedes_ref"},
        name=name,
    )
    authorization_id = _ref(record.pop("authorization_ref"), f"{name}.authorization_ref")
    supersedes = record.pop("supersedes_ref", None)
    if supersedes is not None:
        supersedes = _ref(supersedes, f"{name}.supersedes_ref")
    source_refs = _sequence(record.pop("source_turn_refs"), f"{name}.source_turn_refs")
    try:
        compiled_sources = [source_ids[_ref(item, f"{name}.source_turn_refs item")] for item in source_refs]
    except KeyError as exc:
        raise ValueError(f"{name} references unknown turn {exc.args[0]!r}") from exc
    return {
        "authorization_id": authorization_id,
        **record,
        "valid_from": _format_timestamp(_timestamp(record["valid_from"], f"{name}.valid_from")),
        "valid_until": _format_timestamp(
            _timestamp(record["valid_until"], f"{name}.valid_until")
        ),
        "supersedes": supersedes,
        "source_turn_ids": compiled_sources,
    }


def _transaction(value: object, *, transaction_id: str, name: str) -> dict[str, Any]:
    transaction = dict(_mapping(value, name))
    _keys(
        transaction,
        required={
            "grantee",
            "action",
            "vendor",
            "category",
            "amount",
            "currency",
            "action_time",
        },
        name=name,
    )
    transaction["action_time"] = _format_timestamp(
        _timestamp(transaction["action_time"], f"{name}.action_time")
    )
    return {"transaction_id": transaction_id, **transaction}


def _patch(value: object, *, name: str) -> dict[str, Any]:
    patch = dict(_mapping(value, name))
    if "valid_from" in patch:
        patch["valid_from"] = _format_timestamp(
            _timestamp(patch["valid_from"], f"{name}.valid_from")
        )
    if "valid_until" in patch:
        patch["valid_until"] = _format_timestamp(
            _timestamp(patch["valid_until"], f"{name}.valid_until")
        )
    return patch


def compile_case(
    source: dict[str, Any],
    *,
    source_path: Path | None = None,
    allow_single_probe_pair: bool = False,
    allow_tiny_control_fixture: bool = False,
) -> AuthorizationCase:
    location = str(source_path) if source_path is not None else "authoring source"
    _keys(
        source,
        required={
            "schema_version",
            "case_id",
            "source_id_namespace",
            "benchmark",
            "policy",
            "authorized_issuers",
            "blocks",
            "events",
            "probe_pairs",
            "tags",
        },
        name=location,
    )
    schema_version = _text(source["schema_version"], f"{location}.schema_version")
    case_id = _ref(source["case_id"], f"{location}.case_id")
    namespace = _text(
        source["source_id_namespace"], f"{location}.source_id_namespace"
    )
    if not _NAMESPACE_PATTERN.fullmatch(namespace):
        raise ValueError(f"{location}.source_id_namespace must be eight lowercase hex digits")

    blocks = [
        _mapping(item, f"{location}.blocks[{index}]")
        for index, item in enumerate(_sequence(source["blocks"], f"{location}.blocks"))
    ]
    events = [
        _mapping(item, f"{location}.events[{index}]")
        for index, item in enumerate(_sequence(source["events"], f"{location}.events"))
    ]
    occurred_at = _turn_times(blocks, events)

    source_ids: dict[str, str] = {}
    block_ids: dict[str, str] = {}
    compiled_blocks = []
    ordinal = 0
    for block_index, block in enumerate(blocks):
        _keys(
            block,
            required={"ref", "title", "ended_at", "turns"},
            name=f"{location}.blocks[{block_index}]",
        )
        block_ref = _ref(block["ref"], f"{location}.blocks[{block_index}].ref")
        if block_ref in block_ids:
            raise ValueError(f"{location}: duplicate block ref {block_ref!r}")
        block_id = f"{case_id}_{block_ref}"
        block_ids[block_ref] = block_id
        compiled_turns = []
        for turn_index, turn_value in enumerate(
            _sequence(block["turns"], f"{location}.{block_ref}.turns")
        ):
            turn = dict(
                _mapping(turn_value, f"{location}.{block_ref}.turns[{turn_index}]")
            )
            _keys(
                turn,
                required={"ref", "actor_id", "speaker", "content"},
                optional={"occurred_at"},
                name=f"{location}.{block_ref}.turns[{turn_index}]",
            )
            turn_ref = _ref(
                turn["ref"], f"{location}.{block_ref}.turns[{turn_index}].ref"
            )
            if turn_ref in source_ids:
                raise ValueError(f"{location}: duplicate turn ref {turn_ref!r}")
            ordinal += 1
            source_id = f"src_{namespace}_{ordinal:03d}"
            source_ids[turn_ref] = source_id
            compiled_turns.append(
                {
                    "turn_id": source_id,
                    "actor_id": turn["actor_id"],
                    "speaker": turn["speaker"],
                    "content": turn["content"],
                    "occurred_at": occurred_at[turn_ref],
                }
            )
        compiled_blocks.append(
            {
                "block_id": block_id,
                "block_index": block_index,
                "title": block["title"],
                "ended_at": _format_timestamp(
                    _timestamp(block["ended_at"], f"{location}.{block_ref}.ended_at")
                ),
                "turns": compiled_turns,
            }
        )

    compiled_events = []
    for event_index, event in enumerate(events):
        name = f"{location}.events[{event_index}]"
        _keys(
            event,
            required={
                "ref",
                "event_type",
                "issuer",
                "block_ref",
                "effective_at",
                "authorization_ref",
                "source_turn_refs",
            },
            optional={"record", "patch"},
            name=name,
        )
        event_ref = _ref(event["ref"], f"{name}.ref")
        block_ref = _ref(event["block_ref"], f"{name}.block_ref")
        try:
            block_id = block_ids[block_ref]
        except KeyError as exc:
            raise ValueError(f"{name} references unknown block {block_ref!r}") from exc
        source_refs = _sequence(event["source_turn_refs"], f"{name}.source_turn_refs")
        try:
            compiled_sources = [
                source_ids[_ref(item, f"{name}.source_turn_refs item")]
                for item in source_refs
            ]
        except KeyError as exc:
            raise ValueError(f"{name} references unknown turn {exc.args[0]!r}") from exc
        compiled_events.append(
            {
                "event_id": f"{case_id}_{event_ref}",
                "event_type": event["event_type"],
                "issuer": event["issuer"],
                "block_id": block_id,
                "effective_at": _format_timestamp(
                    _timestamp(event["effective_at"], f"{name}.effective_at")
                ),
                "authorization_id": _ref(
                    event["authorization_ref"], f"{name}.authorization_ref"
                ),
                "source_turn_ids": compiled_sources,
                "record": (
                    _record(event["record"], source_ids=source_ids, name=f"{name}.record")
                    if event.get("record") is not None
                    else None
                ),
                "patch": (
                    _patch(event["patch"], name=f"{name}.patch")
                    if event.get("patch") is not None
                    else None
                ),
            }
        )

    compiled_pairs = []
    for pair_index, pair_value in enumerate(
        _sequence(source["probe_pairs"], f"{location}.probe_pairs")
    ):
        pair = _mapping(pair_value, f"{location}.probe_pairs[{pair_index}]")
        name = f"{location}.probe_pairs[{pair_index}]"
        _keys(
            pair,
            required={"ref", "dimension", "in_scope", "out_of_scope"},
            name=name,
        )
        pair_ref = _ref(pair["ref"], f"{name}.ref")
        compiled_probes: dict[str, Any] = {}
        for scope in ("in_scope", "out_of_scope"):
            suffix = "in" if scope == "in_scope" else "out"
            compiled_probes[scope] = {
                "name": f"{case_id}_{pair_ref}_{suffix}",
                "request_scope": scope,
                "transaction": _transaction(
                    pair[scope],
                    transaction_id=f"{case_id}_txn_{pair_ref}_{suffix}",
                    name=f"{name}.{scope}",
                ),
            }
        compiled_pairs.append(
            {
                "pair_id": f"{case_id}_{pair_ref}",
                "dimension": pair["dimension"],
                **compiled_probes,
            }
        )

    compiled = {
        "schema_version": schema_version,
        "case_id": case_id,
        "authoring_hash": _authoring_hash(source),
        "policy": source["policy"],
        "authorized_issuers": source["authorized_issuers"],
        "benchmark": source["benchmark"],
        "blocks": compiled_blocks,
        "events": compiled_events,
        "probe_pairs": compiled_pairs,
        "tags": source["tags"],
    }
    try:
        case = AuthorizationCase.from_dict(compiled)
        validate_case(
            case,
            allow_single_probe_pair=allow_single_probe_pair,
            allow_tiny_control_fixture=allow_tiny_control_fixture,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid compiled case from {location}: {exc}") from exc
    return case


def _load_source(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {path}: {exc}") from exc
    return _mapping(value, str(path))


def compile_version(
    version: str = "calibration_v1",
    *,
    source_dir: Path | None = None,
) -> bytes:
    directory = source_dir or CORPUS_DIR / version
    paths = sorted(directory.glob("*.yaml"))
    if not paths:
        raise ValueError(f"no authoring YAML files found in {directory}")
    cases = [compile_case(_load_source(path), source_path=path) for path in paths]
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError(f"duplicate case IDs in {directory}")
    source_ids = [
        turn.turn_id for case in cases for block in case.blocks for turn in block.turns
    ]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError(f"opaque source IDs collide across {directory}")
    lines = [
        json.dumps(case.to_dict(), ensure_ascii=False, separators=(",", ":"))
        for case in cases
    ]
    return ("\n".join(lines) + "\n").encode()


def check_compiled(
    version: str = "calibration_v1",
    *,
    source_dir: Path | None = None,
    output_path: Path | None = None,
) -> None:
    target = output_path or DATA_DIR / f"{version}.jsonl"
    expected = compile_version(version, source_dir=source_dir)
    try:
        actual = target.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"compiled corpus is missing: {target}; run with --write") from exc
    if actual != expected:
        raise ValueError(
            f"compiled corpus differs from authoring sources: {target}; "
            "do not edit generated JSONL by hand, run with --write"
        )


def write_compiled(
    version: str = "calibration_v1",
    *,
    source_dir: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    target = output_path or DATA_DIR / f"{version}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(compile_version(version, source_dir=source_dir))
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile readable procurement case YAML into generated JSONL."
    )
    parser.add_argument("--version", default="calibration_v1")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify generated JSONL")
    mode.add_argument("--write", action="store_true", help="rewrite generated JSONL")
    args = parser.parse_args()
    if args.write:
        target = write_compiled(args.version)
        print(f"Wrote {target}")
    else:
        check_compiled(args.version)
        print(f"{args.version}: compiled corpus is current")


if __name__ == "__main__":
    main()
