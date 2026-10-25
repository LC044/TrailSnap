"""Nightly coverage for AI admission gate edge paths (2026-10-24).

之前只覆盖了「队列已满 -> 429」这一条路径；等待超时（asyncio.TimeoutError ->
429）与 slot() 上下文管理器（无论正常退出还是抛异常都要归还信号量）都没被测到。
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.config import settings
from app.core.admission import AdmissionGate


pytestmark = [pytest.mark.smoke]


@pytest.mark.asyncio
async def test_acquire_timeout_raises_429_and_resets_waiting_counter(monkeypatch):
    monkeypatch.setattr(settings, "AI_ADMISSION_QUEUE", 5)
    monkeypatch.setattr(settings, "AI_ADMISSION_WAIT_SECONDS", 0.05)
    gate = AdmissionGate("timeout-gate", concurrency=1)

    await gate.acquire()
    try:
        with pytest.raises(HTTPException) as exc_info:
            await gate.acquire()
    finally:
        gate.release()

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "5"
    # 超时后等待计数必须回落，否则后续请求会被误判成「队列已满」。
    assert gate._waiting == 0


@pytest.mark.asyncio
async def test_slot_releases_semaphore_on_normal_exit():
    gate = AdmissionGate("slot-gate", concurrency=1)

    async with gate.slot():
        assert gate._semaphore.locked()

    assert not gate._semaphore.locked()
    # 释放后可以立刻再次获取，不会被排队。
    await asyncio.wait_for(gate.acquire(), timeout=1.0)
    gate.release()


@pytest.mark.asyncio
async def test_slot_releases_semaphore_when_body_raises():
    gate = AdmissionGate("slot-gate", concurrency=1)

    with pytest.raises(RuntimeError):
        async with gate.slot():
            raise RuntimeError("boom")

    assert not gate._semaphore.locked()
    assert gate._waiting == 0


@pytest.mark.asyncio
async def test_concurrency_is_at_least_one_even_for_zero_limit():
    gate = AdmissionGate("zero-gate", concurrency=0)

    await asyncio.wait_for(gate.acquire(), timeout=1.0)
    assert gate._semaphore.locked()
    gate.release()
