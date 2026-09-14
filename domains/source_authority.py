"""Default immutable-principal authority rules for domain source turns."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .base import (
    AuthorizationMemoryDomain,
    CitedSourceAuthorityAdapter,
    CitedSourceAuthoritySpec,
    ImmutablePrincipalSourceAuthorityAdapter,
)


def cited_source_authority_adapter(
    domain: AuthorizationMemoryDomain,
) -> CitedSourceAuthorityAdapter:
    if domain.cited_source_authority is not None:
        return domain.cited_source_authority
    return ImmutablePrincipalSourceAuthorityAdapter(
        CitedSourceAuthoritySpec(
            principal_id=_turn_principal_id,
            authorization_capable_principals=(
                lambda case: _authorization_capable_principals(domain, case)
            ),
            record_source_turn_ids=_record_source_turn_ids,
        )
    )


def _authorization_capable_principals(
    domain: AuthorizationMemoryDomain,
    case: Any,
) -> tuple[str, ...]:
    metadata = domain.corpus.case_metadata(case)
    values = metadata.get("authorized_principals")
    if values is None:
        values = metadata.get("authorized_issuers")
    if values is None:
        context = domain.get_prompt_policy().context_builder(case)
        values = context.get("authorized_principals")
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(
            f"domain {domain.domain_id!r} does not expose an immutable "
            "authorization-capable principal set"
        )
    principals = tuple(values)
    if not principals or any(
        not isinstance(value, str) or not value.strip() for value in principals
    ):
        raise ValueError("authorization-capable principals must be nonempty strings")
    return principals


def _turn_principal_id(turn: Any) -> str:
    value = getattr(turn, "actor_id", None)
    if value is None:
        value = getattr(turn, "speaker_id", None)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source turn has no normalized principal identity")
    return value


def _record_source_turn_ids(record: Mapping[str, Any]) -> tuple[str, ...]:
    value = record.get("source_turn_ids")
    if isinstance(value, str):
        return tuple(value.split(" | "))
    if not isinstance(value, Sequence):
        raise ValueError("record source_turn_ids must be a string or sequence")
    if any(not isinstance(item, str) for item in value):
        raise ValueError("record source_turn_ids must contain only strings")
    return tuple(value)
