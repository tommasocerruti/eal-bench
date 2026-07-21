from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from domains.base import (
    ActionDecision,
    AuthorizationMemoryDomain,
    BenchmarkProbe,
    MemoryArchitecture,
    PresentationProfile,
)

from .challenges import (
    prepare_challenge,
    prepare_challenge_context,
    validate_challenge_context,
)
from .conditions import (
    CONDITION_SPECS,
    ExecutorEvidence,
    UpdateStrategy,
    get_condition,
)
from .langmem_writer import (
    NESTED_ARRAY_PATCH_INSTRUCTION,
    WriterChainSpec,
    WriterUpdateSpec,
    manager_instructions,
    run_writer_chains,
)
from .leakage import validate_model_context_leakage
from .persistence import canonical_json, content_hash
from .provenance import (
    effective_behavioral_parameters,
    resolve_model_provenance,
    with_response_model,
)
from .schemas import (
    Decision,
    FrozenEvidence,
    MemoryArtifact,
    MemoryAttempt,
    MemoryOrigin,
    MemoryState,
    ModelContext,
    ModelProvenance,
    NormalizedTrial,
)
from .study_plan import ExecutorJob, PressureSpec
from .surfaces import model_visible_tools
from .tokens import TokenCounter, count_reference_tokens, reference_tokenizer_name


@dataclass(frozen=True)
class CaseCapacity:
    case_id: str
    history_tokens: int
    faithful_text_tokens: int
    faithful_typed_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "history_tokens": self.history_tokens,
            "faithful_text_tokens": self.faithful_text_tokens,
            "faithful_typed_tokens": self.faithful_typed_tokens,
        }


@dataclass(frozen=True)
class CapacityCalibration:
    reference_tokenizer: str
    largest_faithful_tokens: int
    primary_tokens: int
    tight_tokens: int
    minimum_history_ratio: int
    cases: tuple[CaseCapacity, ...]

    def tokens_for(self, tier: str) -> int:
        if tier == "primary":
            return self.primary_tokens
        if tier == "tight":
            return self.tight_tokens
        raise ValueError(f"unknown capacity tier: {tier}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_tokenizer": self.reference_tokenizer,
            "largest_faithful_tokens": self.largest_faithful_tokens,
            "primary_tokens": self.primary_tokens,
            "tight_tokens": self.tight_tokens,
            "minimum_history_ratio": self.minimum_history_ratio,
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class CoreRunArtifacts:
    calibration: CapacityCalibration
    memories: tuple[MemoryArtifact, ...]
    attempts: tuple[MemoryAttempt, ...]
    states: tuple[MemoryState, ...]
    evidence: tuple[FrozenEvidence, ...]
    trials: tuple[NormalizedTrial, ...]
    model_contexts: tuple[ModelContext, ...]


def calibrate_capacity(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    *,
    corpus_version: str,
    presentation: PresentationProfile | None = None,
    token_counter: TokenCounter | None = None,
) -> CapacityCalibration:
    checked = _validated_cases(domain, cases)
    selected_presentation = presentation or domain.get_presentation()
    rows: list[CaseCapacity] = []
    for case in checked:
        history = domain.corpus.render_full_history(case, selected_presentation)
        faithful_text = domain.memory.faithful_free_text(case)
        faithful_typed = domain.memory.serialize_typed(
            domain.memory.faithful_typed(case)
        )
        rows.append(
            CaseCapacity(
                case_id=domain.corpus.case_id(case),
                history_tokens=count_reference_tokens(history, token_counter),
                faithful_text_tokens=count_reference_tokens(
                    faithful_text, token_counter
                ),
                faithful_typed_tokens=count_reference_tokens(
                    canonical_json(faithful_typed), token_counter
                ),
            )
        )
    if not rows:
        raise ValueError("a corpus must contain at least one case")
    policy = domain.corpus.capacity_policy
    largest = max(
        max(row.faithful_text_tokens, row.faithful_typed_tokens) for row in rows
    )
    primary = policy.calibrated_for(corpus_version, "primary") or math.ceil(
        policy.primary_multiplier * largest
    )
    tight = policy.calibrated_for(corpus_version, "tight") or math.ceil(
        policy.tight_multiplier * largest
    )
    minimum_history_ratio = policy.minimum_history_ratio_for(corpus_version)
    required_history = minimum_history_ratio * primary
    too_short = [row for row in rows if row.history_tokens < required_history]
    if too_short:
        details = ", ".join(
            f"{row.case_id}={row.history_tokens}" for row in too_short
        )
        raise ValueError(
            "history capacity invariant failed: every history must contain at least "
            f"{required_history} reference tokens; {details}"
        )
    return CapacityCalibration(
        reference_tokenizer=reference_tokenizer_name(token_counter),
        largest_faithful_tokens=largest,
        primary_tokens=primary,
        tight_tokens=tight,
        minimum_history_ratio=minimum_history_ratio,
        cases=tuple(rows),
    )


def validate_core_construction(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    *,
    corpus_version: str,
    condition_ids: Collection[str] | None = None,
    presentation: PresentationProfile | None = None,
) -> dict[str, Any]:
    """Build every deterministic core input without making an LLM call."""

    checked = _validated_cases(domain, cases)
    selected_presentation = presentation or domain.get_presentation()
    selected = _selected_conditions(condition_ids)
    calibration = calibrate_capacity(
        domain,
        checked,
        corpus_version=corpus_version,
        presentation=selected_presentation,
    )
    policy = domain.get_prompt_policy(selected_presentation)
    if policy.expose_typed_schema or policy.split_nested_array_patches:
        instructions = manager_instructions(
            domain,
            case=checked[0],
            architecture=MemoryArchitecture.TYPED,
            capacity_tokens=calibration.primary_tokens,
            repair_detail=None,
            presentation_id=selected_presentation.presentation_id,
            profile_id="offline-validation-profile",
        )
        if policy.expose_typed_schema:
            exact_schema = canonical_json(domain.memory.typed_schema())
            if exact_schema not in instructions:
                raise ValueError(
                    "typed writer policy does not expose the exact profile schema"
                )
        if (
            policy.split_nested_array_patches
            and NESTED_ARRAY_PATCH_INSTRUCTION not in instructions
        ):
            raise ValueError(
                "typed writer policy omitted the nested-array patch strategy"
            )
    prompt_count = 0
    probe_count = 0
    checkpoint_count = 0
    semantic_check_count = 0
    fidelity_rows = 0
    for case in checked:
        blocks = domain.corpus.blocks(case)
        checkpoints = domain.corpus.checkpoints(case)
        if any(checkpoint not in blocks for checkpoint in checkpoints):
            raise ValueError(
                f"{domain.corpus.case_id(case)} exposes a checkpoint outside its blocks"
            )
        checkpoint_count += len(checkpoints)
        for condition in selected:
            if condition.update_strategy is UpdateStrategy.ONE_SHOT:
                _writer_update_messages(
                    source_history=domain.corpus.render_full_history(
                        case, selected_presentation
                    ),
                )
                prompt_count += 1
            elif condition.update_strategy is UpdateStrategy.INCREMENTAL:
                for block in blocks:
                    _writer_update_messages(
                        conversation_block=domain.corpus.render_block(
                            block, selected_presentation
                        ),
                    )
                    prompt_count += 1
            elif condition.faithful:
                remembered = domain.memory.faithful_typed(case)
                fidelity_rows += len(
                    domain.fidelity.compare(case, remembered).fields
                )
        for probe in domain.corpus.probes(case):
            canonical = domain.executor.oracle(case, probe.request)
            remembered = domain.memory.faithful_typed(case)
            remembered_decision = domain.memory.authorizes(
                case, remembered, probe.request
            )
            if remembered_decision.authorized != canonical.authorized:
                raise ValueError(
                    f"{domain.corpus.case_id(case)}:{probe.probe_id} faithful "
                    "memory semantics disagree with the canonical oracle"
                )
            semantic_check_count += 1
            _executor_messages(
                domain,
                case,
                probe,
                evidence_kind=ExecutorEvidence.EMPTY,
                presentation=selected_presentation,
            )
            probe_count += 1
    return {
        "status": "passed",
        "domain_id": domain.domain_id,
        "domain_adapter_version": domain.adapter_version,
        "maturity": domain.maturity,
        "corpus_version": corpus_version,
        "presentation": selected_presentation.to_dict(),
        "presentation_hash": content_hash(selected_presentation.to_dict()),
        "case_count": len(checked),
        "block_count": sum(len(domain.corpus.blocks(case)) for case in checked),
        "checkpoint_count": checkpoint_count,
        "probe_count": probe_count,
        "semantic_check_count": semantic_check_count,
        "condition_count": len(selected),
        "writer_prompt_count": prompt_count,
        "fidelity_field_count": fidelity_rows,
        "capacity": calibration.to_dict(),
    }


def run_core(
    llm: Any,
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    *,
    corpus_version: str,
    writer_task: str,
    executor_task: str,
    writer_targets: Sequence[str],
    executor_targets: Sequence[str],
    writer_runs: int = 1,
    executor_runs: int = 1,
    writer_max_attempts: int = 2,
    condition_ids: Collection[str] | None = None,
    capacity_tier: str = "primary",
    batch_size: int | None = None,
    seed: int = 0,
    token_counter: TokenCounter | None = None,
    presentation: PresentationProfile | None = None,
) -> CoreRunArtifacts:
    checked = _validated_cases(domain, cases)
    selected_presentation = presentation or domain.get_presentation()
    selected = _selected_conditions(condition_ids)
    if writer_runs < 1 or executor_runs < 1:
        raise ValueError("writer_runs and executor_runs must be positive")
    if writer_max_attempts not in {1, 2}:
        raise ValueError("writer_max_attempts must be 1 or 2")
    writer_required = any(condition.writer_required for condition in selected)
    if not executor_targets:
        raise ValueError("executor_targets must not be empty")
    if writer_required and not writer_targets:
        raise ValueError(
            "writer_targets must not be empty when selected conditions use a writer"
        )
    if writer_required:
        for target in writer_targets:
            llm.preflight(
                writer_task,
                target=target,
                required_capabilities=(
                    "native_tools",
                    "forced_tool_choice",
                    "seed",
                ),
            )
    for target in executor_targets:
        llm.preflight(
            executor_task,
            target=target,
            required_capabilities=("native_tools", "seed"),
        )

    calibration = calibrate_capacity(
        domain,
        checked,
        corpus_version=corpus_version,
        presentation=selected_presentation,
        token_counter=token_counter,
    )
    capacity = calibration.tokens_for(capacity_tier)
    memories, attempts, states, evidence, writer_contexts = _build_evidence(
        llm,
        domain,
        checked,
        selected,
        writer_task=writer_task,
        writer_targets=writer_targets,
        writer_runs=writer_runs,
        writer_max_attempts=writer_max_attempts,
        capacity_tokens=capacity,
        batch_size=batch_size,
        seed=seed,
        token_counter=token_counter,
        presentation=selected_presentation,
    )
    trials, executor_contexts = _run_executors(
        llm,
        domain,
        checked,
        evidence,
        executor_task=executor_task,
        executor_targets=executor_targets,
        executor_runs=executor_runs,
        batch_size=batch_size,
        seed=seed,
        presentation=selected_presentation,
    )
    return CoreRunArtifacts(
        calibration=calibration,
        memories=tuple(memories),
        attempts=tuple(attempts),
        states=tuple(states),
        evidence=tuple(evidence),
        trials=tuple(trials),
        model_contexts=tuple((*writer_contexts, *executor_contexts)),
    )


def _build_evidence(
    llm: Any,
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    selected: Sequence[Any],
    *,
    writer_task: str,
    writer_targets: Sequence[str],
    writer_runs: int,
    writer_max_attempts: int,
    capacity_tokens: int,
    batch_size: int | None,
    seed: int,
    token_counter: TokenCounter | None,
    presentation: PresentationProfile,
) -> tuple[
    list[MemoryArtifact],
    list[MemoryAttempt],
    list[MemoryState],
    list[FrozenEvidence],
    list[ModelContext],
]:
    memories: list[MemoryArtifact] = []
    attempts: list[MemoryAttempt] = []
    states: list[MemoryState] = []
    evidence: list[FrozenEvidence] = []
    model_contexts: list[ModelContext] = []
    presentation_hash = content_hash(presentation.to_dict())

    for case in cases:
        case_id = domain.corpus.case_id(case)
        for condition in selected:
            if condition.writer_required:
                continue
            if condition.evidence is ExecutorEvidence.EMPTY:
                evidence.append(
                    _freeze_evidence(
                        domain_id=domain.domain_id,
                        case_id=case_id,
                        condition_id=condition.condition_id,
                        memory_run_id=0,
                        presentation_id=presentation.presentation_id,
                        presentation_hash=presentation_hash,
                    )
                )
            elif condition.evidence is ExecutorEvidence.FULL_HISTORY:
                history = domain.corpus.render_full_history(case, presentation)
                evidence.append(
                    _freeze_evidence(
                        domain_id=domain.domain_id,
                        case_id=case_id,
                        condition_id=condition.condition_id,
                        memory_run_id=0,
                        source_history=history,
                        presentation_id=presentation.presentation_id,
                        presentation_hash=presentation_hash,
                    )
                )
            elif condition.faithful:
                payload: str | Mapping[str, Any]
                if condition.architecture is MemoryArchitecture.FREE_TEXT:
                    payload = domain.memory.faithful_free_text(case)
                    payload_schema_id = None
                    payload_schema_version = None
                else:
                    payload = domain.memory.serialize_typed(
                        domain.memory.faithful_typed(case)
                    )
                    payload_schema_id = domain.memory.payload_schema_id
                    payload_schema_version = str(payload.get("schema_version", "3"))
                artifact = _create_artifact(
                    domain=domain,
                    case=case,
                    condition_id=condition.condition_id,
                    architecture=condition.architecture,
                    origin=MemoryOrigin.FAITHFUL,
                    payload=payload,
                    payload_schema_id=payload_schema_id,
                    payload_schema_version=payload_schema_version,
                    writer=None,
                    run_id=0,
                    writer_seed=None,
                    block_index=_last_block_index(domain, case),
                    previous=None,
                    capacity_tokens=capacity_tokens,
                    token_counter=token_counter,
                    presentation_id=presentation.presentation_id,
                    presentation_hash=presentation_hash,
                )
                memories.append(artifact)
                evidence.append(_evidence_from_artifact(artifact, memory_run_id=0))

    writer_specs: list[WriterChainSpec] = []
    writer_conditions = [
        condition for condition in selected if condition.writer_required
    ]
    for target_id in writer_targets:
        for condition in writer_conditions:
            if condition.architecture is None:
                raise ValueError("writer condition is missing an architecture")
            for run_id in range(writer_runs):
                for case in cases:
                    if condition.update_strategy is UpdateStrategy.ONE_SHOT:
                        updates = (
                            WriterUpdateSpec(
                                block_index=_last_block_index(domain, case),
                                messages=tuple(
                                    _writer_update_messages(
                                        source_history=domain.corpus.render_full_history(
                                            case, presentation
                                        )
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
                                        conversation_block=domain.corpus.render_block(
                                            block, presentation
                                        )
                                    )
                                ),
                                visible_source_ids=domain.corpus.source_turn_ids(
                                    case,
                                    through_block_index=_block_index(block, position),
                                ),
                                input_kind="new_conversation_block",
                            )
                            for position, block in enumerate(
                                domain.corpus.blocks(case)
                            )
                        )
                    else:
                        raise ValueError(
                            f"unsupported writer strategy: {condition.update_strategy}"
                        )
                    writer_specs.append(
                        WriterChainSpec(
                            case=case,
                            condition_id=condition.condition_id,
                            architecture=condition.architecture,
                            run_id=run_id,
                            writer_seed=seed + run_id,
                            target_id=target_id,
                            updates=updates,
                            presentation_id=presentation.presentation_id,
                            presentation_hash=presentation_hash,
                        )
                    )
    generated = run_writer_chains(
        llm,
        domain,
        writer_specs,
        writer_task=writer_task,
        max_attempts=writer_max_attempts,
        capacity_tokens=capacity_tokens,
        batch_size=batch_size,
        token_counter=token_counter,
    )
    memories.extend(generated.memories)
    attempts.extend(generated.attempts)
    states.extend(generated.states)
    evidence.extend(generated.final_evidence)
    model_contexts.extend(generated.model_contexts)
    _require_unique((item.evidence_id for item in evidence), "evidence")
    return memories, attempts, states, evidence, model_contexts


def _run_executors(
    llm: Any,
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    evidence: Sequence[FrozenEvidence],
    *,
    executor_task: str,
    executor_targets: Sequence[str],
    executor_runs: int,
    batch_size: int | None,
    seed: int,
    presentation: PresentationProfile,
) -> tuple[list[NormalizedTrial], list[ModelContext]]:
    cases_by_id = {
        domain.corpus.case_id(case): case
        for case in cases
    }
    jobs: list[tuple[FrozenEvidence, Any, BenchmarkProbe, int]] = []
    for item in evidence:
        case = cases_by_id[item.case_id]
        for probe in domain.corpus.probes(case):
            for executor_run_id in range(executor_runs):
                jobs.append((item, case, probe, executor_run_id))

    trials: list[NormalizedTrial] = []
    model_contexts: list[ModelContext] = []
    tools = model_visible_tools(domain, presentation)
    presentation_hash = content_hash(presentation.to_dict())
    for target_id in executor_targets:
        for executor_run_id in range(executor_runs):
            executor_seed = seed + executor_run_id
            executor = resolve_model_provenance(
                llm.config,
                executor_task,
                target_id,
                effective_parameters=effective_behavioral_parameters(
                    llm.config,
                    executor_task,
                    overrides={
                        "temperature": 1.0,
                        "seed": executor_seed,
                        "tool_choice": "auto",
                    },
                    tools=tools,
                    required_capabilities=("native_tools", "seed"),
                ),
            )
            run_jobs = [job for job in jobs if job[3] == executor_run_id]
            messages = [
                _executor_messages(
                    domain,
                    case,
                    probe,
                    evidence_kind=get_condition(item.condition_id).evidence,
                    memory=item.payload,
                    source_history=item.source_history,
                    presentation=presentation,
                )
                for item, case, probe, _ in run_jobs
            ]
            trial_ids = [
                _stable_id(
                    "trial",
                    domain.domain_id,
                    item.evidence_id,
                    probe.probe_id,
                    target_id,
                    executor.provider or "",
                    executor.requested_model or "",
                    executor.resolved_model or "",
                    str(executor_run_id),
                    str(executor_seed),
                    presentation.presentation_id,
                    presentation_hash,
                )
                for item, _, probe, _ in run_jobs
            ]
            call_ids = [
                _stable_id("call", trial_id, "executor")
                for trial_id in trial_ids
            ]
            run_contexts = [
                _executor_model_context(
                    domain,
                    case,
                    probe,
                    item,
                    messages=item_messages,
                    tools=tools,
                    executor=executor,
                    executor_run_id=executor_run_id,
                    call_id=call_id,
                    trial_id=trial_id,
                    presentation=presentation,
                    presentation_hash=presentation_hash,
                )
                for (item, case, probe, _), item_messages, call_id, trial_id in zip(
                    run_jobs, messages, call_ids, trial_ids
                )
            ]
            responses = llm.batch(
                executor_task,
                messages,
                target=target_id,
                call_ids=call_ids,
                tools=tools,
                tool_choice="auto",
                temperature=1.0,
                seed=executor_seed,
                batch_size=batch_size,
                return_exceptions=True,
                required_capabilities=("native_tools", "seed"),
            )
            for (
                (item, case, probe, _),
                response,
                trial_id,
                call_id,
                model_context,
            ) in zip(
                run_jobs,
                responses,
                trial_ids,
                call_ids,
                run_contexts,
            ):
                effective_context = (
                    model_context
                    if isinstance(response, Exception)
                    else replace(
                        model_context,
                        model=with_response_model(
                            model_context.model,
                            _response_model(response),
                        ),
                    )
                )
                model_contexts.append(effective_context)
                trials.append(
                    _score_executor_response(
                        domain,
                        case,
                        probe,
                        item,
                        response,
                        executor,
                        executor_run_id=executor_run_id,
                        seed=executor_seed,
                        trial_id=trial_id,
                        call_id=call_id,
                        model_context_id=effective_context.context_id,
                        presentation=presentation,
                        presentation_hash=presentation_hash,
                    )
                )
    _require_unique((trial.metadata["core"]["trial_id"] for trial in trials), "trial")
    _require_unique((context.context_id for context in model_contexts), "model context")
    return trials, model_contexts


def run_executor_jobs(
    llm: Any,
    domain: AuthorizationMemoryDomain,
    jobs: Sequence[ExecutorJob],
    *,
    study_id: str,
    executor_task: str,
    executor_targets: Sequence[str],
    executor_runs: int,
    batch_size: int | None,
    seed: int,
    presentation: PresentationProfile,
    pressure_specs: Sequence[PressureSpec] = (),
) -> tuple[list[NormalizedTrial], list[ModelContext]]:
    """Execute a domain-built study job set through the shared batch path."""

    checked = tuple(jobs)
    if not checked:
        return [], []
    if executor_runs < 1:
        raise ValueError("executor_runs must be positive")
    if not executor_targets:
        raise ValueError("executor_targets must not be empty")
    for job in checked:
        job.validate(domain)
    pressure_by_id = {
        pressure.pressure_id: pressure for pressure in pressure_specs
    }
    tools = model_visible_tools(domain, presentation)
    presentation_hash = content_hash(presentation.to_dict())
    trials: list[NormalizedTrial] = []
    model_contexts: list[ModelContext] = []
    grouped_jobs: dict[tuple[str, int, int], list[ExecutorJob]] = {}
    ordinary_jobs = [
        job for job in checked if job.executor_target_id is None
    ]
    frozen_jobs = [
        job for job in checked if job.executor_target_id is not None
    ]
    if ordinary_jobs:
        for target_id in executor_targets:
            for executor_run_id in range(executor_runs):
                grouped_jobs.setdefault(
                    (target_id, executor_run_id, seed + executor_run_id),
                    [],
                ).extend(ordinary_jobs)
    for job in frozen_jobs:
        assert job.executor_target_id is not None
        assert job.executor_run_id is not None
        assert job.executor_seed is not None
        grouped_jobs.setdefault(
            (
                job.executor_target_id,
                job.executor_run_id,
                job.executor_seed,
            ),
            [],
        ).append(job)

    for (
        target_id,
        executor_run_id,
        executor_seed,
    ), route_jobs in sorted(grouped_jobs.items()):
        identity_rows = [
            planned_study_job_identity(
                domain,
                job,
                study_id=study_id,
                executor_task=executor_task,
                target_id=target_id,
                executor_run_id=executor_run_id,
                seed=executor_seed,
                presentation=presentation,
                config=llm.config,
            )
            for job in route_jobs
        ]
        executor = identity_rows[0]["executor"]
        messages = [
            _study_job_messages(
                domain,
                job,
                presentation=presentation,
                pressure=(
                    pressure_by_id[job.pressure_id]
                    if job.pressure_id is not None
                    else None
                ),
            )
            for job in route_jobs
        ]
        trial_ids = [row["trial_id"] for row in identity_rows]
        call_ids = [row["call_id"] for row in identity_rows]
        contexts = [
            _study_job_model_context(
                domain,
                job,
                messages=item_messages,
                tools=tools,
                executor=executor,
                executor_run_id=executor_run_id,
                call_id=call_id,
                trial_id=trial_id,
                study_id=study_id,
                pressure=(
                    pressure_by_id[job.pressure_id]
                    if job.pressure_id is not None
                    else None
                ),
                presentation=presentation,
                presentation_hash=presentation_hash,
            )
            for job, item_messages, call_id, trial_id in zip(
                route_jobs,
                messages,
                call_ids,
                trial_ids,
            )
        ]
        responses = llm.batch(
            executor_task,
            messages,
            target=target_id,
            call_ids=call_ids,
            tools=tools,
            tool_choice="auto",
            temperature=1.0,
            seed=executor_seed,
            batch_size=batch_size,
            return_exceptions=True,
            required_capabilities=("native_tools", "seed"),
        )
        for job, response, trial_id, call_id, context in zip(
            route_jobs,
            responses,
            trial_ids,
            call_ids,
            contexts,
        ):
            effective_context = (
                context
                if isinstance(response, Exception)
                else replace(
                    context,
                    model=with_response_model(
                        context.model,
                        _response_model(response),
                    ),
                )
            )
            model_contexts.append(effective_context)
            trials.append(
                _score_executor_response(
                    domain,
                    job.case,
                    job.probe,
                    job.evidence,
                    response,
                    executor,
                    executor_run_id=executor_run_id,
                    seed=executor_seed,
                    trial_id=trial_id,
                    call_id=call_id,
                    model_context_id=effective_context.context_id,
                    presentation=presentation,
                    presentation_hash=presentation_hash,
                    oracle_block_index=job.oracle_block_index,
                    study_id=study_id,
                    study_metadata={
                        "job_id": job.job_id,
                        "pressure_id": job.pressure_id,
                        **dict(job.metadata),
                    },
                    challenge_pressure_id=(
                        pressure_by_id[
                            job.pressure_id
                        ].challenge_pressure_id
                        if job.pressure_id is not None
                        else None
                    ),
                    challenge_metadata=_job_challenge_metadata(
                        domain,
                        job,
                        pressure=(
                            pressure_by_id[job.pressure_id]
                            if job.pressure_id is not None
                            else None
                        ),
                    ),
                )
            )
    _require_unique(
        (trial.metadata["core"]["trial_id"] for trial in trials),
        "trial",
    )
    _require_unique(
        (context.context_id for context in model_contexts),
        "model context",
    )
    return trials, model_contexts


def planned_study_job_identity(
    domain: AuthorizationMemoryDomain,
    job: ExecutorJob,
    *,
    study_id: str,
    executor_task: str,
    target_id: str,
    executor_run_id: int,
    seed: int,
    presentation: PresentationProfile,
    config: Any,
) -> dict[str, Any]:
    """Return the frozen route and IDs for one future executor call."""

    tools = model_visible_tools(domain, presentation)
    parameters = effective_behavioral_parameters(
        config,
        executor_task,
        overrides={
            "temperature": 1.0,
            "seed": seed,
            "tool_choice": "auto",
        },
        tools=tools,
        required_capabilities=("native_tools", "seed"),
    )
    executor = resolve_model_provenance(
        config,
        executor_task,
        target_id,
        effective_parameters=parameters,
    )
    presentation_hash = content_hash(presentation.to_dict())
    trial_id = _stable_id(
        "trial",
        domain.domain_id,
        study_id,
        job.job_id,
        job.evidence.evidence_id,
        job.probe.probe_id,
        target_id,
        executor.provider or "",
        executor.requested_model or "",
        executor.resolved_model or "",
        str(executor_run_id),
        str(seed),
        presentation.presentation_id,
        presentation_hash,
    )
    return {
        "executor": executor,
        "target_id": target_id,
        "provider": executor.provider,
        "requested_model": executor.requested_model,
        "resolved_model": executor.resolved_model,
        "effective_parameters": dict(executor.effective_parameters),
        "executor_run_id": executor_run_id,
        "seed": seed,
        "trial_id": trial_id,
        "call_id": _stable_id("call", trial_id, "executor"),
    }


def validate_executor_job_surfaces(
    domain: AuthorizationMemoryDomain,
    jobs: Sequence[ExecutorJob],
    *,
    presentation: PresentationProfile,
    pressure_specs: Sequence[PressureSpec] = (),
) -> dict[str, Any]:
    """Assemble and hash every offline-known executor surface."""

    pressure_by_id = {
        pressure.pressure_id: pressure for pressure in pressure_specs
    }
    tools = model_visible_tools(domain, presentation)
    hashes = []
    for job in jobs:
        pressure = (
            pressure_by_id[job.pressure_id]
            if job.pressure_id is not None
            else None
        )
        messages = _study_job_messages(
            domain,
            job,
            presentation=presentation,
            pressure=pressure,
        )
        hashes.append(
            content_hash(
                {
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                }
            )
        )
    return {
        "status": "passed",
        "jobs": len(jobs),
        "context_hashes": len(hashes),
        "unique_context_hashes": len(set(hashes)),
    }


def _study_job_messages(
    domain: AuthorizationMemoryDomain,
    job: ExecutorJob,
    *,
    presentation: PresentationProfile,
    pressure: PressureSpec | None,
) -> list[dict[str, Any]]:
    if job.messages is not None:
        return [dict(message) for message in job.messages]
    if job.evidence.source_history is not None:
        evidence_kind = ExecutorEvidence.FULL_HISTORY
    elif job.evidence.payload is not None:
        evidence_kind = ExecutorEvidence.MEMORY
    else:
        evidence_kind = ExecutorEvidence.EMPTY
    context = {
        **(
            {"identity_context": job.context.identity}
            if job.context.identity is not None
            else {}
        ),
        **(
            {"operational_context": job.context.operational}
            if job.context.operational is not None
            else {}
        ),
        **dict(job.context.sections),
    }
    if pressure is not None:
        context.update(
            {
                "pressure_id": pressure.pressure_id,
                "pressure_placement": pressure.placement,
                "pressure_text": pressure.text,
                **dict(pressure.metadata),
            }
        )
        if pressure.placement == "operational_context":
            context["operational_context"] = pressure.text
    prepared_challenge = _prepared_job_challenge(
        domain,
        job,
        pressure=pressure,
    )
    return _executor_messages(
        domain,
        job.case,
        job.probe,
        evidence_kind=evidence_kind,
        memory=job.evidence.payload,
        source_history=job.evidence.source_history,
        pressure=context or None,
        challenge_pressure_id=(
            pressure.challenge_pressure_id
            if pressure is not None
            else None
        ),
        prepared_challenge_text=(
            prepared_challenge.rendered_text
            if prepared_challenge is not None
            else None
        ),
        presentation=presentation,
    )


def _study_job_model_context(
    domain: AuthorizationMemoryDomain,
    job: ExecutorJob,
    *,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
    executor: ModelProvenance,
    executor_run_id: int,
    call_id: str,
    trial_id: str,
    study_id: str,
    pressure: PressureSpec | None,
    presentation: PresentationProfile,
    presentation_hash: str,
) -> ModelContext:
    prepared_challenge = _prepared_job_challenge(
        domain,
        job,
        pressure=pressure,
    )
    challenge_metadata = (
        job.challenge_metadata
        if job.challenge_metadata is not None
        else (
            prepared_challenge.metadata()
            if prepared_challenge is not None
            else None
        )
    )
    context = _executor_model_context(
        domain,
        job.case,
        job.probe,
        job.evidence,
        messages=messages,
        tools=tools,
        executor=executor,
        executor_run_id=executor_run_id,
        call_id=call_id,
        trial_id=trial_id,
        presentation=presentation,
        presentation_hash=presentation_hash,
        challenge_metadata=challenge_metadata,
    )
    return replace(
        context,
        block_index=job.oracle_block_index,
        metadata={
            **context.metadata,
            **(
                {"challenge": prepared_challenge.metadata()}
                if prepared_challenge is not None
                else {}
            ),
            "request_authorized": domain.executor.oracle(
                job.case,
                job.probe.request,
                through_block_index=job.oracle_block_index,
            ).authorized,
            "study_id": study_id,
            "job_id": job.job_id,
            "pressure_id": job.pressure_id,
            **dict(job.metadata),
        },
    )


def _prepared_job_challenge(
    domain: AuthorizationMemoryDomain,
    job: ExecutorJob,
    *,
    pressure: PressureSpec | None,
) -> Any | None:
    if job.challenge_metadata is not None:
        return None
    pressure_id = (
        pressure.challenge_pressure_id
        if pressure is not None
        else None
    )
    if job.challenge_context is not None:
        validate_challenge_context(
            domain,
            job.case,
            job.probe,
            job.challenge_context,
            through_block_index=job.oracle_block_index,
        )
        selected_id = pressure_id
        if selected_id is None:
            if domain.challenge is None:
                raise ValueError(
                    f"{job.job_id}: custom challenge has no default pressure"
                )
            selected_id = domain.challenge.default_pressure_id
        return prepare_challenge_context(
            domain,
            job.challenge_context,
            pressure_id=selected_id,
        )
    return prepare_challenge(
        domain,
        job.case,
        job.probe,
        pressure_id=pressure_id,
    )


def _job_challenge_metadata(
    domain: AuthorizationMemoryDomain,
    job: ExecutorJob,
    *,
    pressure: PressureSpec | None,
) -> Mapping[str, Any] | None:
    if job.challenge_metadata is not None:
        return job.challenge_metadata
    prepared = _prepared_job_challenge(
        domain,
        job,
        pressure=pressure,
    )
    return prepared.metadata() if prepared is not None else None


def _executor_model_context(
    domain: AuthorizationMemoryDomain,
    case: Any,
    probe: BenchmarkProbe,
    evidence: FrozenEvidence,
    *,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
    executor: ModelProvenance,
    executor_run_id: int,
    call_id: str,
    trial_id: str,
    presentation: PresentationProfile,
    presentation_hash: str,
    challenge_metadata: Mapping[str, Any] | None = None,
) -> ModelContext:
    normalized_messages = tuple(dict(message) for message in messages)
    normalized_tools = tuple(dict(tool) for tool in tools)
    tool_choice = "auto"
    digest = content_hash(
        {
            "messages": list(normalized_messages),
            "tools": list(normalized_tools),
            "tool_choice": tool_choice,
        }
    )
    oracle = domain.executor.oracle(case, probe.request)
    challenge = (
        None
        if challenge_metadata is not None
        else prepare_challenge(domain, case, probe)
    )
    context = ModelContext(
        context_id=_stable_id("context", call_id, digest),
        content_hash=digest,
        stage="executor",
        domain_id=domain.domain_id,
        case_id=domain.corpus.case_id(case),
        condition_id=evidence.condition_id,
        block_index=None,
        probe_id=probe.probe_id,
        writer_run_id=evidence.memory_run_id,
        executor_run_id=executor_run_id,
        memory_id=evidence.memory_id,
        memory_attempt_id=evidence.source_attempt_id,
        evidence_id=evidence.evidence_id,
        trial_id=trial_id,
        call_id=call_id,
        framework_run_id=None,
        messages=normalized_messages,
        tools=normalized_tools,
        tool_choice=tool_choice,
        model=executor,
        presentation_id=presentation.presentation_id,
        presentation_hash=presentation_hash,
        metadata={
            "pair_id": probe.pair_id,
            "dimension": probe.dimension,
            "request_scope": probe.request_scope,
            "request_authorized": oracle.authorized,
            "architecture": (
                evidence.architecture.value
                if evidence.architecture is not None
                else None
            ),
            "memory_implementation_id": evidence.memory_implementation_id,
            "memory_implementation_hash": evidence.memory_implementation_hash,
            "profile_id": evidence.profile_id,
            "prompt_policy_id": presentation.prompt_policy_id,
            **(
                {
                    "challenge": (
                        dict(challenge_metadata)
                        if challenge_metadata is not None
                        else challenge.metadata()
                    )
                }
                if challenge_metadata is not None or challenge is not None
                else {}
            ),
        },
    )
    validate_model_context_leakage(domain, case, context)
    return context


def select_terminal_call(
    domain: AuthorizationMemoryDomain,
    calls: Sequence[Any],
) -> tuple[tuple[int, str, Any] | None, list[tuple[int, str, Any]]]:
    """Prefer any consequential action while retaining all terminal-call counts."""

    terminal: list[tuple[int, str, Any]] = []
    for index, call in enumerate(calls):
        name, raw_arguments = _tool_name_arguments(call)
        if name in domain.executor.terminal_tools:
            terminal.append((index, name, raw_arguments))
    selected = next(
        (
            item
            for item in terminal
            if item[1] in domain.action_tools
        ),
        terminal[0] if terminal else None,
    )
    return selected, terminal


def _score_executor_response(
    domain: AuthorizationMemoryDomain,
    case: Any,
    probe: BenchmarkProbe,
    evidence: FrozenEvidence,
    response: Any,
    executor: ModelProvenance,
    *,
    executor_run_id: int,
    seed: int,
    trial_id: str,
    call_id: str,
    model_context_id: str,
    presentation: PresentationProfile,
    presentation_hash: str,
    oracle_block_index: int | None = None,
    study_id: str = "core",
    study_metadata: Mapping[str, Any] | None = None,
    challenge_pressure_id: str | None = None,
    challenge_metadata: Mapping[str, Any] | None = None,
) -> NormalizedTrial:
    oracle = domain.executor.oracle(
        case,
        probe.request,
        through_block_index=oracle_block_index,
    )
    challenge = (
        None
        if challenge_metadata is not None
        else prepare_challenge(
            domain,
            case,
            probe,
            pressure_id=challenge_pressure_id,
        )
    )
    metadata = {
        "core": {
            "pair_id": probe.pair_id,
            "dimension": probe.dimension,
            "request_scope": probe.request_scope,
            "architecture": (
                evidence.architecture.value
                if evidence.architecture is not None
                else None
            ),
            "memory_implementation_id": evidence.memory_implementation_id,
            "memory_implementation_hash": evidence.memory_implementation_hash,
            "profile_id": evidence.profile_id,
            "trial_id": trial_id,
            "call_id": call_id,
            "model_context_id": model_context_id,
            "presentation_id": presentation.presentation_id,
            "presentation_hash": presentation_hash,
            "presentation": presentation.to_dict(),
        },
        "study": {
            "study_id": study_id,
            **dict(study_metadata or {}),
        },
        "domain": {
            **dict(probe.metadata),
            **(
                {
                    "challenge": (
                        dict(challenge_metadata)
                        if challenge_metadata is not None
                        else challenge.metadata()
                    )
                }
                if challenge_metadata is not None or challenge is not None
                else {}
            ),
        },
    }
    if isinstance(response, Exception):
        return NormalizedTrial(
            domain_id=domain.domain_id,
            domain_adapter_version=domain.adapter_version,
            case_id=domain.corpus.case_id(case),
            probe_id=probe.probe_id,
            condition_id=evidence.condition_id,
            writer=evidence.writer,
            executor=executor,
            writer_run_id=evidence.memory_run_id,
            writer_seed=evidence.writer_seed,
            executor_run_id=executor_run_id,
            seed=seed,
            evidence_id=evidence.evidence_id,
            memory_id=evidence.memory_id,
            request_authorized=oracle.authorized,
            decision=Decision.PROVIDER_ERROR,
            requested_action_taken=False,
            unauthorized_action_taken=False,
            action_mismatch=False,
            compliant=False,
            parseable=False,
            provider_error=f"{type(response).__name__}: {response}",
            finish_reason=None,
            response_text="",
            tool_call_count=0,
            terminal_call_count=0,
            raw_tool_name=None,
            raw_tool_arguments=None,
            metadata=metadata,
        )

    calls = _response_tool_calls(response)
    selected, terminal = select_terminal_call(domain, calls)
    response_text = _response_text(response)
    finish_reason = _finish_reason(response)
    response_model = _response_model(response)
    effective_executor = with_response_model(executor, response_model)
    if selected is None:
        return NormalizedTrial(
            domain_id=domain.domain_id,
            domain_adapter_version=domain.adapter_version,
            case_id=domain.corpus.case_id(case),
            probe_id=probe.probe_id,
            condition_id=evidence.condition_id,
            writer=evidence.writer,
            executor=effective_executor,
            writer_run_id=evidence.memory_run_id,
            writer_seed=evidence.writer_seed,
            executor_run_id=executor_run_id,
            seed=seed,
            evidence_id=evidence.evidence_id,
            memory_id=evidence.memory_id,
            request_authorized=oracle.authorized,
            decision=Decision.NO_ACTION,
            requested_action_taken=False,
            unauthorized_action_taken=False,
            action_mismatch=False,
            compliant=False,
            parseable=False,
            provider_error=None,
            finish_reason=finish_reason,
            response_text=response_text,
            tool_call_count=len(calls),
            terminal_call_count=len(terminal),
            raw_tool_name=None,
            raw_tool_arguments=None,
            metadata=metadata,
        )
    _, tool_name, raw_arguments = selected
    if len(calls) != 1 or len(terminal) != 1:
        return NormalizedTrial(
            domain_id=domain.domain_id,
            domain_adapter_version=domain.adapter_version,
            case_id=domain.corpus.case_id(case),
            probe_id=probe.probe_id,
            condition_id=evidence.condition_id,
            writer=evidence.writer,
            executor=effective_executor,
            writer_run_id=evidence.memory_run_id,
            writer_seed=evidence.writer_seed,
            executor_run_id=executor_run_id,
            seed=seed,
            evidence_id=evidence.evidence_id,
            memory_id=evidence.memory_id,
            request_authorized=oracle.authorized,
            decision=Decision.INVALID,
            requested_action_taken=False,
            unauthorized_action_taken=False,
            action_mismatch=False,
            compliant=False,
            parseable=False,
            provider_error=None,
            finish_reason=finish_reason,
            response_text=response_text,
            tool_call_count=len(calls),
            terminal_call_count=len(terminal),
            raw_tool_name=tool_name,
            raw_tool_arguments=raw_arguments,
            metadata=metadata,
        )
    try:
        arguments = (
            json.loads(raw_arguments)
            if isinstance(raw_arguments, str)
            else raw_arguments
        )
        if not isinstance(arguments, Mapping):
            raise ValueError("tool arguments must be an object")
        score = domain.executor.score_tool_call(
            case,
            probe.request,
            tool_name,
            arguments,
            through_block_index=oracle_block_index,
        )
        decision = Decision.from_action(score.decision)
        parseable = score.valid_arguments
        requested_taken = score.decision is ActionDecision.EXECUTE_REQUESTED
        mismatch = score.decision is ActionDecision.EXECUTE_OTHER
        unauthorized_taken = (
            score.decision
            in {
                ActionDecision.EXECUTE_REQUESTED,
                ActionDecision.EXECUTE_OTHER,
            }
            and score.action_authorized is False
        )
        compliant = score.compliant
    except (TypeError, ValueError, json.JSONDecodeError):
        arguments = raw_arguments
        decision = Decision.INVALID
        parseable = False
        requested_taken = False
        mismatch = False
        unauthorized_taken = False
        compliant = False
    return NormalizedTrial(
        domain_id=domain.domain_id,
        domain_adapter_version=domain.adapter_version,
        case_id=domain.corpus.case_id(case),
        probe_id=probe.probe_id,
        condition_id=evidence.condition_id,
        writer=evidence.writer,
        executor=effective_executor,
        writer_run_id=evidence.memory_run_id,
        writer_seed=evidence.writer_seed,
        executor_run_id=executor_run_id,
        seed=seed,
        evidence_id=evidence.evidence_id,
        memory_id=evidence.memory_id,
        request_authorized=oracle.authorized,
        decision=decision,
        requested_action_taken=requested_taken,
        unauthorized_action_taken=unauthorized_taken,
        action_mismatch=mismatch,
        compliant=compliant,
        parseable=parseable,
        provider_error=None,
        finish_reason=finish_reason,
        response_text=response_text,
        tool_call_count=len(calls),
        terminal_call_count=len(terminal),
        raw_tool_name=tool_name,
        raw_tool_arguments=arguments,
        metadata=metadata,
    )


def _writer_update_messages(
    *,
    source_history: str | None = None,
    conversation_block: str | None = None,
) -> list[dict[str, str]]:
    one_shot = source_history is not None
    incremental = conversation_block is not None
    if one_shot == incremental:
        raise ValueError(
            "writer messages require either source history or one conversation block"
        )
    if one_shot:
        content = _delimit("SOURCE_HISTORY", source_history or "")
    else:
        content = _delimit(
            "NEW_CONVERSATION_BLOCK",
            conversation_block or "",
        )
    return [{"role": "user", "content": content}]


def _executor_messages(
    domain: AuthorizationMemoryDomain,
    case: Any,
    probe: BenchmarkProbe,
    *,
    evidence_kind: ExecutorEvidence,
    memory: str | Mapping[str, Any] | None = None,
    source_history: str | None = None,
    pressure: Mapping[str, Any] | None = None,
    challenge_pressure_id: str | None = None,
    prepared_challenge_text: str | None = None,
    presentation: PresentationProfile | None = None,
) -> list[dict[str, str]]:
    policy = domain.get_prompt_policy(presentation)
    if evidence_kind is ExecutorEvidence.EMPTY:
        evidence = _delimit(
            "PERSISTENT_MEMORY",
            policy.empty_evidence_text,
        )
    elif evidence_kind is ExecutorEvidence.FULL_HISTORY:
        if source_history is None:
            raise ValueError("full-history evidence requires source_history")
        evidence = _delimit("SOURCE_HISTORY", source_history)
    elif evidence_kind is ExecutorEvidence.MEMORY:
        if memory is None:
            raise ValueError("memory evidence requires a payload")
        serialized = memory if isinstance(memory, str) else canonical_json(memory)
        evidence = _delimit("PERSISTENT_MEMORY", serialized)
    else:
        raise ValueError(f"unsupported executor evidence: {evidence_kind}")
    challenge = (
        None
        if prepared_challenge_text is not None
        else prepare_challenge(
            domain,
            case,
            probe,
            pressure_id=challenge_pressure_id,
        )
    )
    request_pressure = {
        **dict(pressure or {}),
        **(
            {
                "operational_context": (
                    prepared_challenge_text
                    if prepared_challenge_text is not None
                    else challenge.rendered_text
                )
            }
            if prepared_challenge_text is not None or challenge is not None
            else {}
        ),
    }
    request = domain.executor.render_request(
        case,
        probe,
        pressure=request_pressure or None,
        presentation=presentation,
    )
    return [
        {
            "role": "system",
            "content": domain.executor.system_prompt(case, presentation),
        },
        {
            "role": "user",
            "content": "\n\n".join(
                (
                    evidence,
                    _delimit("CURRENT_REQUEST", request),
                    policy.executor_instruction,
                )
            ),
        },
    ]


def _create_artifact(
    *,
    domain: AuthorizationMemoryDomain,
    case: Any,
    condition_id: str,
    architecture: MemoryArchitecture,
    origin: MemoryOrigin,
    payload: str | Mapping[str, Any],
    payload_schema_id: str | None,
    payload_schema_version: str | None,
    writer: ModelProvenance | None,
    run_id: int,
    writer_seed: int | None,
    block_index: int,
    previous: MemoryArtifact | None,
    capacity_tokens: int,
    token_counter: TokenCounter | None,
    presentation_id: str,
    presentation_hash: str | None = None,
) -> MemoryArtifact:
    serialized = payload if isinstance(payload, str) else canonical_json(payload)
    reference_tokens = count_reference_tokens(serialized, token_counter)
    if reference_tokens > capacity_tokens:
        raise ValueError(
            f"candidate uses {reference_tokens} reference tokens; "
            f"capacity is {capacity_tokens}"
        )
    case_id = domain.corpus.case_id(case)
    chain_id = (
        previous.chain_id
        if previous is not None
        else _stable_id(
            "chain",
            domain.domain_id,
            case_id,
            condition_id,
            str(run_id),
            writer.target_id if writer is not None else "baseline",
            presentation_id,
            presentation_hash or "",
        )
    )
    parent_id = previous.memory_id if previous is not None else None
    digest = content_hash(payload)
    memory_id = _stable_id(
        "mem",
        chain_id,
        parent_id or "",
        str(block_index),
        digest,
    )
    return MemoryArtifact(
        memory_id=memory_id,
        parent_memory_id=parent_id,
        chain_id=chain_id,
        domain_id=domain.domain_id,
        case_id=case_id,
        condition_id=condition_id,
        block_index=block_index,
        writer_run_id=run_id if writer is not None else None,
        writer_seed=writer_seed if writer is not None else None,
        writer=writer,
        architecture=architecture,
        origin=origin,
        payload_schema_id=payload_schema_id,
        payload_schema_version=payload_schema_version,
        payload=payload if isinstance(payload, str) else dict(payload),
        reference_tokens=reference_tokens,
        reference_tokenizer=reference_tokenizer_name(token_counter),
        content_hash=digest,
        presentation_id=presentation_id,
        presentation_hash=presentation_hash,
    )


def _freeze_evidence(
    *,
    domain_id: str,
    case_id: str,
    condition_id: str,
    memory_run_id: int,
    artifact: MemoryArtifact | None = None,
    source_history: str | None = None,
    presentation_id: str | None = None,
    presentation_hash: str | None = None,
) -> FrozenEvidence:
    if artifact is not None and source_history is not None:
        raise ValueError("evidence cannot contain both memory and full history")
    if artifact is not None:
        writer = artifact.writer
        architecture = artifact.architecture
        memory_id = artifact.memory_id
        payload = artifact.payload
        digest = artifact.content_hash
        presentation_id = artifact.presentation_id
        presentation_hash = artifact.presentation_hash
    elif source_history is not None:
        writer = None
        architecture = None
        memory_id = None
        payload = None
        digest = content_hash(source_history)
    else:
        writer = None
        architecture = None
        memory_id = None
        payload = None
        digest = content_hash("empty")
    if presentation_id is None or presentation_hash is None:
        raise ValueError("evidence requires versioned presentation provenance")
    evidence_id = _stable_id(
        "evidence",
        domain_id,
        case_id,
        condition_id,
        str(memory_run_id),
        memory_id or digest,
        presentation_id,
        presentation_hash or "",
    )
    return FrozenEvidence(
        evidence_id=evidence_id,
        domain_id=domain_id,
        case_id=case_id,
        condition_id=condition_id,
        memory_run_id=memory_run_id,
        writer_seed=artifact.writer_seed if artifact is not None else None,
        writer=writer,
        architecture=architecture,
        memory_id=memory_id,
        payload=payload,
        source_history=source_history,
        content_hash=digest,
        memory_implementation_id=(
            artifact.memory_implementation_id if artifact is not None else None
        ),
        memory_implementation_hash=(
            artifact.memory_implementation_hash if artifact is not None else None
        ),
        profile_id=artifact.profile_id if artifact is not None else None,
        source_attempt_id=(
            artifact.source_attempt_id if artifact is not None else None
        ),
        presentation_id=presentation_id,
        presentation_hash=presentation_hash,
    )


def _evidence_from_artifact(
    artifact: MemoryArtifact,
    *,
    memory_run_id: int,
) -> FrozenEvidence:
    return _freeze_evidence(
        domain_id=artifact.domain_id,
        case_id=artifact.case_id,
        condition_id=artifact.condition_id,
        memory_run_id=memory_run_id,
        artifact=artifact,
    )


def _validated_cases(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
) -> tuple[Any, ...]:
    checked = tuple(cases)
    if not checked:
        raise ValueError("cases must not be empty")
    ids = []
    for case in checked:
        domain.corpus.validate_case(case)
        ids.append(domain.corpus.case_id(case))
    _require_unique(ids, "case")
    return checked


def _selected_conditions(
    condition_ids: Collection[str] | None,
) -> tuple[Any, ...]:
    if condition_ids is None:
        return CONDITION_SPECS
    selected_ids = tuple(condition_ids)
    if not selected_ids:
        raise ValueError("condition_ids must not be empty")
    _require_unique(selected_ids, "condition")
    return tuple(get_condition(condition_id) for condition_id in selected_ids)


def _last_block_index(
    domain: AuthorizationMemoryDomain,
    case: Any,
) -> int:
    blocks = domain.corpus.blocks(case)
    if not blocks:
        raise ValueError(
            f"case {domain.corpus.case_id(case)!r} has no conversation blocks"
        )
    return _block_index(blocks[-1], len(blocks) - 1)


def _block_index(block: Any, fallback: int) -> int:
    if isinstance(block, Mapping):
        value = block.get("block_index", fallback)
    else:
        value = getattr(block, "block_index", fallback)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("block_index must be a non-negative integer")
    return value


def _response_tool_calls(response: Any) -> list[Any]:
    if isinstance(response, Mapping):
        choices = response.get("choices", [])
        message = choices[0].get("message", {}) if choices else {}
        return list(message.get("tool_calls") or [])
    choices = getattr(response, "choices", ())
    message = choices[0].message if choices else None
    return list(getattr(message, "tool_calls", None) or [])


def _tool_name_arguments(call: Any) -> tuple[str, Any]:
    if isinstance(call, Mapping):
        function = call.get("function", {})
        return str(function.get("name", "")), function.get("arguments")
    function = getattr(call, "function", None)
    return (
        str(getattr(function, "name", "")),
        getattr(function, "arguments", None),
    )


def _response_text(response: Any) -> str:
    if isinstance(response, Mapping):
        choices = response.get("choices", [])
        message = choices[0].get("message", {}) if choices else {}
        return str(message.get("content") or "")
    choices = getattr(response, "choices", ())
    message = choices[0].message if choices else None
    return str(getattr(message, "content", None) or "")


def _finish_reason(response: Any) -> str | None:
    if isinstance(response, Mapping):
        choices = response.get("choices", [])
        value = choices[0].get("finish_reason") if choices else None
    else:
        choices = getattr(response, "choices", ())
        value = getattr(choices[0], "finish_reason", None) if choices else None
    return str(value) if value is not None else None


def _response_model(response: Any) -> str | None:
    value = (
        response.get("model")
        if isinstance(response, Mapping)
        else getattr(response, "model", None)
    )
    return str(value) if value is not None else None


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()}"


def _delimit(tag: str, value: str) -> str:
    return f"<{tag}>\n{value}\n</{tag}>"


def _require_unique(values: Collection[str], name: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)):
        raise ValueError(f"{name} identifiers must be unique")
