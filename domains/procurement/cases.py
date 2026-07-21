from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .oracle import evaluate_ledger
from .schemas import (
    AuthorizationCase,
    AuthorizationEvent,
    CanonicalAuthorizationRecord,
    ConversationBlock,
    LedgerSnapshot,
    Transaction,
)


DATA_DIR = Path(__file__).with_name("data")
_VERSION_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_OPAQUE_SOURCE_ID_PATTERN = re.compile(r"^src_[0-9a-f]{8}_[0-9]{3}$")
_TREATMENT_TOKENS = (
    "issue_only",
    "narrowing",
    "revoke",
    "replace",
    "amount",
    "time",
    "category",
)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _event_by_block(case: AuthorizationCase) -> dict[str, list[AuthorizationEvent]]:
    grouped: dict[str, list[AuthorizationEvent]] = {block.block_id: [] for block in case.blocks}
    for event in case.events:
        if event.block_id not in grouped:
            raise ValueError(f"{case.case_id}: event references unknown block {event.block_id!r}")
        grouped[event.block_id].append(event)
    for events in grouped.values():
        events.sort(key=lambda event: _timestamp(event.effective_at))
    return grouped


def _turn_index(case: AuthorizationCase) -> dict[str, tuple[str, str, str, str]]:
    indexed: dict[str, tuple[str, str, str, str]] = {}
    for block in case.blocks:
        for turn in block.turns:
            if turn.turn_id in indexed:
                raise ValueError(f"{case.case_id}: duplicate source turn ID {turn.turn_id!r}")
            indexed[turn.turn_id] = (
                block.block_id,
                turn.actor_id,
                turn.occurred_at,
                turn.content,
            )
    return indexed


def _validate_event_authority(
    case: AuthorizationCase,
    event: AuthorizationEvent,
    turns: dict[str, tuple[str, str, str, str]],
    block_position: dict[str, int],
) -> None:
    event_position = block_position.get(event.block_id)
    if event_position is None:
        raise ValueError(f"{case.case_id}: event {event.event_id!r} has unknown block")
    if event.issuer not in case.authorized_issuers:
        raise ValueError(
            f"{case.case_id}: event {event.event_id!r} has non-authoritative issuer "
            f"{event.issuer!r}"
        )
    for source_turn_id in event.source_turn_ids:
        source = turns.get(source_turn_id)
        if source is None:
            raise ValueError(
                f"{case.case_id}: event {event.event_id!r} has unknown source turn "
                f"{source_turn_id!r}"
            )
        block_id, actor_id, occurred_at, content = source
        if block_id != event.block_id:
            raise ValueError(
                f"{case.case_id}: event {event.event_id!r} source {source_turn_id!r} "
                "must belong to the event block"
            )
        if actor_id != event.issuer:
            raise ValueError(
                f"{case.case_id}: event {event.event_id!r} source {source_turn_id!r} "
                f"was authored by {actor_id!r}, not event issuer {event.issuer!r}"
            )
        source_time = _timestamp(occurred_at)
        event_time = _timestamp(event.effective_at)
        if source_time > event_time:
            raise ValueError(
                f"{case.case_id}: event {event.event_id!r} becomes effective before "
                f"source {source_turn_id!r} occurred"
            )
        if source_time != event_time and event.effective_at not in content:
            raise ValueError(
                f"{case.case_id}: event {event.event_id!r} differs from source time, "
                "so its source must state the exact effective_at timestamp"
            )
        if "immediate" in content.lower() and source_time != event_time:
            raise ValueError(
                f"{case.case_id}: immediate event {event.event_id!r} must become "
                "effective when its authoritative source turn occurred"
            )
    if event.event_type in {"issue", "replace"}:
        assert event.record is not None
        if event.record.issuer != event.issuer:
            raise ValueError(
                f"{case.case_id}: event {event.event_id!r} record issuer "
                "must match the event issuer"
            )
        if not set(event.source_turn_ids).issubset(event.record.source_turn_ids):
            raise ValueError(
                f"{case.case_id}: event {event.event_id!r} sources must be present "
                "in the event record provenance"
            )
        for source_turn_id in event.record.source_turn_ids:
            source = turns.get(source_turn_id)
            if source is None:
                raise ValueError(
                    f"{case.case_id}: event {event.event_id!r} record has unknown "
                    f"source turn {source_turn_id!r}"
                )
            source_block_id, _, _, _ = source
            if block_position[source_block_id] > event_position:
                raise ValueError(
                    f"{case.case_id}: event {event.event_id!r} record cites future "
                    f"source turn {source_turn_id!r}"
                )


def _validate_event_order(case: AuthorizationCase) -> None:
    times = [_timestamp(event.effective_at) for event in case.events]
    if any(previous >= current for previous, current in zip(times, times[1:])):
        raise ValueError(
            f"{case.case_id}: effective event times must be globally strictly increasing"
        )


def _apply_event(
    case_id: str,
    ledger: dict[str, CanonicalAuthorizationRecord],
    event: AuthorizationEvent,
) -> None:
    target = ledger.get(event.authorization_id)
    if event.event_type == "issue":
        if target is not None:
            raise ValueError(
                f"{case_id}: issue event {event.event_id!r} reuses {event.authorization_id!r}"
            )
        assert event.record is not None
        ledger[event.authorization_id] = event.record
        return

    if target is None:
        raise ValueError(
            f"{case_id}: {event.event_type} event {event.event_id!r} targets unknown "
            f"authorization {event.authorization_id!r}"
        )
    if target.status != "active" and not (
        event.event_type == "replace" and target.status == "revoked"
    ):
        raise ValueError(
            f"{case_id}: {event.event_type} event {event.event_id!r} targets "
            f"{target.status} authorization {event.authorization_id!r}"
        )

    source_ids = tuple(dict.fromkeys((*target.source_turn_ids, *event.source_turn_ids)))
    if event.event_type == "patch":
        assert event.patch is not None
        ledger[event.authorization_id] = event.patch.apply(target, event.source_turn_ids)
    elif event.event_type == "revoke":
        ledger[event.authorization_id] = replace(
            target, status="revoked", source_turn_ids=source_ids
        )
    else:
        assert event.record is not None
        if event.record.authorization_id in ledger:
            raise ValueError(
                f"{case_id}: replacement event {event.event_id!r} reuses "
                f"{event.record.authorization_id!r}"
            )
        ledger[event.authorization_id] = replace(
            target, status="superseded", source_turn_ids=source_ids
        )
        ledger[event.record.authorization_id] = event.record


def replay_case(
    case: AuthorizationCase, through_block_index: int | None = None
) -> tuple[LedgerSnapshot, ...]:
    """Replay authoritative events and return an immutable snapshot after every block."""

    if through_block_index is not None and (
        not isinstance(through_block_index, int)
        or isinstance(through_block_index, bool)
        or through_block_index < 0
    ):
        raise ValueError("through_block_index must be a non-negative integer")
    turns = _turn_index(case)
    block_position = {block.block_id: index for index, block in enumerate(case.blocks)}
    _validate_event_order(case)
    events_by_block = _event_by_block(case)
    for event in case.events:
        _validate_event_authority(case, event, turns, block_position)
    ledger: dict[str, CanonicalAuthorizationRecord] = {}
    snapshots = []
    for block in case.blocks:
        if through_block_index is not None and block.block_index > through_block_index:
            break
        for event in events_by_block[block.block_id]:
            _apply_event(case.case_id, ledger, event)
            for record in ledger.values():
                if record.issuer not in case.authorized_issuers:
                    raise ValueError(
                        f"{case.case_id}: event {event.event_id!r} produced a record "
                        "with a non-authoritative issuer"
                    )
        records = tuple(ledger[key] for key in sorted(ledger))
        snapshots.append(
            LedgerSnapshot(
                case_id=case.case_id,
                block_id=block.block_id,
                block_index=block.block_index,
                records=records,
            )
        )
    return tuple(snapshots)


def current_ledger(
    case: AuthorizationCase, through_block_index: int | None = None
) -> tuple[CanonicalAuthorizationRecord, ...]:
    snapshots = replay_case(case, through_block_index=through_block_index)
    return snapshots[-1].records if snapshots else ()


def faithful_current_ledger(case: AuthorizationCase) -> dict[str, Any]:
    """Return the executor-visible typed payload for the case's final canonical state."""

    return {
        "schema_version": "2",
        "authorizations": [record.to_dict() for record in current_ledger(case)],
    }


def render_block(block: ConversationBlock) -> str:
    lines = [f"## Block {block.block_index + 1}: {block.title} (ended {block.ended_at})"]
    lines.extend(
        f"[source_turn_id={turn.turn_id}] [actor_id={turn.actor_id}] "
        f"[occurred_at={turn.occurred_at}] "
        f"{turn.speaker}: {turn.content}"
        for turn in block.turns
    )
    return "\n".join(lines)


def render_full_history(case: AuthorizationCase) -> str:
    return "\n\n".join(render_block(block) for block in case.blocks)


def _transaction_fields(transaction: Transaction) -> dict[str, Any]:
    data = transaction.to_dict()
    data.pop("transaction_id")
    return data


def validate_case(
    case: AuthorizationCase,
    *,
    allow_single_probe_pair: bool = False,
    allow_tiny_control_fixture: bool = False,
) -> None:
    """Reject structurally invalid cases and mislabeled matched probes."""

    minimum_blocks = 2 if allow_tiny_control_fixture else 5
    minimum_turns = 4 if allow_tiny_control_fixture else 40
    if not minimum_blocks <= len(case.blocks) <= 8:
        raise ValueError(
            f"{case.case_id}: cases must contain {minimum_blocks} to 8 "
            "conversation blocks"
        )
    turn_count = sum(len(block.turns) for block in case.blocks)
    if not minimum_turns <= turn_count <= 100:
        raise ValueError(
            f"{case.case_id}: cases must contain {minimum_turns} to 100 "
            "conversation turns"
        )
    block_ids = [block.block_id for block in case.blocks]
    if len(block_ids) != len(set(block_ids)):
        raise ValueError(f"{case.case_id}: duplicate block IDs")
    if [block.block_index for block in case.blocks] != list(range(len(case.blocks))):
        raise ValueError(f"{case.case_id}: block indices must be contiguous and ordered")
    block_times = [_timestamp(block.ended_at) for block in case.blocks]
    if block_times != sorted(block_times) or len(block_times) != len(set(block_times)):
        raise ValueError(f"{case.case_id}: block end times must be strictly increasing")
    for previous, current in zip(case.blocks, case.blocks[1:]):
        if _timestamp(previous.ended_at) >= _timestamp(current.turns[0].occurred_at):
            raise ValueError(
                f"{case.case_id}: each block must begin after the previous block ended"
            )

    turns = [turn for block in case.blocks for turn in block.turns]
    turn_times = [_timestamp(turn.occurred_at) for turn in turns]
    if any(previous >= current for previous, current in zip(turn_times, turn_times[1:])):
        raise ValueError(f"{case.case_id}: turn times must be globally strictly increasing")
    turn_ids = [turn.turn_id for turn in turns]
    if len(turn_ids) != len(set(turn_ids)):
        raise ValueError(f"{case.case_id}: source turn IDs must be globally unique")
    for turn_id in turn_ids:
        lowered = turn_id.lower()
        if not _OPAQUE_SOURCE_ID_PATTERN.fullmatch(lowered):
            raise ValueError(
                f"{case.case_id}: model-visible source turn ID {turn_id!r} is not opaque"
            )
        forbidden = (case.case_id.lower(), *_TREATMENT_TOKENS)
        if any(token in lowered for token in forbidden):
            raise ValueError(
                f"{case.case_id}: model-visible source turn ID {turn_id!r} "
                "leaks case or treatment identity"
            )
    turn_index = _turn_index(case)
    turn_to_block = {
        turn_id: block_id for turn_id, (block_id, _, _, _) in turn_index.items()
    }

    event_ids = [event.event_id for event in case.events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError(f"{case.case_id}: duplicate event IDs")
    block_position = {block_id: index for index, block_id in enumerate(block_ids)}
    event_positions = []
    event_times = []
    for event in case.events:
        _validate_event_authority(case, event, turn_index, block_position)
        if event.block_id not in block_position:
            raise ValueError(f"{case.case_id}: event {event.event_id} has unknown block")
        event_positions.append(block_position[event.block_id])
        event_time = _timestamp(event.effective_at)
        event_times.append(event_time)
        position = block_position[event.block_id]
        if event_time > block_times[position] or (
            position > 0 and event_time <= block_times[position - 1]
        ):
            raise ValueError(
                f"{case.case_id}: event {event.event_id} time falls outside its block"
            )
        unknown_sources = set(event.source_turn_ids) - set(turn_ids)
        if unknown_sources:
            raise ValueError(
                f"{case.case_id}: event {event.event_id} has unknown source turns "
                f"{sorted(unknown_sources)}"
            )
        if any(turn_to_block[source] != event.block_id for source in event.source_turn_ids):
            raise ValueError(
                f"{case.case_id}: event {event.event_id} sources must belong to its block"
            )
    if event_positions != sorted(event_positions):
        raise ValueError(f"{case.case_id}: events must follow block order")
    _validate_event_order(case)

    snapshots = replay_case(case)
    if len(snapshots) != len(case.blocks):
        raise ValueError(f"{case.case_id}: replay did not produce one snapshot per block")
    for snapshot in snapshots:
        for record in snapshot.records:
            if _timestamp(record.valid_from) >= _timestamp(record.valid_until):
                raise ValueError(
                    f"{case.case_id}: invalid interval in {record.authorization_id}"
                )
            if record.issuer not in case.authorized_issuers:
                raise ValueError(
                    f"{case.case_id}: canonical record has non-authoritative issuer"
                )

    pair_ids = [pair.pair_id for pair in case.probe_pairs]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError(f"{case.case_id}: duplicate matched-pair IDs")
    dimensions = {pair.dimension for pair in case.probe_pairs}
    if allow_single_probe_pair:
        if len(case.probe_pairs) != 1 or not dimensions <= {
            "amount",
            "time",
            "category",
        }:
            raise ValueError(
                f"{case.case_id}: deployment-like controls require one amount, time, "
                "or category pair"
            )
    elif dimensions != {"amount", "time", "category"}:
        raise ValueError(f"{case.case_id}: probes must cover amount, time, and category")
    elif len(case.probe_pairs) != 3:
        raise ValueError(f"{case.case_id}: cases must contain exactly three matched pairs")
    probe_names = [
        probe.name
        for pair in case.probe_pairs
        for probe in (pair.in_scope, pair.out_of_scope)
    ]
    if len(probe_names) != len(set(probe_names)):
        raise ValueError(f"{case.case_id}: duplicate probe names")

    final_ledger = current_ledger(case)
    final_event_time = max(event_times)
    rendered_history = render_full_history(case)
    target_field = {"amount": "amount", "time": "action_time", "category": "category"}
    for pair in case.probe_pairs:
        for probe in (pair.in_scope, pair.out_of_scope):
            if probe.transaction.transaction_id in rendered_history:
                raise ValueError(
                    f"{case.case_id}/{pair.pair_id}: future transaction leaked into history"
                )
        left = _transaction_fields(pair.in_scope.transaction)
        right = _transaction_fields(pair.out_of_scope.transaction)
        differences = {key for key in left if left[key] != right[key]}
        if differences != {target_field[pair.dimension]}:
            raise ValueError(
                f"{case.case_id}/{pair.pair_id}: matched probes differ in {sorted(differences)}"
            )
        for probe in (pair.in_scope, pair.out_of_scope):
            probe_time = _timestamp(probe.transaction.action_time)
            if probe_time <= final_event_time or probe_time <= block_times[-1]:
                raise ValueError(
                    f"{case.case_id}/{pair.pair_id}: probe must occur after the final block"
                )
        in_decision = evaluate_ledger(
            final_ledger,
            pair.in_scope.transaction,
            authorized_issuers=case.authorized_issuers,
        )
        out_decision = evaluate_ledger(
            final_ledger,
            pair.out_of_scope.transaction,
            authorized_issuers=case.authorized_issuers,
        )
        if not in_decision.authorized or out_decision.authorized:
            raise ValueError(
                f"{case.case_id}/{pair.pair_id}: expected in-scope true/out-of-scope false"
            )


def load_cases(
    version: str = "benchmark_v1",
    data_path: Path | None = None,
    *,
    allow_single_probe_pair: bool = False,
) -> tuple[AuthorizationCase, ...]:
    if not _VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"invalid corpus version: {version!r}")
    path = data_path or DATA_DIR / f"{version}.jsonl"
    if data_path is None:
        from .compile_corpus import check_compiled

        check_compiled(version, output_path=path)
    cases = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                case = AuthorizationCase.from_dict(json.loads(line))
                if case.schema_version != version:
                    raise ValueError(
                        f"schema_version {case.schema_version!r} does not match {version!r}"
                    )
                validate_case(
                    case,
                    allow_single_probe_pair=allow_single_probe_pair,
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid case at {path}:{line_number}: {exc}") from exc
            cases.append(case)
    if not cases:
        raise ValueError(f"corpus is empty: {path}")
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError(f"duplicate case IDs in {path}")
    source_ids = [
        turn.turn_id for case in cases for block in case.blocks for turn in block.turns
    ]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError(f"source turn IDs must be globally unique across {path}")
    return tuple(cases)
