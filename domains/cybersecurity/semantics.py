from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import CybersecurityCase, ResponseRequest, parse_timestamp


def record_denial(
    case: CybersecurityCase,
    record: Mapping[str, Any],
    request: ResponseRequest,
) -> str | None:
    del case
    if record.get("status") != "active":
        return "inactive"
    if record.get("issuer") != "security_duty_officer":
        return "issuer"
    if record.get("grantee") != request.actor_id:
        return "actor"
    if record.get("effect") != "permit_incident_response":
        return "effect"
    if record.get("action") != "execute_response_action":
        return "action_type"
    valid_from = record.get("valid_from")
    valid_until = record.get("valid_until")
    if not isinstance(valid_from, str) or not isinstance(valid_until, str):
        return "unknown_window"
    requested_at = parse_timestamp(request.requested_at)
    if not (parse_timestamp(valid_from) <= requested_at < parse_timestamp(valid_until)):
        return "time"
    scope = record.get("scope")
    if not isinstance(scope, Mapping):
        return "missing_scope"
    checks = (
        ("tenant_id", request.tenant_id, "tenant"),
        ("incident_id", request.incident_id, "incident"),
    )
    for field, actual, reason in checks:
        if scope.get(field) != actual:
            return reason
    memberships = (
        ("asset_ids", request.asset_id, "asset"),
        ("environments", request.environment, "environment"),
        ("approved_actions", request.response_action, "response_action"),
        ("vulnerability_ids", request.vulnerability_id, "vulnerability"),
    )
    for field, actual, reason in memberships:
        values = scope.get(field)
        if not isinstance(values, list) or actual not in values:
            return reason
    return None
