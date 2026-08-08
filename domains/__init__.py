"""Explicit registry for authorization-memory benchmark domains."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from .base import AuthorizationMemoryDomain


DomainFactory = Callable[[], AuthorizationMemoryDomain]


def _procurement() -> AuthorizationMemoryDomain:
    from .procurement import ProcurementDomain

    return ProcurementDomain()


def _cybersecurity() -> AuthorizationMemoryDomain:
    from .cybersecurity import create_domain

    return create_domain()


DOMAINS: dict[str, DomainFactory] = {
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
        domain_id
        for domain_id in domain_ids
        if get_domain(domain_id).maturity == maturity
    )


__all__ = [
    "DOMAINS",
    "AuthorizationMemoryDomain",
    "get_domain",
    "list_domains",
]
