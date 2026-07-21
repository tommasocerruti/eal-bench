#!/usr/bin/env python3
"""Validate a model target, optionally through one bounded live component check."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from importlib.metadata import version
from typing import Any, Literal

from langmem import create_memory_manager
from langmem.knowledge.extraction import Memory as LangMemTextProfile
from pydantic import BaseModel, Field

from eal_bench.llm import LLM, LangChainCallLogger, create_langchain_chat_model

from experiments.authorization_memory.langmem_writer import (
    FREE_TEXT_VALUE_INSTRUCTION,
    NESTED_ARRAY_PATCH_INSTRUCTION,
    TYPED_VALUE_INSTRUCTION,
    profile_identity_instruction,
)
from experiments.authorization_memory.schemas import LANGMEM_IMPLEMENTATION_ID

REQUIRED_CAPABILITIES = ("native_tools", "forced_tool_choice", "seed")
CHECK_TOOL_NAME = "report_target_check"
MAX_LIVE_TOKENS = 1024
DEFAULT_LIVE_TOKENS = 1024
LANGMEM_TYPED_PROFILE_ID = "target-check-typed-profile"
LANGMEM_TEXT_PROFILE_ID = "target-check-text-profile"
LANGMEM_STAGE_IDS = (
    "target-check-typed-initial",
    "target-check-typed-continuity",
    "target-check-free-text",
)
LANGMEM_LIVE_CALLS = len(LANGMEM_STAGE_IDS)
COMPONENT_NATIVE_TOOLS = "native-tools"
COMPONENT_LANGMEM_WRITER = "langmem-writer"
COMPONENTS = (COMPONENT_NATIVE_TOOLS, COMPONENT_LANGMEM_WRITER)
CHECK_TOOL = {
    "type": "function",
    "function": {
        "name": CHECK_TOOL_NAME,
        "description": "Report that the model-target capability check succeeded.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["ok"],
                }
            },
            "required": ["status"],
            "additionalProperties": False,
        },
    },
}
FORCED_TOOL_CHOICE = {
    "type": "function",
    "function": {"name": CHECK_TOOL_NAME},
}


class TargetCheckScope(BaseModel):
    allowed_categories: list[str]


class TargetCheckRecord(BaseModel):
    status: Literal["ok", "updated"]
    scope: TargetCheckScope


class TargetCheckMemory(BaseModel):
    """Minimal nested profile used only by the live LangMem target check."""

    records: list[TargetCheckRecord] = Field(default_factory=list)


def _typed_target_check_instructions(*, continuation: bool) -> str:
    action = (
        "Update the existing record by replacing its status with updated."
        if continuation
        else (
            "Add exactly one record with status ok and scope.allowed_categories "
            'set to the JSON array ["endpoint_security_licenses"].'
        )
    )
    return (
        "Maintain the single target-check profile. "
        f"{profile_identity_instruction(LANGMEM_TYPED_PROFILE_ID)} {action} "
        f"{TYPED_VALUE_INSTRUCTION} "
        + (
            "Use one replace patch at /records/0/status."
            if continuation
            else (
                f"{NESTED_ARRAY_PATCH_INSTRUCTION} Use exactly two sequential "
                "patches: first add /records/- with allowed_categories set to "
                "null, then replace /records/0/scope/allowed_categories with the "
                "actual JSON array. The add must precede the dependent replace."
            )
        )
    )


def _initial_typed_request() -> str:
    return (
        "Add the requested target-check record with status ok and "
        'scope.allowed_categories equal to ["endpoint_security_licenses"].'
    )


def _continuity_typed_request() -> str:
    return "Update the existing target-check record status from ok to updated."


def _free_text_target_check_instructions() -> str:
    return (
        "Maintain the single target-check profile. "
        f"{profile_identity_instruction(LANGMEM_TEXT_PROFILE_ID)} "
        f"{FREE_TEXT_VALUE_INSTRUCTION} The existing string may look like JSON, "
        "but it remains an atomic string. When requested, replace content with "
        'the exact string "Status: active (msg_001, msg_002)".'
    )


def _free_text_request() -> str:
    return 'Set the profile content to exactly "Status: active (msg_001, msg_002)".'


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        help="configured model target ID (default: target_check task default)",
    )
    parser.add_argument(
        "--component",
        choices=COMPONENTS,
        default=COMPONENT_NATIVE_TOOLS,
        help=(
            "native forced-tool transport or the LangMem profile writer "
            f"(default: {COMPONENT_NATIVE_TOOLS})"
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "make one bounded component check; the LangMem writer suite uses "
            f"{LANGMEM_LIVE_CALLS} sequential provider calls"
        ),
    )
    parser.add_argument(
        "--skip-credential-check",
        action="store_true",
        help="offline only: validate configuration without requiring the provider key",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_LIVE_TOKENS,
        help=(
            f"live completion budget (1-{MAX_LIVE_TOKENS}; "
            f"default: {DEFAULT_LIVE_TOKENS})"
        ),
    )
    parser.add_argument("--seed", type=int, default=20260719)
    return parser


def _route_report(
    llm: LLM,
    target: str | None,
    *,
    require_api_key: bool,
) -> dict[str, Any]:
    route = llm.preflight(
        "target_check",
        target=target,
        required_capabilities=REQUIRED_CAPABILITIES,
        require_api_key=require_api_key,
    )
    return {
        "target_id": route.target_id,
        "provider": route.provider,
        "requested_model": route.requested_model,
        "resolved_model": route.resolved_model,
        "declared_capabilities": sorted(route.capabilities),
        "required_capabilities": list(REQUIRED_CAPABILITIES),
        "max_concurrency": route.max_concurrency,
        "rate_limit": {
            "max_rate": route.rate_limit.max_rate,
            "period_seconds": route.rate_limit.period_seconds,
        },
    }


def _usage_report(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        raw = usage.model_dump(exclude_none=True)
    elif isinstance(usage, dict):
        raw = usage
    else:
        return {"raw": str(usage)}
    return {
        "prompt_tokens": raw.get("prompt_tokens"),
        "completion_tokens": raw.get("completion_tokens"),
        "total_tokens": raw.get("total_tokens"),
        "cost_usd": raw.get("cost"),
        "raw": raw,
    }


def _live_check(
    llm: LLM,
    route_report: dict[str, Any],
    *,
    max_tokens: int,
    seed: int,
) -> dict[str, Any]:
    started = time.monotonic()
    response = llm.complete(
        "target_check",
        messages=[
            {
                "role": "user",
                "content": (
                    f"Call {CHECK_TOOL_NAME} with status set to ok. "
                    "Do not answer with prose."
                ),
            }
        ],
        target=route_report["target_id"],
        required_capabilities=REQUIRED_CAPABILITIES,
        tools=[CHECK_TOOL],
        tool_choice=FORCED_TOOL_CHOICE,
        seed=seed,
        max_tokens=max_tokens,
    )
    latency_ms = round((time.monotonic() - started) * 1000)
    choices = list(getattr(response, "choices", []) or [])
    choice = choices[0] if choices else None
    finish_reason = None if choice is None else getattr(choice, "finish_reason", None)
    message = None if choice is None else getattr(choice, "message", None)
    tool_calls = list(getattr(message, "tool_calls", []) or [])

    validation_errors: list[str] = []
    parsed_arguments: dict[str, Any] | None = None
    observed_tool_name: str | None = None
    if len(tool_calls) != 1:
        validation_errors.append(f"expected one tool call, received {len(tool_calls)}")
    else:
        call = tool_calls[0]
        function = getattr(call, "function", None)
        observed_tool_name = (
            None if function is None else getattr(function, "name", None)
        )
        if observed_tool_name != CHECK_TOOL_NAME:
            validation_errors.append(
                f"expected tool {CHECK_TOOL_NAME!r}, received {observed_tool_name!r}"
            )
        raw_arguments = (
            None if function is None else getattr(function, "arguments", None)
        )
        try:
            parsed = json.loads(raw_arguments or "")
        except (TypeError, json.JSONDecodeError) as exc:
            validation_errors.append(f"tool arguments are not valid JSON: {exc}")
        else:
            if not isinstance(parsed, dict):
                validation_errors.append("tool arguments must be a JSON object")
            else:
                parsed_arguments = parsed
                if parsed != {"status": "ok"}:
                    validation_errors.append(
                        "tool arguments must be exactly {'status': 'ok'}"
                    )

    return {
        "status": "passed" if not validation_errors else "failed",
        "mode": "live",
        "component": COMPONENT_NATIVE_TOOLS,
        **route_report,
        "credential_checked": True,
        "network_request_made": True,
        "response_model": (
            str(response.model) if getattr(response, "model", None) else None
        ),
        "finish_reason": finish_reason,
        "latency_ms": latency_ms,
        "usage": _usage_report(response),
        "tool_call": {
            "name": observed_tool_name,
            "arguments": parsed_arguments,
        },
        "effective_parameters": {
            "max_tokens": max_tokens,
            "seed": seed,
            "tool_choice": "forced",
        },
        "validation_errors": validation_errors,
        "call_log": str(llm.logger.path),
    }


def _framework_versions() -> dict[str, str]:
    return {
        package: version(package)
        for package in (
            "langmem",
            "trustcall",
            "langchain",
            "langchain-core",
            "langchain-openai",
            "langchain-openrouter",
        )
    }


def _aggregate_langchain_usage(records: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
    }
    present = {key: False for key in totals}
    missing_cost = 0
    for record in records:
        usage = record.get("usage")
        if not isinstance(usage, dict):
            missing_cost += 1
            continue
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value
                present[key] = True
        cost = usage.get("cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            totals["cost_usd"] += float(cost)
            present["cost_usd"] = True
        else:
            missing_cost += 1
    return {
        key: (value if present[key] else None) for key, value in totals.items()
    } | {"calls_missing_cost": missing_cost}


def _langmem_offline_check(
    llm: LLM,
    route_report: dict[str, Any],
    *,
    max_tokens: int,
    seed: int,
    require_api_key: bool,
) -> dict[str, Any]:
    callback = LangChainCallLogger(llm.logger)
    model, route, effective_params = create_langchain_chat_model(
        llm.config,
        "target_check",
        route_report["target_id"],
        seed=seed,
        callbacks=(callback,),
        required_capabilities=REQUIRED_CAPABILITIES,
        require_api_key=require_api_key,
        parameter_overrides={"max_tokens": max_tokens},
    )
    typed_manager = create_memory_manager(
        model,
        schemas=[TargetCheckMemory],
        instructions=_typed_target_check_instructions(continuation=False),
        enable_inserts=False,
        enable_updates=True,
        enable_deletes=False,
    )
    text_manager = create_memory_manager(
        model,
        schemas=[LangMemTextProfile],
        instructions=_free_text_target_check_instructions(),
        enable_inserts=False,
        enable_updates=True,
        enable_deletes=False,
    )
    return {
        "status": "passed",
        "mode": "offline",
        "component": COMPONENT_LANGMEM_WRITER,
        **route_report,
        "credential_checked": require_api_key,
        "network_request_made": False,
        "langchain_model_class": type(model).__name__,
        "langmem_manager_class": type(typed_manager).__name__,
        "framework_versions": _framework_versions(),
        "memory_implementation_id": LANGMEM_IMPLEMENTATION_ID,
        "protocol_stages": list(LANGMEM_STAGE_IDS),
        "maximum_provider_calls": LANGMEM_LIVE_CALLS,
        "effective_parameters": {
            **effective_params,
            "max_steps": 1,
            "trustcall_max_attempts": 1,
            "max_concurrency": route.max_concurrency,
        },
        "profiles": [
            {
                "id": LANGMEM_TYPED_PROFILE_ID,
                "schema": TargetCheckMemory.__name__,
                "enable_inserts": typed_manager.enable_inserts,
                "enable_updates": typed_manager.enable_updates,
                "enable_deletes": typed_manager.enable_deletes,
            },
            {
                "id": LANGMEM_TEXT_PROFILE_ID,
                "schema": LangMemTextProfile.__name__,
                "enable_inserts": text_manager.enable_inserts,
                "enable_updates": text_manager.enable_updates,
                "enable_deletes": text_manager.enable_deletes,
            },
        ],
        "call_log": str(llm.logger.path),
    }


async def _langmem_live_check(
    llm: LLM,
    route_report: dict[str, Any],
    *,
    max_tokens: int,
    seed: int,
) -> dict[str, Any]:
    started = time.monotonic()
    callback = LangChainCallLogger(llm.logger)
    model, route, effective_params = create_langchain_chat_model(
        llm.config,
        "target_check",
        route_report["target_id"],
        seed=seed,
        callbacks=(callback,),
        required_capabilities=REQUIRED_CAPABILITIES,
        parameter_overrides={"max_tokens": max_tokens},
    )
    async def invoke_stage(
        *,
        stage_id: str,
        manager: Any,
        profile_id: str,
        existing: BaseModel,
        request: str,
    ) -> tuple[list[Any], str | None, dict[str, Any]]:
        memories: list[Any] = []
        invocation_error: str | None = None
        try:
            memories = await asyncio.wait_for(
                manager.ainvoke(
                    {
                        "messages": [{"role": "user", "content": request}],
                        "existing": [(profile_id, existing)],
                        "max_steps": 1,
                    },
                    config={
                        "configurable": {"max_attempts": 1},
                        "metadata": {
                            "call_id": f"call-{stage_id}",
                            "memory_attempt_id": stage_id,
                            "memory_implementation_id": LANGMEM_IMPLEMENTATION_ID,
                            "profile_id": profile_id,
                            "check_component": COMPONENT_LANGMEM_WRITER,
                        },
                        "tags": ["target-check", COMPONENT_LANGMEM_WRITER],
                        "max_concurrency": route.max_concurrency,
                    },
                ),
                timeout=180,
            )
        except Exception as exc:  # noqa: BLE001 - report compatibility failure
            if isinstance(exc, TimeoutError):
                await callback.finalize_attempt_error(
                    stage_id,
                    exc,
                    termination="target_check_timeout",
                )
            invocation_error = f"{type(exc).__name__}: {exc}"
        return memories, invocation_error, callback.observation(stage_id)

    typed_initial_manager = create_memory_manager(
        model,
        schemas=[TargetCheckMemory],
        instructions=_typed_target_check_instructions(continuation=False),
        enable_inserts=False,
        enable_updates=True,
        enable_deletes=False,
    )
    initial, initial_error, initial_observation = await invoke_stage(
        stage_id=LANGMEM_STAGE_IDS[0],
        manager=typed_initial_manager,
        profile_id=LANGMEM_TYPED_PROFILE_ID,
        existing=TargetCheckMemory(),
        request=_initial_typed_request(),
    )
    initial_profile = (
        initial[0].content
        if len(initial) == 1
        and initial[0].id == LANGMEM_TYPED_PROFILE_ID
        and isinstance(initial[0].content, TargetCheckMemory)
        else TargetCheckMemory()
    )
    typed_continuity_manager = create_memory_manager(
        model,
        schemas=[TargetCheckMemory],
        instructions=_typed_target_check_instructions(continuation=True),
        enable_inserts=False,
        enable_updates=True,
        enable_deletes=False,
    )
    continuity, continuity_error, continuity_observation = await invoke_stage(
        stage_id=LANGMEM_STAGE_IDS[1],
        manager=typed_continuity_manager,
        profile_id=LANGMEM_TYPED_PROFILE_ID,
        existing=initial_profile,
        request=_continuity_typed_request(),
    )
    text_manager = create_memory_manager(
        model,
        schemas=[LangMemTextProfile],
        instructions=_free_text_target_check_instructions(),
        enable_inserts=False,
        enable_updates=True,
        enable_deletes=False,
    )
    text_memories, text_error, text_observation = await invoke_stage(
        stage_id=LANGMEM_STAGE_IDS[2],
        manager=text_manager,
        profile_id=LANGMEM_TEXT_PROFILE_ID,
        existing=LangMemTextProfile(
            content='{"status":"pending","sources":["msg_001"]}'
        ),
        request=_free_text_request(),
    )
    observations = {
        LANGMEM_STAGE_IDS[0]: initial_observation,
        LANGMEM_STAGE_IDS[1]: continuity_observation,
        LANGMEM_STAGE_IDS[2]: text_observation,
    }
    all_run_ids = [
        run_id
        for observation in observations.values()
        for run_id in observation["run_ids"]
    ]
    records_by_run_id = callback.records_by_run_id
    records = [
        records_by_run_id[run_id]
        for run_id in all_run_ids
        if run_id in records_by_run_id
    ]
    validation_errors: list[str] = []
    for stage_id, error in (
        (LANGMEM_STAGE_IDS[0], initial_error),
        (LANGMEM_STAGE_IDS[1], continuity_error),
        (LANGMEM_STAGE_IDS[2], text_error),
    ):
        if error is not None:
            validation_errors.append(f"{stage_id}: {error}")
    expected_initial = {
        "records": [
            {
                "status": "ok",
                "scope": {
                    "allowed_categories": ["endpoint_security_licenses"]
                },
            }
        ]
    }
    expected_continuity = {
        "records": [
            {
                "status": "updated",
                "scope": {
                    "allowed_categories": ["endpoint_security_licenses"]
                },
            }
        ]
    }
    if initial_error is None and len(initial) != 1:
        validation_errors.append(
            f"typed initial: expected one profile, received {len(initial)}"
        )
    elif initial_error is None:
        memory = initial[0]
        if memory.id != LANGMEM_TYPED_PROFILE_ID:
            validation_errors.append("typed initial did not preserve the profile ID")
        elif not isinstance(memory.content, TargetCheckMemory):
            validation_errors.append("typed initial returned an unexpected schema")
        elif memory.content.model_dump(mode="json") != expected_initial:
            validation_errors.append(
                "typed initial did not preserve the required nested array"
            )
    if continuity_error is None and len(continuity) != 1:
        validation_errors.append(
            f"typed continuity: expected one profile, received {len(continuity)}"
        )
    elif continuity_error is None:
        memory = continuity[0]
        if memory.id != LANGMEM_TYPED_PROFILE_ID:
            validation_errors.append("typed continuity did not preserve the profile ID")
        elif not isinstance(memory.content, TargetCheckMemory):
            validation_errors.append("typed continuity returned an unexpected schema")
        elif memory.content.model_dump(mode="json") != expected_continuity:
            validation_errors.append(
                "typed continuity did not update the same accepted profile"
            )
    if text_error is None and len(text_memories) != 1:
        validation_errors.append(
            f"free text: expected one profile, received {len(text_memories)}"
        )
    elif text_error is None:
        memory = text_memories[0]
        if memory.id != LANGMEM_TEXT_PROFILE_ID:
            validation_errors.append("free text did not preserve the profile ID")
        elif not isinstance(memory.content, LangMemTextProfile):
            validation_errors.append("free text returned an unexpected schema")
        elif memory.content.content != "Status: active (msg_001, msg_002)":
            validation_errors.append(
                "free-text content was not replaced as one atomic plain-text string"
            )
    expected_profile_by_stage = {
        LANGMEM_STAGE_IDS[0]: LANGMEM_TYPED_PROFILE_ID,
        LANGMEM_STAGE_IDS[1]: LANGMEM_TYPED_PROFILE_ID,
        LANGMEM_STAGE_IDS[2]: LANGMEM_TEXT_PROFILE_ID,
    }
    for stage_id, observation in observations.items():
        if observation["call_count"] != 1:
            validation_errors.append(
                f"{stage_id}: expected one underlying chat-model call, received "
                f"{observation['call_count']}"
            )
        for run_id in observation["run_ids"]:
            record = records_by_run_id.get(run_id)
            if not isinstance(record, dict):
                continue
            for tool_call in (record.get("response") or {}).get("tool_calls", []) or []:
                args = tool_call.get("args") if isinstance(tool_call, dict) else None
                if (
                    isinstance(args, dict)
                    and args.get("json_doc_id")
                    != expected_profile_by_stage[stage_id]
                ):
                    validation_errors.append(
                        f"{stage_id}: PatchDoc used the wrong json_doc_id"
                    )
    return {
        "status": "passed" if not validation_errors else "failed",
        "mode": "live",
        "component": COMPONENT_LANGMEM_WRITER,
        **route_report,
        "credential_checked": True,
        "network_request_made": True,
        "langchain_model_class": type(model).__name__,
        "langmem_manager_class": type(typed_initial_manager).__name__,
        "framework_versions": _framework_versions(),
        "memory_implementation_id": LANGMEM_IMPLEMENTATION_ID,
        "protocol_stages": list(LANGMEM_STAGE_IDS),
        "maximum_provider_calls": LANGMEM_LIVE_CALLS,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "usage": _aggregate_langchain_usage(records),
        "model_observations": observations,
        "invocation_errors": {
            LANGMEM_STAGE_IDS[0]: initial_error,
            LANGMEM_STAGE_IDS[1]: continuity_error,
            LANGMEM_STAGE_IDS[2]: text_error,
        },
        "raw_tool_calls": [
            tool_call
            for record in records
            if isinstance(record.get("response"), dict)
            for tool_call in record["response"].get("tool_calls", []) or []
        ],
        "effective_parameters": {
            **effective_params,
            "max_steps": 1,
            "trustcall_max_attempts": 1,
            "max_concurrency": route.max_concurrency,
        },
        "typed_profile": {
            "id": continuity[0].id if len(continuity) == 1 else None,
            "content": (
                continuity[0].content.model_dump(mode="json")
                if len(continuity) == 1
                and isinstance(continuity[0].content, TargetCheckMemory)
                else None
            ),
        },
        "free_text_profile": {
            "id": text_memories[0].id if len(text_memories) == 1 else None,
            "content": (
                text_memories[0].content.content
                if len(text_memories) == 1
                and isinstance(text_memories[0].content, LangMemTextProfile)
                else None
            ),
        },
        "validation_errors": validation_errors,
        "call_log": str(llm.logger.path),
    }


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    if not 1 <= args.max_tokens <= MAX_LIVE_TOKENS:
        parser.error(f"--max-tokens must be between 1 and {MAX_LIVE_TOKENS}")
    if args.live and args.skip_credential_check:
        parser.error("--skip-credential-check cannot be combined with --live")

    llm: LLM | None = None
    try:
        llm = LLM()
        route_report = _route_report(
            llm,
            args.target,
            require_api_key=not args.skip_credential_check,
        )
        if args.component == COMPONENT_LANGMEM_WRITER and args.live:
            report = asyncio.run(
                _langmem_live_check(
                    llm,
                    route_report,
                    max_tokens=args.max_tokens,
                    seed=args.seed,
                )
            )
        elif args.component == COMPONENT_LANGMEM_WRITER:
            report = _langmem_offline_check(
                llm,
                route_report,
                max_tokens=args.max_tokens,
                seed=args.seed,
                require_api_key=not args.skip_credential_check,
            )
        elif args.live:
            report = _live_check(
                llm,
                route_report,
                max_tokens=args.max_tokens,
                seed=args.seed,
            )
        else:
            report = {
                "status": "passed",
                "mode": "offline",
                "component": COMPONENT_NATIVE_TOOLS,
                **route_report,
                "credential_checked": not args.skip_credential_check,
                "network_request_made": False,
            }
    except Exception as exc:  # noqa: BLE001 - command reports configuration/API failures
        report = {
            "status": "failed",
            "mode": "live" if args.live else "offline",
            "component": args.component,
            "target_id": args.target or "(target_check task default)",
            "error": f"{type(exc).__name__}: {exc}",
            "call_log": None if llm is None else str(llm.logger.path),
        }

    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "passed":
        sys.exit(1)


if __name__ == "__main__":
    main()
