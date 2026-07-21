"""The client. OpenAI-shaped in and out; every provider runs through the `openai` SDK by
swapping base_url + api_key. Calls are rate-limited, concurrency-capped, retried, and logged.

    llm = LLM()
    resp = llm.complete("default", messages=[...])       # sync
    results = llm.batch("default", [msgs1, msgs2, ...])   # parallel
    answer = await llm.acomplete("default", messages=[...])
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from openai.types.chat import ChatCompletion
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .config import Config, ResolvedModelTarget, TaskConfig, load_config
from .errors import ConfigError
from .logger import JSONLLogger
from .ratelimit import GateRegistry

# Transient failures worth retrying. Auth/validation errors are NOT here — they fail fast.
RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_message(msg) -> dict[str, Any]:
    """Pull the parts of an assistant message we want in the log (content + tool calls)."""
    tool_calls = None
    if getattr(msg, "tool_calls", None):
        tool_calls = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return {"content": msg.content, "tool_calls": tool_calls}


def _capability_requirements(
    params: dict[str, Any],
    required_capabilities: Iterable[str],
) -> frozenset[str]:
    required = {str(capability).strip() for capability in required_capabilities}
    required.discard("")
    if params.get("tools"):
        required.add("native_tools")
    tool_choice = params.get("tool_choice")
    if tool_choice not in (None, "auto", "none"):
        required.add("forced_tool_choice")
    if "seed" in params:
        required.add("seed")
    return frozenset(required)


def _validate_capabilities(
    route: ResolvedModelTarget,
    required: frozenset[str],
) -> None:
    missing = sorted(required - route.capabilities)
    if missing:
        available = ", ".join(sorted(route.capabilities)) or "(none)"
        raise ConfigError(
            f"Model target '{route.target_id}' lacks required capabilities: "
            f"{', '.join(missing)}. Declared capabilities: {available}."
        )


class LLM:
    def __init__(
        self,
        config: Config | str | None = None,
        *,
        logger: JSONLLogger | None = None,
        transport_max_retries: int | None = None,
    ):
        """`config`: a Config, a path to a YAML file, or None to load ./config.yaml.
        `logger`: override where calls are logged (e.g. per-run log file).
        `transport_max_retries`: optional OpenAI-SDK retry bound; task retries remain
        benchmark-owned."""
        if (
            transport_max_retries is not None
            and (
                isinstance(transport_max_retries, bool)
                or not isinstance(transport_max_retries, int)
                or transport_max_retries < 0
            )
        ):
            raise ValueError("transport_max_retries must be a non-negative integer")
        if config is None:
            self.config = load_config()
        elif isinstance(config, Config):
            self.config = config
        else:
            self.config = load_config(config)

        self.logger = logger or JSONLLogger(self.config.log_path)
        self._gates = GateRegistry()
        self._clients: dict[str, AsyncOpenAI] = {}
        self.transport_max_retries = transport_max_retries

    # -- provider clients -----------------------------------------------------------

    def _client_for(self, provider_name: str) -> AsyncOpenAI:
        client = self._clients.get(provider_name)
        if client is None:
            p = self.config.provider(provider_name)
            kwargs: dict[str, Any] = {
                "base_url": p.base_url,
                "api_key": p.resolve_api_key(),
            }
            if self.transport_max_retries is not None:
                kwargs["max_retries"] = self.transport_max_retries
            client = AsyncOpenAI(**kwargs)
            self._clients[provider_name] = client
        return client

    def preflight(
        self,
        task: str,
        *,
        target: str | None = None,
        model: str | None = None,
        required_capabilities: Iterable[str] = (),
        require_api_key: bool = True,
    ) -> ResolvedModelTarget:
        """Resolve and validate a call route without making an API request."""
        route = self.config.resolve_target(task, target=target, model=model)
        _validate_capabilities(
            route, _capability_requirements({}, required_capabilities)
        )
        if require_api_key:
            self.config.provider(route.provider).resolve_api_key()
        return route

    # -- async core -----------------------------------------------------------------

    async def acomplete(
        self,
        task: str,
        messages: list[dict[str, Any]],
        *,
        target: str | None = None,
        call_id: str | None = None,
        required_capabilities: Iterable[str] = (),
        **overrides: Any,
    ) -> ChatCompletion:
        """One completion for `task`. Extra kwargs (temperature, tools, ...) override the
        task defaults and pass through. `target=` can switch provider and model together;
        `model=` remains a same-provider override."""
        if call_id is not None and (
            not isinstance(call_id, str) or not call_id.strip()
        ):
            raise ValueError("call_id must be a non-empty string or None")
        tc: TaskConfig = self.config.task(task)

        initial_route = self.config.resolve_target(task, target=target)
        params = {
            **tc.params,
            **initial_route.request_parameters,
            **overrides,
        }
        model_override = params.pop("model", None)
        route = (
            initial_route
            if model_override is None
            else self.config.resolve_target(
                task,
                target=target,
                model=str(model_override),
            )
        )
        required = _capability_requirements(params, required_capabilities)
        _validate_capabilities(route, required)
        client = self._client_for(route.provider)
        gate = self._gates.get(
            route.gate_key,
            max_concurrency=route.max_concurrency,
            rate_limit=route.rate_limit,
        )
        request_log = {
            "messages": messages,
            "params": params,
            "tools": params.get("tools"),
            "required_capabilities": sorted(required),
        }

        started = time.monotonic()
        attempts = 0
        try:
            async with gate.slot():
                async for attempt in AsyncRetrying(
                    retry=retry_if_exception_type(RETRYABLE),
                    wait=wait_random_exponential(multiplier=1, max=30),
                    stop=stop_after_attempt(tc.max_retries),
                    reraise=True,
                ):
                    with attempt:
                        attempts = attempt.retry_state.attempt_number
                        resp = await client.chat.completions.create(
                            model=route.resolved_model, messages=messages, **params
                        )
        except Exception as exc:  # noqa: BLE001 — we log every failure then re-raise
            await self._log(
                tc,
                route,
                request_log,
                None,
                attempts,
                started,
                call_id=call_id,
                error=exc,
            )
            raise

        await self._log(
            tc,
            route,
            request_log,
            resp,
            attempts,
            started,
            call_id=call_id,
            error=None,
        )
        return resp

    async def abatch(
        self,
        task: str,
        messages_list: Iterable[list[dict[str, Any]]],
        *,
        target: str | None = None,
        call_ids: Iterable[str | None] | None = None,
        required_capabilities: Iterable[str] = (),
        batch_size: int | None = None,
        max_batch_retries: int = 3,
        return_exceptions: bool = False,
        **overrides: Any,
    ) -> list[ChatCompletion]:
        """Many completions in parallel, in waves of `batch_size`, retrying failures until
        all have a result. Results stay in input order. Stragglers that fail every
        `max_batch_retries` waves raise, or land in-slot with `return_exceptions=True`."""
        items = list(messages_list)
        logical_call_ids = (
            [None] * len(items) if call_ids is None else list(call_ids)
        )
        if len(logical_call_ids) != len(items):
            raise ValueError(
                "call_ids must contain exactly one entry per messages_list item"
            )
        invalid_call_ids = [
            value
            for value in logical_call_ids
            if value is not None
            and (not isinstance(value, str) or not value.strip())
        ]
        if invalid_call_ids:
            raise ValueError("call_ids entries must be non-empty strings or None")
        materialized_ids = [
            value for value in logical_call_ids if value is not None
        ]
        if len(materialized_ids) != len(set(materialized_ids)):
            raise ValueError("non-null call_ids entries must be unique")
        required_capabilities = tuple(required_capabilities)
        results: list[Any] = [None] * len(items)
        if not items:
            return results

        size = batch_size or self.config.batch_size
        pending = list(range(len(items)))
        last_exc: dict[int, Exception] = {}

        for _ in range(max(1, max_batch_retries)):
            if not pending:
                break
            retry_next: list[int] = []
            for start in range(0, len(pending), size):
                wave = pending[start : start + size]
                done = await asyncio.gather(
                    *(
                        self.acomplete(
                            task,
                            items[i],
                            target=target,
                            call_id=logical_call_ids[i],
                            required_capabilities=required_capabilities,
                            **overrides,
                        )
                        for i in wave
                    ),
                    return_exceptions=True,
                )
                for i, r in zip(wave, done):
                    if isinstance(r, Exception):
                        last_exc[i] = r
                        retry_next.append(i)
                    else:
                        results[i] = r
                        last_exc.pop(i, None)
            pending = retry_next

        if pending and not return_exceptions:
            raise last_exc[pending[0]]
        for i in pending:
            results[i] = last_exc[i]
        return results

    # -- sync wrappers --------------------------------------------------------------

    def complete(
        self,
        task: str,
        messages: list[dict[str, Any]],
        *,
        target: str | None = None,
        call_id: str | None = None,
        required_capabilities: Iterable[str] = (),
        **overrides: Any,
    ) -> ChatCompletion:
        return _run_sync(
            self.acomplete(
                task,
                messages,
                target=target,
                call_id=call_id,
                required_capabilities=required_capabilities,
                **overrides,
            )
        )

    def batch(
        self,
        task: str,
        messages_list: Iterable[list[dict[str, Any]]],
        *,
        target: str | None = None,
        call_ids: Iterable[str | None] | None = None,
        required_capabilities: Iterable[str] = (),
        batch_size: int | None = None,
        max_batch_retries: int = 3,
        return_exceptions: bool = False,
        **overrides: Any,
    ) -> list[ChatCompletion]:
        return _run_sync(
            self.abatch(
                task,
                messages_list,
                target=target,
                call_ids=call_ids,
                required_capabilities=required_capabilities,
                batch_size=batch_size,
                max_batch_retries=max_batch_retries,
                return_exceptions=return_exceptions,
                **overrides,
            )
        )

    # -- logging --------------------------------------------------------------------

    async def _log(
        self,
        tc: TaskConfig,
        route: ResolvedModelTarget,
        request_log: dict[str, Any],
        resp: ChatCompletion | None,
        attempts: int,
        started: float,
        *,
        call_id: str | None,
        error: Exception | None,
    ) -> None:
        response_model = (
            str(resp.model) if resp is not None and getattr(resp, "model", None) else None
        )
        record: dict[str, Any] = {
            "ts": _utcnow_iso(),
            "call_id": call_id,
            "task": tc.name,
            "target_id": route.target_id,
            "provider": route.provider,
            "requested_model": route.requested_model,
            "resolved_model": route.resolved_model,
            "response_model": response_model,
            "model": route.resolved_model,
            "request": request_log,
            "response": None,
            "usage": None,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "attempts": attempts,
            "error": None if error is None else f"{type(error).__name__}: {error}",
        }
        if resp is not None:
            choice = resp.choices[0]
            record["response"] = {
                **_serialize_message(choice.message),
                "finish_reason": choice.finish_reason,
            }
            if resp.usage is not None:
                record["usage"] = resp.usage.model_dump()
        await self.logger.log(record)


def _run_sync(coro):
    """Run an async coroutine from sync code; errors if a loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "Sync methods (complete/batch) cannot be called from a running event loop. "
        "Use the async API (acomplete/abatch) instead."
    )


async def run_tool_loop(
    llm: LLM,
    task: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    handlers: dict[str, Callable[..., Any]],
    *,
    max_turns: int = 10,
    **overrides: Any,
) -> list[dict[str, Any]]:
    """Drive a full tool-calling loop: call the model, run the matching `handlers`
    ({name: callable}) for any tool_calls, feed results back, repeat until it stops (or
    max_turns). Handlers take parsed JSON args as kwargs. Returns the final messages."""
    import json

    messages = list(messages)
    for _ in range(max_turns):
        resp = await llm.acomplete(task, messages, tools=tools, **overrides)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content})
            return messages

        # Echo the assistant's tool-call turn, then answer each call.
        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            if name not in handlers:
                result = f"Error: no handler registered for tool '{name}'."
            else:
                result = handlers[name](**args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result if isinstance(result, str) else json.dumps(result),
                }
            )
    raise RuntimeError(f"run_tool_loop exceeded max_turns={max_turns} without finishing.")
