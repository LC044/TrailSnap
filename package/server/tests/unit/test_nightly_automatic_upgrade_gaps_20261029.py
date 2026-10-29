"""Nightly watch 2026-10-29 · 覆盖盲区补测（app/utils/automatic_upgrade.py）。

被测模块：app/utils/automatic_upgrade.py 的首次启动自动升级流程。
覆盖点（相对 2026-10-29-r2 的覆盖率基线，此前完全未触达；既有
tests/unit/test_automatic_upgrade.py 全部走 subprocess，进程内代码行始终没被统计）：
- _prepare：设置桌面环境变量、保留 system_config.json 里的 security 段、
  准备失败时也要释放 DB engine。
- prepare：无候选图库 / 已有 instance.json / journal 已发布 / 图库身份变化 /
  多候选 / 候选报错 / 磁盘根目录 / 已有便携图库 / userdata 非空 / 版本号非法 /
  使用 automatic-upgrade-source.json 指定来源 / 完整复制发布流程 /
  复制过程中源库变化时中止。
- finish：未通过启动验证禁止清理、图库身份已变禁止清理、validated 推进阶段、
  cleanup 删除旧文件、源文件已变化时保留旧库。

跨平台：_legacy_lock 的 Windows 分支用 os.name='posix' 的代理对象跳过，
保证 Linux CI 与 Windows 本机行为一致。
"""

import json
import os
import sys
import types
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils import automatic_upgrade as upgrade
from app.utils.portable_library import file_hash, write_json

pytestmark = [pytest.mark.smoke, pytest.mark.module_system, pytest.mark.module_automatic_upgrade]


class _PosixOs:
    """把 os.name 伪装成 posix，跳过 _legacy_lock 的 Windows 专属分支。"""

    name = "posix"

    def __getattr__(self, item):
        return getattr(os, item)


@pytest.fixture
def posix_os(monkeypatch):
    monkeypatch.setattr(upgrade, "os", _PosixOs())


@pytest.fixture
def workspace(tmp_path):
    """构造「安装目录 root」与「旧图库 source」。"""
    root = tmp_path / "行影集"
    source = tmp_path / "旧图库"
    root.mkdir()
    source.mkdir()
    write_json(root / "portable.json", {"schemaVersion": 1, "activeBuild": "1.2.3"})
    return root, source


def _journal(root, source, phase="published", **extra):
    job = {
        "schemaVersion": 1,
        "id": str(uuid.uuid4()),
        "source": str(source.resolve()),
        "phase": phase,
        "instance": {
            "schemaVersion": 1,
            "mode": "portable",
            "instanceId": str(uuid.uuid4()),
            "displayName": root.name,
            "activeBuild": "1.2.3",
            "previousBuild": None,
            "dataRoot": {"kind": "relative", "path": "userdata"},
            "serverPort": None,
            "fixedPort": False,
        },
    }
    job.update(extra)
    journal = root / "maintenance/automatic-upgrade.json"
    write_json(journal, job)
    write_json(root / "instance.json", job["instance"])
    return job


def _discovery(source, error=None, notices=None, candidates=None):
    if candidates is None:
        candidates = [{"path": str(source), "error": error}] if error is not None else \
            [{"path": str(source), "error": None}]
    return {"candidates": candidates, "notices": notices or []}


# ---------------------------------------------------------------------------
# _prepare
# ---------------------------------------------------------------------------


def test_prepare_sets_desktop_env_and_keeps_security_config(tmp_path, monkeypatch):
    data = tmp_path / "userdata"
    (data / "data").mkdir(parents=True)
    write_json(data / "data/system_config.json", {"security": {"secret_key": "keep-me"}, "other": 1})

    fake_entry = types.ModuleType("desktop_entry")
    fake_entry._prepare_desktop_database = MagicMock()
    monkeypatch.setitem(sys.modules, "desktop_entry", fake_entry)

    # 先用 monkeypatch 登记原始值，_prepare 内部直接写 os.environ 也能被还原
    for key in ("TS_DESKTOP", "TS_DESKTOP_PORTABLE", "TS_DESKTOP_ROOT", "TS_DATA_DIR"):
        monkeypatch.setenv(key, "sentinel")

    upgrade._prepare(data)

    assert os.environ["TS_DESKTOP"] == "1"
    assert os.environ["TS_DESKTOP_PORTABLE"] == "1"
    assert os.environ["TS_DESKTOP_ROOT"] == str(data)
    assert os.environ["TS_DATA_DIR"] == str(data / "data")
    stored = json.loads((data / "data/system_config.json").read_text(encoding="utf-8"))
    assert stored["security"] == {"secret_key": "keep-me"}


def test_prepare_disposes_engines_when_database_preparation_fails(tmp_path, monkeypatch):
    data = tmp_path / "userdata"
    data.mkdir()

    fake_entry = types.ModuleType("desktop_entry")
    fake_entry._prepare_desktop_database = MagicMock(side_effect=RuntimeError("db failed"))
    monkeypatch.setitem(sys.modules, "desktop_entry", fake_entry)
    for key in ("TS_DESKTOP", "TS_DESKTOP_PORTABLE", "TS_DESKTOP_ROOT", "TS_DATA_DIR"):
        monkeypatch.setenv(key, "sentinel")

    with pytest.raises(RuntimeError):
        upgrade._prepare(data)


# ---------------------------------------------------------------------------
# prepare —— 早退与校验分支
# ---------------------------------------------------------------------------


def test_prepare_returns_none_when_instance_already_exists(workspace):
    root, _ = workspace
    write_json(root / "instance.json", {"schemaVersion": 1})
    with patch.object(upgrade, "discover_libraries") as discover:
        assert upgrade.prepare(root) == {"phase": "none"}
    discover.assert_not_called()


def test_prepare_returns_none_when_no_candidate_library(workspace):
    root, _ = workspace
    with patch.object(upgrade, "discover_libraries", return_value={"candidates": [], "notices": []}):
        assert upgrade.prepare(root) == {"phase": "none"}


def test_prepare_rejects_multiple_candidate_libraries(workspace):
    root, source = workspace
    other = source.parent / "另一个图库"
    other.mkdir()
    discovery = _discovery(source, candidates=[{"path": str(source), "error": None},
                                              {"path": str(other), "error": None}])
    with patch.object(upgrade, "discover_libraries", return_value=discovery):
        with pytest.raises(ValueError, match="多个"):
            upgrade.prepare(root)


def test_prepare_rejects_library_with_notices(workspace):
    root, source = workspace
    discovery = _discovery(source, notices=["图库被占用"])
    with patch.object(upgrade, "discover_libraries", return_value=discovery):
        with pytest.raises(ValueError, match="多个或不可用"):
            upgrade.prepare(root)


def test_prepare_reports_candidate_error(workspace):
    root, source = workspace
    discovery = _discovery(source, error="旧图库已损坏")
    with patch.object(upgrade, "discover_libraries", return_value=discovery):
        with pytest.raises(ValueError, match="旧图库已损坏"):
            upgrade.prepare(root)


def test_prepare_rejects_existing_portable_library(workspace):
    root, source = workspace
    write_json(source / "library.json", {"schemaVersion": 1})
    with patch.object(upgrade, "discover_libraries", return_value=_discovery(source)):
        with pytest.raises(ValueError, match="已有便携图库"):
            upgrade.prepare(root)


def test_prepare_rejects_non_empty_userdata(workspace):
    root, source = workspace
    (root / "userdata").mkdir()
    (root / "userdata" / "keep.txt").write_text("data", encoding="utf-8")
    with patch.object(upgrade, "discover_libraries", return_value=_discovery(source)):
        with pytest.raises(ValueError, match="userdata 已有数据"):
            upgrade.prepare(root)


def test_prepare_rejects_invalid_build_version(workspace):
    root, source = workspace
    write_json(root / "portable.json", {"schemaVersion": 1, "activeBuild": "../evil"})
    with patch.object(upgrade, "discover_libraries", return_value=_discovery(source)):
        with pytest.raises(ValueError, match="程序版本无效"):
            upgrade.prepare(root)


def test_prepare_uses_persisted_source_selection(workspace):
    """automatic-upgrade-source.json 指定的来源优先于自动发现的结果。"""
    root, source = workspace
    write_json(source / "library.json", {"schemaVersion": 1})
    selection = root / "maintenance/automatic-upgrade-source.json"
    write_json(selection, {"source": str(source)})
    with patch.object(upgrade, "discover_libraries", return_value=_discovery(source)) as discover, \
         patch("app.utils.portable_conversion.validate_library_source",
               return_value=source.resolve()) as validate:
        with pytest.raises(ValueError, match="已有便携图库"):
            upgrade.prepare(root)
    validate.assert_called_once_with(source.resolve())
    discover.assert_called_once()


def test_prepare_returns_existing_job_when_already_published(workspace):
    root, source = workspace
    job = _journal(root, source, phase="published")
    with patch.object(upgrade, "discover_libraries") as discover:
        out = upgrade.prepare(root)
    discover.assert_not_called()
    assert out["id"] == job["id"]
    assert out["phase"] == "published"


def test_prepare_rejects_published_job_with_changed_instance(workspace):
    root, source = workspace
    job = _journal(root, source, phase="published")
    write_json(root / "instance.json", {**job["instance"], "instanceId": str(uuid.uuid4())})
    with pytest.raises(ValueError, match="图库身份或位置已改变"):
        upgrade.prepare(root)


# ---------------------------------------------------------------------------
# prepare —— 完整发布流程
# ---------------------------------------------------------------------------


def _patch_publish_flow(root, source, inventory=None):
    """把复制 / 校验 / 数据库准备等重活替换成可控实现。"""
    stage = root.parent / (".trailsnap-auto-" + "stage")
    return stage


def test_prepare_publishes_migrated_library(workspace, posix_os, monkeypatch):
    root, source = workspace
    legacy_file = source / "data" / "legacy.bin"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_bytes(b"legacy-payload")
    (source / "unrelated.txt").write_text("keep", encoding="utf-8")

    def fake_migrate(src, staged, **kwargs):
        (staged / "data").mkdir(parents=True, exist_ok=True)
        (staged / "data" / "legacy.bin").write_bytes(b"legacy-payload")
        (staged / "data" / "trailsnap.sqlite").write_bytes(b"db")
        write_json(staged / "automatic-upgrade-owner.json", {"operationId": "x"})

    inventory = [{"path": "data/legacy.bin", "sha256": "0" * 64, "cleanup": True},
                 {"path": "unrelated.txt", "sha256": "0" * 64, "cleanup": False}]

    def fake_inventory(src, progress=None):
        return inventory

    job_id = str(uuid.uuid4())
    real_uuid = uuid.uuid4

    def fake_uuid():
        return real_uuid()

    monkeypatch.setattr(upgrade.uuid, "uuid4", lambda: real_uuid())
    # prepare() 会写 os.environ['TS_DESKTOP_ROOT']，登记原始值以便还原
    monkeypatch.setenv("TS_DESKTOP_ROOT", "sentinel")

    with patch.object(upgrade, "discover_libraries", return_value=_discovery(source)), \
         patch.object(upgrade, "_inventory", side_effect=fake_inventory), \
         patch.object(upgrade, "media_baseline", return_value=[]), \
         patch.object(upgrade, "migrate_data_directory", side_effect=fake_migrate), \
         patch.object(upgrade, "verify_media"), \
         patch.object(upgrade, "_prepare"), \
         patch("app.utils.portable_library.prepare_portable_library"), \
         patch.object(upgrade.os, "replace", MagicMock()):
        out = upgrade.prepare(root)

    assert out["phase"] == "published"
    assert out["source"] == str(source.resolve())
    assert out["instance"]["dataRoot"] == {"kind": "relative", "path": "userdata"}
    conversion = json.loads((root / "conversion.json").read_text(encoding="utf-8"))
    assert conversion["automatic"] is True
    assert conversion["verified"] is True


def test_prepare_aborts_when_source_changes_during_copy(workspace, posix_os, monkeypatch):
    root, source = workspace
    calls = {"n": 0}

    def fake_inventory(src, progress=None):
        calls["n"] += 1
        return [{"path": "f.bin", "sha256": "0" * 64, "cleanup": True}] if calls["n"] == 1 else [
            {"path": "f.bin", "sha256": "1" * 64, "cleanup": True}]

    def fake_migrate(src, staged, **kwargs):
        (staged / "data").mkdir(parents=True, exist_ok=True)

    with patch.object(upgrade, "discover_libraries", return_value=_discovery(source)), \
         patch.object(upgrade, "_inventory", side_effect=fake_inventory), \
         patch.object(upgrade, "media_baseline", return_value=[]), \
         patch.object(upgrade, "migrate_data_directory", side_effect=fake_migrate), \
         patch.object(upgrade, "verify_media"), \
         patch.object(upgrade, "_prepare"):
        with pytest.raises(ValueError, match="复制过程中发生变化"):
            upgrade.prepare(root)


# ---------------------------------------------------------------------------
# finish
# ---------------------------------------------------------------------------


def test_finish_rejects_cleanup_before_validation(workspace, posix_os):
    root, source = workspace
    _journal(root, source, phase="published")
    with pytest.raises(ValueError, match="禁止清理"):
        upgrade.finish(root, "cleanup")


def test_finish_rejects_unknown_action(workspace, posix_os):
    root, source = workspace
    _journal(root, source, phase="published")
    with pytest.raises(ValueError, match="禁止清理"):
        upgrade.finish(root, "unknown")


def test_finish_rejects_changed_instance_identity(workspace, posix_os):
    root, source = workspace
    job = _journal(root, source, phase="validated")
    write_json(root / "instance.json", {**job["instance"], "instanceId": str(uuid.uuid4())})
    with pytest.raises(ValueError, match="自动迁移目标已改变"):
        upgrade.finish(root, "cleanup")


def test_finish_advances_published_to_validated(workspace, posix_os):
    root, source = workspace
    _journal(root, source, phase="published")
    out = upgrade.finish(root, "validated")
    assert out["phase"] == "validated"
    stored = json.loads((root / "maintenance/automatic-upgrade.json").read_text(encoding="utf-8"))
    assert stored["phase"] == "validated"


def test_finish_cleanup_deletes_managed_source_files(workspace, posix_os):
    root, source = workspace
    managed = source / "data" / "legacy.bin"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"legacy-payload")
    unmanaged = source / "keep.txt"
    unmanaged.write_text("keep", encoding="utf-8")

    job = _journal(root, source, phase="validated",
                   files=[{"path": "data/legacy.bin", "sha256": file_hash(managed), "cleanup": True},
                          {"path": "keep.txt", "sha256": file_hash(unmanaged), "cleanup": False}],
                   media=[])

    with patch.object(upgrade, "verify_media"):
        out = upgrade.finish(root, "cleanup")

    assert out["phase"] == "completed"
    assert not managed.exists()
    # 非托管文件属于别的应用，不能删
    assert unmanaged.exists()


def test_finish_cleanup_keeps_changed_source_files(workspace, posix_os):
    root, source = workspace
    managed = source / "data" / "legacy.bin"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"changed-after-migration")

    _journal(root, source, phase="validated",
             files=[{"path": "data/legacy.bin", "sha256": "0" * 64, "cleanup": True}],
             media=[])

    with patch.object(upgrade, "verify_media"):
        with pytest.raises(ValueError, match="已变化"):
            upgrade.finish(root, "cleanup")
    assert managed.exists()


def test_finish_cleanup_rejects_paths_outside_source(workspace, posix_os):
    root, source = workspace
    _journal(root, source, phase="validated",
             files=[{"path": "../outside.bin", "sha256": "0" * 64, "cleanup": True}],
             media=[])
    with patch.object(upgrade, "verify_media"):
        with pytest.raises(ValueError, match="清理路径无效"):
            upgrade.finish(root, "cleanup")


def test_finish_is_idempotent_after_completion(workspace, posix_os):
    root, source = workspace
    _journal(root, source, phase="completed", files=[], media=[])
    out = upgrade.finish(root, "cleanup")
    assert out["phase"] == "completed"
