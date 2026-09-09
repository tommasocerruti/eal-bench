"""Frozen Finance corpora and deterministic authorization replay."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from domains.base import AuthorizationEnvelope, BenchmarkProbe, PresentationProfile

from .models import (
    AuthorizationEvent,
    ConversationBlock,
    ConversationTurn,
    FinanceCase,
    TradeRequest,
)


PACKAGE_DIR = Path(__file__).parent
DATA_DIR = PACKAGE_DIR / "data"
VERSIONS = ("calibration_v1", "benchmark_v1")


def _versions() -> tuple[str, ...]:
    return VERSIONS


def load_cases(version: str) -> tuple[FinanceCase, ...]:
    if version not in VERSIONS:
        raise ValueError(f"unsupported Finance corpus: {version!r}")
    payload = json.loads((DATA_DIR / f"{version}.json").read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != "finance_redesign_corpus_v1"
        or payload.get("corpus_version") != version
    ):
        raise ValueError(f"{version}: frozen canonical source has the wrong identity")
    cases = tuple(_case_from_dict(item) for item in payload.get("cases", ()))
    for case in cases:
        validate_case(case)
    return cases


def source_files(version: str) -> tuple[Path, ...]:
    if version not in VERSIONS:
        raise ValueError(f"unsupported Finance corpus: {version!r}")
    from .corpus_redesign import source_files as redesign_source_files

    return redesign_source_files(version)


def corpus_provenance(version: str) -> Mapping[str, Any]:
    from .corpus_redesign import provenance

    return provenance(version, len(load_cases(version)))


def replay_case(
    case: FinanceCase,
    through_block_index: int | None = None,
) -> tuple[AuthorizationEnvelope, ...]:
    limit = case.blocks[-1].block_index if through_block_index is None else through_block_index
    records: dict[str, AuthorizationEnvelope] = {}
    for event in sorted(case.events, key=lambda item: (item.block_index, item.event_id)):
        if event.block_index > limit:
            break
        if event.event_type in {"issue", "replace"}:
            if event.record is None:
                raise ValueError(f"{event.event_id}: missing issued record")
            records[event.authorization_id] = event.record
            if event.event_type == "replace" and event.supersedes in records:
                prior = records[event.supersedes]
                records[event.supersedes] = replace(prior, status="superseded")
        elif event.event_type == "patch":
            current = records.get(event.authorization_id)
            if current is None or event.changes is None:
                raise ValueError(f"{event.event_id}: patch target is unavailable")
            scope = {**current.scope, **dict(event.changes.get("scope", {}))}
            direct = {key: value for key, value in event.changes.items() if key != "scope"}
            records[event.authorization_id] = replace(
                current,
                **direct,
                scope=scope,
                source_turn_ids=(*current.source_turn_ids, event.source_turn_id),
            )
        elif event.event_type == "revoke":
            current = records.get(event.authorization_id)
            if current is None:
                raise ValueError(f"{event.event_id}: revoke target is unavailable")
            records[event.authorization_id] = replace(
                current,
                status="revoked",
                source_turn_ids=(*current.source_turn_ids, event.source_turn_id),
            )
        else:
            raise ValueError(f"{event.event_id}: unsupported event type")
    return tuple(record for _, record in sorted(records.items()) if record.status == "active")


def evaluate_request(
    case: FinanceCase,
    request: TradeRequest,
    through_block_index: int | None = None,
) -> tuple[bool, str]:
    from .semantics import record_denial

    denials = []
    for record in replay_case(case, through_block_index):
        reason = record_denial(case, record.to_dict(), request)
        if reason is None:
            return True, f"permitted:{record.authorization_id}"
        denials.append(f"{record.authorization_id}={reason}")
    return False, "no_matching_trading_mandate:" + ";".join(denials)


def render_block(
    block: ConversationBlock,
    presentation: PresentationProfile | None = None,
) -> str:
    del presentation
    lines = []
    for turn in block.turns:
        lines.extend(
            (
                f"[{turn.occurred_at} | {turn.channel}]",
                f"{turn.speaker_label} [{turn.turn_id}]",
                turn.text,
                "",
            )
        )
    return "\n".join(lines).rstrip()


def render_full_history(
    case: FinanceCase,
    presentation: PresentationProfile | None = None,
) -> str:
    return "\n\n".join(render_block(block, presentation) for block in case.blocks)


def source_turn_ids(
    case: FinanceCase,
    through_block_index: int | None = None,
) -> frozenset[str]:
    return frozenset(
        turn.turn_id
        for block in case.blocks
        if through_block_index is None or block.block_index <= through_block_index
        for turn in block.turns
    )


def validate_case(case: FinanceCase) -> None:
    from .corpus_redesign import validate_case as validate_redesign_case

    validate_redesign_case(case)


def _case_from_dict(raw: Mapping[str, Any]) -> FinanceCase:
    blocks = tuple(
        ConversationBlock(
            block_id=str(block["block_id"]),
            block_index=int(block["block_index"]),
            ended_at=str(block["ended_at"]),
            turns=tuple(ConversationTurn(**turn) for turn in block["turns"]),
        )
        for block in raw["blocks"]
    )
    events = tuple(
        AuthorizationEvent(
            event_id=str(event["event_id"]),
            block_index=int(event["block_index"]),
            event_type=str(event["event_type"]),
            authorization_id=str(event["authorization_id"]),
            issuer=str(event["issuer"]),
            source_turn_id=str(event["source_turn_id"]),
            record=(AuthorizationEnvelope.from_dict(event["record"]) if event.get("record") else None),
            changes=event.get("changes"),
            supersedes=event.get("supersedes"),
        )
        for event in raw["events"]
    )
    probes = tuple(
        BenchmarkProbe(
            probe_id=str(probe["probe_id"]),
            pair_id=str(probe["pair_id"]),
            dimension=str(probe["dimension"]),
            request_scope=str(probe["request_scope"]),
            request=_request_from_dict(probe["request"]),
            metadata=dict(probe["metadata"]),
        )
        for probe in raw["probes"]
    )
    return FinanceCase(
        case_id=str(raw["case_id"]),
        family=str(raw["family"]),
        organization=str(raw["organization"]),
        portfolio_name=str(raw["portfolio_name"]),
        blocks=blocks,
        events=events,
        probes=probes,
        preferred_requests={
            str(pair_id): _request_from_dict(request)
            for pair_id, request in raw["preferred_requests"].items()
        },
        pressure_addition=str(raw["pressure_addition"]),
        operational_stakes=str(raw["operational_stakes"]),
        alternative_disadvantage=str(raw["alternative_disadvantage"]),
        metadata=dict(raw["metadata"]),
    )


def _request_from_dict(raw: Mapping[str, Any]) -> TradeRequest:
    request = TradeRequest.from_dict(raw)
    return replace(
        request,
        execution_course=str(raw.get("execution_course", "submitted_order")),
        operational_near_match=raw.get("operational_near_match"),
    )
