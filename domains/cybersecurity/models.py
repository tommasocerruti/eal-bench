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
class ResponseRequest:
    actor_id: str
    tenant_id: str
    incident_id: str
    asset_id: str
    environment: str
    response_action: str
    vulnerability_id: str
    requested_at: str
    execution_course: str = field(
        default="submitted_response",
        compare=False,
        repr=False,
    )
    operational_near_match: Mapping[str, str] | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    @property
    def action(self) -> str:
        if self.execution_course in {
            "operational_near_match",
            "option_1",
            "operational_payload",
        }:
            return "execute_operational_payload"
        return "execute_submitted_payload"

    def to_dict(self) -> dict[str, str]:
        return {
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "incident_id": self.incident_id,
            "asset_id": self.asset_id,
            "environment": self.environment,
            "response_action": self.response_action,
            "vulnerability_id": self.vulnerability_id,
            "requested_at": self.requested_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ResponseRequest:
        return cls(
            **{
                name: str(value[name])
                for name in (
                    "actor_id",
                    "tenant_id",
                    "incident_id",
                    "asset_id",
                    "environment",
                    "response_action",
                    "vulnerability_id",
                    "requested_at",
                )
            }
        )


def resolve_execution_course(
    requested: ResponseRequest,
    course: object,
) -> ResponseRequest | None:
    if course in {"submitted_response", "submitted_payload"}:
        return requested
    if course not in {
        "operational_near_match",
        "option_1",
        "operational_payload",
    }:
        return None
    payload = requested.operational_near_match
    if not isinstance(payload, Mapping):
        return None
    try:
        return replace(
            ResponseRequest.from_dict(dict(payload)),
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
    changes: dict[str, Any] | None = None
    supersedes: str | None = None


@dataclass(frozen=True)
class CybersecurityCase:
    case_id: str
    family: str
    organization: str
    system_name: str
    blocks: tuple[ConversationBlock, ...]
    events: tuple[AuthorizationEvent, ...]
    probes: tuple[BenchmarkProbe, ...]
    preferred_request: ResponseRequest
    preferred_requests: dict[str, ResponseRequest]
    pressure_addition: str
    operational_stakes: str
    alternative_disadvantage: str
    metadata: dict[str, Any]


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def patch_envelope(
    current: AuthorizationEnvelope,
    changes: dict[str, Any],
    source_turn_id: str,
) -> AuthorizationEnvelope:
    scope = {**current.scope, **dict(changes.get("scope", {}))}
    direct = {
        key: value
        for key, value in changes.items()
        if key != "scope" and hasattr(current, key)
    }
    return replace(
        current,
        **direct,
        scope=scope,
        source_turn_ids=(*current.source_turn_ids, source_turn_id),
    )
