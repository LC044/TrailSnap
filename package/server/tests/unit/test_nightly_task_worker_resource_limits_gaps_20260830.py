"""Unit tests covering 2026-08-30 nightly coverage gap scan (round 4).

Target: app/service/task_worker.py `_get_resource_limits`,
`_resource_limiter`, `_make_resource_limiter`, `_on_resource_limit_change`,
`_is_system_overloaded`, `_prefetch_limit` -- small helpers currently
uncovered by the existing test_task_worker.py and
test_nightly_task_worker_gaps_20260815.py suite.

The helpers are pure-ish: they only read system_config + an in-memory
resource_limiters dict, so they can be exercised by patching
system_config.config.task (and the AdaptiveResourceLimiter constructor)
without spinning up a DB.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _bare_worker():
    from app.service import task_worker
    return task_worker.TaskWorker.__new__(task_worker.TaskWorker)


def _task_config(
    *,
    concurrency_level: str = "low",
    adaptive_concurrency: bool = True,
    cpu_high_watermark: float = 90.0,
    memory_high_watermark: float = 90.0,
    aimd_success_threshold: int = 8,
    aimd_cooldown_seconds: float = 1.0,
):
    return SimpleNamespace(
        concurrency_level=concurrency_level,
        adaptive_concurrency=adaptive_concurrency,
        cpu_high_watermark=cpu_high_watermark,
        memory_high_watermark=memory_high_watermark,
        aimd_success_threshold=aimd_success_threshold,
        aimd_cooldown_seconds=aimd_cooldown_seconds,
    )


def test_get_resource_limits_low_level_uses_default_one_per_resource():
    worker = _bare_worker()
    worker._get_concurrency_settings = lambda: {
        "cpu_consumer": 3,
        "io_consumer": 4,
        "ai_consumer": 5,
    }
    with patch(
        "app.service.task_worker.resolve_concurrency_level",
        return_value="low",
    ):
        limits = worker._get_resource_limits()
    assert limits["classification"] == 1
    assert limits["ocr"] == 1
    assert limits["face"] == 1
    assert limits["embedding"] == 1
    assert limits["tickets"] == 1
    assert limits["visual_llm"] == 1
    assert limits["local_llm"] == 1
    assert limits["cpu"] == 3
    assert limits["io"] == 4


def test_get_resource_limits_medium_bumps_face_embedding_visual_llm():
    worker = _bare_worker()
    worker._get_concurrency_settings = lambda: {
        "cpu_consumer": 3,
        "io_consumer": 4,
        "ai_consumer": 5,
    }
    with patch(
        "app.service.task_worker.resolve_concurrency_level",
        return_value="medium",
    ):
        limits = worker._get_resource_limits()
    assert limits["face"] == 2
    assert limits["embedding"] == 2
    assert limits["visual_llm"] == 2
    assert limits["classification"] == 1
    assert limits["ocr"] == 1
    assert limits["tickets"] == 1


def test_get_resource_limits_high_raises_classification_ocr_tickets_visual_llm():
    worker = _bare_worker()
    worker._get_concurrency_settings = lambda: {
        "cpu_consumer": 3,
        "io_consumer": 4,
        "ai_consumer": 5,
    }
    with patch(
        "app.service.task_worker.resolve_concurrency_level",
        return_value="high",
    ):
        limits = worker._get_resource_limits()
    assert limits["classification"] == 2
    assert limits["ocr"] == 2
    assert limits["face"] == 2
    assert limits["embedding"] == 2
    assert limits["tickets"] == 2
    assert limits["visual_llm"] == 4


def test_resource_limiter_creates_then_caches_limiter():
    worker = _bare_worker()
    worker.resource_limiters = {}
    worker.adaptive_limits = {}
    worker._get_resource_limits = lambda: {"face": 2}
    fake_limiter = MagicMock(name="limiter")
    worker._make_resource_limiter = MagicMock(return_value=fake_limiter)

    first = worker._resource_limiter("face")
    second = worker._resource_limiter("face")

    assert first is fake_limiter
    assert second is fake_limiter
    worker._make_resource_limiter.assert_called_once_with("face", 2, None)


def test_resource_limiter_unknown_key_uses_default_ceiling_of_one():
    worker = _bare_worker()
    worker.resource_limiters = {}
    worker.adaptive_limits = {}
    worker._get_resource_limits = lambda: {}
    worker._make_resource_limiter = MagicMock(return_value=MagicMock())

    worker._resource_limiter("ocr")

    worker._make_resource_limiter.assert_called_once_with("ocr", 1, None)


def test_make_resource_limiter_adaptive_uses_half_ceiling_when_no_persisted():
    worker = _bare_worker()
    fake_limiter_cls = MagicMock()
    captured = {}

    def _capture(resource_key, **kwargs):
        captured.update(kwargs)
        return MagicMock(name=f"limiter:{resource_key}")

    fake_limiter_cls.side_effect = _capture

    with patch("app.service.task_worker.AdaptiveResourceLimiter", fake_limiter_cls):
        with patch(
            "app.service.task_worker.system_config",
            SimpleNamespace(config=SimpleNamespace(task=_task_config())),
        ):
            worker._make_resource_limiter("face", 4, None)

    assert captured["initial_limit"] == 2
    assert captured["max_limit"] == 4
    assert captured["success_threshold"] == 8
    assert captured["cooldown_seconds"] == 1.0


def test_make_resource_limiter_adaptive_off_pins_initial_to_ceiling():
    worker = _bare_worker()
    fake_limiter_cls = MagicMock()
    captured = {}

    def _capture(resource_key, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    fake_limiter_cls.side_effect = _capture

    with patch("app.service.task_worker.AdaptiveResourceLimiter", fake_limiter_cls):
        with patch(
            "app.service.task_worker.system_config",
            SimpleNamespace(
                config=SimpleNamespace(
                    task=_task_config(adaptive_concurrency=False),
                )
            ),
        ):
            worker._make_resource_limiter("embedding", 6, None)

    assert captured["initial_limit"] == 6
    assert captured["max_limit"] == 6


def test_make_resource_limiter_adaptive_on_honors_persisted_initial():
    worker = _bare_worker()
    fake_limiter_cls = MagicMock()
    captured = {}

    def _capture(resource_key, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    fake_limiter_cls.side_effect = _capture

    with patch("app.service.task_worker.AdaptiveResourceLimiter", fake_limiter_cls):
        with patch(
            "app.service.task_worker.system_config",
            SimpleNamespace(config=SimpleNamespace(task=_task_config())),
        ):
            worker._make_resource_limiter("visual_llm", 4, "3")

    assert captured["initial_limit"] == 3
    assert captured["max_limit"] == 4


def test_make_resource_limiter_adaptive_off_ignores_persisted_initial():
    worker = _bare_worker()
    fake_limiter_cls = MagicMock()
    captured = {}

    def _capture(resource_key, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    fake_limiter_cls.side_effect = _capture

    with patch("app.service.task_worker.AdaptiveResourceLimiter", fake_limiter_cls):
        with patch(
            "app.service.task_worker.system_config",
            SimpleNamespace(
                config=SimpleNamespace(
                    task=_task_config(adaptive_concurrency=False),
                )
            ),
        ):
            worker._make_resource_limiter("ocr", 2, "9")

    assert captured["initial_limit"] == 2
    assert captured["max_limit"] == 2


def test_make_resource_limiter_falls_back_to_half_ceiling_on_garbage_persisted():
    worker = _bare_worker()
    fake_limiter_cls = MagicMock()
    captured = {}

    def _capture(resource_key, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    fake_limiter_cls.side_effect = _capture

    with patch("app.service.task_worker.AdaptiveResourceLimiter", fake_limiter_cls):
        with patch(
            "app.service.task_worker.system_config",
            SimpleNamespace(config=SimpleNamespace(task=_task_config())),
        ):
            worker._make_resource_limiter("tickets", 4, "not-a-number")

    assert captured["initial_limit"] == 2


def test_on_resource_limit_change_publishes_event_and_persists_dict():
    worker = _bare_worker()
    worker.adaptive_limits = {}
    worker._save_system_state = MagicMock()
    worker._publish = MagicMock()

    worker._on_resource_limit_change("face", 3, "downshift")

    assert worker.adaptive_limits == {"face": 3}
    worker._save_system_state.assert_called_once_with(
        "adaptive_resource_limits", {"face": 3}
    )
    args, _ = worker._publish.call_args
    assert args[0] == "task.concurrency"
    assert args[1] == {"resource_key": "face", "limit": 3, "reason": "downshift"}


@pytest.mark.parametrize(
    ("cpu", "memory", "expected"),
    [
        (50.0, 50.0, False),
        (95.0, 50.0, True),
        (50.0, 95.0, True),
        (90.0, 90.0, True),
    ],
)
def test_is_system_overloaded_uses_either_watermark(cpu, memory, expected):
    worker = _bare_worker()
    worker.system_pressure = {"cpu": cpu, "memory": memory}

    with patch(
        "app.service.task_worker.system_config",
        SimpleNamespace(
            config=SimpleNamespace(
                task=_task_config(
                    cpu_high_watermark=90.0,
                    memory_high_watermark=90.0,
                )
            )
        ),
    ):
        assert worker._is_system_overloaded() is expected


@pytest.mark.parametrize(
    ("category", "consumer", "expected"),
    [
        ("CPU", 1, 2),
        ("IO", 2, 4),
        ("AI", 5, 10),
    ],
)
def test_prefetch_limit_uses_double_consumer_with_floor_of_two(
    category, consumer, expected
):
    worker = _bare_worker()
    worker._get_concurrency_settings = lambda: {
        "cpu_consumer": 1,
        "io_consumer": 2,
        "ai_consumer": 5,
    }

    assert worker._prefetch_limit(category) == expected
