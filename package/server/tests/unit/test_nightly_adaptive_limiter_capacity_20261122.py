"""Nightly watch 2026-11-22 · app/service/adaptive_limiter.py::has_capacity / _set_limit 盲区。

这两个是限流器的内部判据：
- ``has_capacity(ceiling)`` 决定是否还能再拿一个名额，必须同时满足
  「当前并发 < 当前上限」和「当前并发 < 传入的天花板（取更小者）」。
- ``_set_limit(value, reason)`` 把上限夹在 [min_limit, max_limit] 内，并且
  只有真正发生变化时才回调 on_change（避免噪声通知）。

既有 test_adaptive_limiter.py 覆盖了增减策略，但没有直接锁定这两个判据本身。

本文件覆盖：
- has_capacity 受 min(current_limit, ceiling) 约束（happy）
- has_capacity 在并发已满时返回 False（edge）
- has_capacity 不传 ceiling 时使用 max_limit（edge）
- _set_limit 夹紧到 min/max 边界（edge）
- _set_limit 值未变化时不触发 on_change（error / 无变化）
"""

import pytest

from app.service.adaptive_limiter import AdaptiveResourceLimiter

pytestmark = [pytest.mark.smoke]


def _limiter(**kwargs):
    kwargs.setdefault("name", "test")
    kwargs.setdefault("initial_limit", 2)
    kwargs.setdefault("max_limit", 4)
    kwargs.setdefault("min_limit", 1)
    return AdaptiveResourceLimiter(**kwargs)


def test_has_capacity_is_bounded_by_the_smaller_of_current_limit_and_ceiling():
    limiter = _limiter(initial_limit=2, max_limit=8)

    assert limiter.has_capacity() is True
    # 并发 0，但天花板是 0 -> 依然没有名额
    assert limiter.has_capacity(ceiling=0) is False
    assert limiter.has_capacity(ceiling=1) is True


def test_has_capacity_returns_false_once_the_current_limit_is_reached():
    limiter = _limiter(initial_limit=2, max_limit=2)

    limiter._in_use = 2

    assert limiter.has_capacity() is False


def test_has_capacity_without_a_ceiling_uses_the_max_limit():
    limiter = _limiter(initial_limit=1, max_limit=8)

    limiter._in_use = 5

    # current_limit(1) 小于 max_limit(8)，所以仍然没有名额
    assert limiter.has_capacity() is False


def test_set_limit_clamps_the_value_into_the_min_max_range():
    limiter = _limiter(initial_limit=2, max_limit=4, min_limit=1)

    limiter._set_limit(99, "too_high")
    assert limiter.current_limit == 4

    limiter._set_limit(0, "too_low")
    assert limiter.current_limit == 1


def test_set_limit_notifies_only_when_the_limit_actually_changes():
    changes = []
    limiter = _limiter(initial_limit=2, max_limit=4,
                       on_change=lambda name, value, reason: changes.append((name, value, reason)))

    limiter._set_limit(2, "same")
    assert changes == []

    limiter._set_limit(3, "grow")
    assert changes == [("test", 3, "grow")]

    # 夹紧到 max_limit=4 仍然是变化 -> 会通知，且值被夹到 4
    limiter._set_limit(99, "clamped_to_max")
    assert changes == [("test", 3, "grow"), ("test", 4, "clamped_to_max")]
    assert limiter.current_limit == 4

    # 再次设为同一个值 -> 不重复通知
    limiter._set_limit(4, "same")
    assert changes == [("test", 3, "grow"), ("test", 4, "clamped_to_max")]

