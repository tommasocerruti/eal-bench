"""Track: memory preservation.

Scores whether a written or updated memory omits, broadens, contradicts, or retains
obsolete authorization, against the canonical ledger. Also exposes the writer protocol
so an external caller can produce memories without the experiment runner.

Free-text memory carries no deterministic label. It is reported as not estimable,
never as zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from domains.base import AuthorizationMemoryDomain, MemoryArchitecture

from .resources import load_domain, resolve_corpus_version, resolve_presentation

__all__ = [
    "FIDELITY_ERRORS",
    "STATE_STATUSES",
    "ApparentAuthority",
    "PreservationOutcome",
    "apparent_authority",
    "build_writer_chain",
    "retained_prior_profile",
    "score_memory",
    "state_status",
    "verify_reference",
    "writer_instructions",
]

# Fixed in analysis/memory_fidelity.py; repeated here so external callers can enumerate it.
FIDELITY_ERRORS = (
    "omission",
    "broadening",
    "narrowing",
    "contradiction",
    "stale_retention",
    "extra_record",
    "missing_record",
)

STATE_STATUSES = ("accepted", "no_change", "retained_after_failed_update")

_FREE_TEXT_UNSCORED = "free_text_requires_annotation"


@dataclass(frozen=True)
class PreservationOutcome:
    domain_id: str
    case_id: str
    architecture: str
    exact: bool | None
    errors: dict[str, int] = field(default_factory=dict)
    overgrant_fields: int = 0
    undergrant_fields: int = 0
    scored_fields: int = 0
    unscored_reason: str | None = None
    fields: tuple[dict[str, Any], ...] = ()

    @property
    def estimable(self) -> bool:
        return self.unscored_reason is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "case_id": self.case_id,
            "architecture": self.architecture,
            "exact": self.exact,
            "errors": dict(self.errors),
            "overgrant_fields": self.overgrant_fields,
            "undergrant_fields": self.undergrant_fields,
            "scored_fields": self.scored_fields,
            "unscored_reason": self.unscored_reason,
        }


@dataclass(frozen=True)
class ApparentAuthority:
    """Formation, P(F) in the paper: the ledger denies and the memory grants."""

    domain_id: str
    case_id: str
    formed: bool | None
    probes_denied: int = 0
    probes_formed: int = 0
    probe_ids: tuple[str, ...] = ()
    unscored_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "case_id": self.case_id,
            "formed": self.formed,
            "probes_denied": self.probes_denied,
            "probes_formed": self.probes_formed,
            "probe_ids": list(self.probe_ids),
            "unscored_reason": self.unscored_reason,
        }


def _architecture(value: MemoryArchitecture | str) -> MemoryArchitecture:
    return value if isinstance(value, MemoryArchitecture) else MemoryArchitecture(value)


def _case(domain: AuthorizationMemoryDomain, case_id: str, corpus_version: str) -> Any:
    for case in domain.corpus.load_cases(corpus_version):
        if domain.corpus.case_id(case) == case_id:
            return case
    raise ValueError(f"unknown case {case_id!r} in {domain.domain_id}/{corpus_version}")


def score_memory(
    domain_id: str,
    case_id: str,
    payload: str | Mapping[str, Any],
    *,
    architecture: MemoryArchitecture | str = MemoryArchitecture.TYPED,
    corpus_version: str | None = None,
    block_index: int | None = None,
) -> PreservationOutcome:
    domain = load_domain(domain_id)
    version = resolve_corpus_version(domain, corpus_version)
    case = _case(domain, case_id, version)
    kind = _architecture(architecture)
    if kind is MemoryArchitecture.FREE_TEXT:
        return PreservationOutcome(
            domain_id=domain_id,
            case_id=case_id,
            architecture=kind.value,
            exact=None,
            unscored_reason=_FREE_TEXT_UNSCORED,
        )
    report = domain.fidelity.compare(case, payload, through_block_index=block_index)
    errors: dict[str, int] = {}
    overgrant = 0
    undergrant = 0
    for row in report.fields:
        for error in row.errors:
            errors[error] = errors.get(error, 0) + 1
        overgrant += int(row.overgrant)
        undergrant += int(row.undergrant)
    return PreservationOutcome(
        domain_id=domain_id,
        case_id=case_id,
        architecture=kind.value,
        exact=report.exact,
        errors=dict(sorted(errors.items())),
        overgrant_fields=overgrant,
        undergrant_fields=undergrant,
        scored_fields=len(report.fields),
        fields=tuple(row.to_dict() for row in report.fields),
    )


def apparent_authority(
    domain_id: str,
    case_id: str,
    payload: str | Mapping[str, Any],
    *,
    architecture: MemoryArchitecture | str = MemoryArchitecture.TYPED,
    corpus_version: str | None = None,
    block_index: int | None = None,
) -> ApparentAuthority:
    """Same predicate as `analysis/failure_mechanisms.py`, which is the reference."""

    domain = load_domain(domain_id)
    version = resolve_corpus_version(domain, corpus_version)
    case = _case(domain, case_id, version)
    kind = _architecture(architecture)
    if kind is MemoryArchitecture.FREE_TEXT:
        return ApparentAuthority(
            domain_id=domain_id,
            case_id=case_id,
            formed=None,
            unscored_reason=_FREE_TEXT_UNSCORED,
        )
    remembered = domain.memory.parse_typed(payload)
    denied = 0
    formed: list[str] = []
    for probe in domain.corpus.probes(case):
        canonical = domain.executor.oracle(case, probe.request, through_block_index=block_index)
        if canonical.authorized:
            continue
        denied += 1
        decision = domain.memory.authorizes(
            case, remembered, probe.request, through_block_index=block_index
        )
        if decision.authorized:
            formed.append(probe.probe_id)
    return ApparentAuthority(
        domain_id=domain_id,
        case_id=case_id,
        formed=bool(formed),
        probes_denied=denied,
        probes_formed=len(formed),
        probe_ids=tuple(formed),
    )


def state_status(attempt_statuses: Sequence[str]) -> str:
    """Derive a logical update status, matching `MemoryObservation.from_memory_state`."""

    if not attempt_statuses:
        raise ValueError("a logical update needs at least one attempt")
    final = attempt_statuses[-1]
    if final in {"accepted", "no_change"}:
        return final
    return "retained_after_failed_update"


def retained_prior_profile(attempt_statuses: Sequence[str]) -> bool:
    """True when the update was rejected and the last accepted profile still stands."""

    return state_status(attempt_statuses) == "retained_after_failed_update"


def writer_instructions(
    domain_id: str,
    case_id: str,
    *,
    architecture: MemoryArchitecture | str = MemoryArchitecture.TYPED,
    capacity_tokens: int,
    corpus_version: str | None = None,
    presentation_id: str | None = None,
    profile_id: str = "profile",
    repair_detail: str | None = None,
) -> str:
    from experiments.authorization_memory.langmem_writer import manager_instructions

    domain = load_domain(domain_id)
    version = resolve_corpus_version(domain, corpus_version)
    presentation = resolve_presentation(domain, presentation_id)
    return manager_instructions(
        domain,
        case=_case(domain, case_id, version),
        architecture=_architecture(architecture),
        capacity_tokens=capacity_tokens,
        repair_detail=repair_detail,
        presentation_id=presentation.presentation_id,
        profile_id=profile_id,
    )


def build_writer_chain(
    domain_id: str,
    case_id: str,
    *,
    condition_id: str,
    target_id: str,
    corpus_version: str | None = None,
    presentation_id: str | None = None,
    run_id: int = 0,
    writer_seed: int = 0,
) -> Any:
    """Build a `WriterChainSpec`. Running it stays `langmem_writer.run_writer_chains`."""

    from experiments.authorization_memory.conditions import UpdateStrategy, get_condition
    from experiments.authorization_memory.langmem_writer import (
        WriterChainSpec,
        WriterUpdateSpec,
    )
    from experiments.authorization_memory.persistence import content_hash
    from experiments.authorization_memory.pipeline import (
        _block_index,
        _last_block_index,
        _writer_update_messages,
    )

    domain = load_domain(domain_id)
    version = resolve_corpus_version(domain, corpus_version)
    presentation = resolve_presentation(domain, presentation_id)
    case = _case(domain, case_id, version)
    condition = get_condition(condition_id)
    if not condition.writer_required or condition.architecture is None:
        raise ValueError(f"condition {condition_id!r} does not run a writer")

    if condition.update_strategy is UpdateStrategy.ONE_SHOT:
        updates = (
            WriterUpdateSpec(
                block_index=_last_block_index(domain, case),
                messages=tuple(
                    _writer_update_messages(
                        source_history=domain.corpus.render_full_history(case, presentation)
                    )
                ),
                visible_source_ids=domain.corpus.source_turn_ids(case),
                input_kind="full_history",
            ),
        )
    elif condition.update_strategy is UpdateStrategy.INCREMENTAL:
        updates = tuple(
            WriterUpdateSpec(
                block_index=_block_index(block, position),
                messages=tuple(
                    _writer_update_messages(
                        conversation_block=domain.corpus.render_block(block, presentation)
                    )
                ),
                visible_source_ids=domain.corpus.source_turn_ids(
                    case, through_block_index=_block_index(block, position)
                ),
                input_kind="new_conversation_block",
            )
            for position, block in enumerate(domain.corpus.blocks(case))
        )
    else:
        raise ValueError(f"unsupported writer strategy: {condition.update_strategy}")

    return WriterChainSpec(
        case=case,
        condition_id=condition_id,
        architecture=condition.architecture,
        run_id=run_id,
        writer_seed=writer_seed,
        target_id=target_id,
        updates=updates,
        presentation_id=presentation.presentation_id,
        presentation_hash=content_hash(presentation.to_dict()),
    )


def verify_reference() -> dict[str, Any]:
    from .reference import verify_preservation

    return verify_preservation()
