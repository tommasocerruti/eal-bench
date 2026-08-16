"""LangChain model construction and call provenance for LangMem writers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler, BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, convert_to_openai_messages
from langchain_core.outputs import LLMResult
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from langchain_openrouter import ChatOpenRouter

from .config import Config, ResolvedModelTarget
from .errors import ConfigError
from .logger import JSONLLogger
from .models import resolve_model

_RATE_LIMITERS: dict[str, InMemoryRateLimiter] = {}
_RATE_LIMITERS_LOCK = Lock()
_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "callbacks",
    "client",
    "default_headers",
    "headers",
    "http_async_client",
    "http_client",
    "openai_api_key",
}


def _is_permanent_provider_error(error: BaseException) -> bool:
    name = type(error).__name__.lower()
    return any(
        marker in name
        for marker in (
            "badrequest",
            "forbidden",
            "paymentrequired",
            "permissiondenied",
            "unauthorized",
        )
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).lower() in _SENSITIVE_KEYS
                else _jsonable(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, type) and hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json", exclude_none=True))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


_OPENAI_MESSAGE_KEYS = {
    "role",
    "content",
    "name",
    "tool_call_id",
    "tool_calls",
}


def _serialize_messages(messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
    converted = convert_to_openai_messages(
        list(messages),
        include_id=False,
    )
    if not isinstance(converted, list):
        raise TypeError("LangChain message conversion did not return a list")
    normalized: list[dict[str, Any]] = []
    for index, message in enumerate(converted):
        if not isinstance(message, Mapping):
            raise TypeError(
                f"LangChain message {index} did not convert to an object"
            )
        unexpected = sorted(set(message) - _OPENAI_MESSAGE_KEYS)
        if unexpected:
            raise ValueError(
                "LangChain message conversion exposed unsupported provider "
                f"fields at index {index}: {unexpected}"
            )
        if not isinstance(message.get("role"), str) or "content" not in message:
            raise ValueError(
                f"LangChain message {index} lacks provider role/content fields"
            )
        normalized.append(_jsonable(dict(message)))
    return normalized


def _serialize_tools(value: Any) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    if isinstance(value, Mapping) or isinstance(value, type):
        candidates = [value]
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        candidates = list(value)
    else:
        raise TypeError("LangChain tools must be a tool or a sequence of tools")
    converted: list[dict[str, Any]] = []
    for index, tool in enumerate(candidates):
        normalized = convert_to_openai_tool(tool)
        if not isinstance(normalized, Mapping):
            raise TypeError(
                f"LangChain tool {index} did not convert to an object"
            )
        converted.append(_jsonable(dict(normalized)))
    return converted


def _first_generation(response: LLMResult) -> Any | None:
    if not response.generations or not response.generations[0]:
        return None
    return response.generations[0][0]


def _response_model(response: LLMResult, generation: Any | None) -> str | None:
    message = None if generation is None else getattr(generation, "message", None)
    sources = [
        getattr(message, "response_metadata", None),
        getattr(generation, "generation_info", None),
        response.llm_output,
    ]
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for key in ("model_name", "model", "model_id"):
            if source.get(key):
                return str(source[key])
    return None


def _finish_reason(response: LLMResult, generation: Any | None) -> str | None:
    message = None if generation is None else getattr(generation, "message", None)
    sources = [
        getattr(message, "response_metadata", None),
        getattr(generation, "generation_info", None),
        response.llm_output,
    ]
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for key in ("finish_reason", "stop_reason"):
            if source.get(key) is not None:
                return str(source[key])
    return None


def _find_provider_cost(value: Any) -> float | int | str | None:
    if isinstance(value, Mapping):
        for key in ("cost", "total_cost"):
            cost = value.get(key)
            if isinstance(cost, (int, float, str)) and not isinstance(cost, bool):
                return cost
        for item in value.values():
            if (cost := _find_provider_cost(item)) is not None:
                return cost
    elif isinstance(value, (list, tuple)):
        for item in value:
            if (cost := _find_provider_cost(item)) is not None:
                return cost
    return None


def _usage(response: LLMResult, generation: Any | None) -> dict[str, Any] | None:
    message = None if generation is None else getattr(generation, "message", None)
    response_metadata = getattr(message, "response_metadata", None)
    generation_info = getattr(generation, "generation_info", None)
    candidates = [
        (
            response_metadata.get("token_usage")
            if isinstance(response_metadata, Mapping)
            else None
        ),
        (
            response.llm_output.get("token_usage")
            if isinstance(response.llm_output, Mapping)
            else None
        ),
        getattr(message, "usage_metadata", None),
    ]
    usage: dict[str, Any] = {}
    for candidate in candidates:
        if hasattr(candidate, "model_dump"):
            candidate = candidate.model_dump(mode="json", exclude_none=True)
        if isinstance(candidate, Mapping):
            usage.update(_jsonable(candidate))

    if "prompt_tokens" not in usage and "input_tokens" in usage:
        usage["prompt_tokens"] = usage["input_tokens"]
    if "completion_tokens" not in usage and "output_tokens" in usage:
        usage["completion_tokens"] = usage["output_tokens"]
    if "total_tokens" not in usage:
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        if isinstance(prompt, int) and isinstance(completion, int):
            usage["total_tokens"] = prompt + completion

    if "cost" not in usage:
        for source in (response_metadata, generation_info, response.llm_output):
            if (cost := _find_provider_cost(source)) is not None:
                usage["cost"] = cost
                break
    return usage or None


def _rate_limiter(route: ResolvedModelTarget) -> InMemoryRateLimiter | None:
    if route.rate_limit.max_rate is None or route.rate_limit.max_rate <= 0:
        return None
    requests_per_second = route.rate_limit.max_rate / route.rate_limit.period_seconds
    with _RATE_LIMITERS_LOCK:
        limiter = _RATE_LIMITERS.get(route.gate_key)
        if limiter is None:
            limiter = InMemoryRateLimiter(
                requests_per_second=requests_per_second,
                check_every_n_seconds=min(0.1, 1 / requests_per_second),
                max_bucket_size=1,
            )
            _RATE_LIMITERS[route.gate_key] = limiter
        return limiter


def _validate_capabilities(
    route: ResolvedModelTarget,
    required_capabilities: Iterable[str],
) -> None:
    required = {
        str(capability).strip()
        for capability in required_capabilities
        if str(capability).strip()
    }
    missing = sorted(required - route.capabilities)
    if missing:
        available = ", ".join(sorted(route.capabilities)) or "(none)"
        raise ConfigError(
            f"Model target '{route.target_id}' lacks required capabilities: "
            f"{', '.join(missing)}. Declared capabilities: {available}."
        )


def _provider_model_params(
    route: ResolvedModelTarget,
    effective_params: Mapping[str, Any],
) -> dict[str, Any]:
    params = dict(effective_params)
    if route.provider == "openrouter":
        extra_body = dict(params.pop("extra_body", {}) or {})
        provider_routing = extra_body.pop("provider", None)
        if extra_body:
            raise ConfigError(
                "ChatOpenRouter target parameters support only "
                "extra_body.provider."
            )
        if provider_routing is not None:
            params["openrouter_provider"] = provider_routing
        return params
    if route.provider == "openai" or "max_tokens" not in params:
        return params
    if "max_completion_tokens" in params:
        raise ConfigError(
            "Configure only one of max_tokens and max_completion_tokens."
        )
    max_tokens = params.pop("max_tokens")
    extra_body = dict(params.pop("extra_body", {}) or {})
    if "max_tokens" in extra_body and extra_body["max_tokens"] != max_tokens:
        raise ConfigError("Conflicting max_tokens values in params and extra_body.")
    extra_body["max_tokens"] = max_tokens
    params["extra_body"] = extra_body
    return params


def create_langchain_chat_model(
    config: Config,
    task: str,
    target: str | None = None,
    *,
    seed: int | None = None,
    callbacks: Sequence[BaseCallbackHandler] = (),
    required_capabilities: Iterable[str] = (),
    require_api_key: bool = True,
    parameter_overrides: Mapping[str, Any] | None = None,
) -> tuple[BaseChatModel, ResolvedModelTarget, dict[str, Any]]:
    """Build the provider-specific LangChain writer model without making a request."""
    task_config = config.task(task)
    route = config.resolve_target(task, target=target)
    effective_params = {
        **task_config.params,
        **route.request_parameters,
        **({} if parameter_overrides is None else dict(parameter_overrides)),
    }
    if seed is not None:
        effective_params["seed"] = seed
    model_override = effective_params.pop("model", None)
    if model_override is not None:
        requested_model = str(model_override)
        route = ResolvedModelTarget(
            target_id=route.target_id,
            provider=route.provider,
            requested_model=requested_model,
            resolved_model=resolve_model(requested_model),
            capabilities=route.capabilities,
            request_parameters=dict(route.request_parameters),
            rate_limit=route.rate_limit,
            max_concurrency=route.max_concurrency,
            configured_target_id=route.configured_target_id,
        )

    required = set(required_capabilities)
    if "seed" in effective_params:
        required.add("seed")
    _validate_capabilities(route, required)

    provider = config.provider(route.provider)
    api_key = provider.resolve_api_key() if require_api_key else "offline-placeholder"
    model_metadata = {
        "eal_transport": "langchain",
        "eal_task": task_config.name,
        "eal_target_id": route.target_id,
        "eal_provider": route.provider,
        "eal_requested_model": route.requested_model,
        "eal_resolved_model": route.resolved_model,
        "eal_effective_params": _jsonable(effective_params),
    }
    provider_model_params = _provider_model_params(route, effective_params)
    common: dict[str, Any] = {
        "model": route.resolved_model,
        "api_key": api_key,
        "base_url": provider.base_url,
        "callbacks": list(callbacks),
        "metadata": model_metadata,
        "tags": [
            "soar",
            f"task:{task_config.name}",
            f"provider:{route.provider}",
            f"target:{route.target_id}",
        ],
        "max_retries": task_config.max_retries,
        "rate_limiter": _rate_limiter(route),
        **provider_model_params,
    }
    if route.provider == "openrouter":
        model: BaseChatModel = ChatOpenRouter(**common)
    else:
        model = ChatOpenAI(**common)
    return model, route, dict(effective_params)


class LangChainCallLogger(AsyncCallbackHandler):
    """Write underlying LangMem chat-model calls and expose attempt-level provenance."""

    def __init__(self, logger: JSONLLogger):
        self.logger = logger
        self._pending: dict[str, dict[str, Any]] = {}
        self._records: dict[str, dict[str, Any]] = {}
        self._attempt_run_ids: dict[str, list[str]] = {}
        self._permanent_error_events: dict[str, asyncio.Event] = {}
        self._permanent_errors: dict[str, BaseException] = {}

    @property
    def records_by_run_id(self) -> dict[str, dict[str, Any]]:
        return dict(self._records)

    def observation(self, memory_attempt_id: str) -> dict[str, Any]:
        run_ids = list(self._attempt_run_ids.get(memory_attempt_id, ()))
        records = [self._records[run_id] for run_id in run_ids if run_id in self._records]
        return {
            "memory_attempt_id": memory_attempt_id,
            "call_count": len(records),
            "run_ids": run_ids,
            "response_models": [record.get("response_model") for record in records],
            "finish_reasons": [
                (
                    record["response"].get("finish_reason")
                    if isinstance(record.get("response"), Mapping)
                    else None
                )
                for record in records
            ],
            "errors": [record.get("error") for record in records],
        }

    async def wait_for_permanent_error(
        self, memory_attempt_id: str
    ) -> BaseException:
        event = self._permanent_error_events.setdefault(
            memory_attempt_id, asyncio.Event()
        )
        await event.wait()
        return self._permanent_errors[memory_attempt_id]

    def clear_permanent_error_watch(self, memory_attempt_id: str) -> None:
        self._permanent_error_events.pop(memory_attempt_id, None)
        self._permanent_errors.pop(memory_attempt_id, None)

    async def finalize_attempt_error(
        self,
        memory_attempt_id: str,
        error: BaseException,
        *,
        termination: str,
    ) -> None:
        """Persist provider calls left pending by an outer cancellation."""

        pending_run_ids = [
            run_id
            for run_id, pending in self._pending.items()
            if str(pending["metadata"].get("memory_attempt_id"))
            == memory_attempt_id
        ]
        for run_id in pending_run_ids:
            pending = self._pending.pop(run_id)
            metadata = pending["metadata"]
            record = {
                "ts": pending["ts"],
                "call_id": metadata.get("call_id"),
                "transport": "langchain",
                "langchain_run_id": run_id,
                "langchain_parent_run_id": pending["parent_run_id"],
                "tags": pending["tags"],
                "metadata": metadata,
                "task": metadata.get("eal_task"),
                "target_id": metadata.get("eal_target_id"),
                "provider": metadata.get("eal_provider"),
                "requested_model": metadata.get("eal_requested_model"),
                "resolved_model": metadata.get("eal_resolved_model"),
                "response_model": None,
                "model": metadata.get("eal_resolved_model"),
                "request": pending["request"],
                "response": None,
                "usage": None,
                "latency_ms": round(
                    (time.monotonic() - pending["started"]) * 1000
                ),
                "attempts": None,
                "error": f"{type(error).__name__}: {error}",
                "termination": termination,
            }
            self._records[run_id] = record
            await self.logger.log(record)

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        del serialized
        run_key = str(run_id)
        safe_metadata = _jsonable(metadata or {})
        memory_attempt_id = safe_metadata.get("memory_attempt_id")
        if memory_attempt_id is not None:
            attempt_key = str(memory_attempt_id)
            self._attempt_run_ids.setdefault(attempt_key, []).append(run_key)

        batches = [_serialize_messages(batch) for batch in messages]
        raw_invocation_params = kwargs.get("invocation_params") or {}
        raw_options = kwargs.get("options") or {}
        raw_tools = None
        if isinstance(raw_options, Mapping):
            raw_tools = raw_options.get("tools")
        if raw_tools is None and isinstance(raw_invocation_params, Mapping):
            raw_tools = raw_invocation_params.get("tools")
        tools = _serialize_tools(raw_tools)
        invocation_params = _jsonable(raw_invocation_params)
        if isinstance(invocation_params, dict) and raw_tools is not None:
            invocation_params["tools"] = tools
        observed_capabilities: set[str] = set()
        if tools:
            observed_capabilities.add("native_tools")
        tool_choice = (
            raw_options.get("tool_choice")
            if isinstance(raw_options, Mapping)
            else None
        )
        if tool_choice is None and isinstance(raw_invocation_params, Mapping):
            tool_choice = raw_invocation_params.get("tool_choice")
        tool_choice = _jsonable(tool_choice)
        if isinstance(invocation_params, dict) and tool_choice is not None:
            invocation_params["tool_choice"] = tool_choice
        if tool_choice not in (None, "auto", "none"):
            observed_capabilities.add("forced_tool_choice")
        if isinstance(invocation_params, Mapping) and "seed" in invocation_params:
            observed_capabilities.add("seed")
        self._pending[run_key] = {
            "started": time.monotonic(),
            "ts": _utcnow_iso(),
            "parent_run_id": None if parent_run_id is None else str(parent_run_id),
            "tags": _jsonable(tags or []),
            "metadata": safe_metadata,
            "request": {
                "messages": batches[0] if len(batches) == 1 else None,
                "message_batches": batches if len(batches) != 1 else None,
                "params": invocation_params,
                "tools": tools,
                "tool_choice": tool_choice,
                "required_capabilities": sorted(observed_capabilities),
            },
        }

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, tags, kwargs
        run_key = str(run_id)
        pending = self._pending.pop(run_key, None) or {
            "started": time.monotonic(),
            "ts": _utcnow_iso(),
            "parent_run_id": None,
            "tags": [],
            "metadata": {},
            "request": None,
        }
        generation = _first_generation(response)
        message = None if generation is None else getattr(generation, "message", None)
        finish_reason = _finish_reason(response, generation)
        metadata = pending["metadata"]
        record = {
            "ts": pending["ts"],
            "call_id": metadata.get("call_id"),
            "transport": "langchain",
            "langchain_run_id": run_key,
            "langchain_parent_run_id": pending["parent_run_id"],
            "tags": pending["tags"],
            "metadata": metadata,
            "task": metadata.get("eal_task"),
            "target_id": metadata.get("eal_target_id"),
            "provider": metadata.get("eal_provider"),
            "requested_model": metadata.get("eal_requested_model"),
            "resolved_model": metadata.get("eal_resolved_model"),
            "response_model": _response_model(response, generation),
            "model": metadata.get("eal_resolved_model"),
            "request": pending["request"],
            "response": (
                None
                if message is None
                else {
                    "content": _jsonable(getattr(message, "content", None)),
                    "tool_calls": _jsonable(getattr(message, "tool_calls", None)),
                    "invalid_tool_calls": _jsonable(
                        getattr(message, "invalid_tool_calls", None)
                    ),
                    "finish_reason": finish_reason,
                    "provider_metadata": _jsonable(
                        getattr(message, "response_metadata", None)
                    ),
                }
            ),
            "usage": _usage(response, generation),
            "latency_ms": round((time.monotonic() - pending["started"]) * 1000),
            "attempts": None,
            "error": None,
        }
        self._records[run_key] = record
        await self.logger.log(record)

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        del parent_run_id, tags, kwargs
        run_key = str(run_id)
        pending = self._pending.pop(run_key, None) or {
            "started": time.monotonic(),
            "ts": _utcnow_iso(),
            "parent_run_id": None,
            "tags": [],
            "metadata": {},
            "request": None,
        }
        metadata = pending["metadata"]
        record = {
            "ts": pending["ts"],
            "call_id": metadata.get("call_id"),
            "transport": "langchain",
            "langchain_run_id": run_key,
            "langchain_parent_run_id": pending["parent_run_id"],
            "tags": pending["tags"],
            "metadata": metadata,
            "task": metadata.get("eal_task"),
            "target_id": metadata.get("eal_target_id"),
            "provider": metadata.get("eal_provider"),
            "requested_model": metadata.get("eal_requested_model"),
            "resolved_model": metadata.get("eal_resolved_model"),
            "response_model": None,
            "model": metadata.get("eal_resolved_model"),
            "request": pending["request"],
            "response": None,
            "usage": None,
            "latency_ms": round((time.monotonic() - pending["started"]) * 1000),
            "attempts": None,
            "error": f"{type(error).__name__}: {error}",
        }
        self._records[run_key] = record
        await self.logger.log(record)
        memory_attempt_id = metadata.get("memory_attempt_id")
        if (
            memory_attempt_id is not None
            and _is_permanent_provider_error(error)
        ):
            attempt_key = str(memory_attempt_id)
            self._permanent_errors[attempt_key] = error
            self._permanent_error_events.setdefault(
                attempt_key, asyncio.Event()
            ).set()
