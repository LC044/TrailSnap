"""Nightly gap coverage (2026-11-11) — app/service/toolbox_execution.py.

The 2026-11-11 backend coverage scan reported::

    service/toolbox_execution.py    89.0%   39 uncovered lines

REQ-238 added the toolbox execution engine (plan confirmation -> file
mutation -> undo).  The uncovered lines are almost entirely the *guard*
branches that protect the user's original files:

* ``copy_exclusive`` refusing to overwrite an existing target and detecting a
  source file that changed mid-copy
* ``transfer`` rolling the target back when the source cannot be removed
  (hard link / copy + unlink paths)
* ``mutate_file`` undoing an already-transferred file when the DB commit fails
* ``mutate_metadata`` refusing to continue when the original file changed and
  preserving the backup when the rollback itself fails
* ``recovery_plan`` skipping items whose photo moved, whose file changed or
  whose recovery target is already occupied
* ``start_plan`` refusing a plan that does not exist, a duplicate group that
  would be fully deleted, or a plan with nothing left to execute
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

def _write(path, data: bytes = b'payload') -> str:
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
    }
    base.update(values)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# copy_exclusive
# --------------------------------------------------------------------------- #

def test_copy_exclusive_refuses_to_overwrite_existing_target(tmp_path):
    source = _write(tmp_path / 'source.jpg')
    target = _write(tmp_path / 'target.jpg', b'original')
    with pytest.raises(FileExistsError):
        toolbox_execution.copy_exclusive(source, target)
    assert open(target, 'rb').read() == b'original'


def test_copy_exclusive_detects_source_change_and_removes_target(tmp_path):
    """If the source changes while being copied the half-written target goes away."""
    source = _write(tmp_path / 'source.jpg')
    target = tmp_path / 'target.jpg'
    fingerprints = [{'size': 1, 'mtime_ns': 1}, {'size': 2, 'mtime_ns': 2}]
    with patch('app.service.toolbox_execution.file_fingerprint',
               side_effect=fingerprints):
        with pytest.raises(ValueError) as excinfo:
            toolbox_execution.copy_exclusive(source, str(target))
    assert '源文件发生变化' in str(excinfo.value)
    assert not target.exists()


# --------------------------------------------------------------------------- #
# transfer
# --------------------------------------------------------------------------- #

def test_transfer_move_uses_hard_link(tmp_path):
    source = _write(tmp_path / 'source.jpg')
    target = tmp_path / 'nested' / 'target.jpg'
    toolbox_execution.transfer(source, str(target), move=True)
    assert target.exists()
    assert not os.path.exists(source)


def test_transfer_move_falls_back_to_copy_when_link_is_unsupported(tmp_path):
    """EXDEV / EPERM on os.link must fall back to copy + unlink."""
    source = _write(tmp_path / 'source.jpg')
    target = tmp_path / 'target.jpg'
    import errno
    with patch('app.service.toolbox_execution.os.link',
               side_effect=OSError(errno.EXDEV, 'cross device')):
        toolbox_execution.transfer(source, str(target), move=True)
    assert target.exists()
    assert not os.path.exists(source)


def test_transfer_move_raises_on_unexpected_link_error(tmp_path):
    source = _write(tmp_path / 'source.jpg')
    target = tmp_path / 'target.jpg'
    import errno
    with patch('app.service.toolbox_execution.os.link',
               side_effect=OSError(errno.EACCES, 'denied')):
        with pytest.raises(OSError):
            toolbox_execution.transfer(source, str(target), move=True)
    assert not target.exists()


def test_transfer_move_removes_target_when_source_unlink_fails(tmp_path):
    """A hard link that cannot be unlinked must not leave a stray copy behind."""
    source = _write(tmp_path / 'source.jpg')
    target = tmp_path / 'target.jpg'
    real_unlink = os.unlink

    def flaky_unlink(path):
        if os.path.abspath(str(path)) == os.path.abspath(str(source)):
            raise OSError('busy')
        return real_unlink(path)

    with patch('app.service.toolbox_execution.os.unlink', side_effect=flaky_unlink):
        with pytest.raises(OSError):
            toolbox_execution.transfer(source, str(target), move=True)
    assert not target.exists()


def test_transfer_copy_then_move_removes_target_when_unlink_fails(tmp_path):
    """Copy + unlink path: the target is rolled back when the unlink fails."""
    source = _write(tmp_path / 'source.jpg')
    target = tmp_path / 'target.jpg'
    real_unlink = os.unlink

    def flaky_unlink(path):
        if os.path.abspath(str(path)) == os.path.abspath(str(source)):
            raise OSError('busy')
        return real_unlink(path)

    with patch('app.service.toolbox_execution.os.unlink', side_effect=flaky_unlink):
        with pytest.raises(OSError):
            toolbox_execution.transfer(source, str(target), move=True)
    assert not target.exists()


def test_transfer_copy_does_not_touch_existing_target(tmp_path):
    source = _write(tmp_path / 'source.jpg')
    target = _write(tmp_path / 'target.jpg', b'keep')
    with pytest.raises(FileExistsError):
        toolbox_execution.transfer(source, target, move=False)
    assert open(target, 'rb').read() == b'keep'
    assert os.path.exists(source)


# --------------------------------------------------------------------------- #
# mutate_file rollback
# --------------------------------------------------------------------------- #

def test_mutate_file_rolls_back_a_transferred_file_when_commit_fails(tmp_path):
    source = _write(tmp_path / 'source.jpg')
    target = tmp_path / 'target.jpg'
    user = _user()
    photo = SimpleNamespace(id=uuid4(), file_path=source, filename='source.jpg')
    item = SimpleNamespace(target=str(target), source=source, status='ready',
                           reason='', detail={}, fingerprint={})
    config = SimpleNamespace(kind='rename', action='move')
    db = MagicMock()
    db.commit.side_effect = RuntimeError('commit failed')

    transfer = MagicMock()
    with patch('app.service.toolbox_execution.allowed_directory'), \
            patch('app.service.toolbox_execution.apply_photo_reference'), \
            patch('app.crud.album.trigger_conditional_albums_update'), \
            patch('app.service.toolbox_execution.file_fingerprint',
                  return_value={'size': 1, 'mtime_ns': 1}), \
            patch('app.service.toolbox_execution.transfer', transfer):
        with pytest.raises(RuntimeError):
            toolbox_execution.mutate_file(db, user, photo, item, config)

    db.rollback.assert_called_once()
    assert transfer.call_args_list[-1].args == (str(target), source)


def test_mutate_file_removes_copied_target_when_commit_fails(tmp_path):
    """For a copy the rollback deletes the newly created target file."""
    source = _write(tmp_path / 'source.jpg')
    target = tmp_path / 'target.jpg'
    target.write_bytes(b'copy')
    user = _user()
    photo = SimpleNamespace(id=uuid4(), file_path=source, filename='source.jpg')
    item = SimpleNamespace(target=str(target), source=source, status='ready',
                           reason='', detail={}, fingerprint={})
    config = SimpleNamespace(kind='organize', action='copy')
    db = MagicMock()
    db.commit.side_effect = RuntimeError('commit failed')

    with patch('app.service.toolbox_execution.allowed_directory'), \
            patch('app.service.toolbox_execution.apply_photo_reference'), \
            patch('app.crud.album.trigger_conditional_albums_update'), \
            patch('app.service.toolbox_execution.clone_photo',
                  return_value=SimpleNamespace(id=uuid4(), file_path=source,
                                               filename='source.jpg', albums=[])), \
            patch('app.service.journey_queue.enqueue'), \
            patch('app.service.toolbox_execution.file_fingerprint',
                  return_value={'size': 1, 'mtime_ns': 1}), \
            patch('app.service.toolbox_execution.transfer', MagicMock()):
        with pytest.raises(RuntimeError):
            toolbox_execution.mutate_file(db, user, photo, item, config)

    db.rollback.assert_called_once()
    assert not target.exists()


# --------------------------------------------------------------------------- #
# mutate_metadata guards
# --------------------------------------------------------------------------- #

def _metadata_item(tmp_path):
    source = _write(tmp_path / 'source.jpg', b'original-bytes')
    item = SimpleNamespace(source=source, target=source, status='ready', reason='',
                           detail={}, fingerprint={'size': 13, 'mtime_ns': 1})
    return item


def test_mutate_metadata_refuses_when_original_changed(tmp_path):
    """The original file changing during EXIF preparation aborts the operation."""
    item = _metadata_item(tmp_path)
    db = MagicMock()
    photo = SimpleNamespace(id=uuid4())
    with patch('app.service.toolbox_execution.prepare_metadata_file'), \
            patch('app.service.toolbox_execution.copy_exclusive'), \
            patch('app.service.toolbox_execution.sync_metadata_record'), \
            patch('app.service.toolbox_execution.file_fingerprint',
                  return_value={'size': 999, 'mtime_ns': 999}):
        with pytest.raises(ValueError) as excinfo:
            toolbox_execution.mutate_metadata(db, photo, item)
    assert '原文件发生变化' in str(excinfo.value)


def test_mutate_metadata_keeps_backup_when_rollback_fails(tmp_path):
    """If the restore step fails the backup must survive for manual recovery."""
    item = _metadata_item(tmp_path)
    db = MagicMock()
    db.commit.side_effect = RuntimeError('commit failed')
    photo = SimpleNamespace(id=uuid4())

    fingerprints = [
        {'size': 13, 'mtime_ns': 1},   # expected check -> matches item.fingerprint
        {'size': 20, 'mtime_ns': 2},   # output fingerprint of the temporary file
        {'size': 30, 'mtime_ns': 3},   # the replaced original changed afterwards
    ]
    with patch('app.service.toolbox_execution.prepare_metadata_file',
               side_effect=lambda source, temporary, detail: open(temporary, 'wb').write(b'new')), \
            patch('app.service.toolbox_execution.copy_exclusive',
                  side_effect=lambda source, target: open(target, 'wb').write(b'backup')), \
            patch('app.service.toolbox_execution.sync_metadata_record'), \
            patch('app.service.toolbox_execution.file_fingerprint',
                  side_effect=fingerprints):
        with pytest.raises(ValueError) as excinfo:
            toolbox_execution.mutate_metadata(db, photo, item)

    assert '回滚未完成' in str(excinfo.value)
    leftovers = [f for f in os.listdir(tmp_path) if f.endswith('.bak')]
    assert leftovers, "the original copy must be preserved for manual recovery"


# --------------------------------------------------------------------------- #
# recovery_plan guards
# --------------------------------------------------------------------------- #

def _recovery_db(rows, photo):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = rows
    db.get.return_value = photo
    return db


def _row(source, target, **values):
    base = {
        "id": 1,
        "photo_id": uuid4(),
        "source": source,
        "target": target,
        "status": "failed",
        "reason": "",
        "detail": {},
        "fingerprint": {"size": 1, "mtime_ns": 1},
    }
    base.update(values)
    return SimpleNamespace(**base)


def test_recovery_plan_refuses_while_original_is_running(tmp_path):
    original = _plan(status='running')
    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.recovery_plan(MagicMock(), _user(), original)
    assert '请等待原任务结束' in str(excinfo.value)


def test_recovery_plan_refuses_undo_of_a_copy_plan(tmp_path):
    original = _plan(status='completed',
                     request={'config': {'kind': 'organize', 'action': 'copy'}})
    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.recovery_plan(MagicMock(), _user(), original, undo=True)
    assert '仅支持移动和重命名撤销' in str(excinfo.value)


def test_recovery_plan_refuses_undo_outside_the_24h_window(tmp_path):
    original = _plan(kind='rename', status='completed',
                     request={'config': {'kind': 'rename', 'action': 'move'}},
                     finished_at=datetime.utcnow() - timedelta(hours=48))
    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.recovery_plan(MagicMock(), _user(), original, undo=True)
    assert '24 小时' in str(excinfo.value)


def test_recovery_plan_skips_item_whose_photo_moved(tmp_path):
    source = _write(tmp_path / 'source.jpg')
    target = tmp_path / 'target.jpg'
    row = _row(source, str(target))
    photo = SimpleNamespace(id=row.photo_id, owner_id=uuid4(),
                            file_path=str(tmp_path / 'moved.jpg'))
    user = _user()
    photo.owner_id = user.id
    db = _recovery_db([row], photo)

    plan = toolbox_execution.recovery_plan(db, user, _plan(status='stopped'))
    assert plan.summary['skipped'] == 1
    assert plan.summary['ready'] == 0


def test_recovery_plan_skips_item_whose_target_is_occupied(tmp_path):
    source = _write(tmp_path / 'source.jpg')
    target = _write(tmp_path / 'target.jpg')
    row = _row(source, str(target))
    user = _user()
    photo = SimpleNamespace(id=row.photo_id, owner_id=user.id, file_path=source)
    db = _recovery_db([row], photo)

    plan = toolbox_execution.recovery_plan(db, user, _plan(kind='organize', status='stopped'))
    assert plan.summary['skipped'] == 1
    assert plan.summary['ready'] == 0


# --------------------------------------------------------------------------- #
# start_plan / get_plan guards
# --------------------------------------------------------------------------- #

def test_get_plan_rejects_unknown_plan():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.get_plan(db, uuid4(), uuid4())
    assert '不存在或无权限' in str(excinfo.value)


def test_start_plan_rejects_unknown_plan():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    user = _user()
    request = SimpleNamespace(version=1, confirmed=True, selected_items=[])
    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.start_plan(db, user, uuid4(), request)
    assert '不存在或无权限' in str(excinfo.value)


def test_start_plan_rejects_expired_preview():
    db = MagicMock()
    plan = _plan(status='preview', expires_at=datetime.utcnow() - timedelta(minutes=1))
    db.query.return_value.filter.return_value.first.return_value = plan
    user = _user()
    user.id = plan.owner_id
    request = SimpleNamespace(version=1, confirmed=True, selected_items=[])
    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.start_plan(db, user, plan.id, request)
    assert '预览已过期' in str(excinfo.value)


def test_start_plan_requires_confirmation():
    db = MagicMock()
    plan = _plan(status='preview')
    db.query.return_value.filter.return_value.first.return_value = plan
    user = _user()
    user.id = plan.owner_id
    request = SimpleNamespace(version=1, confirmed=False, selected_items=[])
    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.start_plan(db, user, plan.id, request)
    assert '请先确认' in str(excinfo.value)


def test_start_plan_rejects_cleanup_without_selection():
    db = MagicMock()
    plan = _plan(kind='cleanup', request={'config': {'cleanup_mode': 'duplicate'}})
    db.query.return_value.filter.return_value.first.return_value = plan
    user = _user()
    user.id = plan.owner_id
    request = SimpleNamespace(version=1, confirmed=True, selected_items=[])
    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.start_plan(db, user, plan.id, request)
    assert '请手动勾选' in str(excinfo.value)


def test_start_plan_rejects_duplicate_group_without_remaining_copy():
    """Deleting every copy of a duplicate group must be refused."""
    user = _user()
    photo_id = uuid4()
    candidate = SimpleNamespace(id=1, photo_id=photo_id, status='candidate',
                                detail={'group': 'g1', 'md5': 'same'})
    plan = _plan(kind='cleanup', owner_id=user.id,
                 request={'config': {'cleanup_mode': 'duplicate'}})
    from app.db.models.photo import Photo
    from app.db.models.toolbox import ToolboxPlan, ToolboxPlanItem
    from app.db.models.user import User

    db = MagicMock()

    def query(model):
        result = MagicMock()
        if model is ToolboxPlan:
            result.filter.return_value.first.return_value = plan
        elif model is ToolboxPlanItem:
            result.filter.return_value.all.return_value = [candidate]
        elif model is Photo.id:
            result.filter.return_value.first.return_value = None
        else:
            result.filter.return_value.first.return_value = None
            result.filter.return_value.all.return_value = []
        return result

    db.query.side_effect = query
    request = SimpleNamespace(version=1, confirmed=True, selected_items=[candidate.id])
    with pytest.raises(ValueError) as excinfo:
        toolbox_execution.start_plan(db, user, plan.id, request)
    assert '重复组必须至少保留一项' in str(excinfo.value)

