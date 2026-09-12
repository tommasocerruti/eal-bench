"""Versioned identity for the resources an evaluation track consumes.

Every trial and every metric carries one of these. Two results are comparable only
when their `ResourceVersions` match.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from domains import get_domain, list_domains
from domains.base import AuthorizationMemoryDomain, PresentationProfile

PROTOCOL_ID = "eal_bench.eval/v1"
SCORER_ID = "eal_bench.eval.scoring/v1"

__all__ = [
    "PROTOCOL_ID",
    "SCORER_ID",
    "ResourceVersions",
    "list_domains",
    "load_domain",
    "resolve_corpus_version",
    "resolve_presentation",
]


@dataclass(frozen=True)
class ResourceVersions:
    domain_id: str
    domain_adapter_version: str
    domain_maturity: str
    corpus_version: str
    presentation_id: str
    presentation_hash: str
    memory_implementation_id: str
    memory_implementation_hash: str
    scorer_id: str = SCORER_ID
    protocol_id: str = PROTOCOL_ID

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_domain(domain_id: str) -> AuthorizationMemoryDomain:
    return get_domain(domain_id)


def resolve_corpus_version(
    domain: AuthorizationMemoryDomain,
    corpus_version: str | None = None,
) -> str:
    if corpus_version is None:
        return domain.corpus.default_version
    if corpus_version not in domain.corpus.versions:
        available = ", ".join(domain.corpus.versions)
        raise ValueError(
            f"unknown corpus version {corpus_version!r} for domain "
            f"{domain.domain_id!r}; available: {available}"
        )
    return corpus_version


def resolve_presentation(
    domain: AuthorizationMemoryDomain,
    presentation_id: str | None = None,
) -> PresentationProfile:
    resolved = presentation_id or domain.default_presentation_id
    try:
        return domain.presentations[resolved]
    except KeyError as exc:
        available = ", ".join(sorted(domain.presentations))
        raise ValueError(
            f"unknown presentation {resolved!r} for domain "
            f"{domain.domain_id!r}; available: {available}"
        ) from exc


def describe(
    domain: AuthorizationMemoryDomain,
    *,
    corpus_version: str | None = None,
    presentation_id: str | None = None,
) -> ResourceVersions:
    from experiments.authorization_memory.langmem_writer import (
        memory_implementation_manifest,
    )
    from experiments.authorization_memory.persistence import content_hash

    presentation = resolve_presentation(domain, presentation_id)
    manifest = memory_implementation_manifest(domain)
    return ResourceVersions(
        domain_id=domain.domain_id,
        domain_adapter_version=domain.adapter_version,
        domain_maturity=domain.maturity,
        corpus_version=resolve_corpus_version(domain, corpus_version),
        presentation_id=presentation.presentation_id,
        presentation_hash=content_hash(presentation.to_dict()),
        memory_implementation_id=manifest["memory_implementation_id"],
        memory_implementation_hash=manifest["memory_implementation_hash"],
    )
