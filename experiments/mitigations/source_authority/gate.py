"""Deterministic cited-source authority gating for typed memories."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from domains.base import (
    AuthorizationMemoryDomain,
    SourceAuthorityMetadata,
)

from domains.source_authority import cited_source_authority_adapter


GATE_SCHEMA_VERSION = "cited_source_authority_gate_v1"


@dataclass(frozen=True)
class CitationGateDecision:
    source_turn_id: str
    passed: bool
    reason: str
    source: SourceAuthorityMetadata | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_turn_id": self.source_turn_id,
            "passed": self.passed,
            "reason": self.reason,
            "source": self.source.to_dict() if self.source is not None else None,
        }


@dataclass(frozen=True)
class RecordGateDecision:
    record_index: int
    authorization_id: str
    passed: bool
    reason: str
    citations: tuple[CitationGateDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_index": self.record_index,
            "authorization_id": self.authorization_id,
            "passed": self.passed,
            "reason": self.reason,
            "citations": [item.to_dict() for item in self.citations],
        }


@dataclass(frozen=True)
class SourceAuthorityGateResult:
    schema_version: str
    through_block_index: int | None
    input_record_count: int
    retained_record_count: int
    gated_state: Mapping[str, Any]
    decisions: tuple[RecordGateDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "through_block_index": self.through_block_index,
            "input_record_count": self.input_record_count,
            "retained_record_count": self.retained_record_count,
            "removed_record_count": self.input_record_count
            - self.retained_record_count,
            "gated_state": dict(self.gated_state),
            "decisions": [item.to_dict() for item in self.decisions],
        }


def apply_cited_source_authority_gate(
    domain: AuthorizationMemoryDomain,
    case: Any,
    remembered_state: Any,
    *,
    through_block_index: int | None,
) -> SourceAuthorityGateResult:
    """Retain records only when every cited visible source is authority-capable."""

    resolver = cited_source_authority_adapter(domain)
    normalized = domain.memory.serialize_typed(remembered_state)
    records = normalized.get("authorizations")
    if not isinstance(records, list):
        raise ValueError("typed memory authorizations must be a list")
    visible_sources = resolver.resolve(case, through_block_index)
    all_sources = resolver.resolve(case, None)
    retained: list[Mapping[str, Any]] = []
    decisions: list[RecordGateDecision] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError("typed memory authorization must be an object")
        citations = resolver.record_source_turn_ids(record)
        passed, reason, citation_decisions = evaluate_cited_sources(
            citations,
            visible_sources=visible_sources,
            all_sources=all_sources,
        )
        if passed:
            retained.append(record)
        decisions.append(
            RecordGateDecision(
                record_index=index,
                authorization_id=str(record.get("authorization_id", "")),
                passed=passed,
                reason=reason,
                citations=citation_decisions,
            )
        )
    gated_payload = {**normalized, "authorizations": retained}
    gated_state = domain.memory.serialize_typed(
        domain.memory.parse_typed(gated_payload)
    )
    return SourceAuthorityGateResult(
        schema_version=GATE_SCHEMA_VERSION,
        through_block_index=through_block_index,
        input_record_count=len(records),
        retained_record_count=len(retained),
        gated_state=gated_state,
        decisions=tuple(decisions),
    )


def evaluate_cited_sources(
    source_turn_ids: tuple[str, ...],
    *,
    visible_sources: Mapping[str, SourceAuthorityMetadata],
    all_sources: Mapping[str, SourceAuthorityMetadata],
) -> tuple[bool, str, tuple[CitationGateDecision, ...]]:
    decisions = tuple(
        _citation_decision(
            source_turn_id,
            visible_sources=visible_sources,
            all_sources=all_sources,
        )
        for source_turn_id in source_turn_ids
    )
    if not decisions:
        return False, "missing_provenance", decisions
    for decision in decisions:
        if not decision.passed:
            return False, decision.reason, decisions
    return True, "all_cited_sources_authority_capable", decisions


def _citation_decision(
    source_turn_id: str,
    *,
    visible_sources: Mapping[str, SourceAuthorityMetadata],
    all_sources: Mapping[str, SourceAuthorityMetadata],
) -> CitationGateDecision:
    if not isinstance(source_turn_id, str) or not source_turn_id.strip():
        return CitationGateDecision(
            source_turn_id=(
                source_turn_id if isinstance(source_turn_id, str) else ""
            ),
            passed=False,
            reason="missing_provenance",
            source=None,
        )
    source = visible_sources.get(source_turn_id)
    if source is None:
        return CitationGateDecision(
            source_turn_id=source_turn_id,
            passed=False,
            reason=(
                "future_provenance"
                if source_turn_id in all_sources
                else "unknown_provenance"
            ),
            source=all_sources.get(source_turn_id),
        )
    if not source.authorization_capable:
        return CitationGateDecision(
            source_turn_id=source_turn_id,
            passed=False,
            reason="source_not_authority_capable",
            source=source,
        )
    return CitationGateDecision(
        source_turn_id=source_turn_id,
        passed=True,
        reason="source_authority_capable",
        source=source,
    )
