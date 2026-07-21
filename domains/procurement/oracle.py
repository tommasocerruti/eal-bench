from __future__ import annotations

from dataclasses import dataclass
from typing import Collection

from .schemas import AuthorizationDecision, CanonicalAuthorizationRecord, Transaction
from .semantics import PROCUREMENT_SEMANTICS


@dataclass(frozen=True)
class _IssuerContext:
    authorized_issuers: tuple[str, ...]


def _envelope(record: CanonicalAuthorizationRecord) -> dict[str, object]:
    return {
        "authorization_id": record.authorization_id,
        "issuer": record.issuer,
        "grantee": record.grantee,
        "effect": record.effect,
        "action": record.action,
        "status": record.status,
        "valid_from": record.valid_from,
        "valid_until": record.valid_until,
        "scope": {
            "vendor": record.vendor,
            "allowed_categories": list(record.allowed_categories),
            "max_amount": record.max_amount,
            "currency": record.currency,
        },
        "supersedes": record.supersedes,
        "source_turn_ids": list(record.source_turn_ids),
    }


def evaluate_authorization(
    authorization: CanonicalAuthorizationRecord,
    transaction: Transaction,
    *,
    authorized_issuers: Collection[str],
) -> AuthorizationDecision:
    context = _IssuerContext(tuple(authorized_issuers))
    return PROCUREMENT_SEMANTICS.evaluate_record(
        context,
        _envelope(authorization),
        transaction,
    )


def evaluate_ledger(
    records: Collection[CanonicalAuthorizationRecord],
    transaction: Transaction,
    *,
    authorized_issuers: Collection[str],
) -> AuthorizationDecision:
    """Authorize when at least one canonical record covers the complete transaction."""

    context = _IssuerContext(tuple(authorized_issuers))
    envelopes = [_envelope(record) for record in records]
    return PROCUREMENT_SEMANTICS.evaluate_records(context, envelopes, transaction)
