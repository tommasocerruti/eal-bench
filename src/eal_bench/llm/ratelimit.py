"""Per-target rate + concurrency gates."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from aiolimiter import AsyncLimiter

from .config import RateLimit


class TaskGate:
    """Concurrency + rate gate for one provider/target route."""

    def __init__(self, max_concurrency: int, max_rate: float | None, period_seconds: float):
        self._sem = asyncio.Semaphore(max_concurrency)
        self._limiter = (
            AsyncLimiter(max_rate, period_seconds) if max_rate and max_rate > 0 else None
        )

    @asynccontextmanager
    async def slot(self):
        """Hold one concurrency slot and one rate-limit token for the duration."""
        async with self._sem:
            if self._limiter is not None:
                async with self._limiter:
                    yield
            else:
                yield


class GateRegistry:
    """One gate per provider/target route, built lazily on first use."""

    def __init__(self):
        self._gates: dict[str, TaskGate] = {}

    def get(
        self,
        route: str,
        *,
        max_concurrency: int | None = None,
        rate_limit: RateLimit | None = None,
    ) -> TaskGate:
        if max_concurrency is None or rate_limit is None:
            raise TypeError(
                "max_concurrency and rate_limit are required for a target route."
            )
        gate = self._gates.get(route)
        if gate is None:
            gate = TaskGate(
                max_concurrency=max_concurrency,
                max_rate=rate_limit.max_rate,
                period_seconds=rate_limit.period_seconds,
            )
            self._gates[route] = gate
        return gate
