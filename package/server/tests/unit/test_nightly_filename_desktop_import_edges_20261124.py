"""Nightly watch 2026-11-24 — app/utils/filename.py 与 app/utils/desktop_import.py 边界补测。

* filename.is_valid_timestamp：超大毫秒时间戳触发 fromtimestamp 的 ValueError，
  必须被吞掉返回 None，而不是把异常抛给调用方。
* desktop_import.cleanup_staging：临时目录不存在、临时目录本身是链接、
  临时目录内部含链接三种情况都要安全退出或明确报错。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.utils import desktop_import
from app.utils import filename as filename_utils


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# --------------------------------------------------------------------------- #
# filename.is_valid_timestamp
# --------------------------------------------------------------------------- #

def test_is_valid_timestamp_rejects_out_of_range_milliseconds():
    """13 位毫秒时间戳过大时 datetime 构造失败，应返回 None 而不是抛错。"""
    assert filename_utils.is_valid_timestamp("9999999999999", "photo.jpg") is None


def test_is_valid_timestamp_rejects_non_numeric_digits():
    """长度合法但内容不是数字时同样返回 None。"""
    assert filename_utils.is_valid_timestamp("170000000a", "photo.jpg") is None


def test_is_valid_timestamp_accepts_in_range_seconds():
    """正常秒级时间戳仍应被接受。"""
    assert filename_utils.is_valid_timestamp("1700000000", "photo.jpg") is not None


# --------------------------------------------------------------------------- #
# desktop_import.cleanup_staging
# --------------------------------------------------------------------------- #

def _stage(target: Path, operation_id: str) -> Path:
    stage = target.parent / (".trailsnap-portable-" + operation_id)
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "import-operation.json").write_text(
        json.dumps({"operationId": operation_id, "target": str(target.resolve())}),
        encoding="utf-8",
    )
    return stage


def test_cleanup_staging_ignores_missing_staging_directory(tmp_path):
    """没有临时目录时直接返回，不做任何删除。"""
    target = tmp_path / "library"
    target.mkdir()
    operation_id = str(uuid.uuid4())

    assert desktop_import.cleanup_staging(target, operation_id) is None
    assert target.exists()


def test_cleanup_staging_refuses_a_symlinked_staging_directory(tmp_path, monkeypatch):
    """临时目录本身是链接时必须报错停止，绝不能递归删除链接目标。"""
    target = tmp_path / "library"
    target.mkdir()
    operation_id = str(uuid.uuid4())
    _stage(target, operation_id)

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(self):
        if self.name == ".trailsnap-portable-" + operation_id:
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(ValueError, match="链接"):
        desktop_import.cleanup_staging(target, operation_id)

    assert target.exists()
    assert (target.parent / (".trailsnap-portable-" + operation_id)).exists()


def test_cleanup_staging_refuses_links_inside_the_staging_directory(tmp_path, monkeypatch):
    """临时目录内部出现链接时必须报错停止，不得删除任何文件。"""
    target = tmp_path / "library"
    target.mkdir()
    operation_id = str(uuid.uuid4())
    stage = _stage(target, operation_id)
    (stage / "payload.txt").write_text("payload", encoding="utf-8")

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(self):
        if self.name == "payload.txt":
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(ValueError, match="链接"):
        desktop_import.cleanup_staging(target, operation_id)

    assert (stage / "payload.txt").exists()


def test_cleanup_staging_removes_only_its_own_staging_directory(tmp_path):
    """正常情况下只删除本次操作留下的临时目录，目标库保持不变。"""
    target = tmp_path / "library"
    target.mkdir()
    operation_id = str(uuid.uuid4())
    stage = _stage(target, operation_id)
    (stage / "payload.txt").write_text("payload", encoding="utf-8")

    desktop_import.cleanup_staging(target, operation_id)

    assert not stage.exists()
    assert target.exists()
