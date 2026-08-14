from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import FinanceCase, TradeRequest, parse_timestamp


def record_denial(
    case: FinanceCase,
    record: Mapping[str, Any],
    request: TradeRequest,
) -> str | None:
    del case
    if record.get("status") != "active":
        return "inactive"
    if record.get("issuer") != "portfolio_mandate_officer":
        return "issuer"
    if record.get("grantee") != request.actor_id:
        return "actor"
    if record.get("effect") != "permit_portfolio_order":
        return "effect"
    if record.get("action") != "place_portfolio_order":
        return "action"
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
    exact = (
        ("account_id", request.account_id, "account"),
        ("settlement_currency", request.settlement_currency, "currency"),
    )
    for field, actual, reason in exact:
        if scope.get(field) != actual:
            return reason
    memberships = (
        ("strategy_ids", request.strategy_id, "strategy"),
        ("instrument_ids", request.instrument_id, "instrument"),
        ("sides", request.side, "side"),
        ("order_types", request.order_type, "order_type"),
    )
    for field, actual, reason in memberships:
        values = scope.get(field)
        if not isinstance(values, list) or actual not in values:
            return reason
    maximum_quantity = scope.get("max_quantity")
    if not isinstance(maximum_quantity, int) or request.quantity > maximum_quantity:
        return "quantity"
    minimum_price = scope.get("min_limit_price_micros")
    maximum_price = scope.get("max_limit_price_micros")
    if not isinstance(minimum_price, int) or not isinstance(maximum_price, int):
        return "price_window"
    if not minimum_price <= request.limit_price_micros <= maximum_price:
        return "limit_price"
    return None
