from __future__ import annotations

import ast
import json
import re
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from eal_bench.llm import LLM, load_config

from domains.base import AuthorizationMemoryDomain, MemoryArchitecture

from .conditions import CONDITION_SPECS
from .langmem_writer import (
    WriterChainSpec,
    WriterUpdateSpec,
    memory_implementation_manifest,
    run_writer_chains,
    validate_writer_timeout_guard,
)
from .leakage import validate_model_context_leakage
from .pipeline import run_core
from .persistence import canonical_json, content_hash, file_hash, write_json, write_jsonl
from .schemas import (
    LANGMEM_IMPLEMENTATION_ID,
    TRIAL_SCHEMA_VERSION,
    TYPED_MEMORY_PAYLOAD_SCHEMA_VERSION,
)
from .tokens import count_reference_tokens


class OfflineLLM:
    """Deterministic provider and LangChain validation double."""

    def __init__(self, *, typed_payload: dict[str, Any] | None = None) -> None:
        self.offline = True
        self.config = load_config(load_env=False)
        self.logger = _NullLogger()
        self._router = LLM(config=self.config, logger=self.logger)
        self.targets: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.preflights: list[dict[str, Any]] = []
        self.typed_payload = typed_payload

    def langchain_model_factory(
        self,
        config: Any,
        task: str,
        target: str,
        *,
        seed: int,
        callbacks: tuple[Any, ...],
        required_capabilities: tuple[str, ...],
        require_api_key: bool,
        parameter_overrides: dict[str, Any],
    ) -> tuple[BaseChatModel, Any, dict[str, Any]]:
        if require_api_key:
            raise AssertionError("offline LangChain construction resolved credentials")
        base_route = self.preflight(
            task,
            target=target,
            required_capabilities=required_capabilities,
            require_api_key=False,
        )
        model_override = parameter_overrides.get("model")
        route = (
            base_route
            if model_override is None
            else config.resolve_target(task, model=str(model_override))
        )
        if route.target_id != base_route.target_id:
            raise AssertionError("offline compatibility override changed model target")
        params = {
            **config.task(task).params,
            **parameter_overrides,
            "seed": seed,
        }
        params.pop("model", None)
        model = _OfflinePatchModel(
            target_id=target,
            typed_payload=self.typed_payload,
            callbacks=list(callbacks),
            metadata={
                "eal_transport": "langchain",
                "eal_task": task,
                "eal_target_id": route.target_id,
                "eal_provider": route.provider,
                "eal_requested_model": route.requested_model,
                "eal_resolved_model": route.resolved_model,
                "eal_effective_params": params,
            },
        )
        return model, route, params

    def preflight(
        self,
        task: str,
        *,
        target: str,
        required_capabilities: tuple[str, ...],
        require_api_key: bool = False,
        **kwargs: Any,
    ) -> Any:
        del kwargs
        if require_api_key:
            raise AssertionError("offline validation must not resolve credentials")
        self.preflights.append(
            {
                "task": task,
                "target": target,
                "required_capabilities": sorted(required_capabilities),
            }
        )
        return self._router.preflight(
            task,
            target=target,
            required_capabilities=required_capabilities,
            require_api_key=False,
        )

    def batch(
        self,
        task: str,
        messages: list[list[dict[str, str]]],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        target = kwargs["target"]
        self.targets.extend([target] * len(messages))
        self.calls.append(
            {
                "task": task,
                "target": target,
                "count": len(messages),
                "parameters": {
                    key: value
                    for key, value in kwargs.items()
                    if key
                    not in {
                        "tools",
                        "target",
                        "return_exceptions",
                        "batch_size",
                    }
                },
            }
        )
        tools = kwargs["tools"]
        if task == "writer":
            raise AssertionError("the active writer must run through LangMem")
        decline = next(
            (
                tool
                for tool in tools
                if tool["function"]["name"].startswith("decline")
            ),
            tools[-1],
        )
        tool_name = decline["function"]["name"]
        arguments = {"reason": "offline validation"}
        return [
            {
                "model": f"offline-response/{target}",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(arguments),
                                    }
                                }
                            ],
                        },
                    }
                ],
            }
            for _ in messages
        ]


class _NullLogger:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def log(self, record: dict[str, Any]) -> None:
        self.records.append(record)


class _OfflinePatchModel(BaseChatModel):
    target_id: str
    typed_payload: dict[str, Any] | None = None

    @property
    def _llm_type(self) -> str:
        return "offline-langmem-patch"

    def bind_tools(
        self,
        tools: Any,
        *,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.bind(tools=tools, tool_choice=tool_choice, **kwargs)

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        transcript = "\n".join(str(message.content) for message in messages)
        profile_ids = re.findall(r"(profile_[a-f0-9]{24})", transcript)
        if not profile_ids:
            profile_ids = re.findall(r"([0-9a-f]{8}-[0-9a-f-]{27,})", transcript)
        if not profile_ids:
            raise ValueError("offline model could not locate the existing profile ID")
        repaired = any(
            marker in transcript
            for marker in (
                "previous candidate was rejected",
                "previous update did not meet",
                "exact rejected PatchDoc arguments",
            )
        )
        patches: list[dict[str, Any]] = []
        planned_edits = "Apply the deterministic offline validation update."
        if "OFFLINE_TYPED_CHANGE" in transcript:
            if self.typed_payload is None:
                raise ValueError("offline typed change has no scripted payload")
            patches = [
                {
                    "op": "replace",
                    "path": "",
                    "value": self.typed_payload,
                }
            ]
        elif "OFFLINE_OVERFLOW_THEN_REPAIR" in transcript:
            value = "repaired profile" if repaired else "overflow " * 2000
            patches = [{"op": "replace", "path": "/content", "value": value}]
        elif "OFFLINE_ALWAYS_OVERFLOW" in transcript:
            patches = [
                {
                    "op": "replace",
                    "path": "/content",
                    "value": "overflow " * 2000,
                }
            ]
        elif "OFFLINE_UNKNOWN_SOURCE_THEN_REPAIR" in transcript:
            value = (
                "repaired profile"
                if repaired
                else "Authorization cited by src_never_visible_999."
            )
            patches = [{"op": "replace", "path": "/content", "value": value}]
        elif "OFFLINE_INVALID_PATCH_THEN_REPAIR" in transcript:
            patches = [
                {
                    "op": "replace",
                    "path": "/content" if repaired else "/missing_field",
                    "value": "repaired after malformed patch",
                }
            ]
        else:
            content_match = re.search(
                r"OFFLINE_CONTENT_START(.*?)OFFLINE_CONTENT_END",
                transcript,
                re.DOTALL,
            )
            if content_match:
                patches = [
                    {
                        "op": "replace",
                        "path": "/content",
                        "value": content_match.group(1).strip(),
                    }
                ]
        tool_call = {
            "name": "PatchDoc",
            "args": {
                "json_doc_id": profile_ids[0],
                "planned_edits": planned_edits,
                "patches": patches,
            },
            "id": f"offline_{self.target_id}",
            "type": "tool_call",
        }
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[tool_call],
                        response_metadata={
                            "model_name": f"offline-response/{self.target_id}",
                            "finish_reason": "tool_calls",
                            "token_usage": {
                                "prompt_tokens": 10,
                                "completion_tokens": 5,
                                "total_tokens": 15,
                            },
                        },
                    )
                )
            ],
            llm_output={
                "model_name": f"offline-response/{self.target_id}",
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )


def validate_mixed_target_core(
    domain: AuthorizationMemoryDomain,
    *,
    corpus_version: str,
    include_writer_behaviors: bool = True,
) -> dict[str, Any]:
    llm = OfflineLLM()
    cases = tuple(domain.corpus.load_cases(corpus_version))
    artifacts = run_core(
        llm,
        domain,
        cases,
        corpus_version=corpus_version,
        writer_task="writer",
        executor_task="executor",
        writer_targets=("gptoss_baseten", "gptoss_openrouter"),
        executor_targets=("gptoss_baseten", "gptoss_openrouter"),
        writer_runs=1,
        executor_runs=1,
        writer_max_attempts=2,
        seed=0,
    )
    trial_targets = {
        (
            trial.writer.target_id if trial.writer is not None else None,
            trial.executor.target_id,
        )
        for trial in artifacts.trials
    }
    expected_executor_targets = {"gptoss_baseten", "gptoss_openrouter"}
    if {target for _, target in trial_targets} != expected_executor_targets:
        raise AssertionError("mixed executor targets were not preserved")
    expected_writer_targets = {"gptoss_baseten", "gptoss_openrouter"}
    observed_writer_targets = {
        target for target, _ in trial_targets if target is not None
    }
    if observed_writer_targets != expected_writer_targets:
        raise AssertionError("mixed writer targets were not preserved")
    observed_matrix = {
        (writer, executor)
        for writer, executor in trial_targets
        if writer is not None
    }
    expected_matrix = {
        (writer, executor)
        for writer in expected_writer_targets
        for executor in expected_executor_targets
    }
    if observed_matrix != expected_matrix:
        raise AssertionError("writer/executor target matrix is incomplete")
    if any(
        trial.to_dict()["schema_version"] != TRIAL_SCHEMA_VERSION
        for trial in artifacts.trials
    ):
        raise AssertionError("generic trials did not serialize as schema v5")
    if any(
        "seed" not in preflight["required_capabilities"]
        for preflight in llm.preflights
    ):
        raise AssertionError("seed capability was not checked during preflight")
    _validate_artifact_provenance(llm, domain, artifacts)
    writer_behaviors = (
        validate_langmem_writer_behaviors(
            domain,
            corpus_version=corpus_version,
        )
        if include_writer_behaviors
        else None
    )
    control_only = _validate_control_only_without_writer_target(
        domain,
        corpus_version=corpus_version,
    )
    round_trip = _validate_v5_round_trip(domain, artifacts, llm)
    return {
        "status": "passed",
        "domain_id": domain.domain_id,
        "memory_count": len(artifacts.memories),
        "attempt_count": len(artifacts.attempts),
        "evidence_count": len(artifacts.evidence),
        "trial_count": len(artifacts.trials),
        "model_context_count": len(artifacts.model_contexts),
        "executor_targets": sorted(expected_executor_targets),
        "writer_targets": sorted(expected_writer_targets),
        "writer_executor_matrix_size": len(observed_matrix),
        "trial_schema_version": TRIAL_SCHEMA_VERSION,
        "control_only_without_writer_target": control_only,
        "round_trip": round_trip,
        **(
            {"langmem_writer_behaviors": writer_behaviors}
            if writer_behaviors is not None
            else {}
        ),
    }


def validate_langmem_writer_behaviors(
    domain: AuthorizationMemoryDomain,
    *,
    corpus_version: str,
) -> dict[str, Any]:
    """Exercise the bounded deterministic writer contract for one domain."""

    return _validate_langmem_writer_behaviors(
        domain,
        corpus_version=corpus_version,
    )


def _validate_langmem_writer_behaviors(
    domain: AuthorizationMemoryDomain,
    *,
    corpus_version: str,
) -> dict[str, Any]:
    cases = tuple(domain.corpus.load_cases(corpus_version))
    case = cases[0]
    blocks = tuple(domain.corpus.blocks(case))
    target = "gptoss_baseten"

    def update(
        block_index: int,
        content: str,
        *,
        visible: frozenset[str] | None = None,
        kind: str = "new_conversation_block",
    ) -> WriterUpdateSpec:
        return WriterUpdateSpec(
            block_index=block_index,
            messages=({"role": "user", "content": content},),
            visible_source_ids=(
                domain.corpus.source_turn_ids(
                    case,
                    through_block_index=block_index,
                )
                if visible is None
                else visible
            ),
            input_kind=kind,
        )

    incremental_llm = OfflineLLM()
    incremental = run_writer_chains(
        incremental_llm,
        domain,
        (
            WriterChainSpec(
                case=case,
                condition_id="incremental_text",
                architecture=MemoryArchitecture.FREE_TEXT,
                run_id=0,
                writer_seed=0,
                target_id=target,
                presentation_id=domain.default_presentation_id,
                updates=(
                    update(
                        _block_index_for_validation(blocks[0], 0),
                        (
                            "FIRST_BLOCK_TRANSCRIPT_ONLY "
                            "OFFLINE_CONTENT_START accepted alpha "
                            "OFFLINE_CONTENT_END"
                        ),
                    ),
                    update(
                        _block_index_for_validation(blocks[1], 1),
                        "OFFLINE_CONTENT_START accepted alpha beta OFFLINE_CONTENT_END",
                    ),
                ),
            ),
        ),
        writer_task="writer",
        max_attempts=2,
        capacity_tokens=100,
        batch_size=2,
    )
    if len(incremental.states) != 2 or len(incremental.attempts) != 2:
        raise AssertionError("incremental LangMem updates were not recorded atomically")
    if incremental.states[-1].current_memory_id != incremental.memories[-1].memory_id:
        raise AssertionError("incremental state does not point to its accepted profile")
    if incremental.memories[-1].parent_memory_id != incremental.memories[0].memory_id:
        raise AssertionError("incremental LangMem lineage is incomplete")
    second_block_logs = [
        record
        for record in incremental_llm.logger.records
        if record.get("metadata", {}).get("block_index")
        == _block_index_for_validation(blocks[1], 1)
    ]
    if len(second_block_logs) != 1:
        raise AssertionError("incremental update did not make exactly one model call")
    second_request = json.dumps(
        second_block_logs[0].get("request"),
        sort_keys=True,
    )
    if "FIRST_BLOCK_TRANSCRIPT_ONLY" in second_request:
        raise AssertionError("incremental writer leaked prior conversation history")

    typed_payload = dict(
        domain.memory.serialize_typed(domain.memory.faithful_typed(case))
    )
    typed_llm = OfflineLLM(typed_payload=typed_payload)
    typed = run_writer_chains(
        typed_llm,
        domain,
        (
            WriterChainSpec(
                case=case,
                condition_id="one_shot_typed",
                architecture=MemoryArchitecture.TYPED,
                run_id=0,
                writer_seed=0,
                target_id=target,
                presentation_id=domain.default_presentation_id,
                updates=(
                    update(
                        _block_index_for_validation(blocks[-1], len(blocks) - 1),
                        "OFFLINE_TYPED_CHANGE",
                        visible=domain.corpus.source_turn_ids(case),
                        kind="full_history",
                    ),
                ),
            ),
        ),
        writer_task="writer",
        max_attempts=2,
        capacity_tokens=max(
            1000,
            count_reference_tokens(canonical_json(typed_payload)),
        ),
        batch_size=1,
    )
    if typed.attempts[0].status != "accepted":
        raise AssertionError("typed LangMem profile update was not accepted")
    typed_state = domain.memory.parse_typed(typed.memories[-1].payload)
    if (
        domain.memory.serialize_typed(typed_state)
        != domain.memory.serialize_typed(domain.memory.faithful_typed(case))
    ):
        raise AssertionError("typed LangMem profile changed during serialization")

    no_change_llm = OfflineLLM()
    no_change = run_writer_chains(
        no_change_llm,
        domain,
        (
            WriterChainSpec(
                case=case,
                condition_id="one_shot_text",
                architecture=MemoryArchitecture.FREE_TEXT,
                run_id=0,
                writer_seed=0,
                target_id=target,
                presentation_id=domain.default_presentation_id,
                updates=(
                    update(
                        _block_index_for_validation(blocks[-1], len(blocks) - 1),
                        "OFFLINE_NO_CHANGE",
                        visible=domain.corpus.source_turn_ids(case),
                        kind="full_history",
                    ),
                ),
            ),
        ),
        writer_task="writer",
        max_attempts=2,
        capacity_tokens=100,
        batch_size=1,
    )
    if no_change.attempts[0].status != "no_change":
        raise AssertionError("valid unchanged LangMem profile was treated as an error")

    compatibility_routes = run_writer_chains(
        OfflineLLM(),
        domain,
        tuple(
            WriterChainSpec(
                case=case,
                condition_id="one_shot_text",
                architecture=MemoryArchitecture.FREE_TEXT,
                run_id=0,
                writer_seed=0,
                target_id=target,
                model_override=model_override,
                presentation_id=domain.default_presentation_id,
                updates=(
                    update(
                        _block_index_for_validation(blocks[-1], len(blocks) - 1),
                        "OFFLINE_NO_CHANGE",
                        visible=domain.corpus.source_turn_ids(case),
                        kind="full_history",
                    ),
                ),
            )
            for model_override in ("compatibility/model-a", "compatibility/model-b")
        ),
        writer_task="writer",
        max_attempts=1,
        capacity_tokens=100,
        batch_size=1,
    )
    if len({state.state_id for state in compatibility_routes.states}) != 2:
        raise AssertionError("compatibility model overrides reused LangMem state IDs")

    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO

    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        patch_repaired = _run_scripted_text_chain(
            domain,
            case,
            blocks,
            marker="OFFLINE_INVALID_PATCH_THEN_REPAIR",
            target=target,
            capacity_tokens=100,
            two_updates=False,
        )
    if [attempt.status for attempt in patch_repaired.attempts] != [
        "writer_error",
        "accepted",
    ]:
        raise AssertionError(
            "an unapplied LangMem patch was mistaken for a no-change update"
        )
    rejected_patch_call = patch_repaired.attempts[0].raw_arguments
    if (
        not isinstance(rejected_patch_call, dict)
        or rejected_patch_call.get("name") != "PatchDoc"
        or rejected_patch_call.get("args", {}).get("patches", [{}])[0].get("path")
        != "/missing_field"
    ):
        raise AssertionError("rejected PatchDoc call was not retained verbatim")
    if patch_repaired.attempts[0].candidate_payload is None:
        raise AssertionError("rejected PatchDoc lost LangMem's returned profile")
    repair_contexts = [
        context
        for context in patch_repaired.model_contexts
        if context.memory_attempt_id == patch_repaired.attempts[1].attempt_id
    ]
    rejected_patch_args = rejected_patch_call["args"]
    if len(repair_contexts) != 1 or canonical_json(rejected_patch_args) not in "\n".join(
        str(message.get("content", "")) for message in repair_contexts[0].messages
    ):
        raise AssertionError(
            "logical repair did not receive the exact rejected PatchDoc arguments"
        )
    accepted_patch_call = patch_repaired.attempts[1].raw_arguments
    if (
        not isinstance(accepted_patch_call, dict)
        or accepted_patch_call.get("name") != "PatchDoc"
        or accepted_patch_call.get("args", {}).get("patches", [{}])[0].get("path")
        != "/content"
    ):
        raise AssertionError("accepted repair PatchDoc call was not retained verbatim")

    repaired = _run_scripted_text_chain(
        domain,
        case,
        blocks,
        marker="OFFLINE_OVERFLOW_THEN_REPAIR",
        target=target,
        capacity_tokens=20,
        two_updates=False,
    )
    if [attempt.status for attempt in repaired.attempts] != [
        "invalid_payload",
        "accepted",
    ]:
        raise AssertionError("bounded capacity repair did not succeed on attempt two")

    source_repaired = _run_scripted_text_chain(
        domain,
        case,
        blocks,
        marker="OFFLINE_UNKNOWN_SOURCE_THEN_REPAIR",
        target=target,
        capacity_tokens=100,
        two_updates=False,
    )
    if [attempt.status for attempt in source_repaired.attempts] != [
        "invalid_payload",
        "accepted",
    ]:
        raise AssertionError("source-provenance repair did not succeed on attempt two")

    retained = _run_scripted_text_chain(
        domain,
        case,
        blocks,
        marker="OFFLINE_ALWAYS_OVERFLOW",
        target=target,
        capacity_tokens=20,
        two_updates=True,
    )
    if [attempt.status for attempt in retained.attempts] != [
        "accepted",
        "invalid_payload",
        "invalid_payload",
    ]:
        raise AssertionError("failed repair attempts were not preserved")
    if retained.states[-1].status != "retained_after_failed_update":
        raise AssertionError("failed repair did not retain the accepted profile")
    if retained.states[-1].current_memory_id != retained.memories[0].memory_id:
        raise AssertionError("failed repair mutated the accepted profile")
    timeout_guard = validate_writer_timeout_guard()

    return {
        "status": "passed",
        "prose": True,
        "typed": True,
        "one_shot": True,
        "incremental": True,
        "changed": True,
        "no_change": True,
        "model_override_identity": True,
        "invalid_patch_repair": True,
        "rejected_patch_repair_feedback": True,
        "overflow_repair": True,
        "unknown_source_repair": True,
        "failed_repair_atomic_retention": True,
        "incremental_history_isolation": True,
        "timeout_guard": timeout_guard,
    }


def _run_scripted_text_chain(
    domain: AuthorizationMemoryDomain,
    case: Any,
    blocks: tuple[Any, ...],
    *,
    marker: str,
    target: str,
    capacity_tokens: int,
    two_updates: bool,
) -> Any:
    last_index = _block_index_for_validation(blocks[-1], len(blocks) - 1)
    updates = [
        WriterUpdateSpec(
            block_index=0,
            messages=(
                {
                    "role": "user",
                    "content": (
                        "OFFLINE_CONTENT_START stable accepted profile "
                        "OFFLINE_CONTENT_END"
                    ),
                },
            ),
            visible_source_ids=domain.corpus.source_turn_ids(
                case,
                through_block_index=0,
            ),
            input_kind="new_conversation_block",
        )
    ]
    if two_updates:
        updates.append(
            WriterUpdateSpec(
                block_index=last_index,
                messages=({"role": "user", "content": marker},),
                visible_source_ids=domain.corpus.source_turn_ids(case),
                input_kind="new_conversation_block",
            )
        )
    else:
        updates = [
            WriterUpdateSpec(
                block_index=last_index,
                messages=({"role": "user", "content": marker},),
                visible_source_ids=domain.corpus.source_turn_ids(case),
                input_kind="full_history",
            )
        ]
    return run_writer_chains(
        OfflineLLM(),
        domain,
        (
            WriterChainSpec(
                case=case,
                condition_id=(
                    "incremental_text" if two_updates else "one_shot_text"
                ),
                architecture=MemoryArchitecture.FREE_TEXT,
                run_id=0,
                writer_seed=0,
                target_id=target,
                presentation_id=domain.default_presentation_id,
                updates=tuple(updates),
            ),
        ),
        writer_task="writer",
        max_attempts=2,
        capacity_tokens=capacity_tokens,
        batch_size=1,
    )


def _block_index_for_validation(block: Any, fallback: int) -> int:
    if isinstance(block, dict):
        value = block.get("block_index", fallback)
    else:
        value = getattr(block, "block_index", fallback)
    return int(value)


def _validate_control_only_without_writer_target(
    domain: AuthorizationMemoryDomain,
    *,
    corpus_version: str,
) -> bool:
    from experiments.authorization_memory.runner import _manifest

    llm = OfflineLLM()
    control_conditions = tuple(
        condition.condition_id
        for condition in CONDITION_SPECS
        if not condition.writer_required
    )
    artifacts = run_core(
        llm,
        domain,
        domain.corpus.load_cases(corpus_version),
        corpus_version=corpus_version,
        writer_task="writer",
        executor_task="executor",
        writer_targets=(),
        executor_targets=("gptoss_openrouter",),
        condition_ids=control_conditions,
        writer_runs=1,
        executor_runs=1,
        seed=0,
    )
    if any(call["task"] == "writer" for call in llm.calls):
        raise AssertionError("control-only validation made a writer call")
    if any(preflight["task"] == "writer" for preflight in llm.preflights):
        raise AssertionError("control-only validation preflighted a writer target")
    if any(
        item.memory_implementation_id is not None
        or item.memory_implementation_hash is not None
        for item in (*artifacts.memories, *artifacts.evidence)
    ):
        raise AssertionError("control-only artifacts claim a memory implementation")
    if any(
        trial.metadata.get("core", {}).get("memory_implementation_id")
        is not None
        or trial.metadata.get("core", {}).get("memory_implementation_hash")
        is not None
        for trial in artifacts.trials
    ):
        raise AssertionError("control-only trials claim a memory implementation")
    manifest = _manifest(
        domain,
        config=llm.config,
        corpus_version=corpus_version,
        cases=domain.corpus.load_cases(corpus_version),
        selected_conditions=control_conditions,
        writer_task="writer",
        executor_task="executor",
        writer_targets=(),
        executor_targets=("gptoss_openrouter",),
        writer_runs=1,
        executor_runs=1,
        writer_max_attempts=2,
        capacity_tier="primary",
        batch_size=llm.config.batch_size,
        seed=0,
        command="offline control-only validation",
    )
    if (
        manifest.get("memory_implementation_id") is not None
        or manifest.get("memory_implementation_hash") is not None
        or manifest["writer"].get("active") is not False
        or manifest["writer"].get("memory_implementation_id") is not None
        or manifest["writer"].get("framework") is not None
    ):
        raise AssertionError("control-only manifest claims LangMem")
    return True


def _validate_artifact_provenance(
    llm: OfflineLLM,
    domain: AuthorizationMemoryDomain,
    artifacts: Any,
) -> None:
    implementation_hash = memory_implementation_manifest(domain)[
        "memory_implementation_hash"
    ]
    expected_providers = {
        "gptoss_baseten": "baseten",
        "gptoss_openrouter": "openrouter",
    }
    writer_provenances = [attempt.writer for attempt in artifacts.attempts]
    writer_provenances.extend(
        memory.writer
        for memory in artifacts.memories
        if memory.writer is not None
    )
    writer_provenances.extend(
        trial.writer
        for trial in artifacts.trials
        if trial.writer is not None
    )
    executor_provenances = [trial.executor for trial in artifacts.trials]
    provenances = [*writer_provenances, *executor_provenances]
    if not provenances:
        raise AssertionError("offline validation produced no model provenance")
    for provenance in provenances:
        if provenance.target_id not in expected_providers:
            raise AssertionError("artifact contains an unexpected target")
        route = llm.config.resolve_target(
            "writer",
            target=provenance.target_id,
        )
        if provenance.provider != expected_providers[provenance.target_id]:
            raise AssertionError("artifact provider provenance is incorrect")
        if provenance.requested_model != route.requested_model:
            raise AssertionError("artifact requested model provenance is incorrect")
        if provenance.resolved_model != route.resolved_model:
            raise AssertionError("artifact resolved model provenance is incorrect")
        if provenance.response_model != (
            f"offline-response/{provenance.target_id}"
        ):
            raise AssertionError("artifact response model provenance is missing")
        parameters = provenance.effective_parameters
        if parameters.get("temperature") != 1.0:
            raise AssertionError("effective temperature was not preserved")
        if parameters.get("max_tokens") != 4096:
            raise AssertionError("effective completion limit was not preserved")
        if parameters.get("seed") != 0:
            raise AssertionError("deterministic seed was not preserved")
    for provenance in executor_provenances:
        parameters = provenance.effective_parameters
        if not parameters.get("tool_names"):
            raise AssertionError("executor native tools were not preserved")
        if "seed" not in parameters.get("required_capabilities", []):
            raise AssertionError("executor seed capability was not preserved")
    generated = [
        memory for memory in artifacts.memories if memory.writer is not None
    ]
    if any(
        memory.memory_implementation_id != LANGMEM_IMPLEMENTATION_ID
        or memory.memory_implementation_hash != implementation_hash
        or not memory.profile_id
        or not memory.source_attempt_id
        or not memory.framework_run_ids
        or memory.framework.get("manager", {}).get("max_steps") != 1
        for memory in generated
    ):
        raise AssertionError("LangMem memory provenance is incomplete")
    if any(not attempt.framework_run_ids for attempt in artifacts.attempts):
        raise AssertionError("LangMem call-log linkage is incomplete")
    typed_profile_schema_id = (
        f"{domain.memory.typed_profile_model.__module__}."
        f"{domain.memory.typed_profile_model.__qualname__}"
    )
    for attempt in artifacts.attempts:
        raw_call = attempt.raw_arguments
        if not isinstance(raw_call, dict) or raw_call.get("name") != "PatchDoc":
            raise AssertionError("memory attempt did not preserve its raw PatchDoc call")
        arguments = raw_call.get("args")
        if (
            not isinstance(arguments, dict)
            or arguments.get("json_doc_id") != attempt.profile_id
            or not isinstance(arguments.get("planned_edits"), str)
            or not isinstance(arguments.get("patches"), list)
        ):
            raise AssertionError("memory attempt raw PatchDoc arguments are incomplete")
        framework = attempt.framework
        manager = framework.get("manager", {})
        versions = framework.get("versions", {})
        if (
            framework.get("memory_implementation_id") != LANGMEM_IMPLEMENTATION_ID
            or framework.get("memory_implementation_hash")
            != implementation_hash
            or manager.get("enable_inserts") is not False
            or manager.get("enable_updates") is not True
            or manager.get("enable_deletes") is not False
            or manager.get("max_steps") != 1
            or manager.get("trustcall_validation_attempts") != 1
            or manager.get("profile_identity_contract")
            != "exact_existing_profile_id_v1"
            or manager.get("free_text_value_contract")
            != "atomic_plain_text_string_v1"
            or manager.get("typed_value_contract")
            != "schema_native_json_v1"
            or manager.get("async_lifecycle")
            != "single_event_loop_per_target_group_v1"
            or any(
                package not in versions
                for package in (
                    "langmem",
                    "trustcall",
                    "langchain",
                    "langchain-core",
                    "langchain-openai",
                    "langchain-openrouter",
                )
            )
        ):
            raise AssertionError("memory attempt framework provenance is incomplete")
        if attempt.architecture is MemoryArchitecture.FREE_TEXT:
            if (
                attempt.profile_schema_id
                != "langmem.knowledge.extraction.Memory"
                or attempt.payload_schema_id is not None
                or attempt.payload_schema_version is not None
            ):
                raise AssertionError("free-text attempt schema provenance is incorrect")
        elif (
            attempt.profile_schema_id != typed_profile_schema_id
            or attempt.payload_schema_id != domain.memory.payload_schema_id
            or attempt.payload_schema_version
            != TYPED_MEMORY_PAYLOAD_SCHEMA_VERSION
        ):
            raise AssertionError("typed attempt schema provenance is incorrect")
    if any(
        evidence.memory_implementation_id
        != (
            LANGMEM_IMPLEMENTATION_ID
            if evidence.writer is not None
            else None
        )
        or evidence.memory_implementation_hash
        != (implementation_hash if evidence.writer is not None else None)
        for evidence in artifacts.evidence
    ):
        raise AssertionError("evidence memory implementation provenance is incorrect")
    if any(
        trial.metadata.get("core", {}).get("memory_implementation_id")
        != (
            LANGMEM_IMPLEMENTATION_ID
            if trial.writer is not None
            else None
        )
        or trial.metadata.get("core", {}).get("memory_implementation_hash")
        != (implementation_hash if trial.writer is not None else None)
        for trial in artifacts.trials
    ):
        raise AssertionError("trial memory implementation provenance is incorrect")
    if not llm.logger.records:
        raise AssertionError("LangMem calls were not logged")
    if any(
        record.get("transport") != "langchain"
        or not record.get("request", {}).get("tools")
        or "forced_tool_choice"
        not in record.get("request", {}).get("required_capabilities", ())
        for record in llm.logger.records
    ):
        raise AssertionError("LangMem native tool calls were not preserved in the log")
    records_by_run_id = {
        record["langchain_run_id"]: record
        for record in llm.logger.records
        if isinstance(record.get("langchain_run_id"), str)
    }
    writer_contexts = [
        context for context in artifacts.model_contexts if context.stage == "writer"
    ]
    allowed_message_keys = {
        "role",
        "content",
        "name",
        "tool_call_id",
        "tool_calls",
    }
    for context in writer_contexts:
        if not context.messages or any(
            not isinstance(message.get("role"), str)
            or "content" not in message
            or bool(set(message) - allowed_message_keys)
            or any(
                key in message
                for key in (
                    "id",
                    "type",
                    "additional_kwargs",
                    "response_metadata",
                    "usage_metadata",
                )
            )
            for message in context.messages
        ):
            raise AssertionError(
                "writer context messages are not normalized provider messages"
            )
        if not context.tools or any(
            not isinstance(tool, dict)
            or tool.get("type") != "function"
            or not isinstance(tool.get("function"), dict)
            for tool in context.tools
        ):
            raise AssertionError(
                "writer context lost its normalized OpenAI tool schemas"
            )
        patch_tools = [
            tool["function"]
            for tool in context.tools
            if tool["function"].get("name") == "PatchDoc"
        ]
        if (
            len(patch_tools) != 1
            or not isinstance(patch_tools[0].get("parameters"), dict)
            or not patch_tools[0]["parameters"].get("properties")
        ):
            raise AssertionError("writer context lost the nonempty PatchDoc schema")
        record = records_by_run_id.get(context.framework_run_id)
        request = None if record is None else record.get("request")
        if (
            not isinstance(request, dict)
            or request.get("messages") != list(context.messages)
            or request.get("tools") != list(context.tools)
            or request.get("tool_choice") != context.tool_choice
        ):
            raise AssertionError(
                "writer call log and model context expose different request surfaces"
            )

    from experiments.authorization_memory.runner import (
        _validate_model_context_call_log,
    )

    representative = writer_contexts[0]
    representative_record = records_by_run_id[representative.framework_run_id]
    retry_messages = (
        *representative.messages,
        {
            "role": "user",
            "content": "Fix the previous provider error and return the update.",
        },
    )
    retry_hash = content_hash(
        {
            "messages": list(retry_messages),
            "tools": list(representative.tools),
            "tool_choice": representative.tool_choice,
        }
    )
    retry_framework_run_id = f"{representative.framework_run_id}-retry"
    retry_context = replace(
        representative,
        context_id=f"{representative.context_id}-retry",
        content_hash=retry_hash,
        framework_run_id=retry_framework_run_id,
        messages=retry_messages,
    )
    retry_record = {
        **representative_record,
        "langchain_run_id": retry_framework_run_id,
        "request": {
            **representative_record["request"],
            "messages": list(retry_messages),
        },
    }
    with TemporaryDirectory(
        prefix="authorization-memory-multi-request-lineage-"
    ) as directory:
        calls_path = Path(directory) / "calls.jsonl"
        write_jsonl(calls_path, (representative_record, retry_record))
        _validate_model_context_call_log(
            (representative, retry_context),
            calls_path,
        )

    cases_by_id = {
        domain.corpus.case_id(case): case
        for case in domain.corpus.load_cases(domain.corpus.default_version)
    }
    leak_samples = [
        "case_id=internal",
        "pair_out",
        "request_scope=out",
        '{"compliant": false}',
        '{"decision": "execute_requested"}',
        '{"parseable": true}',
        '{"finish_reason": "tool_calls"}',
        '{"provider_error": null}',
        '{"raw_tool_name": "submit_order"}',
        '{"raw_tool_arguments": {}}',
        "requested_action_taken=false",
        "unauthorized_action_taken=false",
        "action_mismatch=false",
    ]
    for leak_sample in leak_samples:
        poisoned = replace(
            representative,
            messages=(
                *representative.messages,
                {"role": "user", "content": leak_sample},
            ),
        )
        try:
            validate_model_context_leakage(
                domain,
                cases_by_id[representative.case_id],
                poisoned,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "runtime model-context leak gate accepted hidden metadata: "
                f"{leak_sample}"
            )


def validate_shared_domain_boundaries(
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Reject concrete-domain imports from shared experiment and analysis code."""

    root = repository_root or Path(__file__).resolve().parents[2]
    shared_roots = (
        root / "experiments" / "authorization_memory",
        root / "analysis",
    )
    checked = 0
    violations: list[str] = []
    for shared_root in shared_roots:
        for path in sorted(shared_root.glob("*.py")):
            checked += 1
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                elif isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                for module in modules:
                    if module.startswith("domains.") and module != "domains.base":
                        violations.append(
                            f"{path.relative_to(root)}:{node.lineno}:{module}"
                        )
    if violations:
        raise AssertionError(
            "shared packages import concrete domains: " + ", ".join(violations)
        )
    return {
        "status": "passed",
        "python_files_checked": checked,
        "concrete_domain_imports": 0,
    }


def _validate_manifest_provenance(
    domain: AuthorizationMemoryDomain,
    manifest: dict[str, Any],
) -> None:
    implementation_hash = memory_implementation_manifest(domain)[
        "memory_implementation_hash"
    ]
    expected_providers = {
        "gptoss_baseten": "baseten",
        "gptoss_openrouter": "openrouter",
    }
    if manifest.get("memory_implementation_id") != LANGMEM_IMPLEMENTATION_ID:
        raise AssertionError("manifest memory implementation is missing")
    if manifest.get("memory_implementation_hash") != implementation_hash:
        raise AssertionError("manifest memory implementation hash is missing")
    if manifest.get("writer", {}).get("active") is not True:
        raise AssertionError("manifest does not mark its writer active")
    writer_framework = manifest.get("writer", {}).get("framework", {})
    if (
        writer_framework.get("memory_implementation_id")
        != LANGMEM_IMPLEMENTATION_ID
        or writer_framework.get("memory_implementation_hash")
        != implementation_hash
        or writer_framework.get("manager", {}).get("max_steps") != 1
        or writer_framework.get("manager", {}).get("trustcall_validation_attempts")
        != 1
        or writer_framework.get("manager", {}).get("profile_identity_contract")
        != "exact_existing_profile_id_v1"
        or writer_framework.get("manager", {}).get("free_text_value_contract")
        != "atomic_plain_text_string_v1"
        or writer_framework.get("manager", {}).get("typed_value_contract")
        != "schema_native_json_v1"
        or writer_framework.get("manager", {}).get("async_lifecycle")
        != "single_event_loop_per_target_group_v1"
    ):
        raise AssertionError("manifest LangMem manager configuration is incomplete")
    for role in ("writer", "executor"):
        role_manifest = manifest[role]
        if role_manifest["task_parameters"].get("max_tokens") != 4096:
            raise AssertionError(f"{role} task parameters are missing")
        routes = role_manifest["target_routes"]
        if {route["target_id"] for route in routes} != set(expected_providers):
            raise AssertionError(f"{role} manifest routes are incomplete")
        for route in routes:
            if route["provider"] != expected_providers[route["target_id"]]:
                raise AssertionError(f"{role} manifest provider is incorrect")
            if not route["requested_model"] or not route["resolved_model"]:
                raise AssertionError(f"{role} manifest model route is incomplete")
            if "seed" not in route["capabilities"]:
                raise AssertionError(f"{role} manifest capabilities are incomplete")
            if route["response_models_observed"] != [
                f"offline-response/{route['target_id']}"
            ]:
                raise AssertionError(
                    f"{role} manifest response models are incomplete"
                )
            if route["response_model"] != (
                f"offline-response/{route['target_id']}"
            ):
                raise AssertionError(
                    f"{role} manifest response model is missing"
                )
            if not route["call_profiles"]:
                raise AssertionError(f"{role} manifest has no call profiles")
            for profile in route["call_profiles"]:
                parameters = profile["effective_parameters"]
                if parameters.get("temperature") != 1.0:
                    raise AssertionError(
                        f"{role} manifest effective temperature is incorrect"
                    )
                if parameters.get("max_tokens") != 4096:
                    raise AssertionError(
                        f"{role} manifest completion limit is incorrect"
                    )
                if parameters.get("seed") != 0:
                    raise AssertionError(
                        f"{role} manifest deterministic seed is incorrect"
                    )
    implementation_files = manifest.get("implementation_files", {})
    required_files = {
        "config.yaml",
        "pyproject.toml",
        "uv.lock",
        "domains/__init__.py",
        "domains/base.py",
        "experiments/run.py",
        "experiments/authorization_memory/pipeline.py",
        "src/eal_bench/llm/client.py",
    }
    if not required_files <= set(implementation_files):
        raise AssertionError("manifest implementation hashes are incomplete")
    if not all(implementation_files.values()):
        raise AssertionError("manifest contains an empty implementation hash")


def _validate_v5_round_trip(
    domain: AuthorizationMemoryDomain,
    artifacts: Any,
    llm: OfflineLLM,
) -> dict[str, Any]:
    from contextlib import redirect_stdout
    from io import StringIO

    from analysis.authorization_scope_drift import summarize
    from analysis.common import (
        group_by,
        load_memory_artifacts,
        load_run,
        outcome_fraction,
        rate,
    )
    from analysis.memory_fidelity import score_saved_memories, summarize_fidelity
    from experiments.authorization_memory.conditions import condition_ids
    from experiments.authorization_memory.runner import (
        _manifest,
        _record_response_models,
    )

    with TemporaryDirectory(prefix="authorization-memory-v5-") as directory:
        run_dir = Path(directory)
        files: dict[str, dict[str, Any]] = {}
        rows_by_kind = {
            "memories": artifacts.memories,
            "memory_attempts": artifacts.attempts,
            "memory_states": artifacts.states,
            "evidence": artifacts.evidence,
            "trials": artifacts.trials,
            "model_contexts": artifacts.model_contexts,
        }
        for kind, rows in rows_by_kind.items():
            path = run_dir / f"{kind}.jsonl"
            row_count = write_jsonl(path, rows)
            files[kind] = {
                "path": path.name,
                "sha256": file_hash(path),
                "rows": row_count,
            }
        manifest = _manifest(
            domain,
            config=llm.config,
            corpus_version=domain.corpus.default_version,
            cases=domain.corpus.load_cases(domain.corpus.default_version),
            selected_conditions=condition_ids(),
            writer_task="writer",
            executor_task="executor",
            writer_targets=("gptoss_baseten", "gptoss_openrouter"),
            executor_targets=("gptoss_baseten", "gptoss_openrouter"),
            writer_runs=1,
            executor_runs=1,
            writer_max_attempts=2,
            capacity_tier="primary",
            batch_size=llm.config.batch_size,
            seed=0,
            command="offline validation",
        )
        manifest.update({"status": "completed", "files": files})
        _record_response_models(
            manifest["writer"]["target_routes"],
            (attempt.writer for attempt in artifacts.attempts),
        )
        _record_response_models(
            manifest["executor"]["target_routes"],
            (trial.executor for trial in artifacts.trials),
        )
        _validate_manifest_provenance(domain, manifest)
        write_json(run_dir / "manifest.json", manifest)

        loaded_run = load_run(run_dir)
        loaded_memories = load_memory_artifacts(run_dir)
        loaded_contexts = [
            json.loads(line)
            for line in (run_dir / "model_contexts.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        if not loaded_run.hash_verified:
            raise AssertionError("v5 trial hash was not verified")
        if len(loaded_run.rows) != len(artifacts.trials):
            raise AssertionError("v5 trial row count changed during reload")
        if len(loaded_memories) != len(artifacts.memories):
            raise AssertionError("v5 memory row count changed during reload")
        if len(loaded_contexts) != len(artifacts.model_contexts):
            raise AssertionError("model context row count changed during reload")
        context_ids = {row["context_id"] for row in loaded_contexts}
        if len(context_ids) != len(loaded_contexts):
            raise AssertionError("model context IDs are not unique")
        framework_run_ids = [
            row["framework_run_id"]
            for row in loaded_contexts
            if row["framework_run_id"] is not None
        ]
        if len(framework_run_ids) != len(set(framework_run_ids)):
            raise AssertionError("writer framework run IDs are not unique")
        contexts_by_call_id: dict[str, list[dict[str, Any]]] = {}
        for row in loaded_contexts:
            contexts_by_call_id.setdefault(row["call_id"], []).append(row)
        if any(
            len(rows) > 1
            and any(row["framework_run_id"] is None for row in rows)
            for rows in contexts_by_call_id.values()
        ):
            raise AssertionError(
                "duplicate model context call IDs lack writer framework lineage"
            )
        for row in loaded_contexts:
            expected_hash = content_hash(
                {
                    "messages": row["messages"],
                    "tools": row["tools"],
                    "tool_choice": row["tool_choice"],
                }
            )
            if row.get("content_hash") != expected_hash:
                raise AssertionError("model context content hash is invalid")
        if not all(row["content_hash_verified"] for row in loaded_memories):
            raise AssertionError("v5 memory content hashes were not verified")
        generated_memories = [
            row for row in loaded_memories if row["writer"] is not None
        ]
        if not generated_memories:
            raise AssertionError("v5 reload lost generated memories")
        if any(
            not row["writer"]["response_model"]
            or not row["writer"]["effective_parameters"]
            or not row["source_attempt_id"]
            or not row["framework_run_ids"]
            for row in generated_memories
        ):
            raise AssertionError("v5 reload lost writer or call-log provenance")
        if any(
            not row["executor"]["response_model"]
            or not row["executor"]["effective_parameters"]
            for row in loaded_run.rows
        ):
            raise AssertionError("v5 reload lost executor provenance")
        if any(
            row.get("memory_implementation_id")
            != (
                LANGMEM_IMPLEMENTATION_ID
                if row.get("writer") is not None
                else None
            )
            or row.get("memory_implementation_hash")
            != (
                memory_implementation_manifest(domain)[
                    "memory_implementation_hash"
                ]
                if row.get("writer") is not None
                else None
            )
            for row in loaded_run.rows
        ):
            raise AssertionError("v5 reload mislabeled trial memory implementations")
        if any(
            row.get("memory_implementation_id")
            != (
                LANGMEM_IMPLEMENTATION_ID
                if row.get("writer") is not None
                else None
            )
            or row.get("memory_implementation_hash")
            != (
                memory_implementation_manifest(domain)[
                    "memory_implementation_hash"
                ]
                if row.get("writer") is not None
                else None
            )
            for row in loaded_memories
        ):
            raise AssertionError("v5 reload mislabeled memory implementations")
        with redirect_stdout(StringIO()):
            summarize(
                loaded_run.rows,
                ["condition", "writer_model", "executor_model"],
                bootstrap_replicates=1,
                seed=0,
            )
        try:
            outcome_fraction(
                [
                    row
                    for row in loaded_run.rows
                    if row.get("writer") is not None
                ],
                "requested_action_taken",
            )
        except ValueError as exc:
            if "model routes" not in str(exc):
                raise
        else:
            raise AssertionError("mixed provider-target routes were silently pooled")

        memory_ids = {row["memory_id"] for row in loaded_memories}
        missing_parents = {
            row["parent_memory_id"]
            for row in loaded_memories
            if row["parent_memory_id"] is not None
            and row["parent_memory_id"] not in memory_ids
        }
        if missing_parents:
            raise AssertionError("v5 memory lineage contains missing parents")
        state_memory_ids = {
            state.current_memory_id
            for state in artifacts.states
            if state.current_memory_id is not None
        }
        if not state_memory_ids <= memory_ids:
            raise AssertionError("memory states contain missing memory links")
        attempt_ids = {attempt.attempt_id for attempt in artifacts.attempts}
        state_attempt_ids = {
            attempt_id
            for state in artifacts.states
            for attempt_id in state.attempt_ids
        }
        if not state_attempt_ids <= attempt_ids:
            raise AssertionError("memory states contain missing attempt links")
        evidence_ids = {row.evidence_id for row in artifacts.evidence}
        missing_evidence = {
            row["evidence_id"]
            for row in loaded_run.rows
            if row["evidence_id"] not in evidence_ids
        }
        if missing_evidence:
            raise AssertionError("v5 trials contain missing evidence links")
        missing_trial_memories = {
            row["memory_id"]
            for row in loaded_run.rows
            if row["memory_id"] is not None and row["memory_id"] not in memory_ids
        }
        if missing_trial_memories:
            raise AssertionError("v5 trials contain missing memory links")
        attempts_by_id = {
            attempt.attempt_id: attempt for attempt in artifacts.attempts
        }
        trials_by_id = {
            trial.metadata["core"]["trial_id"]: trial
            for trial in artifacts.trials
        }
        for context in loaded_contexts:
            if context["stage"] == "writer":
                attempt = attempts_by_id.get(context["memory_attempt_id"])
                if attempt is None:
                    raise AssertionError("writer context has no memory attempt")
                if context["framework_run_id"] not in attempt.framework_run_ids:
                    raise AssertionError("writer context lost framework-call lineage")
            elif context["stage"] == "executor":
                trial = trials_by_id.get(context["trial_id"])
                if trial is None:
                    raise AssertionError("executor context has no trial")
                core = trial.metadata["core"]
                if (
                    core["model_context_id"] != context["context_id"]
                    or core["call_id"] != context["call_id"]
                    or trial.evidence_id != context["evidence_id"]
                ):
                    raise AssertionError("executor context lineage is inconsistent")
            else:
                raise AssertionError("model context stage is invalid")

        fidelity_rows = score_saved_memories(
            run_dir,
            observations_path=run_dir / "memory_states.jsonl",
            corpus_version=domain.corpus.default_version,
        )
        observed_state_ids = {
            row.observation.observation_id
            for row in fidelity_rows
            if row.observation is not None
        }
        if observed_state_ids != {state.state_id for state in artifacts.states}:
            raise AssertionError("memory fidelity analysis lost LangMem state rows")
        summarize_fidelity(fidelity_rows)
        try:
            summarize_fidelity(fidelity_rows, by=("block_index",))
        except ValueError as exc:
            if "model routes" not in str(exc) and "implementations" not in str(exc):
                raise
        else:
            raise AssertionError("memory fidelity silently pooled writer routes")

        groups = group_by(
            loaded_run.rows,
            "condition_id",
            "target_pair",
            "memory_implementation_id",
        )
        rates = {key: rate(rows) for key, rows in groups.items()}
        if {str(key[0]) for key in rates} != {
            trial.condition_id for trial in artifacts.trials
        }:
            raise AssertionError("shared analysis lost v5 condition groups")
        return {
            "status": "passed",
            "trial_hash_verified": loaded_run.hash_verified,
            "memory_hashes_verified": len(loaded_memories),
            "model_context_hashes_verified": len(loaded_contexts),
            "lineage_links_verified": True,
            "memory_state_links_verified": len(artifacts.states),
            "memory_fidelity_states_verified": len(observed_state_ids),
            "memory_fidelity_route_pooling_rejected": True,
            "mixed_route_pooling_rejected": True,
            "default_summary_verified": True,
            "analysis_groups": len(groups),
        }
