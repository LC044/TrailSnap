"""Nightly watch 2026-11-09 (round 2): media API helper gaps.

Targets uncovered branches in ``app/api/media.py`` reported by the
2026-11-09 coverage snapshot:

* ``_normalized_md5`` / ``_normalized_sha256`` - checksum normalisation and
  their HTTP 400 rejections.
* ``_existing_content_hashes`` / ``_existing_content_photo`` - only photos
  whose file still exists on disk are reported as duplicates.
* ``_stream_md5`` - digest of a chunked stream.
* ``_validate_chunk_sequence`` - missing / out-of-order / wrong-count chunks.
* ``_live_photo_video_path`` - extension rules for the companion video.
* ``_apply_mobile_source_metadata`` - photo_time / md5 backfill semantics.
* ``_preserve_source_file_time`` - source timestamp is written to the file.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

import hashlib
import io
import os
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import media
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.user import User

pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def owner(db):
    owner_id = uuid4()
    db.add(User(id=owner_id, username="nightly-media-helper-owner", hashed_password="x"))
    db.commit()
    return owner_id


def _photo(db, owner_id, tmp_path, name="p.jpg", md5=None):
    path = tmp_path / name
    path.write_bytes(b"payload")
    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename=name,
        file_path=str(path),
        file_type=FileType.image,
        md5=md5,
        is_deleted=False,
    )
    db.add(photo)
    db.commit()
    return photo


# --- checksum normalisation -------------------------------------------------

def test_normalized_md5_lowercases_and_trims():
    assert media._normalized_md5("  " + "A" * 32 + "  ") == "a" * 32


def test_normalized_md5_rejects_non_string():
    assert media._normalized_md5(None) is None
    assert media._normalized_md5(123) is None


def test_normalized_md5_rejects_malformed_value():
    with pytest.raises(HTTPException) as excinfo:
        media._normalized_md5("not-a-hash")
    assert excinfo.value.status_code == 400
    assert "32-character hexadecimal MD5" in excinfo.value.detail


def test_normalized_sha256_accepts_uppercase_and_lowercases():
    digest = "AB" * 32
    assert media._normalized_sha256(digest) == digest.lower()


def test_normalized_sha256_rejects_malformed_value():
    with pytest.raises(HTTPException) as excinfo:
        media._normalized_sha256("abc")
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid SHA-256"


# --- duplicate detection ----------------------------------------------------

def test_existing_content_hashes_ignores_missing_files(db, owner, tmp_path):
    present = _photo(db, owner, tmp_path, name="present.jpg", md5="a" * 32)
    gone = _photo(db, owner, tmp_path, name="gone.jpg", md5="b" * 32)
    os.remove(gone.file_path)

    hashes = media._existing_content_hashes(db, owner, ["a" * 32, "b" * 32])

    assert hashes == ["a" * 32]
    assert present.id


def test_existing_content_hashes_returns_empty_for_no_input(db, owner):
    assert media._existing_content_hashes(db, owner, []) == []


def test_existing_content_photo_skips_deleted_and_missing_files(db, owner, tmp_path):
    photo = _photo(db, owner, tmp_path, md5="c" * 32)
    photo.is_deleted = True
    db.commit()
    assert media._existing_content_photo(db, owner, "c" * 32) is None

    photo.is_deleted = False
    db.commit()
    assert media._existing_content_photo(db, owner, "c" * 32).id == photo.id

    os.remove(photo.file_path)
    assert media._existing_content_photo(db, owner, "c" * 32) is None


def test_stream_md5_matches_hashlib(tmp_path):
    target = tmp_path / "blob.bin"
    target.write_bytes(b"x" * (1024 * 1024 + 7))
    with open(target, "rb") as stream:
        digest = media._stream_md5(stream)
    assert digest == hashlib.md5((b"x" * (1024 * 1024 + 7))).hexdigest()


# --- chunk sequence ---------------------------------------------------------

def test_validate_chunk_sequence_accepts_contiguous_chunks():
    media._validate_chunk_sequence([0, 1, 2])
    media._validate_chunk_sequence([0, 1], expected_chunks=2)


def test_validate_chunk_sequence_rejects_empty_and_gaps():
    with pytest.raises(ValueError, match="missing or out of sequence"):
        media._validate_chunk_sequence([])
    with pytest.raises(ValueError, match="missing or out of sequence"):
        media._validate_chunk_sequence([0, 2])


def test_validate_chunk_sequence_rejects_wrong_count():
    with pytest.raises(ValueError, match="does not match the original"):
        media._validate_chunk_sequence([0, 1], expected_chunks=3)


# --- live photo companion path ---------------------------------------------

def test_live_photo_video_path_uses_source_extension():
    assert media._live_photo_video_path("/a/b/clip.jpg", "v.mp4") == "/a/b/clip.mp4"
    assert media._live_photo_video_path("/a/b/clip.HEIC", "v.mov") == "/a/b/clip.MOV"


def test_live_photo_video_path_rejects_unsupported_types():
    with pytest.raises(ValueError, match="Unsupported live photo image type"):
        media._live_photo_video_path("/a/b/clip.png", "v.mp4")
    with pytest.raises(ValueError, match="Unsupported live photo video type"):
        media._live_photo_video_path("/a/b/clip.jpg", "v.avi")


# --- source metadata --------------------------------------------------------

def test_apply_mobile_source_metadata_sets_photo_time_and_md5(db, owner, tmp_path):
    photo = _photo(db, owner, tmp_path)
    source_time = datetime(2024, 5, 1, 12, 30, 0)
    media._apply_mobile_source_metadata(db, photo, source_time, "d" * 32)
    db.refresh(photo)
    assert photo.photo_time == source_time
    assert photo.md5 == "d" * 32


def test_apply_mobile_source_metadata_keeps_explicit_photo_time(db, owner, tmp_path):
    photo = _photo(db, owner, tmp_path)
    explicit = datetime(2019, 1, 1, 0, 0, 0)
    photo.photo_time = explicit
    db.commit()
    media._apply_mobile_source_metadata(db, photo, datetime(2024, 5, 1, 12, 30, 0), None)
    db.refresh(photo)
    assert photo.photo_time == explicit


def test_apply_mobile_source_metadata_keeps_existing_md5(db, owner, tmp_path):
    photo = _photo(db, owner, tmp_path, md5="e" * 32)
    media._apply_mobile_source_metadata(db, photo, None, "f" * 32)
    db.refresh(photo)
    assert photo.md5 == "e" * 32


def test_preserve_source_file_time_writes_mtime(tmp_path):
    target = tmp_path / "kept.jpg"
    target.write_bytes(b"data")
    source_time = datetime(2022, 3, 4, 5, 6, 7)
    media._preserve_source_file_time(str(target), source_time)
    assert int(os.path.getmtime(target)) == int(source_time.timestamp())


def test_preserve_source_file_time_is_noop_without_source_time(tmp_path):
    target = tmp_path / "kept.jpg"
    target.write_bytes(b"data")
    before = os.path.getmtime(target)
    media._preserve_source_file_time(str(target), None)
    assert os.path.getmtime(target) == before

