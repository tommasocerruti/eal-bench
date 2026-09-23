"""Bounded event sourcing: runtime."""

from __future__ import annotations

import os as _os


import copy


import json


from collections import defaultdict

from collections.abc import Mapping, Sequence

from dataclasses import dataclass, field, replace


from pathlib import Path


from typing import Any

from eal_bench.llm import LLM


from domains.base import (
    AuthorizationMemoryDomain,
    MemoryArchitecture,
)

from experiments.authorization_memory.leakage import validate_model_context_leakage

from experiments.authorization_memory.persistence import (
    canonical_json,
    content_hash,
    file_hash,
    write_jsonl,
)

from experiments.authorization_memory.pipeline import (
    _job_challenge_metadata,
    _score_executor_response,
    _study_job_messages,
    _study_job_model_context,
    planned_study_job_identity,
)

from experiments.authorization_memory.provenance import (
    effective_behavioral_parameters,
    resolve_model_provenance,
    with_response_model,
)

from experiments.authorization_memory.schemas import (
    FrozenEvidence,
    MemoryArtifact,
    MemoryOrigin,
    ModelContext,
    ModelProvenance,
)

from experiments.authorization_memory.study_plan import ExecutorJob

from experiments.authorization_memory.surfaces import model_visible_tools

from experiments.authorization_memory.tokens import count_reference_tokens, reference_tokenizer_name


from .core import (
    DIAGNOSTIC_SCHEMA_VERSION,
    EVENT_CONDITION_ID,
    EVENT_DELTA_SCHEMA_VERSION,
    EVENT_LOG_SCHEMA_VERSION,
    EVENT_SCHEMA_VERSION,
    EVENT_SOURCING_STUDY_ID,
    EVENT_TOOL_NAME,
    EventBatchValidation,
    ExtractedEvent,
    IMPLEMENTATION_ID,
    PublicEventReducer,
    REDUCED_STATE_SCHEMA_VERSION,
    RESOURCE_SCHEMA_VERSION,
    _block_source_ids,
    _canonical_events_by_block,
    _forced_tool_choice,
    _stable_id,
    event_tool,
    event_writer_messages,
    validate_event_arguments,
)


# Completion budget of the event writer. The paper's protocol uses 4,096 tokens; writers that reason inside the
# completion (Inkling) need more, set EAL_EVENT_WRITER_MAX_TOKENS when launching such a run.
EVENT_WRITER_MAX_TOKENS = int(_os.environ.get("EAL_EVENT_WRITER_MAX_TOKENS", "4096"))


@dataclass
class _Trajectory:
    case: Any
    target_id: str
    seed: int
    reducer: PublicEventReducer
    completed_blocks: set[int] = field(default_factory=set)
    current_memory_id: str | None = None

    @property
    def case_id(self) -> str:
        return self.reducer.domain.corpus.case_id(self.case)

    @property
    def key(self) -> str:
        return f"{self.target_id}|{self.case_id}|{self.seed}"

    @property
    def chain_id(self) -> str:
        return _stable_id("event-chain", self.target_id, self.case_id, str(self.seed))


@dataclass(frozen=True)
class _WriterAttemptInput:
    trajectory: _Trajectory
    block: Any
    attempt_index: int
    repair_of_attempt_id: str | None
    messages: list[dict[str, Any]]
    call_id: str
    attempt_id: str
    logical_update_id: str
    previous_state: Mapping[str, Any]
    block_text: str
    visible_source_ids: frozenset[str]
    addressable_authorization_ids: frozenset[str]


def _empty_checkpoint(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "event_writer_checkpoint_v1",
        "manifest_identity_hash": content_hash(
            {
                "domain_id": manifest["domain_id"],
                "case_ids": manifest["case_ids"],
                "seed": manifest["seed"],
                "writer_targets": manifest["writer"]["targets"],
                "implementation_hash": manifest["memory_implementation_hash"],
                "run_plan_sha256": manifest.get("run_plan_sha256")
                or manifest.get("precommit", {}).get("sha256"),
            }
        ),
        "trajectories": {},
        "event_deltas": [],
        "event_log": [],
        "reduced_states": [],
        "event_attempts": [],
        "writer_resources": [],
        "writer_contexts": [],
    }


def _load_checkpoint(path: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    expected = _empty_checkpoint(manifest)
    if not path.is_file():
        _write_checkpoint(path, expected)
        return expected
    value = _read_checkpoint(path)
    if value.get("schema_version") != expected["schema_version"]:
        raise ValueError("unsupported event writer checkpoint")
    if value.get("manifest_identity_hash") != expected["manifest_identity_hash"]:
        raise ValueError("event writer checkpoint identity does not match manifest")
    return value


def _restore_trajectories(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    writer_targets: Sequence[str],
    seed: int,
    checkpoint: Mapping[str, Any],
) -> list[_Trajectory]:
    result = []
    saved = checkpoint.get("trajectories", {})
    for target in writer_targets:
        for case in cases:
            trajectory = _Trajectory(
                case=case,
                target_id=target,
                seed=seed,
                reducer=PublicEventReducer(domain),
            )
            raw = saved.get(trajectory.key, {}) if isinstance(saved, Mapping) else {}
            trajectory.completed_blocks = {int(value) for value in raw.get("completed_blocks", ())}
            trajectory.current_memory_id = raw.get("current_memory_id")
            trajectory.reducer.records = copy.deepcopy(dict(raw.get("records", {})))
            trajectory.reducer.event_log = [_event_from_row(row) for row in raw.get("events", ())]
            blocks = [int(block.block_index) for block in domain.corpus.blocks(case)]
            if trajectory.completed_blocks != set(blocks[: len(trajectory.completed_blocks)]):
                raise ValueError(
                    f"writer checkpoint has a non-prefix block sequence: {trajectory.key}"
                )
            replayed = PublicEventReducer(domain)
            replayed.apply_batch(trajectory.reducer.event_log)
            if canonical_json(replayed.records) != canonical_json(trajectory.reducer.records):
                raise ValueError(
                    f"writer checkpoint state differs from immutable events: {trajectory.key}"
                )
            if len({event.event_id for event in replayed.event_log}) != len(replayed.event_log):
                raise ValueError(f"writer checkpoint duplicates immutable events: {trajectory.key}")
            result.append(trajectory)
    return result


def _event_from_row(row: Mapping[str, Any]) -> ExtractedEvent:
    return ExtractedEvent(
        event_id=str(row["event_id"]),
        event_type=str(row["event_type"]),
        target_authorization_id=row.get("target_authorization_id"),
        source_turn_ids=tuple(row.get("source_turn_ids", ())),
        record=copy.deepcopy(row.get("record")),
        changes=copy.deepcopy(row.get("changes")),
        event_index=int(row.get("event_index", 0)),
    )


def _save_checkpoint(
    path: Path,
    checkpoint: dict[str, Any],
    trajectories: Sequence[_Trajectory],
) -> None:
    checkpoint["trajectories"] = {
        trajectory.key: {
            "completed_blocks": sorted(trajectory.completed_blocks),
            "current_memory_id": trajectory.current_memory_id,
            "records": copy.deepcopy(trajectory.reducer.records),
            "events": [event.to_dict() for event in trajectory.reducer.event_log],
        }
        for trajectory in trajectories
    }
    _write_checkpoint(path, checkpoint)


def _run_event_writers(
    llm: LLM,
    domain: AuthorizationMemoryDomain,
    trajectories: Sequence[_Trajectory],
    checkpoint: dict[str, Any],
    *,
    checkpoint_path: Path,
    writer_task: str,
    presentation_id: str,
    capacity_tokens: int,
    batch_size: int | None,
    implementation_hash: str,
) -> None:
    presentation = domain.get_presentation(presentation_id)
    max_blocks = max(len(domain.corpus.blocks(item.case)) for item in trajectories)
    logged = _call_log_by_id(llm.logger.path)
    for target_id in dict.fromkeys(item.target_id for item in trajectories):
        target_items = [item for item in trajectories if item.target_id == target_id]
        for position in range(max_blocks):
            pending = []
            for trajectory in target_items:
                blocks = tuple(domain.corpus.blocks(trajectory.case))
                if position >= len(blocks):
                    continue
                block = blocks[position]
                if int(block.block_index) in trajectory.completed_blocks:
                    continue
                pending.append(
                    _attempt_input(
                        domain,
                        trajectory,
                        block,
                        attempt_index=0,
                        repair_of_attempt_id=None,
                        presentation_id=presentation.presentation_id,
                        capacity_tokens=capacity_tokens,
                        repair_detail=None,
                    )
                )
            if not pending:
                continue
            first = _invoke_attempts(
                llm,
                writer_task,
                target_id,
                pending,
                batch_size=batch_size,
                logged=logged,
            )
            repairs: list[_WriterAttemptInput] = []
            accepted: dict[str, tuple[_WriterAttemptInput, EventBatchValidation, Any]] = {}
            terminal_failures: dict[str, tuple[_WriterAttemptInput, str, Any]] = {}
            for attempt, observation in zip(pending, first):
                outcome = _evaluate_attempt(
                    domain,
                    attempt,
                    observation,
                    capacity_tokens=capacity_tokens,
                )
                _record_attempt_rows(
                    domain,
                    checkpoint,
                    attempt,
                    observation,
                    outcome,
                    presentation_hash=content_hash(presentation.to_dict()),
                    implementation_hash=implementation_hash,
                    terminal=(
                        isinstance(outcome, EventBatchValidation)
                        or isinstance(observation, Exception)
                    ),
                    writer=_attempt_provenance(llm, writer_task, attempt, observation),
                    presentation_id=presentation.presentation_id,
                )
                if isinstance(outcome, EventBatchValidation):
                    accepted[attempt.trajectory.key] = (attempt, outcome, observation)
                elif isinstance(observation, Exception):
                    terminal_failures[attempt.trajectory.key] = (
                        attempt,
                        f"provider_error:{type(observation).__name__}:{observation}",
                        observation,
                    )
                else:
                    repair_detail = str(outcome)
                    raw = _observation_arguments(observation)
                    if raw is not None:
                        repair_detail += (
                            "\n\nRejected arguments:\n"
                            + canonical_json(raw)
                            + "\nMake the smallest structural correction; do not repeat them unchanged."
                        )
                    repairs.append(
                        _attempt_input(
                            domain,
                            attempt.trajectory,
                            attempt.block,
                            attempt_index=1,
                            repair_of_attempt_id=attempt.attempt_id,
                            presentation_id=presentation.presentation_id,
                            capacity_tokens=capacity_tokens,
                            repair_detail=repair_detail,
                        )
                    )
            if repairs:
                repaired = _invoke_attempts(
                    llm,
                    writer_task,
                    target_id,
                    repairs,
                    batch_size=batch_size,
                    logged=logged,
                )
                for attempt, observation in zip(repairs, repaired):
                    outcome = _evaluate_attempt(
                        domain,
                        attempt,
                        observation,
                        capacity_tokens=capacity_tokens,
                    )
                    _record_attempt_rows(
                        domain,
                        checkpoint,
                        attempt,
                        observation,
                        outcome,
                        presentation_hash=content_hash(presentation.to_dict()),
                        presentation_id=presentation.presentation_id,
                        implementation_hash=implementation_hash,
                        terminal=True,
                        writer=_attempt_provenance(llm, writer_task, attempt, observation),
                    )
                    if isinstance(outcome, EventBatchValidation):
                        accepted[attempt.trajectory.key] = (attempt, outcome, observation)
                    else:
                        terminal_failures[attempt.trajectory.key] = (
                            attempt,
                            (
                                f"provider_error:{type(observation).__name__}:{observation}"
                                if isinstance(observation, Exception)
                                else f"structural_invalid_after_repair:{outcome}"
                            ),
                            observation,
                        )
            for trajectory in [item.trajectory for item in pending]:
                if trajectory.key in accepted:
                    attempt, outcome, observation = accepted[trajectory.key]
                    _finalize_update(
                        domain,
                        checkpoint,
                        trajectory,
                        attempt,
                        status="accepted",
                        events=outcome.events,
                        next_reducer=outcome.reducer,
                        detail="accepted event delta",
                        presentation_hash=content_hash(presentation.to_dict()),
                        presentation_id=presentation.presentation_id,
                        implementation_hash=implementation_hash,
                        writer=_attempt_provenance(llm, writer_task, attempt, observation),
                    )
                else:
                    attempt, detail, observation = terminal_failures[trajectory.key]
                    _finalize_update(
                        domain,
                        checkpoint,
                        trajectory,
                        attempt,
                        status="retained_after_failed_update",
                        events=(),
                        next_reducer=trajectory.reducer,
                        detail=detail,
                        presentation_hash=content_hash(presentation.to_dict()),
                        presentation_id=presentation.presentation_id,
                        implementation_hash=implementation_hash,
                        writer=_attempt_provenance(llm, writer_task, attempt, observation),
                    )
                _save_checkpoint(checkpoint_path, checkpoint, trajectories)


def _attempt_input(
    domain: AuthorizationMemoryDomain,
    trajectory: _Trajectory,
    block: Any,
    *,
    attempt_index: int,
    repair_of_attempt_id: str | None,
    presentation_id: str,
    capacity_tokens: int,
    repair_detail: str | None,
) -> _WriterAttemptInput:
    block_index = int(block.block_index)
    logical_update_id = _stable_id(
        "event-update",
        domain.domain_id,
        trajectory.target_id,
        trajectory.case_id,
        str(trajectory.seed),
        str(block_index),
    )
    attempt_id = _stable_id("event-attempt", logical_update_id, str(attempt_index))
    call_id = _stable_id("call", attempt_id, "writer")
    previous = trajectory.reducer.visible_state()
    block_text = domain.corpus.render_block(
        block,
        domain.get_presentation(presentation_id),
    )
    messages = event_writer_messages(
        domain,
        trajectory.case,
        previous_state=previous,
        block_text=block_text,
        capacity_tokens=capacity_tokens,
        presentation_id=presentation_id,
        repair_detail=repair_detail,
    )
    visible_sources = frozenset(
        set(domain.memory.referenced_source_ids(previous))
        | set(_block_source_ids(domain, trajectory.case, block))
    )
    addressable_ids = frozenset(
        record_id for record_id in trajectory.reducer.records if record_id in block_text
    )
    return _WriterAttemptInput(
        trajectory=trajectory,
        block=block,
        attempt_index=attempt_index,
        repair_of_attempt_id=repair_of_attempt_id,
        messages=messages,
        call_id=call_id,
        attempt_id=attempt_id,
        logical_update_id=logical_update_id,
        previous_state=previous,
        block_text=block_text,
        visible_source_ids=visible_sources,
        addressable_authorization_ids=addressable_ids,
    )


def _invoke_attempts(
    llm: LLM,
    writer_task: str,
    target_id: str,
    attempts: Sequence[_WriterAttemptInput],
    *,
    batch_size: int | None,
    logged: dict[str, Mapping[str, Any]],
) -> list[Any]:
    results: list[Any] = [None] * len(attempts)
    new_indices = []
    for index, attempt in enumerate(attempts):
        record = logged.get(attempt.call_id)
        if record is None:
            new_indices.append(index)
        else:
            results[index] = _logged_observation(record)
    if new_indices:
        tool = event_tool(attempts[0].trajectory.reducer.domain)
        choice = _forced_tool_choice()
        responses = llm.batch(
            writer_task,
            [attempts[index].messages for index in new_indices],
            target=target_id,
            call_ids=[attempts[index].call_id for index in new_indices],
            tools=[tool],
            tool_choice=choice,
            temperature=1.0,
            max_tokens=EVENT_WRITER_MAX_TOKENS,
            seed=attempts[0].trajectory.seed,
            batch_size=batch_size,
            return_exceptions=True,
            required_capabilities=("native_tools", "forced_tool_choice", "seed"),
        )
        for index, response in zip(new_indices, responses):
            results[index] = response
        logged.update(_call_log_by_id(llm.logger.path))
    return results


def _call_log_by_id(path: Path) -> dict[str, Mapping[str, Any]]:
    if not path.is_file():
        return {}
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    result = {}
    for row in rows:
        call_id = row.get("call_id")
        if isinstance(call_id, str) and call_id:
            result[call_id] = row
    return result


def _logged_observation(record: Mapping[str, Any]) -> Any:
    if record.get("error"):
        return RuntimeError(str(record["error"]))
    response = record.get("response")
    if not isinstance(response, Mapping):
        return RuntimeError("logged call has no response")
    return {
        "logged_response": response,
        "response_model": record.get("response_model"),
    }


def _observation_arguments(observation: Any) -> Mapping[str, Any] | None:
    if isinstance(observation, Exception):
        return None
    if isinstance(observation, Mapping) and "logged_response" in observation:
        response = observation["logged_response"]
        calls = response.get("tool_calls") if isinstance(response, Mapping) else None
    else:
        message = observation.choices[0].message
        calls = message.tool_calls
    if not calls or len(calls) != 1:
        return None
    call = calls[0]
    if isinstance(call, Mapping):
        function = call.get("function", {})
        name = function.get("name")
        raw = function.get("arguments")
    else:
        name = call.function.name
        raw = call.function.arguments
    if name != EVENT_TOOL_NAME:
        return None
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _evaluate_attempt(
    domain: AuthorizationMemoryDomain,
    attempt: _WriterAttemptInput,
    observation: Any,
    *,
    capacity_tokens: int,
) -> EventBatchValidation | str:
    if isinstance(observation, Exception):
        return f"provider error: {type(observation).__name__}: {observation}"
    arguments = _observation_arguments(observation)
    if arguments is None:
        return f"exactly one {EVENT_TOOL_NAME} tool call with JSON arguments is required"
    try:
        return validate_event_arguments(
            domain,
            reducer=attempt.trajectory.reducer,
            arguments=arguments,
            visible_source_ids=attempt.visible_source_ids,
            addressable_authorization_ids=attempt.addressable_authorization_ids,
            logical_update_id=attempt.logical_update_id,
            capacity_tokens=capacity_tokens,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return str(exc)


def _attempt_provenance(
    llm: LLM,
    writer_task: str,
    attempt: _WriterAttemptInput,
    observation: Any,
) -> ModelProvenance:
    tool = event_tool(attempt.trajectory.reducer.domain)
    choice = _forced_tool_choice()
    provenance = resolve_model_provenance(
        llm.config,
        writer_task,
        attempt.trajectory.target_id,
        effective_parameters=effective_behavioral_parameters(
            llm.config,
            writer_task,
            overrides={
                "temperature": 1.0,
                "max_tokens": EVENT_WRITER_MAX_TOKENS,
                "seed": attempt.trajectory.seed,
                "tool_choice": choice,
            },
            tools=[tool],
            required_capabilities=("native_tools", "forced_tool_choice", "seed"),
        ),
    )
    if isinstance(observation, Mapping):
        response_model = observation.get("response_model")
    elif isinstance(observation, Exception):
        response_model = None
    else:
        response_model = getattr(observation, "model", None)
    return with_response_model(
        provenance,
        str(response_model) if response_model else None,
    )


def _record_attempt_rows(
    domain: AuthorizationMemoryDomain,
    checkpoint: dict[str, Any],
    attempt: _WriterAttemptInput,
    observation: Any,
    outcome: EventBatchValidation | str,
    *,
    presentation_hash: str,
    implementation_hash: str,
    terminal: bool,
    writer: ModelProvenance,
    presentation_id: str,
) -> None:
    arguments = _observation_arguments(observation)
    status = (
        "accepted"
        if isinstance(outcome, EventBatchValidation)
        else "provider_error"
        if isinstance(observation, Exception)
        else "structural_invalid"
    )
    attempt_row = {
        "schema_version": 1,
        "attempt_id": attempt.attempt_id,
        "logical_update_id": attempt.logical_update_id,
        "attempt_index": attempt.attempt_index,
        "repair_of_attempt_id": attempt.repair_of_attempt_id,
        "domain_id": domain.domain_id,
        "case_id": attempt.trajectory.case_id,
        "condition_id": EVENT_CONDITION_ID,
        "block_index": int(attempt.block.block_index),
        "writer_seed": attempt.trajectory.seed,
        "writer": writer.to_dict(),
        "status": status,
        "detail": "accepted" if isinstance(outcome, EventBatchValidation) else str(outcome),
        "raw_arguments": copy.deepcopy(arguments),
        "terminal_attempt": terminal,
        "memory_implementation_id": IMPLEMENTATION_ID,
        "memory_implementation_hash": implementation_hash,
        "presentation_id": presentation_id,
        "presentation_hash": presentation_hash,
    }
    existing = [
        row for row in checkpoint["event_attempts"] if row["attempt_id"] == attempt.attempt_id
    ]
    if existing:
        if len(existing) != 1 or any(
            existing[0].get(key) != attempt_row.get(key)
            for key in ("status", "raw_arguments", "logical_update_id")
        ):
            raise ValueError("recovered event attempt conflicts with the checkpoint")
        return
    checkpoint["event_attempts"].append(attempt_row)
    tool = event_tool(domain)
    choice = _forced_tool_choice()
    digest = content_hash({"messages": attempt.messages, "tools": [tool], "tool_choice": choice})
    context = ModelContext(
        context_id=_stable_id("context", attempt.call_id, digest),
        content_hash=digest,
        stage="writer",
        domain_id=domain.domain_id,
        case_id=attempt.trajectory.case_id,
        condition_id=EVENT_CONDITION_ID,
        block_index=int(attempt.block.block_index),
        probe_id=None,
        writer_run_id=0,
        executor_run_id=None,
        memory_id=attempt.trajectory.current_memory_id,
        memory_attempt_id=attempt.attempt_id,
        evidence_id=None,
        trial_id=None,
        call_id=attempt.call_id,
        framework_run_id=None,
        messages=tuple(copy.deepcopy(attempt.messages)),
        tools=(tool,),
        tool_choice=choice,
        model=writer,
        presentation_id=presentation_id,
        presentation_hash=presentation_hash,
        metadata={
            "logical_update_id": attempt.logical_update_id,
            "attempt_index": attempt.attempt_index,
            "repair_of_attempt_id": attempt.repair_of_attempt_id,
            "terminal_attempt": terminal,
            "status": status,
            "input_kind": "new_conversation_block",
            "architecture": IMPLEMENTATION_ID,
            "cumulative_event_log_model_visible": False,
            "reference_index_tokens": 0,
        },
    )
    validate_model_context_leakage(domain, attempt.trajectory.case, context)
    checkpoint["writer_contexts"].append(context.to_dict())
    state_text = canonical_json(attempt.previous_state)
    surface_text = canonical_json(
        {"messages": attempt.messages, "tools": [tool], "tool_choice": choice}
    )
    output_text = canonical_json(arguments) if arguments is not None else ""
    checkpoint["writer_resources"].append(
        {
            "schema_version": RESOURCE_SCHEMA_VERSION,
            "attempt_id": attempt.attempt_id,
            "logical_update_id": attempt.logical_update_id,
            "domain_id": domain.domain_id,
            "case_id": attempt.trajectory.case_id,
            "target_id": attempt.trajectory.target_id,
            "writer_seed": attempt.trajectory.seed,
            "block_index": int(attempt.block.block_index),
            "attempt_index": attempt.attempt_index,
            "previous_state_tokens": count_reference_tokens(state_text),
            "reference_index_tokens": 0,
            "new_block_tokens": count_reference_tokens(attempt.block_text),
            "total_writer_surface_tokens": count_reference_tokens(surface_text),
            "writer_output_reference_tokens": count_reference_tokens(output_text),
            "reference_tokenizer": reference_tokenizer_name(),
            "cumulative_event_log_model_visible": False,
        }
    )


def _finalize_update(
    domain: AuthorizationMemoryDomain,
    checkpoint: dict[str, Any],
    trajectory: _Trajectory,
    attempt: _WriterAttemptInput,
    *,
    status: str,
    events: Sequence[ExtractedEvent],
    next_reducer: PublicEventReducer,
    detail: str,
    presentation_hash: str,
    presentation_id: str,
    implementation_hash: str,
    writer: ModelProvenance,
) -> None:
    block_index = int(attempt.block.block_index)
    parent_memory_id = trajectory.current_memory_id
    trajectory.reducer = next_reducer
    reduced = trajectory.reducer.visible_state()
    memory_id = _stable_id(
        "event-memory",
        trajectory.chain_id,
        str(block_index),
        content_hash(reduced),
    )
    trajectory.current_memory_id = memory_id
    trajectory.completed_blocks.add(block_index)
    event_rows = []
    for event in events:
        row = {
            **event.to_dict(),
            "log_schema_version": EVENT_LOG_SCHEMA_VERSION,
            "domain_id": domain.domain_id,
            "case_id": trajectory.case_id,
            "target_id": trajectory.target_id,
            "writer_seed": trajectory.seed,
            "chain_id": trajectory.chain_id,
            "logical_update_id": attempt.logical_update_id,
            "block_index": block_index,
            "source_attempt_id": attempt.attempt_id,
        }
        checkpoint["event_log"].append(row)
        event_rows.append(row)
    checkpoint["event_deltas"].append(
        {
            "schema_version": EVENT_DELTA_SCHEMA_VERSION,
            "delta_id": _stable_id("event-delta", attempt.logical_update_id),
            "logical_update_id": attempt.logical_update_id,
            "domain_id": domain.domain_id,
            "case_id": trajectory.case_id,
            "target_id": trajectory.target_id,
            "writer_seed": trajectory.seed,
            "chain_id": trajectory.chain_id,
            "block_index": block_index,
            "status": status,
            "detail": detail,
            "source_attempt_id": attempt.attempt_id,
            "event_ids": [row["event_id"] for row in event_rows],
            "events": [event.to_dict() for event in events],
            "atomic": True,
            "failed_update_appended_no_events": status != "accepted",
        }
    )
    external_log_json = canonical_json([event.to_dict() for event in trajectory.reducer.event_log])
    external_storage_json = canonical_json(
        [row for row in checkpoint["event_log"] if row["chain_id"] == trajectory.chain_id]
    )
    checkpoint["reduced_states"].append(
        {
            "schema_version": REDUCED_STATE_SCHEMA_VERSION,
            "state_id": _stable_id("event-state", attempt.logical_update_id, content_hash(reduced)),
            "logical_update_id": attempt.logical_update_id,
            "domain_id": domain.domain_id,
            "case_id": trajectory.case_id,
            "target_id": trajectory.target_id,
            "writer_seed": trajectory.seed,
            "chain_id": trajectory.chain_id,
            "block_index": block_index,
            "status": status,
            "memory_id": memory_id,
            "parent_memory_id": parent_memory_id,
            "source_attempt_id": attempt.attempt_id,
            "payload": copy.deepcopy(reduced),
            "reduced_state_tokens": count_reference_tokens(canonical_json(reduced)),
            "external_event_count": len(trajectory.reducer.event_log),
            "external_event_log_tokens": count_reference_tokens(external_log_json),
            "external_event_log_storage_tokens": count_reference_tokens(external_storage_json),
            "external_record_count": len(trajectory.reducer.records),
            "cumulative_event_log_model_visible": False,
            "reference_index_tokens": 0,
        }
    )
    for resource in reversed(checkpoint["writer_resources"]):
        if resource["attempt_id"] == attempt.attempt_id:
            resource.update(
                {
                    "reduced_state_tokens_after_update": count_reference_tokens(
                        canonical_json(reduced)
                    ),
                    "external_event_count_after_update": len(trajectory.reducer.event_log),
                    "external_event_log_tokens_after_update": count_reference_tokens(
                        external_log_json
                    ),
                    "external_event_log_storage_tokens_after_update": (
                        count_reference_tokens(external_storage_json)
                    ),
                }
            )
            break
    memory = MemoryArtifact(
        memory_id=memory_id,
        parent_memory_id=parent_memory_id,
        chain_id=trajectory.chain_id,
        domain_id=domain.domain_id,
        case_id=trajectory.case_id,
        condition_id=EVENT_CONDITION_ID,
        block_index=block_index,
        writer_run_id=0,
        writer_seed=trajectory.seed,
        writer=writer,
        architecture=MemoryArchitecture.TYPED,
        origin=MemoryOrigin.WRITER,
        payload_schema_id=domain.memory.payload_schema_id,
        payload_schema_version=str(reduced["schema_version"]),
        payload=copy.deepcopy(dict(reduced)),
        reference_tokens=count_reference_tokens(canonical_json(reduced)),
        reference_tokenizer=reference_tokenizer_name(),
        content_hash=content_hash(reduced),
        presentation_id=presentation_id,
        presentation_hash=presentation_hash,
        memory_implementation_id=IMPLEMENTATION_ID,
        memory_implementation_hash=implementation_hash,
        profile_id=trajectory.chain_id,
        source_attempt_id=attempt.attempt_id,
        framework={
            "event_schema_version": EVENT_SCHEMA_VERSION,
            "reducer": "public_event_reducer_v1",
            "cumulative_event_log_model_visible": False,
        },
    )
    checkpoint.setdefault("memory_rows", []).append(memory.to_dict())


def _model_provenance_from_row(value: Mapping[str, Any]) -> ModelProvenance:
    return ModelProvenance(
        target_id=value.get("target_id"),
        provider=value.get("provider"),
        requested_model=value.get("requested_model"),
        resolved_model=value.get("resolved_model"),
        response_model=value.get("response_model"),
        effective_parameters=copy.deepcopy(dict(value.get("effective_parameters") or {})),
    )


def _final_writer_artifacts(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    trajectories: Sequence[_Trajectory],
    checkpoint: Mapping[str, Any],
    *,
    presentation_id: str,
    presentation_hash: str,
    implementation_hash: str,
    writer_task: str,
    config: Any,
) -> dict[str, Any]:
    del writer_task, config
    memory_rows = list(checkpoint.get("memory_rows", ()))
    by_id = {row["memory_id"]: row for row in memory_rows}
    evidence_rows = []
    evidence_objects = []
    for trajectory in trajectories:
        expected_blocks = {
            int(block.block_index) for block in domain.corpus.blocks(trajectory.case)
        }
        if trajectory.completed_blocks != expected_blocks:
            raise ValueError(f"trajectory {trajectory.key} is incomplete")
        if trajectory.current_memory_id not in by_id:
            raise ValueError(f"trajectory {trajectory.key} has no final memory row")
        memory = by_id[str(trajectory.current_memory_id)]
        writer = _model_provenance_from_row(memory["writer"])
        evidence_id = _stable_id(
            "event-evidence",
            domain.domain_id,
            trajectory.target_id,
            trajectory.case_id,
            str(trajectory.seed),
            str(trajectory.current_memory_id),
        )
        evidence = FrozenEvidence(
            evidence_id=evidence_id,
            domain_id=domain.domain_id,
            case_id=trajectory.case_id,
            condition_id=EVENT_CONDITION_ID,
            memory_run_id=0,
            writer_seed=trajectory.seed,
            writer=writer,
            architecture=MemoryArchitecture.TYPED,
            memory_id=str(trajectory.current_memory_id),
            payload=copy.deepcopy(memory["payload"]),
            source_history=None,
            content_hash=str(memory["content_hash"]),
            presentation_id=presentation_id,
            presentation_hash=presentation_hash,
            memory_implementation_id=IMPLEMENTATION_ID,
            memory_implementation_hash=implementation_hash,
            profile_id=trajectory.chain_id,
            source_attempt_id=memory.get("source_attempt_id"),
        )
        evidence_rows.append(evidence.to_dict())
        evidence_objects.append(evidence)
    return {
        "memory_rows": memory_rows,
        "evidence_rows": evidence_rows,
        "evidence_objects": tuple(evidence_objects),
    }


def _representation_rows(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    trajectories: Sequence[_Trajectory],
    checkpoint: Mapping[str, Any],
) -> list[dict[str, Any]]:
    cases_by_id = {domain.corpus.case_id(case): case for case in cases}
    states_by_key: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in checkpoint.get("reduced_states", ()):
        key = f"{row['target_id']}|{row['case_id']}|{row['writer_seed']}"
        states_by_key[key].append(row)
    rows = []
    for trajectory in trajectories:
        case = cases_by_id[trajectory.case_id]
        previous_error: bool | None = None
        state_rows = sorted(states_by_key[trajectory.key], key=lambda row: int(row["block_index"]))
        for state_row in state_rows:
            block_index = int(state_row["block_index"])
            payload = domain.memory.parse_typed(state_row["payload"])
            report = domain.fidelity.compare(
                case,
                payload,
                through_block_index=block_index,
            )
            field_rows = tuple(report.fields)
            semantic_error = any(row.errors for row in field_rows)
            authority_gaining_error = any(row.overgrant for row in field_rows)
            rows.append(
                {
                    "schema_version": 1,
                    "row_type": "state_transition",
                    "domain_id": domain.domain_id,
                    "case_id": trajectory.case_id,
                    "target_id": trajectory.target_id,
                    "writer_seed": trajectory.seed,
                    "chain_id": trajectory.chain_id,
                    "block_index": block_index,
                    "memory_id": state_row["memory_id"],
                    "semantic_error": semantic_error,
                    "authority_gaining_error": authority_gaining_error,
                    "final_state_exact": not semantic_error,
                    "field_error_count": sum(bool(row.errors) for row in field_rows),
                    "error_introduction": bool(semantic_error and previous_error is False),
                    "error_persistence": bool(semantic_error and previous_error is True),
                    "self_repair": bool(not semantic_error and previous_error is True),
                    "failed_update": state_row["status"] != "accepted",
                }
            )
            previous_error = semantic_error
        final_payload = trajectory.reducer.visible_state()
        final_block = int(domain.corpus.blocks(case)[-1].block_index)
        for probe in domain.corpus.probes(case):
            canonical = domain.executor.oracle(case, probe.request)
            remembered = domain.memory.authorizes(case, final_payload, probe.request)
            rows.append(
                {
                    "schema_version": 1,
                    "row_type": "request_formation",
                    "domain_id": domain.domain_id,
                    "case_id": trajectory.case_id,
                    "target_id": trajectory.target_id,
                    "writer_seed": trajectory.seed,
                    "chain_id": trajectory.chain_id,
                    "block_index": final_block,
                    "probe_id": probe.probe_id,
                    "pair_id": probe.pair_id,
                    "dimension": probe.dimension,
                    "canonical_authorized": canonical.authorized,
                    "memory_authorized": remembered.authorized,
                    "false_authority": bool(not canonical.authorized and remembered.authorized),
                    "valid_authority_preserved": bool(
                        canonical.authorized and remembered.authorized
                    ),
                    "representation_undergrant": bool(
                        canonical.authorized and not remembered.authorized
                    ),
                }
            )
    return rows


def _event_diagnostic_rows(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    trajectories: Sequence[_Trajectory],
    checkpoint: Mapping[str, Any],
) -> list[dict[str, Any]]:
    generated: dict[tuple[str, str, int, int], list[ExtractedEvent]] = defaultdict(list)
    for row in checkpoint.get("event_log", ()):
        key = (
            str(row["target_id"]),
            str(row["case_id"]),
            int(row["writer_seed"]),
            int(row["block_index"]),
        )
        generated[key].append(_event_from_row(row))
    rows = []
    for trajectory in trajectories:
        canonical = _canonical_events_by_block(domain, trajectory.case)
        block_indices = [int(block.block_index) for block in domain.corpus.blocks(trajectory.case)]
        for block_index in block_indices:
            expected = list(canonical.get(block_index, ()))
            actual = sorted(
                generated.get(
                    (trajectory.target_id, trajectory.case_id, trajectory.seed, block_index),
                    (),
                ),
                key=lambda item: item.event_index,
            )
            paired = min(len(expected), len(actual))
            for index in range(paired):
                gold = expected[index]
                observed = actual[index]
                failures = []
                if observed.event_type != gold.event_type:
                    failures.append("wrong_event_type")
                if observed.target_authorization_id != gold.target_authorization_id:
                    failures.append("wrong_target_reference")
                if canonical_json(observed.record) != canonical_json(gold.record):
                    failures.extend(_record_failure_kinds(observed.record, gold.record))
                if canonical_json(observed.changes) != canonical_json(gold.changes):
                    failures.extend(_record_failure_kinds(observed.changes, gold.changes))
                if tuple(observed.source_turn_ids) != tuple(gold.source_turn_ids):
                    failures.append("incorrect_provenance")
                rows.append(
                    _diagnostic_row(
                        domain,
                        trajectory,
                        block_index,
                        index,
                        observed,
                        gold,
                        failures,
                        alignment="chronological_position",
                    )
                )
            for index, gold in enumerate(expected[paired:], start=paired):
                rows.append(
                    _diagnostic_row(
                        domain,
                        trajectory,
                        block_index,
                        index,
                        None,
                        gold,
                        ["missed_authorization_changing_event"],
                        alignment="unmatched_canonical_tail",
                    )
                )
            for index, observed in enumerate(actual[paired:], start=paired):
                observed_signature = canonical_json(
                    {
                        "event_type": observed.event_type,
                        "target_authorization_id": observed.target_authorization_id,
                        "source_turn_ids": observed.source_turn_ids,
                        "record": observed.record,
                        "changes": observed.changes,
                    }
                )
                prior_signatures = {
                    canonical_json(
                        {
                            "event_type": prior.event_type,
                            "target_authorization_id": prior.target_authorization_id,
                            "source_turn_ids": prior.source_turn_ids,
                            "record": prior.record,
                            "changes": prior.changes,
                        }
                    )
                    for prior in actual[:index]
                }
                rows.append(
                    _diagnostic_row(
                        domain,
                        trajectory,
                        block_index,
                        index,
                        observed,
                        None,
                        [
                            "duplicate_extracted_event"
                            if observed_signature in prior_signatures
                            else "spurious_extracted_event"
                        ],
                        alignment="unmatched_generated_tail",
                    )
                )
    return rows


def _record_failure_kinds(
    observed: Mapping[str, Any] | None,
    expected: Mapping[str, Any] | None,
) -> list[str]:
    if observed is None or expected is None:
        return ["other_record_payload_error"]
    failures = []
    if observed.get("scope") != expected.get("scope"):
        failures.append("scope_corruption")
    validity = {"valid_from", "valid_until"}
    if any(observed.get(key) != expected.get(key) for key in validity):
        failures.append("validity_corruption")
    other = (set(observed) | set(expected)) - {"scope", *validity}
    if any(observed.get(key) != expected.get(key) for key in other):
        failures.append("other_record_payload_error")
    return failures or ["other_record_payload_error"]


def _diagnostic_row(
    domain: AuthorizationMemoryDomain,
    trajectory: _Trajectory,
    block_index: int,
    event_index: int,
    observed: ExtractedEvent | None,
    expected: ExtractedEvent | None,
    failures: Sequence[str],
    *,
    alignment: str,
) -> dict[str, Any]:
    return {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "domain_id": domain.domain_id,
        "case_id": trajectory.case_id,
        "target_id": trajectory.target_id,
        "writer_seed": trajectory.seed,
        "chain_id": trajectory.chain_id,
        "block_index": block_index,
        "event_index": event_index,
        "alignment": alignment,
        "alignment_ambiguous": alignment != "chronological_position",
        "generated_event_id": observed.event_id if observed else None,
        "canonical_event_id": expected.event_id if expected else None,
        "failures": list(dict.fromkeys(failures)),
        "exact": not failures,
    }


def _executor_jobs(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    evidence: Sequence[FrozenEvidence],
    *,
    presentation_id: str,
    presentation_hash: str,
    implementation_hash: str,
) -> tuple[
    tuple[ExecutorJob, ...],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    cases_by_id = {domain.corpus.case_id(case): case for case in cases}
    jobs = []
    oracle_memories: dict[str, dict[str, Any]] = {}
    oracle_evidence: dict[str, FrozenEvidence] = {}
    witnesses = []
    for item in evidence:
        case = cases_by_id[item.case_id]
        assert isinstance(item.payload, Mapping)
        for probe in domain.corpus.probes(case):
            witness_id = _stable_id(
                "residual-witness",
                item.evidence_id,
                probe.probe_id,
            )
            jobs.append(
                ExecutorJob(
                    job_id=_stable_id("event-executor-job", item.evidence_id, probe.probe_id),
                    case=case,
                    probe=probe,
                    evidence=item,
                    metadata={
                        "replay_kind": "event_sourced_full",
                        "residual_witness_id": witness_id,
                    },
                )
            )
            canonical = domain.executor.oracle(case, probe.request)
            remembered = domain.memory.authorizes(case, item.payload, probe.request)
            if canonical.authorized or not remembered.authorized:
                continue
            oracle_key = _stable_id(
                "oracle-event-memory",
                domain.domain_id,
                item.case_id,
                item.writer.target_id if item.writer else "",
                str(item.writer_seed),
            )
            oracle_payload = domain.memory.serialize_typed(domain.memory.faithful_typed(case))
            if oracle_key not in oracle_memories:
                memory = MemoryArtifact(
                    memory_id=oracle_key,
                    parent_memory_id=None,
                    chain_id=_stable_id("oracle-event-chain", oracle_key),
                    domain_id=domain.domain_id,
                    case_id=item.case_id,
                    condition_id="oracle_exact_event_witness",
                    block_index=int(domain.corpus.blocks(case)[-1].block_index),
                    writer_run_id=0,
                    writer_seed=item.writer_seed,
                    writer=item.writer,
                    architecture=MemoryArchitecture.TYPED,
                    origin=MemoryOrigin.FAITHFUL,
                    payload_schema_id=domain.memory.payload_schema_id,
                    payload_schema_version=str(oracle_payload["schema_version"]),
                    payload=copy.deepcopy(dict(oracle_payload)),
                    reference_tokens=count_reference_tokens(canonical_json(oracle_payload)),
                    reference_tokenizer=reference_tokenizer_name(),
                    content_hash=content_hash(oracle_payload),
                    presentation_id=presentation_id,
                    presentation_hash=presentation_hash,
                    memory_implementation_id=IMPLEMENTATION_ID,
                    memory_implementation_hash=implementation_hash,
                    profile_id=None,
                    framework={
                        "controlled_replay": "oracle_exact_replacement",
                        "selected_before_executor_calls": True,
                    },
                )
                oracle_memories[oracle_key] = memory.to_dict()
                exact_evidence = FrozenEvidence(
                    evidence_id=_stable_id("oracle-event-evidence", oracle_key),
                    domain_id=domain.domain_id,
                    case_id=item.case_id,
                    condition_id="oracle_exact_event_witness",
                    memory_run_id=0,
                    writer_seed=item.writer_seed,
                    writer=item.writer,
                    architecture=MemoryArchitecture.TYPED,
                    memory_id=oracle_key,
                    payload=copy.deepcopy(dict(oracle_payload)),
                    source_history=None,
                    content_hash=content_hash(oracle_payload),
                    presentation_id=presentation_id,
                    presentation_hash=presentation_hash,
                    memory_implementation_id=IMPLEMENTATION_ID,
                    memory_implementation_hash=implementation_hash,
                )
                oracle_evidence[oracle_key] = exact_evidence
            jobs.append(
                ExecutorJob(
                    job_id=_stable_id("oracle-event-executor-job", witness_id),
                    case=case,
                    probe=probe,
                    evidence=oracle_evidence[oracle_key],
                    metadata={
                        "replay_kind": "oracle_exact_residual_replacement",
                        "residual_witness_id": witness_id,
                        "paired_event_evidence_id": item.evidence_id,
                    },
                )
            )
            witnesses.append(
                {
                    "schema_version": 1,
                    "witness_id": witness_id,
                    "domain_id": domain.domain_id,
                    "case_id": item.case_id,
                    "probe_id": probe.probe_id,
                    "pair_id": probe.pair_id,
                    "dimension": probe.dimension,
                    "writer_target_id": item.writer.target_id if item.writer else None,
                    "writer_seed": item.writer_seed,
                    "event_evidence_id": item.evidence_id,
                    "event_memory_id": item.memory_id,
                    "oracle_evidence_id": oracle_evidence[oracle_key].evidence_id,
                    "oracle_memory_id": oracle_key,
                    "canonical_request_authorized": False,
                    "event_state_authorized": True,
                    "selected_before_executor_calls": True,
                    "selection_uses_executor_behavior": False,
                }
            )
    return (
        tuple(jobs),
        list(oracle_memories.values()),
        [item.to_dict() for item in oracle_evidence.values()],
        witnesses,
    )


def _executor_job_row(job: ExecutorJob) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "job_id": job.job_id,
        "domain_id": job.evidence.domain_id,
        "case_id": job.evidence.case_id,
        "probe_id": job.probe.probe_id,
        "evidence_id": job.evidence.evidence_id,
        "memory_id": job.evidence.memory_id,
        "request": job.case and job.probe.request.to_dict(),
        "metadata": copy.deepcopy(dict(job.metadata)),
    }


def _run_resumable_executor_jobs(
    llm: LLM,
    domain: AuthorizationMemoryDomain,
    jobs: Sequence[ExecutorJob],
    *,
    run_dir: Path,
    executor_task: str,
    executor_targets: Sequence[str],
    batch_size: int | None,
    seed: int,
    presentation: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run only missing executor trials and recover logged calls after a crash."""

    checkpoint_path = run_dir / "executor_checkpoint.json"
    identity_hash = content_hash(
        {
            "jobs": [_executor_job_row(job) for job in jobs],
            "targets": list(executor_targets),
            "executor_task": executor_task,
            "seed": seed,
            "presentation_hash": content_hash(presentation.to_dict()),
            "executor_routes": [
                resolve_model_provenance(
                    llm.config,
                    executor_task,
                    target,
                    effective_parameters=effective_behavioral_parameters(
                        llm.config,
                        executor_task,
                        overrides={"temperature": 1.0, "seed": seed, "tool_choice": "auto"},
                        tools=model_visible_tools(domain, presentation),
                        required_capabilities=("native_tools", "seed"),
                    ),
                ).to_dict()
                for target in executor_targets
            ],
        }
    )
    if checkpoint_path.is_file():
        checkpoint = _read_checkpoint(checkpoint_path)
        if checkpoint.get("schema_version") != "event_executor_checkpoint_v1":
            raise ValueError("unsupported executor checkpoint")
        if checkpoint.get("identity_hash") != identity_hash:
            raise ValueError("executor checkpoint identity does not match frozen jobs")
    else:
        checkpoint = {
            "schema_version": "event_executor_checkpoint_v1",
            "identity_hash": identity_hash,
            "trials": {},
            "contexts": {},
        }
        _write_checkpoint(checkpoint_path, checkpoint)
    tools = model_visible_tools(domain, presentation)
    presentation_hash = content_hash(presentation.to_dict())
    logged = _call_log_by_id(llm.logger.path)
    ordered_trial_ids = []
    for target_id in executor_targets:
        identities = [
            planned_study_job_identity(
                domain,
                job,
                study_id=EVENT_SOURCING_STUDY_ID,
                executor_task=executor_task,
                target_id=target_id,
                executor_run_id=0,
                seed=seed,
                presentation=presentation,
                config=llm.config,
            )
            for job in jobs
        ]
        ordered_trial_ids.extend(identity["trial_id"] for identity in identities)
        pending = [
            (job, identity)
            for job, identity in zip(jobs, identities)
            if identity["trial_id"] not in checkpoint["trials"]
        ]
        if not pending:
            continue
        messages = [
            _study_job_messages(
                domain,
                job,
                presentation=presentation,
                pressure=None,
            )
            for job, _ in pending
        ]
        observations: list[Any] = [None] * len(pending)
        missing_indices = []
        for index, (_, identity) in enumerate(pending):
            record = logged.get(identity["call_id"])
            if record is None:
                missing_indices.append(index)
            else:
                observations[index] = _logged_chat_completion(record)
        if missing_indices:
            responses = llm.batch(
                executor_task,
                [messages[index] for index in missing_indices],
                target=target_id,
                call_ids=[pending[index][1]["call_id"] for index in missing_indices],
                tools=tools,
                tool_choice="auto",
                temperature=1.0,
                seed=seed,
                batch_size=batch_size,
                return_exceptions=True,
                required_capabilities=("native_tools", "seed"),
            )
            for index, response in zip(missing_indices, responses):
                observations[index] = response
            logged.update(_call_log_by_id(llm.logger.path))
        for (job, identity), item_messages, response in zip(
            pending,
            messages,
            observations,
        ):
            executor = identity["executor"]
            context = _study_job_model_context(
                domain,
                job,
                messages=item_messages,
                tools=tools,
                executor=executor,
                executor_run_id=0,
                call_id=identity["call_id"],
                trial_id=identity["trial_id"],
                study_id=EVENT_SOURCING_STUDY_ID,
                pressure=None,
                presentation=presentation,
                presentation_hash=presentation_hash,
            )
            if not isinstance(response, Exception):
                response_model = getattr(response, "model", None)
                effective_executor = with_response_model(
                    executor,
                    str(response_model) if response_model else None,
                )
                context = replace(context, model=effective_executor)
            else:
                effective_executor = executor
            trial = _score_executor_response(
                domain,
                job.case,
                job.probe,
                job.evidence,
                response,
                effective_executor,
                executor_run_id=0,
                seed=seed,
                trial_id=identity["trial_id"],
                call_id=identity["call_id"],
                model_context_id=context.context_id,
                presentation=presentation,
                presentation_hash=presentation_hash,
                oracle_block_index=job.oracle_block_index,
                study_id=EVENT_SOURCING_STUDY_ID,
                study_metadata={"job_id": job.job_id, **dict(job.metadata)},
                challenge_pressure_id=None,
                challenge_metadata=_job_challenge_metadata(
                    domain,
                    job,
                    pressure=None,
                ),
            )
            checkpoint["trials"][identity["trial_id"]] = trial.to_dict()
            checkpoint["contexts"][identity["trial_id"]] = context.to_dict()
            _write_checkpoint(checkpoint_path, checkpoint)
    expected = len(jobs) * len(executor_targets)
    if len(checkpoint["trials"]) != expected or len(checkpoint["contexts"]) != expected:
        raise ValueError("executor checkpoint is incomplete after execution")
    return (
        [checkpoint["trials"][trial_id] for trial_id in ordered_trial_ids],
        [checkpoint["contexts"][trial_id] for trial_id in ordered_trial_ids],
    )


def _logged_chat_completion(record: Mapping[str, Any]) -> Any:
    if record.get("error"):
        return RuntimeError(str(record["error"]))
    response = record.get("response")
    if not isinstance(response, Mapping):
        return RuntimeError("logged executor call has no response")
    from openai.types.chat import ChatCompletion

    message = {
        "role": "assistant",
        "content": response.get("content"),
        "tool_calls": response.get("tool_calls"),
    }
    return ChatCompletion.model_validate(
        {
            "id": _stable_id("recovered-chat", str(record.get("call_id"))),
            "choices": [
                {
                    "finish_reason": response.get("finish_reason") or "stop",
                    "index": 0,
                    "message": message,
                }
            ],
            "created": 0,
            "model": str(record.get("response_model") or record.get("resolved_model") or "unknown"),
            "object": "chat.completion",
        }
    )


def _write_named_rows(
    run_dir: Path,
    rows: Mapping[str, Sequence[Any]],
) -> dict[str, dict[str, Any]]:
    result = {}
    for name, values in rows.items():
        path = run_dir / f"{name}.jsonl"
        count = write_jsonl(path, values)
        result[name] = {
            "path": path.name,
            "sha256": file_hash(path),
            "rows": count,
        }
    return result


def _jsonl_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _validate_context_call_log_rows(
    contexts: Sequence[Mapping[str, Any]],
    calls_path: Path,
) -> None:
    if not calls_path.is_file():
        if contexts:
            raise ValueError("model contexts exist without a call log")
        return
    by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for line in calls_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        call_id = row.get("call_id")
        if isinstance(call_id, str) and call_id:
            by_id[call_id].append(row)
    context_ids = {str(row["call_id"]) for row in contexts}
    if set(by_id) - context_ids:
        raise ValueError("call log contains logical calls without model contexts")
    for context in contexts:
        call_id = str(context["call_id"])
        records = by_id.get(call_id, ())
        if not records:
            raise ValueError(f"model context {context['context_id']} has no call log row")
        for record in records:
            request = record.get("request")
            if not isinstance(request, Mapping):
                raise ValueError("call log request is missing")
            params = request.get("params")
            tool_choice = request.get("tool_choice")
            if tool_choice is None and isinstance(params, Mapping):
                tool_choice = params.get("tool_choice")
            tools = request.get("tools")
            if tools is None and isinstance(params, Mapping):
                tools = params.get("tools")
            digest = content_hash(
                {
                    "messages": request.get("messages"),
                    "tools": tools or [],
                    "tool_choice": tool_choice,
                }
            )
            if digest != context["content_hash"]:
                raise ValueError(f"call log context hash mismatch for {call_id}")


def _write_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    from tempfile import NamedTemporaryFile

    checkpoint["checkpoint_sha256"] = content_hash(
        {key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"}
    )
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n")
        handle.flush()
    temporary.replace(path)


def _read_checkpoint(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("checkpoint must be an object")
    digest = value.get("checkpoint_sha256")
    if digest != content_hash(
        {key: item for key, item in value.items() if key != "checkpoint_sha256"}
    ):
        raise ValueError("checkpoint content hash does not match")
    return value
