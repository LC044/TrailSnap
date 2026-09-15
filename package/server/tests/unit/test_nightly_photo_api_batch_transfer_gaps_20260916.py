"""2026-09-16 nightly tests for app/api/photo.py priority gaps.

Targets the batch_transfer_photos endpoint and a few related uncovered
branches (collision rename, move failure log, copy new-photo insert + thumbnail
task) that are not exercised by the existing test_photo_api.py or the
2026-09-14 nightly priority gaps suite.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app
from app.api import photo as photo_api
from app.schemas.photo import BatchPhotoTransfer


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _storage_cfg(photo_path, external=None):
    return SimpleNamespace(
        storage=SimpleNamespace(
            photo_storage_path=photo_path,
            external_directories=external or [],
        )
    )


def _photo_with_columns(src_path, columns=("id", "file_path", "filename", "created_at", "updated_at", "owner_id")):
    """构造一个 photo 对象，__table__.columns 反射可用，file_path 指向 src_path。"""
    photo = SimpleNamespace()
    for c in columns:
        setattr(photo, c, f"orig-{c}" if c != "id" else uuid4())
    # 关键：覆盖 file_path 为真实路径
    photo.file_path = str(src_path)
    photo.filename = os.path.basename(str(src_path))
    photo.__table__ = SimpleNamespace(columns=[SimpleNamespace(name=c) for c in columns])
    return photo


# ---------------------------------------------------------------------------
# batch_transfer_photos: target directory validation
# ---------------------------------------------------------------------------


def test_batch_transfer_rejects_target_outside_allowed_roots(tmp_path):
    db = MagicMock()
    user = _user()
    allowed_root = tmp_path / "primary"
    allowed_root.mkdir()
    cfg = _storage_cfg(str(allowed_root))

    payload = BatchPhotoTransfer(
        photo_ids=[uuid4()],
        target_path=str(tmp_path / "outside"),
        action="move",
    )

    with (
        patch.object(photo_api.config_manager, "get_user_config", return_value=cfg),
        patch.object(photo_api.storage, "_get_storage_root", return_value=str(allowed_root)),
    ):
        with pytest.raises(HTTPException) as exc:
            photo_api.batch_transfer_photos(data=payload, db=db, current_user=user)

    assert exc.value.status_code == 403
    assert "Target directory not allowed" in exc.value.detail


def test_batch_transfer_rejects_target_with_prefix_collision_on_external(tmp_path):
    """确保 /external 不会被 /external-evil 这种前缀碰撞绕过白名单。"""
    db = MagicMock()
    user = _user()
    primary = tmp_path / "primary"
    primary.mkdir()
    external = tmp_path / "external"
    cfg = _storage_cfg(str(primary), external=[str(external)])

    payload = BatchPhotoTransfer(
        photo_ids=[uuid4()],
        target_path=str(tmp_path / "external-evil"),
        action="move",
    )

    with (
        patch.object(photo_api.config_manager, "get_user_config", return_value=cfg),
        patch.object(photo_api.storage, "_get_storage_root", return_value=str(primary)),
    ):
        with pytest.raises(HTTPException) as exc:
            photo_api.batch_transfer_photos(data=payload, db=db, current_user=user)

    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# batch_transfer_photos: collision handling
# ---------------------------------------------------------------------------


def test_batch_transfer_move_renames_on_collision(tmp_path):
    db = MagicMock()
    user = _user()
    primary = tmp_path / "primary"
    uploads = primary / "uploads"
    uploads.mkdir(parents=True)
    # target 必须落在 storage_root + "uploads" 子树下
    target = uploads / "sub"
    target.mkdir()
    cfg = _storage_cfg(str(primary))

    src_path = uploads / "vacation.jpg"
    src_path.write_bytes(b"original")
    # 预先在 target 放一个同名文件以触发冲突
    (target / "vacation.jpg").write_bytes(b"already-here")

    photo = _photo_with_columns(src_path)
    payload = BatchPhotoTransfer(
        photo_ids=[uuid4()],
        target_path=str(target),
        action="move",
    )

    with (
        patch.object(photo_api.config_manager, "get_user_config", return_value=cfg),
        patch.object(photo_api.storage, "_get_storage_root", return_value=str(primary)),
        patch.object(photo_api.app.crud.photo, "get_photos_by_ids", return_value=[photo]),
    ):
        response = photo_api.batch_transfer_photos(data=payload, db=db, current_user=user)

    # 新文件被改名（带 8 字符 hex 后缀），原文件被移动
    renamed_files = [f for f in target.iterdir() if f.name.startswith("vacation_") and f.name.endswith(".jpg")]
    assert len(renamed_files) == 1
    assert renamed_files[0].read_bytes() == b"original"
    assert not src_path.exists()
    # photo 对象被更新
    assert photo.file_path == str(renamed_files[0])
    assert photo.filename == renamed_files[0].name
    db.commit.assert_called_once()
    # 源 bug: "Successfully moveed N photos"（move + ed），但行为仍正确
    assert "1" in response.data["message"]


def test_batch_transfer_copy_creates_new_db_row_and_thumb_task(tmp_path):
    db = MagicMock()
    user = _user()
    primary = tmp_path / "primary"
    uploads = primary / "uploads"
    uploads.mkdir(parents=True)
    target = uploads / "sub"
    target.mkdir()
    cfg = _storage_cfg(str(primary))

    src_path = uploads / "album.jpg"
    src_path.write_bytes(b"img-bytes")

    photo = _photo_with_columns(src_path)
    payload = BatchPhotoTransfer(
        photo_ids=[uuid4()],
        target_path=str(target),
        action="copy",
    )

    tm_instance = MagicMock()

    with (
        patch.object(photo_api.config_manager, "get_user_config", return_value=cfg),
        patch.object(photo_api.storage, "_get_storage_root", return_value=str(primary)),
        patch.object(photo_api.app.crud.photo, "get_photos_by_ids", return_value=[photo]),
        patch.object(photo_api.TaskManager, "get_instance", return_value=tm_instance),
    ):
        response = photo_api.batch_transfer_photos(data=payload, db=db, current_user=user)

    # 物理拷贝完成
    assert (target / "album.jpg").exists()
    assert (target / "album.jpg").read_bytes() == b"img-bytes"
    # db.add 被调用一次（新增一行）
    db.add.assert_called_once()
    new_photo_arg = db.add.call_args.args[0]
    assert new_photo_arg.file_path == str(target / "album.jpg")
    # 缩略图任务被登记
    tm_instance.add_task.assert_called_once()
    assert "1" in response.data["message"]


def test_batch_transfer_skips_photos_with_missing_file(tmp_path):
    db = MagicMock()
    user = _user()
    primary = tmp_path / "primary"
    uploads = primary / "uploads"
    uploads.mkdir(parents=True)
    target = uploads / "sub"
    target.mkdir()
    cfg = _storage_cfg(str(primary))

    # photo.file_path 指向不存在的文件
    ghost = uploads / "ghost.jpg"
    photo = _photo_with_columns(ghost)

    payload = BatchPhotoTransfer(
        photo_ids=[uuid4()],
        target_path=str(target),
        action="move",
    )

    with (
        patch.object(photo_api.config_manager, "get_user_config", return_value=cfg),
        patch.object(photo_api.storage, "_get_storage_root", return_value=str(primary)),
        patch.object(photo_api.app.crud.photo, "get_photos_by_ids", return_value=[photo]),
    ):
        response = photo_api.batch_transfer_photos(data=payload, db=db, current_user=user)

    # 没有文件被移动；count=0
    assert "0" in response.data["message"]
    # 没有任何 db.add 调用
    db.add.assert_not_called()


def test_batch_transfer_unknown_action_does_nothing(tmp_path):
    """action 字段不是 move/copy 时，photo_api 没有显式校验 → 不会执行任何 IO。"""
    db = MagicMock()
    user = _user()
    primary = tmp_path / "primary"
    uploads = primary / "uploads"
    uploads.mkdir(parents=True)
    target = uploads / "sub"
    target.mkdir()
    cfg = _storage_cfg(str(primary))

    src_path = uploads / "x.jpg"
    src_path.write_bytes(b"x")
    photo = _photo_with_columns(src_path)

    payload = BatchPhotoTransfer(
        photo_ids=[uuid4()],
        target_path=str(target),
        action="symlink",  # 未知动作
    )

    with (
        patch.object(photo_api.config_manager, "get_user_config", return_value=cfg),
        patch.object(photo_api.storage, "_get_storage_root", return_value=str(primary)),
        patch.object(photo_api.app.crud.photo, "get_photos_by_ids", return_value=[photo]),
    ):
        response = photo_api.batch_transfer_photos(data=payload, db=db, current_user=user)

    # 文件未移动
    assert src_path.exists()
    assert "0" in response.data["message"]
    db.commit.assert_called_once()
