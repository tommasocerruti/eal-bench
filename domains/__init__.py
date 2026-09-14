"""Explicit registry for authorization-memory benchmark domains."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from .base import AuthorizationMemoryDomain
from .event_sourcing import EventSourcingSpec


DomainFactory = Callable[[], AuthorizationMemoryDomain]


def _with_event_sourcing(
    domain: AuthorizationMemoryDomain, spec: EventSourcingSpec
) -> AuthorizationMemoryDomain:
    # Complete construction before exposing the frozen domain through the registry.
    object.__setattr__(domain, "event_sourcing", spec)
    return domain


def _procurement() -> AuthorizationMemoryDomain:
    from .procurement import ProcurementDomain

    domain = ProcurementDomain()
    return _with_event_sourcing(
        domain,
        EventSourcingSpec(
            retain_inactive_records=True,
            replacement_target_field="authorization_id",
            order_by_effective_at=True,
            nested_scope_fields=("vendor", "allowed_categories", "max_amount", "currency"),
        ),
    )


def _cybersecurity() -> AuthorizationMemoryDomain:
    from .cybersecurity import create_domain

    domain = create_domain()
    return _with_event_sourcing(domain, EventSourcingSpec())


def _finance() -> AuthorizationMemoryDomain:
    from .finance import create_domain

    domain = create_domain()
    return _with_event_sourcing(
        domain,
        EventSourcingSpec(
            source_id_separator=" | ",
            empty_supersedes="none",
            flattened_scope_list_fields=("strategy_ids", "instrument_ids", "sides", "order_types"),
        ),
    )


DOMAINS: dict[str, DomainFactory] = {
    "finance": _finance,
    "cybersecurity": _cybersecurity,
    "procurement": _procurement,
}


@lru_cache(maxsize=None)
def get_domain(domain_id: str) -> AuthorizationMemoryDomain:
    try:
        factory = DOMAINS[domain_id]
    except KeyError as exc:
        available = ", ".join(list_domains())
        raise ValueError(f"unknown domain {domain_id!r}; available: {available}") from exc
    return factory()


def list_domains(*, maturity: str | None = None) -> tuple[str, ...]:
    domain_ids = tuple(sorted(DOMAINS))
    if maturity is None:
        return domain_ids
    return tuple(
        domain_id for domain_id in domain_ids if get_domain(domain_id).maturity == maturity
    )


__all__ = [
    "DOMAINS",
    "AuthorizationMemoryDomain",
    "get_domain",
    "list_domains",
]
