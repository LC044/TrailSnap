"""Nightly gap coverage (2026-11-12) - app/service/toolbox_execution.py.

The 2026-11-12 backend coverage scan reported::

    service/toolbox_execution.py    89.0%   39 uncovered lines

The 2026-11-11 nightly round already covered the *file system* guards of this
module (``copy_exclusive``, ``transfer``, the EXIF rollback and the
``recovery_plan`` skip reasons).  What is still uncovered are the branches
that depend on the *shape of the plan* and on the *rollback of a moved file*:

* ``get_plan`` (``27``) - the plan does not exist or belongs to another owner.
* ``start_plan`` (``58-62``, ``138-140``, ``144-148``, ``203-207``,
  ``248``, ``280``, ``293-297``, ``324``, ``326``, ``328``, ``335``,
  ``380``, ``383``, ``385``, ``401``, ``404``, ``408``, ``410``,
  ``413``) - the cleanup duplicate-group guard, the "another task is using
  these files" guard, the recovery guards and the per-item skip reasons.
* ``transfer`` (``138-140``, ``144-148``) - the rollback of the target when
  the source cannot be removed.
* ``mutate_file`` (``203-207``) - the rollback of an already transferred file
  when the database commit fails.
* ``recovery_plan`` (``380``, ``383``, ``385``, ``401``, ``404``,
  ``408``, ``410``, ``413``) - the undo preconditions and the per-row skip
  reasons.

Every database interaction is mocked, so no real user data is touched and no
file outside ``tmp_path`` is written.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.service import toolbox_execution

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _write(path, data: bytes = b"payload") -> str:
    path.write_bytes(data)
    return str(path)


def _user():
    return SimpleNamespace(id=uuid4(), settings={})


def _plan(**values):
    base = {
        "id": uuid4(),
        "owner_id": uuid4(),
        "kind": "organize",
        "status": "preview",
        "version": 1,
        "request": {"config": {"kind": "organize", "action": "copy"}},
        "summary": {},
        "task_id": None,
        "expires_at": datetime.utcnow() + timedelta(minutes=30),
        "finished_at": None,
        "stop_requested": False,
    }
    base.update(values)
    return SimpleNamespace(**base)


def _item(**values):
    base = {
        "id": uuid4(),
        "plan_id": uuid4(),
        "photo_id": uuid4(),
        "source": "",
        "target": "",
        "status": "ready",
        "reason": "",
        "detail": {},
        "fingerprint": {},
    }
    base.update(values)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# get_plan
# --------------------------------------------------------------------------- #

def test_get_plan_rejects_an_unknown_plan():
    """A plan that does not exist (or belongs to somebody else) is refused."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(ValueError, match="操作计划不存在或无权限"):
        toolbox_execution.get_plan(db, uuid4(), uuid4())


# --------------------------------------------------------------------------- #
# transfer - the target rollback
# --------------------------------------------------------------------------- #

def test_transfer_rolls_back_the_target_when_the_source_cannot_be_removed(tmp_path):
    """A failing ``os.unlink`` of the source must remove the copy again."""
    source = _write(tmp_path / "source.jpg")
    target = tmp_path / "sub" / "target.jpg"

    def _fail_unlink(path):
        if str(path) == source:
            raise PermissionError("locked")
        return original_unlink(path)

    original_unlink = os.unlink
    with patch("app.service.toolbox_execution.os.unlink", side_effect=_fail_unlink), \
         patch("app.service.toolbox_execution.os.link", side_effect=OSError(18, "cross device")):
        with pytest.raises(PermissionError):
            toolbox_execution.transfer(source, str(target), move=True)

    assert not target.exists()


# --------------------------------------------------------------------------- #
# mutate_file - the rollback of a transferred file
# --------------------------------------------------------------------------- #

def test_mutate_file_rolls_back_the_transferred_file_when_the_commit_fails(tmp_path):
    """A failing commit moves the file back to its original location."""
    source = _write(tmp_path / "source.jpg", b"x" * 16)
    target = tmp_path / "target.jpg"
    photo = SimpleNamespace(id=uuid4(), file_path=source, filename="source.jpg")
    item = _item(source=source, target=str(target), status="running",
                 detail={"targets": [str(target)]})

    db = MagicMock()
    db.commit.side_effect = RuntimeError("commit failed")

    with patch("app.service.toolbox_execution.allowed_directory"), \
         patch("app.service.toolbox_execution.apply_photo_reference"), \
         patch("app.crud.album.trigger_conditional_albums_update"), \
         patch("app.service.toolbox_execution.disk_budget"), \
         patch("app.service.toolbox_execution.transfer"), \
         patch("app.service.toolbox_execution.clone_photo") as clone_photo, \
         patch("app.service.toolbox_execution.file_fingerprint",
               return_value={"size": 16, "mtime_ns": 1}):
        clone_photo.return_value = SimpleNamespace(id=uuid4())
        with pytest.raises(RuntimeError):
            toolbox_execution.mutate_file(db, _user(), photo, item,
                                         SimpleNamespace(kind="organize", action="move"))

    db.rollback.assert_called()


# --------------------------------------------------------------------------- #
# recovery_plan - the undo preconditions
# --------------------------------------------------------------------------- #

def _recovery_db(rows):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = list(rows)
    return db


def test_recovery_plan_refuses_while_the_original_task_still_runs():
    """A plan that is still queued or running cannot be recovered."""
    original = _plan(status="running")

    with pytest.raises(ValueError, match="请等待原任务结束"):
        toolbox_execution.recovery_plan(MagicMock(), _user(), original)


def test_recovery_plan_refuses_to_undo_a_copy_plan():
    """Only move and rename plans can be undone."""
    original = _plan(kind="organize", status="success",
                     finished_at=datetime.utcnow(),
                     request={"config": {"kind": "organize", "action": "copy"}})

    with pytest.raises(ValueError, match="本版仅支持移动和重命名撤销"):
        toolbox_execution.recovery_plan(MagicMock(), _user(), original, undo=True)


def test_recovery_plan_refuses_an_undo_older_than_24_hours():
    """The undo window is 24 hours."""
    original = _plan(kind="organize", status="success",
                     finished_at=datetime.utcnow() - timedelta(hours=25),
                     request={"config": {"kind": "organize", "action": "move"}})

    with pytest.raises(ValueError, match="已超过 24 小时撤销窗口"):
        toolbox_execution.recovery_plan(MagicMock(), _user(), original, undo=True)


def test_recovery_plan_skips_a_row_whose_photo_moved(tmp_path):
    """A photo that is no longer at the recorded location is skipped."""
    original = _plan(kind="organize", status="success", finished_at=datetime.utcnow())
    row = _item(source=_write(tmp_path / "source.jpg"), target=_write(tmp_path / "target.jpg"),
                status="success", detail={})

    db = _recovery_db([row])
    db.get.return_value = SimpleNamespace(id=row.photo_id, owner_id=original.owner_id,
                                          file_path=str(tmp_path / "elsewhere.jpg"))

    plan = toolbox_execution.recovery_plan(db, SimpleNamespace(id=original.owner_id), original)

    assert plan.summary["ready"] == 0
    assert plan.summary["skipped"] == 1


def test_recovery_plan_skips_a_row_whose_target_is_already_occupied(tmp_path):
    """An existing recovery target is never overwritten."""
    original = _plan(kind="organize", status="success", finished_at=datetime.utcnow())
    source = _write(tmp_path / "source.jpg")
    target = _write(tmp_path / "target.jpg")
    row = _item(source=source, target=target, status="success", detail={})

    db = _recovery_db([row])
    db.get.return_value = SimpleNamespace(id=row.photo_id, owner_id=original.owner_id,
                                          file_path=source)

    plan = toolbox_execution.recovery_plan(db, SimpleNamespace(id=original.owner_id), original)

    assert plan.summary["ready"] == 0
    assert plan.summary["skipped"] == 1


def test_recovery_plan_skips_a_row_whose_source_changed(tmp_path):
    """A source photo whose fingerprint changed must be re-previewed."""
    original = _plan(kind="organize", status="success", finished_at=datetime.utcnow())
    source = _write(tmp_path / "source.jpg")
    target = tmp_path / "target.jpg"
    row = _item(source=source, target=str(target), status="success",
                fingerprint={"size": 1, "mtime_ns": 1}, detail={})

    db = _recovery_db([row])
    db.get.return_value = SimpleNamespace(id=row.photo_id, owner_id=original.owner_id,
                                          file_path=source)

    with patch("app.service.toolbox_execution.fingerprint",
               return_value={"size": 2, "mtime_ns": 2}):
        plan = toolbox_execution.recovery_plan(db, SimpleNamespace(id=original.owner_id), original)

    assert plan.summary["ready"] == 0
    assert plan.summary["skipped"] == 1


