"""Async resource limiter with additive-increase/multiplicative-decrease."""

import asyncio
import math
import time
from typing import Callable, Optional


class AdaptiveResourceLimiter:
    """A resizable limiter whose ceiling is supplied by the device profile."""

    def __init__(
        self,
        name: str,
        initial_limit: int,
        max_limit: int,
        *,
        min_limit: int = 1,
        success_threshold: int = 4,
        cooldown_seconds: float = 5.0,
        on_change: Optional[Callable[[str, int, str], None]] = None,
    ):
        self.name = name
        self.min_limit = max(1, min_limit)
        self.max_limit = max(self.min_limit, max_limit)
        self.current_limit = min(
            self.max_limit, max(self.min_limit, initial_limit)
        )
        self.success_threshold = max(1, success_threshold)
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self._on_change = on_change
        self._condition = asyncio.Condition()
        self._in_use = 0
        self._successes = 0
        self._last_change = 0.0

    @property
    def in_use(self) -> int:
        return self._in_use

    async def acquire(self) -> None:
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._in_use < self.current_limit
            )
            self._in_use += 1

    async def release(self) -> None:
        async with self._condition:
            self._in_use = max(0, self._in_use - 1)
            self._condition.notify_all()

    async def record_success(self) -> None:
        async with self._condition:
            self._successes += 1
            now = time.monotonic()
            if (
                self.current_limit < self.max_limit
                and self._successes >= self.success_threshold
                and now - self._last_change >= self.cooldown_seconds
            ):
                self._set_limit(self.current_limit + 1, "stable_success")
                self._successes = 0
                self._last_change = now
                self._condition.notify_all()

    async def record_overload(self, reason: str = "overload") -> None:
        async with self._condition:
            self._successes = 0
            now = time.monotonic()
            reduced = max(self.min_limit, math.floor(self.current_limit / 2))
            if reduced < self.current_limit:
                self._set_limit(reduced, reason)
                self._last_change = now

    def _set_limit(self, value: int, reason: str) -> None:
        value = min(self.max_limit, max(self.min_limit, value))
        if value == self.current_limit:
            return
        self.current_limit = value
        if self._on_change is not None:
            self._on_change(self.name, value, reason)
