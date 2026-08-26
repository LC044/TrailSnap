"""Round 2026-08-26 coverage gaps for day_caption_service."""

import asyncio
from datetime import datetime, timezone

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_moment]


def test_get_user_lock_creates_and_caches_per_user_id():
    from app.service.moment import day_caption_service as svc

    svc._user_locks.clear()

    async def runner():
        a1 = await svc._get_user_lock("user-a")
        a2 = await svc._get_user_lock("user-a")
        b1 = await svc._get_user_lock("user-b")
        return a1, a2, b1

    a1, a2, b1 = asyncio.run(runner())

    assert isinstance(a1, asyncio.Lock)
    assert a1 is a2
    assert a1 is not b1


def test_resolve_tz_returns_utc_for_empty_tz_name():
    from app.service.moment import day_caption_service as svc

    assert svc._resolve_tz("") == timezone.utc


def test_resolve_tz_returns_utc_for_invalid_timezone():
    from app.service.moment import day_caption_service as svc

    assert svc._resolve_tz("Not/A_Real_Zone") == timezone.utc


def test_day_bounds_utc_returns_naive_day_window():
    from datetime import date
    from app.service.moment import day_caption_service as svc

    day = date(2026, 8, 26)
    start, end = svc.day_bounds_utc(day, "Asia/Shanghai")

    assert start == datetime(2026, 8, 26, 0, 0, 0)
    assert end == datetime(2026, 8, 27, 0, 0, 0)
    assert start.tzinfo is None
    assert end.tzinfo is None
