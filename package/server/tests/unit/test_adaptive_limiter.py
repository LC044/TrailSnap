import asyncio

import pytest

from app.service.adaptive_limiter import AdaptiveResourceLimiter


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.mark.asyncio
async def test_limiter_additively_increases_after_stable_successes():
    changes = []
    limiter = AdaptiveResourceLimiter(
        "ocr", 1, 3,
        success_threshold=2,
        cooldown_seconds=0,
        on_change=lambda *args: changes.append(args),
    )

    await limiter.record_success()
    assert limiter.current_limit == 1
    await limiter.record_success()
    assert limiter.current_limit == 2
    assert changes[-1] == ("ocr", 2, "stable_success")


@pytest.mark.asyncio
async def test_limiter_halves_on_overload_and_never_below_one():
    limiter = AdaptiveResourceLimiter("visual_llm", 4, 4, cooldown_seconds=0)

    await limiter.record_overload("timeout")
    assert limiter.current_limit == 2
    await limiter.record_overload("timeout")
    assert limiter.current_limit == 1
    await limiter.record_overload("timeout")
    assert limiter.current_limit == 1


@pytest.mark.asyncio
async def test_limiter_shrink_does_not_cancel_in_flight_work():
    limiter = AdaptiveResourceLimiter("face", 2, 2, cooldown_seconds=0)
    await limiter.acquire()
    await limiter.acquire()
    await limiter.record_overload("cpu")

    blocked = asyncio.create_task(limiter.acquire())
    await asyncio.sleep(0)
    assert not blocked.done()
    await limiter.release()
    await asyncio.sleep(0)
    assert not blocked.done()
    await limiter.release()
    await asyncio.wait_for(blocked, timeout=1)
    await limiter.release()


@pytest.mark.asyncio
async def test_one_pressure_sample_cannot_repeatedly_halve_concurrency(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('app.service.adaptive_limiter.time.monotonic', lambda: clock[0])
    limiter = AdaptiveResourceLimiter('cpu', 16, 16, cooldown_seconds=5)
    await asyncio.gather(*(limiter.record_overload('system_pressure') for _ in range(16)))
    assert limiter.current_limit == 8
    clock[0] += 5
    await limiter.record_overload('system_pressure', floor=4)
    assert limiter.current_limit == 4
    clock[0] += 5
    await limiter.record_overload('system_pressure', floor=4)
    assert limiter.current_limit == 4
    await limiter.record_overload('memory', floor=1)
    assert limiter.current_limit == 2


@pytest.mark.asyncio
async def test_import_reservation_recovers_a_persisted_low_limit():
    limiter = AdaptiveResourceLimiter('cpu', 1, 8)
    await limiter.ensure_capacity(4)
    assert limiter.current_limit == 4
