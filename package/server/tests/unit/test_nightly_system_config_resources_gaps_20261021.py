"""Unit tests for the 2026-10-21 nightly coverage gap scan.

Module exercised: ``app/core/system_config.py``.

The cgroup / CPU-affinity probing helpers (``_available_cpu_cores``,
``_available_memory_gb``), the level decision function
``get_default_concurrency_level`` and the ``SystemConfigManager`` disk
load/save path had no direct tests. Existing suites only *monkeypatch*
``get_default_concurrency_level`` away, which is precisely why the body never
executes. It also runs nowhere near a DB, so these are cheap and hermetic.

Coverage before this file: 74.6% (44 missed statements out of 173).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


pytestmark = [pytest.mark.smoke]


# Keys are compared against `_normalize(Path(...))`, which drops the leading
# separator -- `Path("/sys/fs/cgroup/cpu.max")` stringifies as
# "\\sys\\fs\\cgroup\\cpu.max" on Windows, so the keys must match that shape.
CPU_MAX = "sys/fs/cgroup/cpu.max"
CPU_QUOTA = "sys/fs/cgroup/cpu/cpu.cfs_quota_us"
CPU_PERIOD = "sys/fs/cgroup/cpu/cpu.cfs_period_us"
MEM_MAX = "sys/fs/cgroup/memory.max"
MEM_LIMIT = "sys/fs/cgroup/memory/memory.limit_in_bytes"


def _normalize(path: Path) -> str:
    return str(path).replace("\\", "/").lstrip("/")


def _patch_read_text(monkeypatch, mapping):
    """Serve cgroup pseudo-files from `mapping`; anything else raises OSError."""

    def fake_read_text(self, *args, **kwargs):
        value = mapping.get(_normalize(self), OSError("no such file"))
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(Path, "read_text", fake_read_text)


def _patch_cpu(monkeypatch, count=16, affinity=16):
    import os

    monkeypatch.setattr(os, "cpu_count", lambda: count)
    if affinity is None:
        monkeypatch.delattr(os, "sched_getaffinity", raising=False)
    else:
        # Not present on Windows; raising=False so the suite stays portable.
        monkeypatch.setattr(
            os, "sched_getaffinity", lambda _pid: set(range(affinity)), raising=False
        )


def _patch_memory(monkeypatch, total_gb):
    import psutil

    monkeypatch.setattr(
        psutil, "virtual_memory", lambda: SimpleNamespace(total=total_gb * (1024 ** 3))
    )


# === _available_cpu_cores ===


def test_cpu_cores_falls_back_to_one_when_cpu_count_is_none(monkeypatch):
    from app.core import system_config

    _patch_cpu(monkeypatch, count=None, affinity=None)
    _patch_read_text(monkeypatch, {})
    assert system_config._available_cpu_cores() == 1


def test_cpu_cores_uses_affinity_when_narrower_than_cpu_count(monkeypatch):
    from app.core import system_config

    _patch_cpu(monkeypatch, count=16, affinity=3)
    _patch_read_text(monkeypatch, {})
    assert system_config._available_cpu_cores() == 3


def test_cpu_cores_tolerates_missing_sched_getaffinity(monkeypatch):
    """Windows has no sched_getaffinity -> AttributeError must not propagate."""
    from app.core import system_config

    _patch_cpu(monkeypatch, count=6, affinity=None)
    _patch_read_text(monkeypatch, {})
    assert system_config._available_cpu_cores() == 6


def test_cpu_cores_honours_cgroup_v2_cpu_max(monkeypatch):
    from app.core import system_config

    _patch_cpu(monkeypatch, count=16, affinity=16)
    # quota 200000 over period 100000 == 2 cores
    _patch_read_text(monkeypatch, {CPU_MAX: "200000 100000\n"})
    assert system_config._available_cpu_cores() == 2


def test_cpu_cores_rounds_partial_quota_up(monkeypatch):
    from app.core import system_config

    _patch_cpu(monkeypatch, count=16, affinity=16)
    # 150000/100000 == 1.5 -> ceil -> 2
    _patch_read_text(monkeypatch, {CPU_MAX: "150000 100000"})
    assert system_config._available_cpu_cores() == 2


def test_cpu_cores_honours_cgroup_v1_quota_and_period(monkeypatch):
    from app.core import system_config

    _patch_cpu(monkeypatch, count=16, affinity=16)
    _patch_read_text(monkeypatch, {
        CPU_MAX: "max 100000",
        CPU_QUOTA: "100000",
        CPU_PERIOD: "100000",
    })
    assert system_config._available_cpu_cores() == 1


@pytest.mark.parametrize(
    "content",
    [
        "max 100000",         # unlimited
        "0 100000",           # zero quota is treated as unset
        "-5 100000",          # negative quota
        "not-a-number 1",     # ValueError
        "100000",             # v2 file without a period -> IndexError
    ],
)
def test_cpu_cores_skips_unusable_cgroup_limits(monkeypatch, content):
    from app.core import system_config

    _patch_cpu(monkeypatch, count=8, affinity=8)
    _patch_read_text(monkeypatch, {CPU_MAX: content})
    assert system_config._available_cpu_cores() == 8


def test_cpu_cores_skips_zero_period(monkeypatch):
    from app.core import system_config

    _patch_cpu(monkeypatch, count=8, affinity=8)
    _patch_read_text(monkeypatch, {
        CPU_MAX: "max 100000",
        CPU_QUOTA: "100000",
        CPU_PERIOD: "0",  # ZeroDivisionError
    })
    assert system_config._available_cpu_cores() == 8


# === _available_memory_gb ===


def test_memory_gb_returns_physical_total_without_cgroup_files(monkeypatch):
    from app.core import system_config

    _patch_memory(monkeypatch, total_gb=32)
    _patch_read_text(monkeypatch, {})
    assert system_config._available_memory_gb() == pytest.approx(32.0)


def test_memory_gb_ignores_unlimited_cgroup_value(monkeypatch):
    from app.core import system_config

    _patch_memory(monkeypatch, total_gb=64)
    _patch_read_text(monkeypatch, {MEM_MAX: "max"})
    assert system_config._available_memory_gb() == pytest.approx(64.0)


def test_memory_gb_clamps_to_cgroup_limit(monkeypatch):
    from app.core import system_config

    _patch_memory(monkeypatch, total_gb=64)
    _patch_read_text(monkeypatch, {MEM_MAX: str(8 * 1024 ** 3)})
    assert system_config._available_memory_gb() == pytest.approx(8.0)


def test_memory_gb_ignores_implausibly_large_limit(monkeypatch):
    """A 1 PiB "limit" means unlimited, not real memory."""
    from app.core import system_config

    _patch_memory(monkeypatch, total_gb=16)
    _patch_read_text(monkeypatch, {MEM_MAX: str(1 << 61)})
    assert system_config._available_memory_gb() == pytest.approx(16.0)


def test_memory_gb_supports_cgroup_v1_limit_file(monkeypatch):
    from app.core import system_config

    _patch_memory(monkeypatch, total_gb=32)
    _patch_read_text(monkeypatch, {MEM_LIMIT: str(4 * 1024 ** 3)})
    assert system_config._available_memory_gb() == pytest.approx(4.0)


def test_memory_gb_skips_unreadable_limit(monkeypatch):
    from app.core import system_config

    _patch_memory(monkeypatch, total_gb=12)
    _patch_read_text(monkeypatch, {MEM_MAX: ValueError("garbage")})
    assert system_config._available_memory_gb() == pytest.approx(12.0)


# === get_default_concurrency_level ===


@pytest.mark.parametrize(
    "cores, memory, expected",
    [
        (16, 32, "high"),
        (8, 16, "high"),      # inclusive lower bounds
        (4, 8, "medium"),
        (4, 6, "low"),        # enough cores, not enough memory
        (2, 32, "low"),       # plenty of memory, not enough cores
        (1, 1, "low"),
    ],
)
def test_default_concurrency_level_thresholds(monkeypatch, cores, memory, expected):
    from app.core import system_config

    monkeypatch.setattr(system_config, "_available_cpu_cores", lambda: cores)
    monkeypatch.setattr(system_config, "_available_memory_gb", lambda: float(memory))
    assert system_config.get_default_concurrency_level() == expected


def test_default_concurrency_level_degrades_to_medium_on_error(monkeypatch):
    from app.core import system_config

    monkeypatch.setattr(
        system_config, "_available_cpu_cores", MagicMock(side_effect=RuntimeError("boom"))
    )
    assert system_config.get_default_concurrency_level() == "medium"


@pytest.mark.parametrize(
    "class_name",
    [
        "ScanScheduleSettings",
        "MomentCaptionScheduleSettings",
        "ProactiveMemoryScheduleSettings",
    ],
)
def test_unknown_schedule_mode_yields_no_cron_expression(class_name):
    """Unknown modes fall through every branch instead of raising."""
    from app.core import system_config

    assert getattr(system_config, class_name)(mode="hourly").to_cron_expression() is None


# === SystemConfigManager load / save ===


def _manager(config_path: Path):
    """Fresh manager instance, bypassing the module-level singleton."""
    from app.core.system_config import SystemConfigManager, SystemSettings

    manager = object.__new__(SystemConfigManager)
    manager._config_path = str(config_path)
    manager.config = SystemSettings()
    return manager


def test_manager_load_creates_default_file_when_absent(tmp_path):
    from app.core.system_config import RecycleBinSettings

    target = tmp_path / "data" / "system_config.json"
    manager = _manager(target)
    manager._load()

    assert target.exists()
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["recycle_bin"]["retention_days"] == RecycleBinSettings().retention_days


def test_manager_load_reads_existing_file(tmp_path):
    from app.core.system_config import ProactiveMemoryScheduleSettings

    target = tmp_path / "system_config.json"
    target.write_text(
        json.dumps({"proactive_memory_schedule": {"max_run_seconds": 42}}),
        encoding="utf-8",
    )
    manager = _manager(target)
    manager._load()

    assert manager.config.proactive_memory_schedule.max_run_seconds == 42
    # untouched nested defaults survive a partial file
    assert manager.config.proactive_memory_schedule.top_photos == \
        ProactiveMemoryScheduleSettings().top_photos


def test_manager_load_falls_back_to_defaults_on_corrupt_file(tmp_path):
    from app.core.system_config import SecuritySettings

    target = tmp_path / "system_config.json"
    target.write_text("{not json", encoding="utf-8")
    manager = _manager(target)
    manager._load()

    assert manager.config.security.access_token_expire_minutes == \
        SecuritySettings().access_token_expire_minutes


def test_manager_load_does_not_overwrite_corrupt_file_with_defaults(tmp_path):
    """A failed parse must not silently reset the user's settings on disk."""
    target = tmp_path / "system_config.json"
    target.write_text("{not json", encoding="utf-8")
    _manager(target)._load()

    assert target.read_text(encoding="utf-8") == "{not json"


def test_manager_save_writes_serialised_settings(tmp_path):
    target = tmp_path / "nested" / "system_config.json"
    manager = _manager(target)
    manager.config.recycle_bin.retention_days = 30
    manager.save()

    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["recycle_bin"]["retention_days"] == 30


def test_manager_save_swallows_write_errors(tmp_path):
    """An unwritable path logs and returns; it never breaks startup."""
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    manager = _manager(blocker / "sub" / "system_config.json")
    manager.save()  # must not raise
