"""覆盖 app/service/tasks/scan.py 的文件名过滤、批量用户扫描与实况照片分组分支。

扫描任务里有三处容易写错的地方此前没有单测：

1. ``scan_directory_recursive`` 会跳过空的文件名过滤模式——空正则会匹配
   所有文件，若不跳过就会把整目录的照片全部过滤掉；
2. 扫描任务没有指定 user_id 时要处理**所有**用户；
3. 新文件按扩展名分组时，实况照片的图/视频配对（HEIC+MOV、JPEG+MP4 …）
   必须落到正确的两个路径上，否则实况照片会退化成两张普通照片。
"""

import asyncio
import os
from unittest.mock import MagicMock

import pytest

from app.service.tasks import scan as scan_module
from app.service.tasks.scan import ScanFolderStrategy, scan_directory_recursive


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# 文件名过滤
# ---------------------------------------------------------------------------

def test_empty_filename_pattern_is_skipped(tmp_path):
    """空的过滤模式被跳过，空正则不会把整个目录的文件都过滤掉。"""
    (tmp_path / "keep.jpg").write_bytes(b"x")
    (tmp_path / "keep2.jpg").write_bytes(b"x")

    found = scan_directory_recursive(
        str(tmp_path),
        {".jpg"},
        {"enable": True, "filename_patterns": ["", "never-matches"]},
        [],
    )

    assert len(found) == 2


def test_filename_pattern_still_filters(tmp_path):
    """非空模式仍然生效。"""
    (tmp_path / "keep.jpg").write_bytes(b"x")
    (tmp_path / "skip.jpg").write_bytes(b"x")

    found = scan_directory_recursive(
        str(tmp_path),
        {".jpg"},
        {"enable": True, "filename_patterns": ["", "^skip"]},
        [],
    )

    names = {os.path.basename(path) for path in found}
    assert names == {"keep.jpg"}


def test_invalid_filename_pattern_is_ignored(tmp_path):
    """非法正则被忽略而不是让整次扫描失败。"""
    (tmp_path / "a.jpg").write_bytes(b"x")

    found = scan_directory_recursive(
        str(tmp_path),
        {".jpg"},
        {"enable": True, "filename_patterns": ["[unclosed"]},
        [],
    )

    assert len(found) == 1


# ---------------------------------------------------------------------------
# 扫描任务：无 user_id 时处理所有用户
# ---------------------------------------------------------------------------

def _worker():
    worker = MagicMock()
    worker.scan_status = {"message": "", "total_files": 0, "deleted": 0}
    return worker


def test_scan_without_user_id_processes_every_user(monkeypatch):
    """任务不带 user_id 时，所有用户都要被扫描。"""
    strategy = ScanFolderStrategy()
    user_a = MagicMock()
    user_a.id = "user-a"
    user_b = MagicMock()
    user_b.id = "user-b"

    db = MagicMock()
    db.query.return_value.all.return_value = [user_a, user_b]

    seen = []

    async def _fake_scan_for_user(self, worker, db, user, roots):
        seen.append((user.id, roots))
        return {"new_files": 1, "deleted_files": 0}

    monkeypatch.setattr(ScanFolderStrategy, "_scan_for_user", _fake_scan_for_user)

    task = MagicMock()
    task.payload = {"scan_roots": ["/data/photos"]}

    result = asyncio.run(strategy.process(_worker(), task, db))

    assert result == {"new_files": 2, "deleted_files": 0}
    assert [item[0] for item in seen] == ["user-a", "user-b"]


def test_scan_with_unknown_user_id_is_skipped(monkeypatch):
    """指定了 user_id 但查无此人时不产生任何扫描。"""
    strategy = ScanFolderStrategy()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    async def _boom(*_args, **_kwargs):
        raise AssertionError("不应进入扫描流程")

    monkeypatch.setattr(ScanFolderStrategy, "_scan_for_user", _boom)

    task = MagicMock()
    task.payload = {"scan_roots": ["/data/photos"], "user_id": "missing"}

    result = asyncio.run(strategy.process(_worker(), task, db))

    assert result == {"new_files": 0, "deleted_files": 0}


# ---------------------------------------------------------------------------
# 新文件分组：扩展名优先级与实况照片配对
# ---------------------------------------------------------------------------

def _patch_gallery_sync(monkeypatch, tmp_path):
    from app.service import gallery_sync

    root = str(tmp_path)
    monkeypatch.setattr(gallery_sync, "path_key", lambda path: str(path).lower())
    monkeypatch.setattr(gallery_sync, "external_roots", lambda _user: [root])
    monkeypatch.setattr(
        gallery_sync,
        "lock_user",
        lambda _db, user_id: MagicMock(id=user_id),
    )
    monkeypatch.setattr(
        gallery_sync,
        "owned_path_tasks",
        lambda _db, _user_id: MagicMock(),
    )
    return root


def _db_mock():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.with_entities.return_value.all.return_value = []
    return db


def _run_create_tasks(monkeypatch, tmp_path, files):
    strategy = ScanFolderStrategy()
    db = _db_mock()
    _patch_gallery_sync(monkeypatch, tmp_path)
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            strategy._create_tasks_for_new_files("user-id", set(files), loop, db)
        )
    finally:
        asyncio.set_event_loop(None)
        loop.close()
    return db


def _created_tasks(db):
    tasks = []
    for call in db.bulk_save_objects.call_args_list:
        tasks.extend(call.args[0])
    return tasks


def test_heic_takes_priority_over_jpeg_for_same_basename(monkeypatch, tmp_path):
    """同一 basename 下 .heic 优先作为图片路径。"""
    files = {
        str(tmp_path / "a.heic"),
        str(tmp_path / "a.jpg"),
    }
    db = _run_create_tasks(monkeypatch, tmp_path, files)

    payloads = [task.payload["file_path"] for task in _created_tasks(db)]
    assert str(tmp_path / "a.heic") in payloads


def test_mov_takes_priority_over_mp4_for_same_basename(monkeypatch, tmp_path):
    """同一 basename 下 .mov 优先作为视频路径。"""
    files = {
        str(tmp_path / "b.mov"),
        str(tmp_path / "b.mp4"),
    }
    db = _run_create_tasks(monkeypatch, tmp_path, files)

    payloads = [task.payload["file_path"] for task in _created_tasks(db)]
    assert str(tmp_path / "b.mov") in payloads


def test_heif_and_jpeg_are_used_when_no_better_extension(monkeypatch, tmp_path):
    """.heif / .jpeg 也会被识别为图片路径。"""
    files = {
        str(tmp_path / "c.heif"),
        str(tmp_path / "d.jpeg"),
    }
    db = _run_create_tasks(monkeypatch, tmp_path, files)

    payloads = [task.payload["file_path"] for task in _created_tasks(db)]
    assert str(tmp_path / "c.heif") in payloads
    assert str(tmp_path / "d.jpeg") in payloads


def test_live_pair_detection_failure_does_not_break_scan(monkeypatch, tmp_path):
    """实况照片配对检查抛异常时，扫描继续把文件作为普通照片入库。"""
    from app.service.live_photo import live_photo_service

    def _boom(_path):
        raise RuntimeError("content id unavailable")

    monkeypatch.setattr(live_photo_service, "get_content_identifier", _boom)

    files = {
        str(tmp_path / "e.jpg"),
        str(tmp_path / "e.mp4"),
    }
    db = _run_create_tasks(monkeypatch, tmp_path, files)

    payloads = [task.payload for task in _created_tasks(db)]
    assert any(item.get("is_live_photo") for item in payloads) is False
    assert len(payloads) == 2


def test_release_resources_is_a_noop():
    """扫描任务释放资源是空实现，调用不应抛错。"""
    assert scan_module.release_resources() is None

