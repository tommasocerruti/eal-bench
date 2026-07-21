from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from domains.base import MemoryArchitecture
from experiments.authorization_memory.langmem_writer import (
    WriterChainSpec,
    WriterUpdateSpec,
)
from experiments.authorization_memory.persistence import content_hash
from experiments.authorization_memory.schemas import (
    FrozenEvidence,
    MemoryArtifact,
    MemoryOrigin,
    ModelProvenance,
)

from .pipeline import (
    CapacityTier,
    FrozenEvidence as DomainEvidence,
)


def artifact_from_domain(value: Any, presentation: Any) -> MemoryArtifact:
    payload = (
        value.payload.to_dict()
        if hasattr(value.payload, "to_dict")
        else value.payload
    )
    return MemoryArtifact(
        memory_id=value.memory_id,
        parent_memory_id=value.parent_memory_id,
        chain_id=value.chain_id,
        domain_id="procurement",
        case_id=value.case_id,
        condition_id=value.condition_id,
        block_index=value.block_index,
        writer_run_id=value.writer_run_id,
        writer_seed=value.writer_seed,
        writer=_writer(value),
        architecture=MemoryArchitecture(value.architecture.value),
        origin=MemoryOrigin(value.origin.value),
        payload_schema_id=value.payload_schema_id,
        payload_schema_version=value.payload_schema_version,
        payload=payload,
        reference_tokens=value.reference_tokens,
        reference_tokenizer=value.reference_tokenizer,
        content_hash=value.content_hash,
        memory_implementation_id=value.memory_implementation_id,
        memory_implementation_hash=value.memory_implementation_hash,
        profile_id=value.profile_id,
        source_attempt_id=value.source_attempt_id,
        framework_run_ids=value.framework_run_ids,
        framework=dict(value.framework),
        presentation_id=presentation.presentation_id,
        presentation_hash=content_hash(presentation.to_dict()),
    )


def evidence_from_domain(
    value: DomainEvidence,
    presentation: Any,
) -> FrozenEvidence:
    payload = (
        value.memory_payload.to_dict()
        if hasattr(value.memory_payload, "to_dict")
        else value.memory_payload
    )
    return FrozenEvidence(
        evidence_id=value.evidence_id,
        domain_id="procurement",
        case_id=value.case_id,
        condition_id=value.condition_id,
        memory_run_id=value.memory_run_id,
        writer_seed=value.writer_seed,
        writer=_writer(value),
        architecture=(
            MemoryArchitecture(value.architecture.value)
            if value.architecture is not None
            else None
        ),
        memory_id=value.memory_id,
        payload=payload,
        source_history=value.source_history,
        content_hash=value.content_hash,
        memory_implementation_id=value.memory_implementation_id,
        memory_implementation_hash=value.memory_implementation_hash,
        profile_id=value.profile_id,
        source_attempt_id=(
            value.artifact.source_attempt_id
            if value.artifact is not None
            else None
        ),
        presentation_id=presentation.presentation_id,
        presentation_hash=content_hash(presentation.to_dict()),
    )


def standard_writer_specs(
    domain: Any,
    cases: Sequence[Any],
    *,
    presentation: Any,
    target_ids: Sequence[str],
    writer_runs: int,
    seed: int,
) -> tuple[WriterChainSpec, ...]:
    from experiments.authorization_memory.conditions import (
        UpdateStrategy,
        get_condition,
    )

    presentation_hash = content_hash(presentation.to_dict())
    specs = []
    for target_id in target_ids:
        for condition_id in (
            "one_shot_text",
            "one_shot_typed",
            "incremental_text",
            "incremental_typed",
        ):
            condition = get_condition(condition_id)
            assert condition.architecture is not None
            for run_id in range(writer_runs):
                for case in cases:
                    if condition.update_strategy is UpdateStrategy.ONE_SHOT:
                        updates = (
                            WriterUpdateSpec(
                                block_index=domain.corpus.blocks(case)[
                                    -1
                                ].block_index,
                                messages=_update_messages(
                                    "SOURCE_HISTORY",
                                    domain.corpus.render_full_history(
                                        case,
                                        presentation,
                                    ),
                                ),
                                visible_source_ids=(
                                    domain.corpus.source_turn_ids(case)
                                ),
                                input_kind="full_history",
                            ),
                        )
                    else:
                        updates = tuple(
                            WriterUpdateSpec(
                                block_index=block.block_index,
                                messages=_update_messages(
                                    "NEW_CONVERSATION_BLOCK",
                                    domain.corpus.render_block(
                                        block,
                                        presentation,
                                    ),
                                ),
                                visible_source_ids=(
                                    domain.corpus.source_turn_ids(
                                        case,
                                        through_block_index=block.block_index,
                                    )
                                ),
                                input_kind="new_conversation_block",
                            )
                            for block in domain.corpus.blocks(case)
                        )
                    specs.append(
                        WriterChainSpec(
                            case=case,
                            condition_id=condition_id,
                            architecture=condition.architecture,
                            run_id=run_id,
                            writer_seed=seed + run_id,
                            target_id=target_id,
                            updates=updates,
                            presentation_id=presentation.presentation_id,
                            presentation_hash=presentation_hash,
                        )
                    )
    return tuple(specs)


def evidence_to_domain(
    value: FrozenEvidence,
    *,
    tier: CapacityTier,
    capacity_tokens: int,
) -> DomainEvidence:
    from .conditions import ExecutorEvidence
    from .schemas import (
        MemoryArchitecture as DomainArchitecture,
        MemoryArtifact as DomainArtifact,
        MemoryOrigin as DomainOrigin,
        TypedCurrentState,
    )

    artifact = None
    if value.memory_id is not None:
        payload = value.payload
        if value.architecture is MemoryArchitecture.TYPED:
            payload = TypedCurrentState.from_dict(dict(payload or {}))
        artifact = DomainArtifact(
            memory_id=value.memory_id,
            parent_memory_id=None,
            chain_id=stable_id("chain", value.memory_id),
            case_id=value.case_id,
            condition_id=value.condition_id,
            block_index=0,
            writer_model=(
                value.writer.requested_model
                if value.writer is not None
                else None
            ),
            architecture=DomainArchitecture(value.architecture.value),
            origin=(
                DomainOrigin.WRITER
                if value.writer is not None
                else DomainOrigin.FAITHFUL
            ),
            payload=payload,
            reference_tokens=0,
            reference_tokenizer="cl100k_base",
            content_hash=value.content_hash,
            writer_target_id=(
                value.writer.target_id if value.writer is not None else None
            ),
            writer_provider=(
                value.writer.provider if value.writer is not None else None
            ),
            writer_requested_model=(
                value.writer.requested_model
                if value.writer is not None
                else None
            ),
            writer_resolved_model=(
                value.writer.resolved_model
                if value.writer is not None
                else None
            ),
            writer_response_model=(
                value.writer.response_model
                if value.writer is not None
                else None
            ),
            writer_effective_parameters=(
                dict(value.writer.effective_parameters)
                if value.writer is not None
                else {}
            ),
            writer_run_id=value.memory_run_id,
            writer_seed=value.writer_seed,
            payload_schema_id=(
                "procurement_authorization_memory_profile"
                if value.architecture is MemoryArchitecture.TYPED
                else None
            ),
            payload_schema_version=(
                "3"
                if value.architecture is MemoryArchitecture.TYPED
                else None
            ),
            memory_implementation_id=value.memory_implementation_id,
            memory_implementation_hash=value.memory_implementation_hash,
            profile_id=value.profile_id,
            source_attempt_id=value.source_attempt_id,
        )
    if value.source_history is not None:
        kind = ExecutorEvidence.FULL_HISTORY
    elif value.payload is not None:
        kind = ExecutorEvidence.MEMORY
    else:
        kind = ExecutorEvidence.EMPTY
    return DomainEvidence(
        evidence_id=value.evidence_id,
        case_id=value.case_id,
        condition_id=value.condition_id,
        memory_run_id=value.memory_run_id,
        writer_model=(
            value.writer.requested_model
            if value.writer is not None
            else None
        ),
        writer_seed=value.writer_seed,
        architecture=(
            DomainArchitecture(value.architecture.value)
            if value.architecture is not None
            else None
        ),
        executor_evidence=kind,
        capacity_tier=tier,
        capacity_tokens=capacity_tokens,
        artifact=artifact,
        memory_payload=artifact.payload if artifact is not None else None,
        source_history=value.source_history,
        content_hash=value.content_hash,
        writer_target_id=(
            value.writer.target_id if value.writer is not None else None
        ),
        writer_provider=(
            value.writer.provider if value.writer is not None else None
        ),
        writer_requested_model=(
            value.writer.requested_model
            if value.writer is not None
            else None
        ),
        writer_resolved_model=(
            value.writer.resolved_model
            if value.writer is not None
            else None
        ),
        writer_response_model=(
            value.writer.response_model
            if value.writer is not None
            else None
        ),
        writer_effective_parameters=(
            dict(value.writer.effective_parameters)
            if value.writer is not None
            else {}
        ),
        memory_implementation_id=value.memory_implementation_id,
        memory_implementation_hash=value.memory_implementation_hash,
        profile_id=value.profile_id,
    )


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
    return f"{prefix}_{digest}"


def _writer(value: Any) -> ModelProvenance | None:
    fields = (
        value.writer_target_id,
        value.writer_provider,
        value.writer_requested_model,
        value.writer_resolved_model,
        value.writer_response_model,
    )
    if not any(fields) and not value.writer_effective_parameters:
        return None
    return ModelProvenance(
        target_id=value.writer_target_id,
        provider=value.writer_provider,
        requested_model=value.writer_requested_model,
        resolved_model=value.writer_resolved_model,
        response_model=value.writer_response_model,
        effective_parameters=dict(value.writer_effective_parameters),
    )


def _update_messages(
    tag: str,
    content: str,
) -> tuple[dict[str, str], ...]:
    return (
        {
            "role": "user",
            "content": f"<{tag}>\n{content}\n</{tag}>",
        },
    )
