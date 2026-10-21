"""Bundled runtime packaging and migration, using isolated files and SQLite."""
import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.system import SystemState
from app.db.models.user import User
from app.service.desktop_ai import recover_legacy_extension_waits
from app.utils.desktop_layout import stage_program

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_legacy_wait_recovery_preserves_attempts_and_user_pause(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    db.add(User(id=owner, username=str(owner), settings={}))
    db.add(SystemState(key='desktop_ai_extension_state', value='waiting_update'))
    db.add(SystemState(key='paused_categories', value='["ocr"]'))
    tasks = []
    for error, status in [('等待安装 AI 扩展', TaskStatus.PENDING),
                          ('等待 AI 扩展更新', TaskStatus.PENDING),
                          ('真实推理失败', TaskStatus.FAILED),
                          ('等待 AI 模型：正在下载', TaskStatus.PENDING)]:
        task = Task(id=uuid4(), owner_id=owner, type=TaskType.OCR, status=status,
                    attempt_count=2, error=error, next_retry_at=datetime.now()+timedelta(minutes=1), payload={})
        db.add(task)
        tasks.append(task)
    db.commit()
    assert recover_legacy_extension_waits(db) == 2
    db.expire_all()
    assert all(task.error is None and task.next_retry_at is None for task in tasks[:2])
    assert all(task.attempt_count == 2 for task in tasks)
    assert tasks[2].error == '真实推理失败'
    assert tasks[3].error == '等待 AI 模型：正在下载'
    assert db.get(SystemState, 'desktop_ai_extension_state') is None
    assert db.get(SystemState, 'paused_categories').value == '["ocr"]'
    assert recover_legacy_extension_waits(db) == 0


def test_complete_build_changes_with_ai_and_rejects_mixed_versions(tmp_path):
    source = tmp_path/'source'
    server, ai = source/'server', source/'ai'
    server.mkdir(parents=True)
    ai.mkdir()
    (source/'trailsnap-desktop.exe').write_bytes(b'shell')
    launcher = source/'launcher.exe'
    launcher.write_bytes(b'launcher')
    (server/'trailsnap-server.exe').write_bytes(b'server')
    (ai/'trailsnap-ai.exe').write_bytes(b'ai')
    for component in (server, ai):
        (component/'runtime-version.json').write_text('{"version":"1.0.0"}')
    def stage():
        return stage_program(tmp_path/'installed',source,server,launcher,None,'1.0.0','x86_64',ai=ai)
    first=stage()
    manifest=json.loads((tmp_path/'installed/app'/first/'manifest.json').read_text())
    assert manifest['bundledAI'] is True
    assert not (tmp_path/'installed/app'/first/'ai-extensions.json').exists()
    (ai/'trailsnap-ai.exe').write_bytes(b'changed AI')
    assert stage() != first
    (ai/'runtime-version.json').write_text('{"version":"0.9.0"}')
    with pytest.raises(ValueError,match='版本不一致'):
        stage()
    (ai/'trailsnap-ai.exe').unlink()
    with pytest.raises(ValueError,match='缺少完整 AI'):
        stage()
