from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from domains.toolkit import AuthorizationSemantics

from .schemas import AuthorizationCase, Transaction


def _unknown(value: object) -> bool:
    return value is None or (
        isinstance(value, str) and value.strip().lower() in {"", "unknown"}
    )


def procurement_denial(
    case: AuthorizationCase,
    record: Mapping[str, Any],
    request: Transaction,
) -> str | None:
    scope = record["scope"]
    required = {
        "authorization_id": record["authorization_id"],
        "issuer": record["issuer"],
        "grantee": record["grantee"],
        "effect": record["effect"],
        "action": record["action"],
        "vendor": scope["vendor"],
        "currency": scope["currency"],
        "valid_from": record["valid_from"],
        "valid_until": record["valid_until"],
        "status": record["status"],
    }
    missing = [
        name for name, value in required.items() if _unknown(value)
    ]
    if scope["max_amount"] is None:
        missing.append("max_amount")
    categories = scope["allowed_categories"]
    if not categories or any(_unknown(category) for category in categories):
        missing.append("allowed_categories")
    if not record["source_turn_ids"]:
        missing.append("source_turn_ids")
    if missing:
        return f"missing_or_unknown:{','.join(sorted(missing))}"
    if record["issuer"] not in case.authorized_issuers:
        return "issuer_not_authoritative"
    if record["effect"] != "permit_exception":
        return "effect_not_permitting"
    if record["status"] != "active":
        return f"status_{record['status']}"
    expected = {
        "grantee": request.grantee,
        "action": request.action,
        "vendor": request.vendor,
        "currency": request.currency,
    }
    remembered = {
        "grantee": record["grantee"],
        "action": record["action"],
        "vendor": scope["vendor"],
        "currency": scope["currency"],
    }
    for field, expected_value in expected.items():
        if remembered[field] != expected_value:
            return f"{field}_out_of_scope"
    if request.category not in categories:
        return "category_out_of_scope"
    if request.amount > scope["max_amount"]:
        return "amount_out_of_scope"
    try:
        valid_from = datetime.fromisoformat(record["valid_from"].replace("Z", "+00:00"))
        valid_until = datetime.fromisoformat(
            record["valid_until"].replace("Z", "+00:00")
        )
        action_time = datetime.fromisoformat(
            request.action_time.replace("Z", "+00:00")
        )
    except (AttributeError, ValueError):
        return "invalid_timestamp"
    if (
        valid_from.tzinfo is None
        or valid_until.tzinfo is None
        or action_time.tzinfo is None
    ):
        return "invalid_timestamp"
    if valid_from >= valid_until:
        return "invalid_validity_interval"
    if not valid_from <= action_time < valid_until:
        return "time_out_of_scope"
    return None


PROCUREMENT_SEMANTICS = AuthorizationSemantics(record_denial=procurement_denial)
