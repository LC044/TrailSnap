"""Nightly gap coverage (2026-11-11) — app/api/media.py (mobile upload paths).

The 2026-11-11 backend coverage scan reported::

    api/media.py    92.8%   59 uncovered lines

The largest remaining block sits in the two mobile upload endpoints
(``upload_photo_generic`` and ``finish_upload_generic``).  Their uncovered
branches are the ones that decide whether a re-upload from the phone is
accepted, replaced or de-duplicated:

* an existing backup photo that is replaced by a new upload
* a duplicate detected by content hash (no new photo is created)
* an ``IntegrityError`` raised while inserting the photo — the endpoint must
  fall back to the already stored photo instead of leaving a stray file
* the chunked variant of the same three situations, plus the "upload session
  not found" / "no chunks found" guards

Every request runs against a real in-memory SQLite session; the upload
plumbing (``storage.save_upload_file``, ``save_and_create_photo``) is stubbed
so no file is really written.
"""

from __future__ import annotations

import asyncio
import io
import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.api import media
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.user import User

pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def owner(db):
    user = User(id=uuid4(), username=f"nightly-{uuid4().hex[:8]}", hashed_password="x")
    db.add(user)
    db.commit()
    return user


async def _inline(func, *args, **kwargs):
    """Stand-in for starlette's run_in_threadpool that runs inline."""
    return func(*args, **kwargs)


def _upload(name: str, data: bytes = b"payload") -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data))


def _run(coro):
    return asyncio.run(coro)


def _existing_photo(db, owner, tmp_path, **values):
    path = tmp_path / "existing.jpg"
    path.write_bytes(b"existing")
    defaults = {
        "id": uuid4(),
        "owner_id": owner.id,
        "filename": "existing.jpg",
        "file_path": str(path),
        "file_type": FileType.image,
        "is_deleted": False,
        "backup_key": "backup-1",
        "md5": "a" * 32,
        "size": 8,
    }
    defaults.update(values)
    photo = Photo(**defaults)
    db.add(photo)
    db.commit()
    return photo


# --------------------------------------------------------------------------- #
# upload_photo_generic — existing backup photo
# --------------------------------------------------------------------------- #

def test_upload_photo_generic_replaces_existing_backup_file(db, owner, tmp_path):
    """Re-uploading a known backup key replaces the file and re-queues tasks."""
    photo = _existing_photo(db, owner, tmp_path)
    upload = _upload("existing.jpg", b"new-bytes")
    replaced = MagicMock(return_value=photo)

    with patch.object(media, "run_in_threadpool", _inline), \
            patch.object(media, "_replace_backup_file", replaced), \
            patch.object(media, "add_tasks") as add_tasks, \
            patch.object(media, "_preserve_source_file_time"), \
            patch.object(media, "_apply_mobile_source_metadata", return_value=photo):
        result = _run(media.upload_photo_generic(
            album_id=None, folder=None, backup_key="backup-1",
            source_photo_time=None, content_md5=None, companion_backup_key=None,
            live_photo_video=None, replace_existing=True, file=upload,
            db=db, current_user=owner))

    assert result is photo
    replaced.assert_called_once()
    add_tasks.assert_called_once()


def test_upload_photo_generic_keeps_existing_backup_without_replace(db, owner, tmp_path):
    """Without ``replace_existing`` the stored photo is returned untouched."""
    photo = _existing_photo(db, owner, tmp_path)
    upload = _upload("existing.jpg", b"new-bytes")

    with patch.object(media, "run_in_threadpool", _inline), \
            patch.object(media, "_replace_backup_file") as replace, \
            patch.object(media, "add_tasks") as add_tasks, \
            patch.object(media, "_apply_mobile_source_metadata", return_value=photo):
        result = _run(media.upload_photo_generic(
            album_id=None, folder=None, backup_key="backup-1",
            source_photo_time=None, content_md5=None, companion_backup_key=None,
            live_photo_video=None, replace_existing=False, file=upload,
            db=db, current_user=owner))

    assert result is photo
    replace.assert_not_called()
    add_tasks.assert_not_called()


# --------------------------------------------------------------------------- #
# upload_photo_generic — duplicate content
# --------------------------------------------------------------------------- #

def test_upload_photo_generic_reuses_duplicate_content(db, owner, tmp_path):
    """A photo with the same content hash is not stored twice."""
    photo = _existing_photo(db, owner, tmp_path, backup_key=None)
    upload = _upload("copy.jpg", b"new-bytes")

    with patch.object(media, "run_in_threadpool", _inline), \
            patch.object(media, "save_and_create_photo") as create, \
            patch.object(media, "add_tasks"), \
            patch.object(media, "_apply_mobile_source_metadata", return_value=photo):
        result = _run(media.upload_photo_generic(
            album_id=None, folder=None, backup_key=None,
            source_photo_time=None, content_md5="a" * 32, companion_backup_key=None,
            live_photo_video=None, replace_existing=False, file=upload,
            db=db, current_user=owner))

    assert result is photo
    create.assert_not_called()


# --------------------------------------------------------------------------- #
# upload_photo_generic — IntegrityError fallback
# --------------------------------------------------------------------------- #

def test_upload_photo_generic_falls_back_when_insert_conflicts(db, owner, tmp_path):
    """A racing insert must not leave a stray file behind."""
    photo = _existing_photo(db, owner, tmp_path)
    upload = _upload("existing.jpg", b"new-bytes")
    saved_path = tmp_path / "saved.jpg"
    saved_path.write_bytes(b"saved")

    with patch.object(media, "run_in_threadpool", _inline), \
            patch.object(media, "_existing_backup_photo", return_value=None), \
            patch("app.service.storage.save_upload_file", return_value=str(saved_path)), \
            patch.object(media, "save_and_create_photo",
                         side_effect=IntegrityError("insert", {}, Exception("duplicate"))), \
            patch.object(media, "add_tasks"):
        # The conflict is detected *after* the file was stored, so the helper
        # finds the photo that a parallel request already committed.
        with patch.object(media, "_existing_backup_photo", side_effect=[None, photo]):
            result = _run(media.upload_photo_generic(
                album_id=None, folder=None, backup_key="backup-1",
                source_photo_time=None, content_md5=None, companion_backup_key=None,
                live_photo_video=None, replace_existing=False, file=upload,
                db=db, current_user=owner))

    assert result is photo
    assert not saved_path.exists()


# --------------------------------------------------------------------------- #
# finish_upload_generic — guards
# --------------------------------------------------------------------------- #

def test_finish_upload_generic_rejects_missing_upload_session(db, owner, tmp_path):
    upload_id = uuid4()
    with patch.object(media, "run_in_threadpool", _inline), \
            patch.object(media, "_chunk_dir", return_value=str(tmp_path / "missing")):
        with pytest.raises(HTTPException) as excinfo:
            _run(media.finish_upload_generic(
                upload_id=upload_id, file_name="a.jpg", album_id=None, folder=None,
                backup_key=None, source_photo_time=None, content_md5=None,
                companion_backup_key=None, live_photo_video=None, replace_existing=False,
                expected_size=None, expected_chunks=None, content_sha256=None,
                db=db, current_user=owner))
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Upload session not found"


def test_finish_upload_generic_rejects_empty_chunk_directory(db, owner, tmp_path):
    upload_id = uuid4()
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    with patch.object(media, "run_in_threadpool", _inline), \
            patch.object(media, "_chunk_dir", return_value=str(chunk_dir)):
        with pytest.raises(HTTPException) as excinfo:
            _run(media.finish_upload_generic(
                upload_id=upload_id, file_name="a.jpg", album_id=None, folder=None,
                backup_key=None, source_photo_time=None, content_md5=None,
                companion_backup_key=None, live_photo_video=None, replace_existing=False,
                expected_size=None, expected_chunks=None, content_sha256=None,
                db=db, current_user=owner))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "No chunks found"


def test_finish_upload_generic_rejects_invalid_expected_size(db, owner):
    with patch.object(media, "run_in_threadpool", _inline):
        with pytest.raises(HTTPException) as excinfo:
            _run(media.finish_upload_generic(
                upload_id=uuid4(), file_name="a.jpg", album_id=None, folder=None,
                backup_key=None, source_photo_time=None, content_md5=None,
                companion_backup_key=None, live_photo_video=None, replace_existing=False,
                expected_size=0, expected_chunks=None, content_sha256=None,
                db=db, current_user=owner))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid expected file size"


def test_finish_upload_generic_rejects_invalid_expected_chunk_count(db, owner):
    with patch.object(media, "run_in_threadpool", _inline):
        with pytest.raises(HTTPException) as excinfo:
            _run(media.finish_upload_generic(
                upload_id=uuid4(), file_name="a.jpg", album_id=None, folder=None,
                backup_key=None, source_photo_time=None, content_md5=None,
                companion_backup_key=None, live_photo_video=None, replace_existing=False,
                expected_size=None, expected_chunks=-1, content_sha256=None,
                db=db, current_user=owner))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid expected chunk count"


def test_finish_upload_generic_rejects_invalid_live_photo_pair(db, owner):
    """The image and the companion video must share the same stem."""
    upload = _upload("clip.mp4", b"video")
    with patch.object(media, "run_in_threadpool", _inline):
        with pytest.raises(HTTPException) as excinfo:
            _run(media.finish_upload_generic(
                upload_id=uuid4(), file_name="other.jpg", album_id=None, folder=None,
                backup_key=None, source_photo_time=None, content_md5=None,
                companion_backup_key=None, live_photo_video=upload, replace_existing=False,
                expected_size=None, expected_chunks=None, content_sha256=None,
                db=db, current_user=owner))
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid live photo pair"


# --------------------------------------------------------------------------- #
# finish_upload_generic — existing / duplicate / conflict
# --------------------------------------------------------------------------- #

def test_finish_upload_generic_replaces_existing_backup_from_chunks(db, owner, tmp_path):
    photo = _existing_photo(db, owner, tmp_path)
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"chunk-0")
    replaced = MagicMock(return_value=photo)

    with patch.object(media, "run_in_threadpool", _inline), \
            patch.object(media, "_chunk_dir", return_value=str(chunk_dir)), \
            patch.object(media, "_replace_backup_file_from_chunks", replaced) as replace, \
            patch.object(media, "add_tasks"), \
            patch.object(media, "_preserve_source_file_time"), \
            patch.object(media, "_apply_mobile_source_metadata", return_value=photo):
        result = _run(media.finish_upload_generic(
            upload_id=uuid4(), file_name="existing.jpg", album_id=None, folder=None,
            backup_key="backup-1", source_photo_time=None, content_md5=None,
            companion_backup_key=None, live_photo_video=None, replace_existing=True,
            expected_size=None, expected_chunks=None, content_sha256=None,
            db=db, current_user=owner))

    assert result is photo
    replace.assert_called_once()


def test_finish_upload_generic_drops_chunk_dir_for_duplicate_content(db, owner, tmp_path):
    photo = _existing_photo(db, owner, tmp_path, backup_key=None)
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"chunk-0")

    with patch.object(media, "run_in_threadpool", _inline), \
            patch.object(media, "_chunk_dir", return_value=str(chunk_dir)), \
            patch.object(media.shutil, "rmtree") as rmtree, \
            patch.object(media, "_apply_mobile_source_metadata", return_value=photo):
        result = _run(media.finish_upload_generic(
            upload_id=uuid4(), file_name="copy.jpg", album_id=None, folder=None,
            backup_key=None, source_photo_time=None, content_md5="a" * 32,
            companion_backup_key=None, live_photo_video=None, replace_existing=False,
            expected_size=None, expected_chunks=None, content_sha256=None,
            db=db, current_user=owner))

    assert result is photo
    rmtree.assert_called_once()


def test_finish_upload_generic_falls_back_when_insert_conflicts(db, owner, tmp_path):
    photo = _existing_photo(db, owner, tmp_path)
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"chunk-0")
    final_path = tmp_path / "final.jpg"
    final_path.write_bytes(b"final")

    with patch.object(media, "run_in_threadpool", _inline), \
            patch.object(media, "_chunk_dir", return_value=str(chunk_dir)), \
            patch.object(media, "_finalize_chunk_upload", return_value=str(final_path)), \
            patch.object(media, "_preserve_source_file_time"), \
            patch.object(media, "save_and_create_photo",
                         side_effect=IntegrityError("insert", {}, Exception("duplicate"))), \
            patch.object(media, "add_tasks"), \
            patch.object(media, "_existing_backup_photo", side_effect=[None, photo]):
        result = _run(media.finish_upload_generic(
            upload_id=uuid4(), file_name="existing.jpg", album_id=None, folder=None,
            backup_key="backup-1", source_photo_time=None, content_md5=None,
            companion_backup_key=None, live_photo_video=None, replace_existing=False,
            expected_size=None, expected_chunks=None, content_sha256=None,
            db=db, current_user=owner))

    assert result is photo
    assert not final_path.exists()



