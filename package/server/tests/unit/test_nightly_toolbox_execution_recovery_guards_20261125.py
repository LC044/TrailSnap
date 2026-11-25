"""Nightly watch 2026-11-25 · app/service/toolbox_execution.py 的恢复计划守卫盲区。

覆盖扫描显示 toolbox_execution.py 未覆盖的行里有一组是「恢复 / 撤销」路线的
安全守卫（L417 起）：源文件被移动过、文件被外部改写、超过 24 小时撤销窗口、
复制副本不支持自动撤销。这些守卫一旦失效就可能覆盖用户文件，属于最高风险的
未覆盖逻辑。

本文件用假 session + 真实临时文件验证：

- 源影像位置被后续操作改变时跳过该明细并写明原因
- 撤销时文件内容被改写则拒绝恢复
- 超过 24 小时撤销窗口直接拒绝
- 复制副本不支持自动撤销
"""

import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.photo import Photo
from app.db.models.toolbox import ToolboxPlanItem
from app.service import toolbox_execution

pytestmark = [pytest.mark.regression, pytest.mark.module_toolbox]


class _Query:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows=(), photos=None):
        self.rows = list(rows)
        self.photos = photos or {}
        self.added = []
        self.commits = 0

    def query(self, *args, **kwargs):
        return _Query(self.rows)

    def get(self, model, key):
        return self.photos.get(key)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


def _user():
    return SimpleNamespace(id=uuid4())


def _original(**kwargs):
    base = dict(
        id=uuid4(), kind="organize", status="done", version=1,
        request={"config": {"action": "move"}}, summary={},
        finished_at=datetime.utcnow() - timedelta(hours=1),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _row(source, target, **kwargs):
    base = dict(id=1, plan_id=uuid4(), photo_id=uuid4(), source=source, target=target,
                status="failed", reason="", detail={}, fingerprint={"size": 1, "mtime_ns": 1})
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_recovery_skips_a_photo_that_moved_away(tmp_path):
    user = _user()
    source = tmp_path / "shot.jpg"
    source.write_bytes(b"photo")
    moved = tmp_path / "elsewhere.jpg"
    moved.write_bytes(b"photo")
    row = _row(str(source), str(tmp_path / "archived.jpg"))
    photo = SimpleNamespace(id=row.photo_id, owner_id=user.id, file_path=str(moved))
    session = _Session([row], photos={row.photo_id: photo})

    plan = toolbox_execution.recovery_plan(session, user, _original())

    item = session.added[-1]
    assert item.status == "skipped"
    assert item.reason == "影像位置已被后续操作改变"
    assert plan.summary == {"total": 1, "ready": 0, "skipped": 1}


def test_undo_refuses_a_modified_file(tmp_path):
    user = _user()
    archived = tmp_path / "archived.jpg"
    archived.write_bytes(b"changed")
    original_source = tmp_path / "shot.jpg"
    original_source.write_bytes(b"photo")
    row = _row(str(original_source), str(archived),
               status="success", detail={"output_fingerprint": {"size": 999, "mtime_ns": 999}})
    photo = SimpleNamespace(id=row.photo_id, owner_id=user.id, file_path=str(archived))
    session = _Session([row], photos={row.photo_id: photo})
    original = _original(kind="rename", finished_at=datetime.utcnow() - timedelta(hours=1))

    plan = toolbox_execution.recovery_plan(session, user, original, undo=True)

    item = session.added[-1]
    assert item.status == "skipped"
    assert item.reason == "文件已被修改"
    assert plan.summary["ready"] == 0


def test_undo_is_refused_after_the_24_hour_window(tmp_path):
    user = _user()
    archived = tmp_path / "archived.jpg"
    archived.write_bytes(b"photo")
    row = _row(str(tmp_path / "shot.jpg"), str(archived), status="success")
    photo = SimpleNamespace(id=row.photo_id, owner_id=user.id, file_path=str(archived))
    session = _Session([row], photos={row.photo_id: photo})
    original = _original(kind="rename", finished_at=datetime.utcnow() - timedelta(hours=25))

    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.recovery_plan(session, user, original, undo=True)

    assert "24 小时撤销窗口" in str(excinfo.value)


def test_undo_is_refused_for_copied_duplicates(tmp_path):
    user = _user()
    original = _original(kind="organize", request={"config": {"action": "copy"}})

    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.recovery_plan(_Session(), user, original, undo=True)

    assert "复制副本请手动核对" in str(excinfo.value)
