from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import jsonpatch
import jsonpointer
from langmem import create_memory_manager
from langmem.knowledge.extraction import Memory as LangMemTextProfile
from pydantic import BaseModel
from eal_bench.llm import LangChainCallLogger, create_langchain_chat_model

from domains.base import AuthorizationMemoryDomain, MemoryArchitecture

from .leakage import validate_model_context_leakage
from .persistence import canonical_json, content_hash
from .schemas import (
    LANGMEM_IMPLEMENTATION_ID,
    TYPED_MEMORY_PAYLOAD_SCHEMA_VERSION,
    FrozenEvidence,
    MemoryArtifact,
    MemoryAttempt,
    MemoryOrigin,
    MemoryState,
    ModelContext,
    ModelProvenance,
)
from .tokens import TokenCounter, count_reference_tokens, reference_tokenizer_name


_MANAGER_CONFIG = {
    "enable_inserts": False,
    "enable_updates": True,
    "enable_deletes": False,
    "max_steps": 1,
    "trustcall_validation_attempts": 1,
    "invocation_timeout_seconds": 180,
    "route_timeout_seconds": 3600,
    "profile_identity_contract": "exact_existing_profile_id_v1",
    "free_text_value_contract": "atomic_plain_text_string_v1",
    "typed_value_contract": "schema_native_json_v1",
    "async_lifecycle": "single_event_loop_per_target_group_v1",
}
_INVOCATION_TIMEOUT_SECONDS = 180.0
_ROUTE_TIMEOUT_SECONDS = 3600.0

NESTED_ARRAY_PATCH_INSTRUCTION = (
    "PatchDoc cannot encode an array nested inside an object that is itself "
    "inside a whole object value. Use ordered dependent patches instead: "
    "first add or replace the containing object with each such nested array "
    "field set to null, then replace each field through its direct JSON "
    "Pointer with the actual array value. A dependent add must precede its "
    "replace even though the generic PatchDoc guidance normally lists "
    "replaces first."
)
FREE_TEXT_VALUE_INSTRUCTION = (
    "The profile has one atomic field named content. For every free-text update, "
    "use exactly one replace patch at /content whose value is the complete revised "
    "plain-text or Markdown string. Never use a descendant path such as "
    "/content/anything, and never encode a structured JSON document inside the "
    "string."
)
TYPED_VALUE_INSTRUCTION = (
    "Preserve the JSON types declared by the typed profile schema. In "
    "particular, emit arrays as JSON arrays, objects as JSON objects, numbers "
    "as numbers, booleans as booleans, and null only where the schema permits "
    "it; do not encode any of them as strings."
)


def profile_identity_instruction(profile_id: str) -> str:
    """Return the shared exact-identity contract for one existing profile."""

    return (
        "The single existing profile ID is "
        f"{canonical_json(profile_id)}. Every PatchDoc call must copy that exact "
        "string into json_doc_id. It is an opaque identifier: never replace it "
        "with an array index, schema name, shortened value, or placeholder."
    )


@dataclass(frozen=True)
class WriterUpdateSpec:
    block_index: int
    messages: tuple[dict[str, str], ...]
    visible_source_ids: frozenset[str]
    input_kind: str


@dataclass(frozen=True)
class WriterChainSpec:
    case: Any
    condition_id: str
    architecture: MemoryArchitecture
    run_id: int
    writer_seed: int
    target_id: str
    updates: tuple[WriterUpdateSpec, ...]
    presentation_id: str
    model_override: str | None = None
    chain_instance_id: str = "default"
    presentation_hash: str | None = None
    instruction_prefix: str | None = None
    artifact_instance_id: str = "default"
    deterministic_session_ids: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WriterRunArtifacts:
    memories: tuple[MemoryArtifact, ...]
    attempts: tuple[MemoryAttempt, ...]
    states: tuple[MemoryState, ...]
    final_evidence: tuple[FrozenEvidence, ...]
    model_contexts: tuple[ModelContext, ...]


@dataclass
class _ActiveChain:
    spec: WriterChainSpec
    chain_id: str
    profile_id: str
    writer: ModelProvenance
    framework: dict[str, Any]
    current: MemoryArtifact | None = None


@dataclass(frozen=True)
class _Invocation:
    payload: str | dict[str, Any] | None
    raw_arguments: Any
    response_model: str | None
    run_ids: tuple[str, ...]
    error: Exception | None


class _PermanentProviderRouteError(RuntimeError):
    pass


def memory_implementation_manifest(
    domain: AuthorizationMemoryDomain,
) -> dict[str, Any]:
    policy = domain.get_prompt_policy()
    contract = {
        "memory_implementation_id": LANGMEM_IMPLEMENTATION_ID,
        "manager": dict(_MANAGER_CONFIG),
        "patch_contract": {
            "profile_identity": _MANAGER_CONFIG["profile_identity_contract"],
            "nested_array": NESTED_ARRAY_PATCH_INSTRUCTION,
            "free_text": FREE_TEXT_VALUE_INSTRUCTION,
            "typed": TYPED_VALUE_INSTRUCTION,
        },
        "writer_instructions": {
            architecture.value: domain.memory.writer_instructions(architecture)
            for architecture in MemoryArchitecture
        },
        "prompt_policy": {
            "prompt_policy_id": policy.prompt_policy_id,
            "writer_state_instruction": policy.writer_state_instruction,
            "writer_inference_instruction": policy.writer_inference_instruction,
            "writer_repair_instruction": policy.writer_repair_instruction,
            "writer_source_instruction": policy.writer_source_instruction,
            "writer_architecture_instructions": dict(
                policy.writer_architecture_instructions
            ),
            "split_nested_array_patches": policy.split_nested_array_patches,
        },
        "profile_schema": domain.memory.typed_schema(),
        "payload_schema_id": domain.memory.payload_schema_id,
    }
    return {
        **contract,
        "memory_implementation_hash": content_hash(contract),
    }


def framework_manifest(
    domain: AuthorizationMemoryDomain,
    *,
    route_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    implementation = memory_implementation_manifest(domain)
    manifest = {
        "memory_implementation_id": LANGMEM_IMPLEMENTATION_ID,
        "memory_implementation_hash": implementation[
            "memory_implementation_hash"
        ],
        "versions": {
            package: _package_version(package)
            for package in (
                "langmem",
                "trustcall",
                "langchain",
                "langchain-core",
                "langchain-openai",
                "langchain-openrouter",
            )
        },
        "manager": dict(_MANAGER_CONFIG),
        "profile_mode": "single_stable_profile",
    }
    if (
        route_timeout_seconds is not None
        and route_timeout_seconds != _ROUTE_TIMEOUT_SECONDS
    ):
        manifest["runtime_overrides"] = {
            "route_timeout_seconds": route_timeout_seconds,
            "canonical_route_timeout_seconds": _ROUTE_TIMEOUT_SECONDS,
        }
    return manifest


def _ensure_route_time(deadline: float, route_timeout_seconds: float) -> None:
    if time.monotonic() >= deadline:
        raise TimeoutError(
            "writer route exceeded its "
            f"{route_timeout_seconds:g}-second wall-time limit"
        )


async def _bounded_manager_invoke(
    manager: Any,
    payload: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    timeout_seconds: float,
    permanent_error_waiter: Any = None,
) -> Any:
    if permanent_error_waiter is None:
        return await asyncio.wait_for(
            manager.ainvoke(payload, config=config),
            timeout=timeout_seconds,
        )

    async def invoke_or_abort() -> Any:
        manager_task = asyncio.create_task(
            manager.ainvoke(payload, config=config)
        )
        error_task = asyncio.create_task(permanent_error_waiter())
        try:
            done, _ = await asyncio.wait(
                (manager_task, error_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if manager_task in done:
                return await manager_task
            provider_error = await error_task
            manager_task.cancel()
            await asyncio.gather(manager_task, return_exceptions=True)
            raise _PermanentProviderRouteError(
                "permanent provider error aborted LangMem invocation: "
                f"{type(provider_error).__name__}: {provider_error}"
            ) from provider_error
        finally:
            for task in (manager_task, error_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                manager_task,
                error_task,
                return_exceptions=True,
            )

    return await asyncio.wait_for(invoke_or_abort(), timeout=timeout_seconds)


def validate_writer_timeout_guard() -> dict[str, Any]:
    class _NeverReturns:
        async def ainvoke(
            self,
            payload: Mapping[str, Any],
            *,
            config: Mapping[str, Any],
        ) -> None:
            del payload, config
            await asyncio.Event().wait()

    started = time.monotonic()
    try:
        asyncio.run(
            _bounded_manager_invoke(
                _NeverReturns(),
                {},
                config={},
                timeout_seconds=0.01,
            )
        )
    except TimeoutError:
        elapsed = time.monotonic() - started
    else:
        raise AssertionError("writer invocation timeout guard did not fire")
    if elapsed > 1.0:
        raise AssertionError("writer invocation timeout guard was not prompt")
    return {
        "status": "passed",
        "invocation_timeout_seconds": _INVOCATION_TIMEOUT_SECONDS,
        "route_timeout_seconds": _ROUTE_TIMEOUT_SECONDS,
    }


def run_writer_chains(
    llm: Any,
    domain: AuthorizationMemoryDomain,
    specs: Sequence[WriterChainSpec],
    *,
    writer_task: str,
    max_attempts: int,
    capacity_tokens: int,
    batch_size: int | None,
    enforce_capacity: bool = True,
    route_timeout_seconds: float = _ROUTE_TIMEOUT_SECONDS,
    token_counter: TokenCounter | None = None,
) -> WriterRunArtifacts:
    with ExitStack() as runner_stack:
        return _run_writer_chains(
            llm,
            domain,
            specs,
            writer_task=writer_task,
            max_attempts=max_attempts,
            capacity_tokens=capacity_tokens,
            batch_size=batch_size,
            enforce_capacity=enforce_capacity,
            route_timeout_seconds=route_timeout_seconds,
            token_counter=token_counter,
            runner_stack=runner_stack,
        )


def _run_writer_chains(
    llm: Any,
    domain: AuthorizationMemoryDomain,
    specs: Sequence[WriterChainSpec],
    *,
    writer_task: str,
    max_attempts: int,
    capacity_tokens: int,
    batch_size: int | None,
    enforce_capacity: bool,
    route_timeout_seconds: float,
    token_counter: TokenCounter | None = None,
    runner_stack: ExitStack,
) -> WriterRunArtifacts:
    if max_attempts not in {1, 2}:
        raise ValueError("max_attempts must be 1 or 2")
    if not 3600 <= route_timeout_seconds <= 21600:
        raise ValueError(
            "route_timeout_seconds must be between 3600 and 21600"
        )
    if not specs:
        return WriterRunArtifacts((), (), (), (), ())
    for spec in specs:
        if not spec.updates:
            raise ValueError("every writer chain must contain at least one update")

    memories: list[MemoryArtifact] = []
    attempts: list[MemoryAttempt] = []
    states: list[MemoryState] = []
    final_evidence: list[FrozenEvidence] = []
    model_contexts: list[ModelContext] = []
    route_deadline = time.monotonic() + route_timeout_seconds
    grouped: dict[
        tuple[str, MemoryArchitecture, int, str | None],
        list[WriterChainSpec],
    ] = {}
    for spec in specs:
        grouped.setdefault(
            (
                spec.target_id,
                spec.architecture,
                spec.run_id,
                spec.model_override,
            ),
            [],
        ).append(spec)

    for (target_id, architecture, run_id, model_override), group in grouped.items():
        request_seed = group[0].writer_seed
        if any(spec.writer_seed != request_seed for spec in group):
            raise ValueError("writer chains in one run group must share a seed")
        callback = LangChainCallLogger(llm.logger)
        factory = getattr(
            llm,
            "langchain_model_factory",
            create_langchain_chat_model,
        )
        model, route, parameters = factory(
            llm.config,
            writer_task,
            target_id,
            seed=request_seed,
            callbacks=(callback,),
            required_capabilities=(
                "native_tools",
                "forced_tool_choice",
                "seed",
            ),
            require_api_key=not getattr(llm, "offline", False),
            parameter_overrides={
                "temperature": 1.0,
                **(
                    {}
                    if model_override is None
                    else {"model": model_override}
                ),
            },
        )
        base_writer = ModelProvenance(
            target_id=route.target_id,
            provider=route.provider,
            requested_model=route.requested_model,
            resolved_model=route.resolved_model,
            effective_parameters=dict(parameters),
        )
        framework = framework_manifest(
            domain,
            route_timeout_seconds=route_timeout_seconds,
        )
        concurrency = route.max_concurrency
        if batch_size is not None:
            concurrency = min(concurrency, batch_size)
        active = [
            _ActiveChain(
                spec=spec,
                chain_id=_stable_id(
                    "chain",
                    domain.domain_id,
                    domain.corpus.case_id(spec.case),
                    spec.condition_id,
                    str(spec.run_id),
                    spec.target_id,
                    route.provider,
                    route.requested_model,
                    route.resolved_model,
                    spec.model_override or "",
                    spec.chain_instance_id,
                    spec.presentation_id,
                    spec.presentation_hash or "",
                ),
                profile_id="",
                writer=base_writer,
                framework=framework,
            )
            for spec in group
        ]
        for chain in active:
            chain.profile_id = _stable_id("profile", chain.chain_id)

        group_runner = runner_stack.enter_context(asyncio.Runner())
        max_updates = max(len(chain.spec.updates) for chain in active)
        for update_position in range(max_updates):
            _ensure_route_time(route_deadline, route_timeout_seconds)
            wave = [
                chain
                for chain in active
                if update_position < len(chain.spec.updates)
            ]
            update_specs = [
                chain.spec.updates[update_position] for chain in wave
            ]
            first_ids = [
                _stable_id(
                    "attempt",
                    _logical_update_id(chain, update),
                    "1",
                )
                for chain, update in zip(wave, update_specs)
            ]
            invocations = group_runner.run(
                _invoke_wave(
                    model,
                    callback,
                    domain,
                    wave,
                    update_specs,
                    first_ids,
                    capacity_tokens=capacity_tokens,
                    batch_size=concurrency,
                    route_deadline=route_deadline,
                )
            )
            _ensure_route_time(route_deadline, route_timeout_seconds)
            retry: list[tuple[_ActiveChain, WriterUpdateSpec, MemoryAttempt]] = []
            for chain, update, invocation in zip(
                wave, update_specs, invocations
            ):
                artifact, attempt = _process_invocation(
                    domain,
                    chain,
                    update,
                    invocation,
                    attempt_index=1,
                    repair_of_attempt_id=None,
                    capacity_tokens=capacity_tokens,
                    enforce_capacity=enforce_capacity,
                    token_counter=token_counter,
                )
                attempts.append(attempt)
                if artifact is not None and (
                    chain.current is None
                    or artifact.memory_id != chain.current.memory_id
                ):
                    chain.current = artifact
                    memories.append(artifact)
                if attempt.status not in {"accepted", "no_change"} and max_attempts == 2:
                    retry.append((chain, update, attempt))
                    terminal_attempt = False
                else:
                    terminal_attempt = True
                    if chain.current is None:
                        chain.current = _artifact(
                            domain,
                            chain,
                            update.block_index,
                            _empty_payload(domain, architecture),
                            writer=attempt.writer,
                            source_attempt_id=attempt.attempt_id,
                            framework_run_ids=attempt.framework_run_ids,
                            capacity_tokens=capacity_tokens,
                            enforce_capacity=enforce_capacity,
                            token_counter=token_counter,
                        )
                        memories.append(chain.current)
                        attempt = replace(
                            attempt,
                            retained_memory_id=chain.current.memory_id,
                        )
                        attempts[-1] = attempt
                    states.append(_state_after_update(chain, update, (attempt,)))
                model_contexts.extend(
                    _writer_model_contexts(
                        callback,
                        domain,
                        chain,
                        update,
                        attempt,
                        invocation,
                        terminal_attempt=terminal_attempt,
                    )
                )

            if retry:
                retry_ids = [
                    _stable_id(
                        "attempt",
                        first.logical_update_id,
                        "2",
                    )
                    for _, _, first in retry
                ]
                retry_invocations = group_runner.run(
                    _invoke_wave(
                        model,
                        callback,
                        domain,
                        [chain for chain, _, _ in retry],
                        [update for _, update, _ in retry],
                        retry_ids,
                        capacity_tokens=capacity_tokens,
                        batch_size=concurrency,
                        repair_feedback=[
                            _repair_feedback(first) for _, _, first in retry
                        ],
                        route_deadline=route_deadline,
                    )
                )
                _ensure_route_time(route_deadline, route_timeout_seconds)
                for (chain, update, first), invocation in zip(
                    retry, retry_invocations
                ):
                    artifact, attempt = _process_invocation(
                        domain,
                        chain,
                        update,
                        invocation,
                        attempt_index=2,
                        repair_of_attempt_id=first.attempt_id,
                        capacity_tokens=capacity_tokens,
                        enforce_capacity=enforce_capacity,
                        token_counter=token_counter,
                    )
                    attempts.append(attempt)
                    if artifact is not None and (
                        chain.current is None
                        or artifact.memory_id != chain.current.memory_id
                    ):
                        chain.current = artifact
                        memories.append(artifact)
                    if chain.current is None:
                        chain.current = _artifact(
                            domain,
                            chain,
                            update.block_index,
                            _empty_payload(domain, architecture),
                            writer=attempt.writer,
                            source_attempt_id=attempt.attempt_id,
                            framework_run_ids=attempt.framework_run_ids,
                            capacity_tokens=capacity_tokens,
                            enforce_capacity=enforce_capacity,
                            token_counter=token_counter,
                        )
                        memories.append(chain.current)
                        first = replace(
                            first,
                            retained_memory_id=chain.current.memory_id,
                        )
                        attempt = replace(
                            attempt,
                            retained_memory_id=chain.current.memory_id,
                        )
                        for index, recorded in enumerate(attempts):
                            if recorded.attempt_id == first.attempt_id:
                                attempts[index] = first
                            elif recorded.attempt_id == attempt.attempt_id:
                                attempts[index] = attempt
                    states.append(
                        _state_after_update(chain, update, (first, attempt))
                    )
                    model_contexts.extend(
                        _writer_model_contexts(
                            callback,
                            domain,
                            chain,
                            update,
                            attempt,
                            invocation,
                            terminal_attempt=True,
                        )
                    )

        for chain in active:
            if chain.current is None:
                update = chain.spec.updates[-1]
                chain.current = _artifact(
                    domain,
                    chain,
                    update.block_index,
                    _empty_payload(domain, architecture),
                    capacity_tokens=capacity_tokens,
                    enforce_capacity=enforce_capacity,
                    token_counter=token_counter,
                )
                memories.append(chain.current)
            final_evidence.append(_freeze(chain.current, chain.spec.run_id))

    _require_unique((row.memory_id for row in memories), "memory")
    _require_unique((row.attempt_id for row in attempts), "memory attempt")
    _require_unique((row.state_id for row in states), "memory state")
    _require_unique((row.evidence_id for row in final_evidence), "evidence")
    _require_unique((row.context_id for row in model_contexts), "model context")
    return WriterRunArtifacts(
        tuple(memories),
        tuple(attempts),
        tuple(states),
        tuple(final_evidence),
        tuple(model_contexts),
    )


async def _invoke_wave(
    model: Any,
    callback: LangChainCallLogger,
    domain: AuthorizationMemoryDomain,
    chains: Sequence[_ActiveChain],
    updates: Sequence[WriterUpdateSpec],
    attempt_ids: Sequence[str],
    *,
    capacity_tokens: int,
    batch_size: int,
    repair_feedback: Sequence[str] | None = None,
    route_deadline: float | None = None,
) -> list[_Invocation]:
    feedback = repair_feedback or [None] * len(chains)

    async def invoke_one(
        chain: _ActiveChain,
        update: WriterUpdateSpec,
        attempt_id: str,
        repair_detail: str | None,
        semaphore: asyncio.Semaphore,
    ) -> _Invocation:
        schema = (
            LangMemTextProfile
            if chain.spec.architecture is MemoryArchitecture.FREE_TEXT
            else domain.memory.typed_profile_model
        )
        attempt_index = 2 if repair_detail is not None else 1
        session_id = (
            _deterministic_session_id(chain, update, attempt_index)
            if chain.spec.deterministic_session_ids
            else None
        )
        manager = create_memory_manager(
            model,
            schemas=[schema],
            instructions=_manager_instructions(
                domain,
                chain,
                capacity_tokens,
                repair_detail,
            ),
            enable_inserts=False,
            enable_updates=True,
            enable_deletes=False,
        )
        if session_id is not None:
            _install_deterministic_session_id(manager, session_id)
        existing = [
            (
                chain.profile_id,
                _profile_from_current(domain, chain),
            )
        ]
        config = {
            "metadata": {
                "call_id": _stable_id("call", attempt_id, "writer"),
                "memory_attempt_id": attempt_id,
                "memory_implementation_id": LANGMEM_IMPLEMENTATION_ID,
                "memory_implementation_hash": chain.framework[
                    "memory_implementation_hash"
                ],
                "profile_id": chain.profile_id,
                "domain_id": domain.domain_id,
                "case_id": domain.corpus.case_id(chain.spec.case),
                "condition_id": chain.spec.condition_id,
                "block_index": update.block_index,
                "input_kind": update.input_kind,
                "presentation_id": chain.spec.presentation_id,
                "presentation_hash": chain.spec.presentation_hash,
                **(
                    {"deterministic_session_id": session_id}
                    if session_id is not None
                    else {}
                ),
                **dict(chain.spec.metadata),
            },
            "configurable": {"max_attempts": 1},
        }
        result: Any = None
        payload: str | dict[str, Any] | None = None
        raw_arguments: Any = None
        try:
            async with semaphore:
                remaining = (
                    _INVOCATION_TIMEOUT_SECONDS
                    if route_deadline is None
                    else min(
                        _INVOCATION_TIMEOUT_SECONDS,
                        route_deadline - time.monotonic(),
                    )
                )
                if remaining <= 0:
                    raise TimeoutError(
                        "writer route exceeded its wall-time limit"
                    )
                try:
                    result = await _bounded_manager_invoke(
                        manager,
                        {
                            "messages": list(update.messages),
                            "existing": existing,
                            "max_steps": 1,
                        },
                        config=config,
                        timeout_seconds=remaining,
                        permanent_error_waiter=lambda: (
                            callback.wait_for_permanent_error(attempt_id)
                        ),
                    )
                finally:
                    callback.clear_permanent_error_watch(attempt_id)
            observation = callback.observation(attempt_id)
            raw_arguments = _raw_underlying_tool_call(callback, observation)
            if len(result) != 1:
                raise ValueError(
                    f"LangMem returned {len(result)} profiles; expected exactly one"
                )
            if result[0].id != chain.profile_id:
                raise ValueError(
                    f"LangMem returned profile {result[0].id!r}; "
                    f"expected {chain.profile_id!r}"
                )
            payload = _payload_from_profile(
                domain,
                chain.spec.architecture,
                result[0].content,
            )
            _validate_underlying_call(
                callback,
                observation,
                profile_id=chain.profile_id,
                existing_profile=existing[0][1],
                returned_profile=result[0].content,
            )
            return _Invocation(
                payload=payload,
                raw_arguments=raw_arguments,
                response_model=_single_response_model(observation),
                run_ids=tuple(observation["run_ids"]),
                error=None,
            )
        except _PermanentProviderRouteError:
            raise
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                await callback.finalize_attempt_error(
                    attempt_id,
                    exc,
                    termination="benchmark_timeout",
                )
            observation = callback.observation(attempt_id)
            if raw_arguments is None:
                raw_arguments = _raw_underlying_tool_call(callback, observation)
            if (
                payload is None
                and isinstance(result, (list, tuple))
                and len(result) == 1
            ):
                try:
                    payload = _payload_from_profile(
                        domain,
                        chain.spec.architecture,
                        result[0].content,
                    )
                except (TypeError, ValueError):
                    pass
            return _Invocation(
                payload=payload,
                raw_arguments=raw_arguments,
                response_model=_single_response_model(observation),
                run_ids=tuple(observation["run_ids"]),
                error=exc,
            )

    async def invoke_all() -> list[_Invocation]:
        semaphore = asyncio.Semaphore(max(1, batch_size))
        return list(
            await asyncio.gather(
                *(
                    invoke_one(
                        chain,
                        update,
                        attempt_id,
                        repair_detail,
                        semaphore,
                    )
                    for chain, update, attempt_id, repair_detail in zip(
                        chains,
                        updates,
                        attempt_ids,
                        feedback,
                    )
                )
            )
        )

    return await invoke_all()


def _process_invocation(
    domain: AuthorizationMemoryDomain,
    chain: _ActiveChain,
    update: WriterUpdateSpec,
    invocation: _Invocation,
    *,
    attempt_index: int,
    repair_of_attempt_id: str | None,
    capacity_tokens: int,
    enforce_capacity: bool,
    token_counter: TokenCounter | None,
) -> tuple[MemoryArtifact | None, MemoryAttempt]:
    logical_id = _logical_update_id(chain, update)
    attempt_id = _stable_id("attempt", logical_id, str(attempt_index))
    writer = replace(chain.writer, response_model=invocation.response_model)
    status = "accepted"
    detail = "accepted"
    artifact: MemoryArtifact | None = None
    candidate = invocation.payload
    changed: bool | None = None
    if invocation.error is not None:
        status = "writer_error"
        detail = f"{type(invocation.error).__name__}: {invocation.error}"
    else:
        try:
            if candidate is None:
                raise ValueError("LangMem returned no profile payload")
            validated = _validate_payload(
                domain,
                chain,
                update,
                candidate,
                capacity_tokens=capacity_tokens,
                enforce_capacity=enforce_capacity,
                token_counter=token_counter,
            )
            prior_payload = (
                chain.current.payload
                if chain.current is not None
                else _empty_payload(domain, chain.spec.architecture)
            )
            changed = content_hash(validated) != content_hash(prior_payload)
            if changed or chain.current is None:
                artifact = _artifact(
                    domain,
                    chain,
                    update.block_index,
                    validated,
                    writer=writer,
                    source_attempt_id=attempt_id,
                    framework_run_ids=invocation.run_ids,
                    capacity_tokens=capacity_tokens,
                    enforce_capacity=enforce_capacity,
                    token_counter=token_counter,
                )
            if not changed:
                if artifact is None:
                    artifact = chain.current
                status = "no_change"
                detail = "LangMem retained the accepted profile unchanged"
        except (TypeError, ValueError) as exc:
            status = "invalid_payload"
            detail = str(exc)
    current_id = chain.current.memory_id if chain.current is not None else None
    accepted_id = (
        artifact.memory_id
        if artifact is not None and status in {"accepted", "no_change"}
        else None
    )
    retained_id = (
        current_id
        if status not in {"accepted", "no_change"} or status == "no_change"
        else None
    )
    return artifact, MemoryAttempt(
        attempt_id=attempt_id,
        logical_update_id=logical_id,
        attempt_index=attempt_index,
        repair_of_attempt_id=repair_of_attempt_id,
        domain_id=domain.domain_id,
        case_id=domain.corpus.case_id(chain.spec.case),
        condition_id=chain.spec.condition_id,
        block_index=update.block_index,
        writer_run_id=chain.spec.run_id,
        writer_seed=chain.spec.writer_seed,
        architecture=chain.spec.architecture,
        writer=writer,
        parent_memory_id=current_id,
        status=status,
        detail=detail,
        raw_arguments=invocation.raw_arguments,
        accepted_memory_id=accepted_id,
        retained_memory_id=retained_id,
        memory_implementation_hash=chain.framework[
            "memory_implementation_hash"
        ],
        profile_id=chain.profile_id,
        profile_schema_id=_profile_schema_id(domain, chain.spec.architecture),
        payload_schema_id=(
            domain.memory.payload_schema_id
            if chain.spec.architecture is MemoryArchitecture.TYPED
            else None
        ),
        payload_schema_version=(
            TYPED_MEMORY_PAYLOAD_SCHEMA_VERSION
            if chain.spec.architecture is MemoryArchitecture.TYPED
            else None
        ),
        framework_run_ids=invocation.run_ids,
        framework=dict(chain.framework),
        candidate_payload=candidate,
        changed=changed,
        presentation_id=chain.spec.presentation_id,
        presentation_hash=chain.spec.presentation_hash,
    )


def _validate_payload(
    domain: AuthorizationMemoryDomain,
    chain: _ActiveChain,
    update: WriterUpdateSpec,
    payload: str | Mapping[str, Any],
    *,
    capacity_tokens: int,
    enforce_capacity: bool,
    token_counter: TokenCounter | None,
) -> str | dict[str, Any]:
    if chain.spec.architecture is MemoryArchitecture.FREE_TEXT:
        if not isinstance(payload, str):
            raise ValueError("free-text profile content must be a string")
        unknown = sorted(
            domain.memory.referenced_source_ids_in_free_text(payload)
            - update.visible_source_ids
        )
        validated: str | dict[str, Any] = payload
    else:
        if not isinstance(payload, Mapping):
            raise ValueError("typed profile payload must be an object")
        state = domain.memory.parse_typed(payload)
        unknown = sorted(
            domain.memory.referenced_source_ids(state) - update.visible_source_ids
        )
        validated = dict(domain.memory.serialize_typed(state))
    if unknown:
        raise ValueError(
            "source_turn_ids were not visible to the writer: "
            + ", ".join(unknown)
        )
    serialized = (
        validated if isinstance(validated, str) else canonical_json(validated)
    )
    tokens = count_reference_tokens(serialized, token_counter)
    if enforce_capacity and tokens > capacity_tokens:
        raise ValueError(
            f"candidate uses {tokens} reference tokens; capacity is {capacity_tokens}"
        )
    return validated


def _artifact(
    domain: AuthorizationMemoryDomain,
    chain: _ActiveChain,
    block_index: int,
    payload: str | Mapping[str, Any],
    *,
    writer: ModelProvenance | None = None,
    source_attempt_id: str | None = None,
    framework_run_ids: tuple[str, ...] = (),
    capacity_tokens: int,
    enforce_capacity: bool = True,
    token_counter: TokenCounter | None,
) -> MemoryArtifact:
    effective_writer = writer or chain.writer
    serialized = payload if isinstance(payload, str) else canonical_json(payload)
    tokens = count_reference_tokens(serialized, token_counter)
    if enforce_capacity and tokens > capacity_tokens:
        raise ValueError(
            f"candidate uses {tokens} reference tokens; capacity is {capacity_tokens}"
        )
    digest = content_hash(payload)
    parent_id = chain.current.memory_id if chain.current is not None else None
    memory_id = _stable_id(
        "mem",
        chain.chain_id,
        parent_id or "",
        str(block_index),
        digest,
    )
    typed = chain.spec.architecture is MemoryArchitecture.TYPED
    return MemoryArtifact(
        memory_id=memory_id,
        parent_memory_id=parent_id,
        chain_id=chain.chain_id,
        domain_id=domain.domain_id,
        case_id=domain.corpus.case_id(chain.spec.case),
        condition_id=chain.spec.condition_id,
        block_index=block_index,
        writer_run_id=chain.spec.run_id,
        writer_seed=chain.spec.writer_seed,
        writer=effective_writer,
        architecture=chain.spec.architecture,
        origin=MemoryOrigin.WRITER,
        payload_schema_id=domain.memory.payload_schema_id if typed else None,
        payload_schema_version=(
            str(payload.get("schema_version", "3"))
            if typed and isinstance(payload, Mapping)
            else None
        ),
        payload=payload if isinstance(payload, str) else dict(payload),
        reference_tokens=tokens,
        reference_tokenizer=reference_tokenizer_name(token_counter),
        content_hash=digest,
        memory_implementation_id=LANGMEM_IMPLEMENTATION_ID,
        memory_implementation_hash=chain.framework[
            "memory_implementation_hash"
        ],
        profile_id=chain.profile_id,
        source_attempt_id=source_attempt_id,
        framework_run_ids=framework_run_ids,
        framework=dict(chain.framework),
        presentation_id=chain.spec.presentation_id,
        presentation_hash=chain.spec.presentation_hash,
    )


def _state_after_update(
    chain: _ActiveChain,
    update: WriterUpdateSpec,
    attempts: Sequence[MemoryAttempt],
) -> MemoryState:
    last = attempts[-1]
    changed = any(attempt.changed is True for attempt in attempts)
    status = last.status
    if status not in {"accepted", "no_change"} and chain.current is not None:
        status = "retained_after_failed_update"
    return MemoryState(
        state_id=_stable_id("state", last.logical_update_id),
        logical_update_id=last.logical_update_id,
        attempt_ids=tuple(attempt.attempt_id for attempt in attempts),
        domain_id=last.domain_id,
        case_id=last.case_id,
        condition_id=last.condition_id,
        block_index=update.block_index,
        writer_run_id=last.writer_run_id,
        writer_seed=last.writer_seed,
        architecture=last.architecture,
        profile_id=chain.profile_id,
        current_memory_id=(
            chain.current.memory_id if chain.current is not None else None
        ),
        status=status,
        changed=changed,
        memory_implementation_hash=last.memory_implementation_hash,
        presentation_id=last.presentation_id,
        presentation_hash=last.presentation_hash,
    )


def _profile_from_current(
    domain: AuthorizationMemoryDomain,
    chain: _ActiveChain,
) -> BaseModel:
    if chain.spec.architecture is MemoryArchitecture.FREE_TEXT:
        content = (
            chain.current.payload
            if chain.current is not None
            else ""
        )
        if not isinstance(content, str):
            raise TypeError("free-text memory artifact contains a non-string payload")
        return LangMemTextProfile(content=content)
    if chain.current is None:
        state = domain.memory.empty_typed()
    else:
        if not isinstance(chain.current.payload, Mapping):
            raise TypeError("typed memory artifact contains a non-object payload")
        state = domain.memory.parse_typed(chain.current.payload)
    return domain.memory.to_typed_profile(state)


def _payload_from_profile(
    domain: AuthorizationMemoryDomain,
    architecture: MemoryArchitecture,
    profile: BaseModel,
) -> str | dict[str, Any]:
    if architecture is MemoryArchitecture.FREE_TEXT:
        if not isinstance(profile, LangMemTextProfile):
            raise TypeError("LangMem returned the wrong free-text profile type")
        return profile.content
    if not isinstance(profile, domain.memory.typed_profile_model):
        raise TypeError("LangMem returned the wrong typed profile type")
    return dict(domain.memory.from_typed_profile(profile))


def _profile_schema_id(
    domain: AuthorizationMemoryDomain,
    architecture: MemoryArchitecture,
) -> str:
    schema = (
        LangMemTextProfile
        if architecture is MemoryArchitecture.FREE_TEXT
        else domain.memory.typed_profile_model
    )
    return f"{schema.__module__}.{schema.__qualname__}"


def _empty_payload(
    domain: AuthorizationMemoryDomain,
    architecture: MemoryArchitecture,
) -> str | dict[str, Any]:
    if architecture is MemoryArchitecture.FREE_TEXT:
        return ""
    return dict(domain.memory.serialize_typed(domain.memory.empty_typed()))


def _manager_instructions(
    domain: AuthorizationMemoryDomain,
    chain: _ActiveChain,
    capacity_tokens: int,
    repair_detail: str | None,
) -> str:
    return manager_instructions(
        domain,
        case=chain.spec.case,
        architecture=chain.spec.architecture,
        capacity_tokens=capacity_tokens,
        repair_detail=repair_detail,
        presentation_id=chain.spec.presentation_id,
        profile_id=chain.profile_id,
        instruction_prefix=chain.spec.instruction_prefix,
    )


def _repair_feedback(attempt: MemoryAttempt) -> str:
    parts = [attempt.detail]
    raw_arguments = attempt.raw_arguments
    if isinstance(raw_arguments, Mapping):
        rejected_arguments = raw_arguments.get("args", raw_arguments)
        if isinstance(rejected_arguments, Mapping):
            parts.append(
                "The exact rejected PatchDoc arguments were:\n"
                f"{canonical_json(rejected_arguments)}\n"
                "Make the smallest schema-valid correction. Do not repeat the rejected "
                "arguments unchanged."
            )
    return "\n\n".join(part for part in parts if part)


def manager_instructions(
    domain: AuthorizationMemoryDomain,
    *,
    case: Any,
    architecture: MemoryArchitecture,
    capacity_tokens: int,
    repair_detail: str | None,
    presentation_id: str,
    profile_id: str,
    instruction_prefix: str | None = None,
) -> str:
    """Build benchmark-owned LangMem instructions for one logical update."""

    presentation = domain.get_presentation(presentation_id)
    policy = domain.get_prompt_policy(presentation)
    fixed_context = policy.context_builder(case)
    if instruction_prefix is not None and (
        not instruction_prefix.strip()
        or instruction_prefix != instruction_prefix.strip()
        or "\n" in instruction_prefix
    ):
        raise ValueError(
            "writer instruction prefix must be one non-empty trimmed paragraph"
        )
    parts = [
        *((instruction_prefix,) if instruction_prefix is not None else ()),
        "Maintain exactly one persistent profile containing current authorization state.",
        "Update the existing profile from the supplied information; do not create another profile.",
        profile_identity_instruction(profile_id),
        policy.writer_state_instruction,
    ]
    if policy.writer_inference_instruction is not None:
        parts.append(policy.writer_inference_instruction)
    parts.append(policy.writer_source_instruction)
    if policy.use_domain_writer_instructions:
        parts.append(domain.memory.writer_instructions(architecture))
    parts.append(
        FREE_TEXT_VALUE_INSTRUCTION
        if architecture is MemoryArchitecture.FREE_TEXT
        else TYPED_VALUE_INSTRUCTION
    )
    if (
        architecture is MemoryArchitecture.TYPED
        and policy.split_nested_array_patches
    ):
        parts.append(NESTED_ARRAY_PATCH_INSTRUCTION)
    architecture_instruction = policy.writer_architecture_instructions.get(
        architecture.value
    )
    if architecture_instruction:
        parts.append(architecture_instruction)
    if (
        architecture is MemoryArchitecture.TYPED
        and policy.expose_typed_schema
    ):
        parts.append(
            "Exact typed profile JSON Schema:\n"
            + canonical_json(domain.memory.typed_schema())
        )
    parts.extend(
        (
            (
                f"The serialized profile must fit within {capacity_tokens} "
                "reference tokens."
            ),
            "Domain context: " + canonical_json(fixed_context),
        )
    )
    if repair_detail is not None:
        parts.append(
            policy.writer_repair_instruction
            + (
                "Correct this issue while updating the same accepted profile: "
                f"{repair_detail}"
            )
        )
    return "\n\n".join(parts)


def _freeze(artifact: MemoryArtifact, memory_run_id: int) -> FrozenEvidence:
    evidence_id = _stable_id(
        "evidence",
        artifact.domain_id,
        artifact.case_id,
        artifact.condition_id,
        str(memory_run_id),
        artifact.memory_id,
    )
    return FrozenEvidence(
        evidence_id=evidence_id,
        domain_id=artifact.domain_id,
        case_id=artifact.case_id,
        condition_id=artifact.condition_id,
        memory_run_id=memory_run_id,
        writer_seed=artifact.writer_seed,
        writer=artifact.writer,
        architecture=artifact.architecture,
        memory_id=artifact.memory_id,
        payload=artifact.payload,
        source_history=None,
        content_hash=artifact.content_hash,
        memory_implementation_id=artifact.memory_implementation_id,
        memory_implementation_hash=artifact.memory_implementation_hash,
        profile_id=artifact.profile_id,
        source_attempt_id=artifact.source_attempt_id,
        presentation_id=artifact.presentation_id,
        presentation_hash=artifact.presentation_hash,
    )


def _writer_model_contexts(
    callback: LangChainCallLogger,
    domain: AuthorizationMemoryDomain,
    chain: _ActiveChain,
    update: WriterUpdateSpec,
    attempt: MemoryAttempt,
    invocation: _Invocation,
    *,
    terminal_attempt: bool,
) -> list[ModelContext]:
    contexts: list[ModelContext] = []
    records = callback.records_by_run_id
    for framework_run_id in invocation.run_ids:
        record = records.get(framework_run_id)
        if not isinstance(record, Mapping):
            raise ValueError(
                f"missing LangChain call record for framework run {framework_run_id}"
            )
        request = record.get("request")
        if not isinstance(request, Mapping):
            raise ValueError(
                f"missing LangChain request for framework run {framework_run_id}"
            )
        messages = request.get("messages")
        if not isinstance(messages, list) or not all(
            isinstance(message, Mapping) for message in messages
        ):
            raise ValueError(
                f"LangChain request {framework_run_id} has no single message sequence"
            )
        raw_tools = request.get("tools")
        tools = (
            tuple(dict(tool) for tool in raw_tools)
            if isinstance(raw_tools, list)
            and all(isinstance(tool, Mapping) for tool in raw_tools)
            else ()
        )
        params = request.get("params")
        tool_choice = request.get("tool_choice")
        if tool_choice is None and isinstance(params, Mapping):
            tool_choice = params.get("tool_choice")
        hash_input = {
            "messages": [dict(message) for message in messages],
            "tools": list(tools),
            "tool_choice": tool_choice,
        }
        digest = content_hash(hash_input)
        call_id = record.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            call_id = _stable_id("call", attempt.attempt_id, framework_run_id)
        model = replace(
            attempt.writer,
            response_model=(
                str(record["response_model"])
                if record.get("response_model")
                else attempt.writer.response_model
            ),
        )
        if not tools:
            raise ValueError(
                f"LangChain request {framework_run_id} has no normalized tools"
            )
        context = ModelContext(
            context_id=_stable_id(
                "context",
                call_id,
                framework_run_id,
                digest,
            ),
            content_hash=digest,
            stage="writer",
            domain_id=attempt.domain_id,
            case_id=attempt.case_id,
            condition_id=attempt.condition_id,
            block_index=attempt.block_index,
            probe_id=None,
            writer_run_id=attempt.writer_run_id,
            executor_run_id=None,
            memory_id=(
                attempt.accepted_memory_id or attempt.retained_memory_id
            ),
            memory_attempt_id=attempt.attempt_id,
            evidence_id=None,
            trial_id=None,
            call_id=call_id,
            framework_run_id=framework_run_id,
            messages=tuple(dict(message) for message in messages),
            tools=tools,
            tool_choice=tool_choice,
            model=model,
            presentation_id=attempt.presentation_id,
            presentation_hash=attempt.presentation_hash,
            metadata={
                "logical_update_id": attempt.logical_update_id,
                "attempt_index": attempt.attempt_index,
                "terminal_attempt": terminal_attempt,
                "status": attempt.status,
                "accepted_memory_id": attempt.accepted_memory_id,
                "retained_memory_id": attempt.retained_memory_id,
                "parent_memory_id": attempt.parent_memory_id,
                "repair_of_attempt_id": attempt.repair_of_attempt_id,
                "profile_id": attempt.profile_id,
                "input_kind": update.input_kind,
                "architecture": chain.spec.architecture.value,
                "response_model": record.get("response_model"),
                "error": record.get("error"),
                **(
                    {
                        "deterministic_session_id": _deterministic_session_id(
                            chain,
                            update,
                            attempt.attempt_index,
                        )
                    }
                    if chain.spec.deterministic_session_ids
                    else {}
                ),
                **dict(chain.spec.metadata),
            },
        )
        validate_model_context_leakage(
            domain,
            chain.spec.case,
            context,
            registered_instruction_prefix=chain.spec.instruction_prefix,
        )
        contexts.append(context)
    return contexts


def _single_response_model(observation: Mapping[str, Any]) -> str | None:
    models = {
        str(model)
        for model in observation.get("response_models", ())
        if model
    }
    return next(iter(models)) if len(models) == 1 else None


def _raw_underlying_tool_call(
    callback: LangChainCallLogger,
    observation: Mapping[str, Any],
) -> Any:
    calls: list[Any] = []
    for run_id in observation.get("run_ids", ()):
        record = callback.records_by_run_id.get(str(run_id))
        response = record.get("response") if isinstance(record, Mapping) else None
        if not isinstance(response, Mapping):
            continue
        for key in ("tool_calls", "invalid_tool_calls"):
            values = response.get(key)
            if isinstance(values, list):
                calls.extend(
                    dict(call) if isinstance(call, Mapping) else call
                    for call in values
                )
    if len(calls) == 1:
        return calls[0]
    return calls or None


def _validate_underlying_call(
    callback: LangChainCallLogger,
    observation: Mapping[str, Any],
    *,
    profile_id: str,
    existing_profile: BaseModel,
    returned_profile: BaseModel,
) -> None:
    run_ids = tuple(observation.get("run_ids", ()))
    if len(run_ids) != 1:
        raise ValueError(
            "LangMem update made "
            f"{len(run_ids)} underlying model calls; expected exactly one"
        )
    record = callback.records_by_run_id.get(str(run_ids[0]))
    if record is None:
        raise ValueError("LangMem call-log record is missing")
    if record.get("error"):
        raise ValueError(f"LangMem model call failed: {record['error']}")
    response = record.get("response")
    tool_calls = (
        response.get("tool_calls")
        if isinstance(response, Mapping)
        else None
    )
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        count = len(tool_calls) if isinstance(tool_calls, list) else 0
        raise ValueError(
            f"LangMem model made {count} tool calls; expected one PatchDoc call"
        )
    call = tool_calls[0]
    if not isinstance(call, Mapping) or call.get("name") != "PatchDoc":
        name = call.get("name") if isinstance(call, Mapping) else None
        raise ValueError(
            f"LangMem model called {name!r}; expected 'PatchDoc'"
        )
    arguments = call.get("args")
    if not isinstance(arguments, Mapping):
        raise ValueError("LangMem PatchDoc arguments must be an object")
    if arguments.get("json_doc_id") != profile_id:
        raise ValueError(
            "LangMem PatchDoc targeted the wrong profile: "
            f"{arguments.get('json_doc_id')!r}"
        )
    if not isinstance(arguments.get("planned_edits"), str):
        raise ValueError("LangMem PatchDoc is missing planned_edits")
    patches = arguments.get("patches")
    if not isinstance(patches, list):
        raise ValueError("LangMem PatchDoc patches must be a list")
    normalized_patches = _validate_patch_operations(patches)
    existing = existing_profile.model_dump(mode="json")
    expected = _apply_patch(existing, normalized_patches)
    try:
        normalized_expected = type(existing_profile).model_validate(expected)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"LangMem PatchDoc produced an invalid profile: {exc}") from exc
    if (
        normalized_expected.model_dump(mode="json")
        != returned_profile.model_dump(mode="json")
    ):
        raise ValueError(
            "LangMem did not apply the recorded PatchDoc to the returned profile"
        )


def _validate_patch_operations(
    patches: Sequence[Any],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, patch in enumerate(patches):
        if not isinstance(patch, Mapping):
            raise ValueError(f"LangMem patch {index} must be an object")
        operation = patch.get("op")
        if operation not in {"add", "remove", "replace"}:
            raise ValueError(
                f"LangMem patch {index} has unsupported operation {operation!r}"
            )
        path = patch.get("path")
        if not isinstance(path, str):
            raise ValueError(f"LangMem patch {index} path must be a string")
        normalized_patch = {"op": operation, "path": path}
        if operation != "remove":
            if "value" not in patch:
                raise ValueError(
                    f"LangMem patch {index} operation {operation!r} requires value"
                )
            normalized_patch["value"] = patch["value"]
        normalized.append(normalized_patch)
    return normalized


def _apply_patch(
    document: Mapping[str, Any],
    patches: Sequence[Mapping[str, Any]],
) -> Any:
    normalized_document = dict(document)
    try:
        return jsonpatch.apply_patch(
            normalized_document,
            list(patches),
            in_place=False,
        )
    except jsonpatch.JsonPatchConflict as exc:
        fixed = _fix_string_append_patches(normalized_document, patches)
        if fixed is None:
            raise ValueError(f"LangMem PatchDoc could not be applied: {exc}") from exc
        try:
            return jsonpatch.apply_patch(
                normalized_document,
                fixed,
                in_place=False,
            )
        except (jsonpatch.JsonPatchException, jsonpointer.JsonPointerException) as inner:
            raise ValueError(
                f"LangMem PatchDoc could not be applied: {inner}"
            ) from inner
    except (jsonpatch.JsonPatchException, jsonpointer.JsonPointerException) as exc:
        raise ValueError(f"LangMem PatchDoc could not be applied: {exc}") from exc


def _fix_string_append_patches(
    document: Mapping[str, Any],
    patches: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]] | None:
    fixed = False
    result: list[dict[str, Any]] = []
    for patch in patches:
        path = str(patch["path"])
        if path.endswith("/-"):
            target_path = path[:-2]
            try:
                existing = jsonpointer.resolve_pointer(document, target_path)
            except jsonpointer.JsonPointerException:
                existing = None
            if isinstance(existing, str):
                fixed = True
                result.append(
                    {
                        "op": "replace",
                        "path": target_path,
                        "value": existing + str(patch.get("value", "")),
                    }
                )
                continue
        result.append(dict(patch))
    return result if fixed else None


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _stable_id(prefix: str, *parts: str) -> str:
    import hashlib

    payload = "\0".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def _logical_update_id(
    chain: _ActiveChain,
    update: WriterUpdateSpec,
) -> str:
    parts = [chain.chain_id, str(update.block_index)]
    if chain.spec.artifact_instance_id != "default":
        parts.append(chain.spec.artifact_instance_id)
    return _stable_id("update", *parts)


def _deterministic_session_id(
    chain: _ActiveChain,
    update: WriterUpdateSpec,
    attempt_index: int,
) -> str:
    attempt_kind = "initial" if attempt_index == 1 else "repair"
    identity = "\0".join(
        (
            chain.chain_id,
            str(update.block_index),
            attempt_kind,
            str(attempt_index),
        )
    )
    return str(uuid.uuid5(uuid.NAMESPACE_OID, identity))


def _install_deterministic_session_id(manager: Any, session_id: str) -> None:
    prepare_messages = manager._prepare_messages

    def prepare_with_stable_session(
        messages: list[Any],
        max_steps: int = 1,
    ) -> list[dict[str, Any]]:
        prepared = prepare_messages(messages, max_steps)
        if len(prepared) != 2 or not isinstance(prepared[1], Mapping):
            raise ValueError("LangMem prepared an unexpected message surface")
        content = prepared[1].get("content")
        if not isinstance(content, str):
            raise ValueError("LangMem prepared instructions without text content")
        opening = re.findall(r"<session_([^>]+)>", content)
        closing = re.findall(r"</session_([^>]+)>", content)
        if len(opening) != 1 or closing != opening:
            raise ValueError("LangMem prepared an unexpected session envelope")
        random_id = opening[0]
        stable_content = content.replace(
            f"<session_{random_id}>",
            f"<session_{session_id}>",
            1,
        ).replace(
            f"</session_{random_id}>",
            f"</session_{session_id}>",
            1,
        )
        normalized = [dict(message) for message in prepared]
        normalized[1]["content"] = stable_content
        return normalized

    manager._prepare_messages = prepare_with_stable_session


def _require_unique(values: Sequence[str] | Any, label: str) -> None:
    materialized = list(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"{label} identifiers are not unique")
