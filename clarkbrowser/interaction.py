# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Small interaction pacing helpers for reliable Playwright automation."""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Awaitable, Callable

_DEFAULT_MIN_INTERVAL_MS = 350
_DEFAULT_JITTER_MS = 200
_DEFAULT_SAME_TARGET_COOLDOWN_MS = 900


class _PacerState:
    def __init__(
        self,
        *,
        min_interval_ms: int,
        jitter_ms: int,
        same_target_cooldown_ms: int,
        seed: int | None,
        now_fn: Callable[[], float],
    ) -> None:
        if min_interval_ms < 0 or jitter_ms < 0 or same_target_cooldown_ms < 0:
            raise ValueError("pacing intervals must be non-negative")
        self.min_interval_s = min_interval_ms / 1000
        self.jitter_s = jitter_ms / 1000
        self.same_target_cooldown_s = same_target_cooldown_ms / 1000
        self._rng = random.Random(seed)
        self._now_fn = now_fn
        self._last_action_at: float | None = None
        self._last_target_at: dict[str, float] = {}

    def delay_for(self, target: str | None = None) -> float:
        now = self._now_fn()
        delay = 0.0
        if self._last_action_at is not None:
            delay = max(delay, self.min_interval_s - (now - self._last_action_at))
        if target and target in self._last_target_at:
            delay = max(
                delay,
                self.same_target_cooldown_s - (now - self._last_target_at[target]),
            )
        if delay > 0 and self.jitter_s > 0:
            delay += self._rng.uniform(0.0, self.jitter_s)
        return max(0.0, delay)

    def record(self, target: str | None = None) -> None:
        now = self._now_fn()
        self._last_action_at = now
        if target:
            self._last_target_at[target] = now


class InteractionPacer:
    """Rate-limit sync Playwright actions so scripts do not burst-click.

    The helper is intentionally small: it waits between actions, adds bounded
    jitter only when a wait is already needed, and applies a longer cooldown
    when the same target is clicked repeatedly.
    """

    def __init__(
        self,
        *,
        min_interval_ms: int = _DEFAULT_MIN_INTERVAL_MS,
        jitter_ms: int = _DEFAULT_JITTER_MS,
        same_target_cooldown_ms: int = _DEFAULT_SAME_TARGET_COOLDOWN_MS,
        seed: int | None = None,
        now_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._now_fn = now_fn or time.monotonic
        self._sleep_fn = sleep_fn or time.sleep
        self._state = _PacerState(
            min_interval_ms=min_interval_ms,
            jitter_ms=jitter_ms,
            same_target_cooldown_ms=same_target_cooldown_ms,
            seed=seed,
            now_fn=self._now_fn,
        )

    def wait(self, target: str | None = None) -> float:
        delay = self._state.delay_for(target)
        if delay > 0:
            self._sleep_fn(delay)
        self._state.record(target)
        return delay

    def click(
        self, page_or_locator: Any, selector: str | None = None, **kwargs: Any
    ) -> Any:
        target = f"click:{selector}" if selector else f"click:{page_or_locator!r}"
        self.wait(target)
        if selector:
            return page_or_locator.locator(selector).click(**kwargs)
        return page_or_locator.click(**kwargs)


class AsyncInteractionPacer:
    """Async variant of InteractionPacer."""

    def __init__(
        self,
        *,
        min_interval_ms: int = _DEFAULT_MIN_INTERVAL_MS,
        jitter_ms: int = _DEFAULT_JITTER_MS,
        same_target_cooldown_ms: int = _DEFAULT_SAME_TARGET_COOLDOWN_MS,
        seed: int | None = None,
        now_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._now_fn = now_fn or time.monotonic
        self._sleep_fn = sleep_fn or asyncio.sleep
        self._state = _PacerState(
            min_interval_ms=min_interval_ms,
            jitter_ms=jitter_ms,
            same_target_cooldown_ms=same_target_cooldown_ms,
            seed=seed,
            now_fn=self._now_fn,
        )

    async def wait(self, target: str | None = None) -> float:
        delay = self._state.delay_for(target)
        if delay > 0:
            await self._sleep_fn(delay)
        self._state.record(target)
        return delay

    async def click(
        self, page_or_locator: Any, selector: str | None = None, **kwargs: Any
    ) -> Any:
        target = f"click:{selector}" if selector else f"click:{page_or_locator!r}"
        await self.wait(target)
        if selector:
            return await page_or_locator.locator(selector).click(**kwargs)
        return await page_or_locator.click(**kwargs)
