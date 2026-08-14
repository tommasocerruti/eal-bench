from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping

from domains.base import AuthorizationEnvelope, BenchmarkProbe


@dataclass(frozen=True)
class ConversationTurn:
    turn_id: str
    occurred_at: str
    channel: str
    speaker_id: str
    speaker_label: str
    text: str


@dataclass(frozen=True)
class ConversationBlock:
    block_id: str
    block_index: int
    ended_at: str
    turns: tuple[ConversationTurn, ...]


@dataclass(frozen=True)
class TradeRequest:
    actor_id: str
    account_id: str
    strategy_id: str
    instrument_id: str
    side: str
    order_type: str
    quantity: int
    limit_price_micros: int
    settlement_currency: str
    requested_at: str
    execution_course: str = field(default="submitted_order", compare=False, repr=False)
    operational_near_match: Mapping[str, Any] | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    @property
    def action(self) -> str:
        if self.execution_course == "operational_payload":
            return "place_operational_order"
        return "place_submitted_order"

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "account_id": self.account_id,
            "strategy_id": self.strategy_id,
            "instrument_id": self.instrument_id,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "limit_price_micros": self.limit_price_micros,
            "settlement_currency": self.settlement_currency,
            "requested_at": self.requested_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TradeRequest:
        return cls(
            actor_id=str(value["actor_id"]),
            account_id=str(value["account_id"]),
            strategy_id=str(value["strategy_id"]),
            instrument_id=str(value["instrument_id"]),
            side=str(value["side"]),
            order_type=str(value["order_type"]),
            quantity=int(value["quantity"]),
            limit_price_micros=int(value["limit_price_micros"]),
            settlement_currency=str(value["settlement_currency"]),
            requested_at=str(value["requested_at"]),
        )


def resolve_execution_course(requested: TradeRequest, course: object) -> TradeRequest | None:
    if course in {"submitted_order", "submitted_payload"}:
        return requested
    if course not in {"operational_near_match", "operational_payload"}:
        return None
    payload = requested.operational_near_match
    if not isinstance(payload, Mapping):
        return None
    try:
        return replace(
            TradeRequest.from_dict(payload),
            execution_course="operational_payload",
            operational_near_match=payload,
        )
    except (KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class AuthorizationEvent:
    event_id: str
    block_index: int
    event_type: str
    authorization_id: str
    issuer: str
    source_turn_id: str
    record: AuthorizationEnvelope | None = None
    changes: Mapping[str, Any] | None = None
    supersedes: str | None = None


@dataclass(frozen=True)
class FinanceCase:
    case_id: str
    family: str
    organization: str
    portfolio_name: str
    blocks: tuple[ConversationBlock, ...]
    events: tuple[AuthorizationEvent, ...]
    probes: tuple[BenchmarkProbe, ...]
    preferred_requests: Mapping[str, TradeRequest]
    pressure_addition: str
    operational_stakes: str
    alternative_disadvantage: str
    metadata: Mapping[str, Any]


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
