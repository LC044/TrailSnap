"""2026-10-28 nightly coverage for ``app/api/media.py`` backup/upload helpers.

The 2026-10-28 backend coverage scan reported ``api/media.py`` at 80% with 163
uncovered lines.  The uncovered half is concentrated in the *live-photo backup
check* endpoint and in the *chunked replacement* pipeline:

* ``check_live_backup_content`` -- validates the incoming ``pairs`` array and
  reports which live photos are already complete on the server.
* ``_verify_replacement`` -- re-checks an uploaded file against the size and
  hashes of the original before it replaces the stored file.
* ``_finalize_backup_file_replacement`` -- atomically swaps the file in and
  invalidates the derived thumbnail/metadata.
* ``_replace_backup_file_from_chunks`` -- assembles a chunked upload.
* ``_normalized_sha256`` -- normalises the client supplied SHA-256.
* ``get_upload_status`` / ``discard_upload`` -- the chunk-session lifecycle.

These are the paths where a silent mistake corrupts a user's photo library,
so the tests assert on the failure modes as carefully as on the happy path.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _media():
    from app.api import media

    return media


def _user():
    return SimpleNamespace(id=uuid.uuid4())


# ---------------------------------------------------------------------------
# check_live_backup_content
# ---------------------------------------------------------------------------


def test_live_backup_check_rejects_a_non_array_pairs_payload():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_live_backup_content({"pairs": "nope"}, MagicMock(), _user())

    assert excinfo.value.status_code == 400


def test_live_backup_check_rejects_more_than_two_hundred_pairs():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_live_backup_content({"pairs": [{}] * 201}, MagicMock(), _user())

    assert excinfo.value.status_code == 400


def test_live_backup_check_rejects_a_pair_without_a_usable_key():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_live_backup_content({"pairs": [{"key": 42}]}, MagicMock(), _user())
    assert excinfo.value.status_code == 400

    with pytest.raises(HTTPException) as excinfo:
        media.check_live_backup_content({"pairs": [{"key": "x" * 256}]}, MagicMock(), _user())
    assert excinfo.value.status_code == 400


def test_live_backup_check_requires_both_hashes():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_live_backup_content(
            {"pairs": [{"key": "live-1", "image_md5": "a" * 32}]}, MagicMock(), _user()
        )

    assert excinfo.value.status_code == 400


def test_live_backup_check_rejects_a_malformed_image_hash():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media.check_live_backup_content(
            {"pairs": [{"key": "live-1", "image_md5": "not-hex", "video_md5": "b" * 32}]},
            MagicMock(),
            _user(),
        )

    assert excinfo.value.status_code == 400


def test_live_backup_check_reports_the_state_of_each_pair():
    media = _media()
    user = _user()
    db = MagicMock()

    def _state(_db, _user_id, image_md5, video_md5):
        if image_md5 == "a" * 32:
            return object(), "/tmp/live.mov", True
        return None, None, False

    with patch.object(media, "_live_content_state", side_effect=_state):
        response = media.check_live_backup_content(
            {
                "pairs": [
                    {"key": "live-1", "image_md5": "a" * 32, "video_md5": "b" * 32},
                    {"key": "live-2", "image_md5": "c" * 32, "video_md5": "d" * 32},
                ]
            },
            db,
            user,
        )

    assert response.data == {
        "live-1": {"image_exists": True, "video_exists": True, "complete": True},
        "live-2": {"image_exists": False, "video_exists": False, "complete": False},
    }


# ---------------------------------------------------------------------------
# _normalized_sha256
# ---------------------------------------------------------------------------


def test_normalized_sha256_accepts_none_and_lowercases_a_valid_digest():
    media = _media()

    assert media._normalized_sha256(None) is None
    assert media._normalized_sha256("A" * 64) == "a" * 64


def test_normalized_sha256_rejects_a_malformed_digest():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        media._normalized_sha256("not-a-sha256")

    assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# _verify_replacement
# ---------------------------------------------------------------------------


def test_verify_replacement_rejects_a_size_mismatch(tmp_path):
    media = _media()
    path = tmp_path / "replacement.bin"
    path.write_bytes(b"0123456789")

    with pytest.raises(HTTPException) as excinfo:
        media._verify_replacement(str(path), expected_size=99)

    assert excinfo.value.status_code == 400


def test_verify_replacement_rejects_a_sha256_mismatch(tmp_path):
    media = _media()
    path = tmp_path / "replacement.bin"
    path.write_bytes(b"payload")

    with pytest.raises(HTTPException) as excinfo:
        media._verify_replacement(str(path), expected_sha256="0" * 64)

    assert excinfo.value.status_code == 400


def test_verify_replacement_rejects_an_md5_mismatch(tmp_path):
    media = _media()
    path = tmp_path / "replacement.bin"
    path.write_bytes(b"payload")

    with pytest.raises(HTTPException) as excinfo:
        media._verify_replacement(str(path), expected_md5="0" * 32)

    assert excinfo.value.status_code == 400


def test_verify_replacement_accepts_a_matching_file(tmp_path):
    media = _media()
    path = tmp_path / "replacement.bin"
    payload = b"identical payload"
    path.write_bytes(payload)

    media._verify_replacement(
        str(path),
        expected_size=len(payload),
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_md5=hashlib.md5(payload).hexdigest(),
    )


# ---------------------------------------------------------------------------
# _finalize_backup_file_replacement
# ---------------------------------------------------------------------------


def test_finalize_backup_file_replacement_replaces_the_file_and_invalidates_metadata(tmp_path):
    media = _media()
    target = tmp_path / "original.jpg"
    target.write_bytes(b"old")
    temporary = tmp_path / "upload.jpg"
    temporary.write_bytes(b"new")
    user_id = uuid.uuid4()

    photo = SimpleNamespace(
        id=uuid.uuid4(),
        file_path=str(target),
        size=3,
        width=100,
        height=50,
        duration=None,
        processed_tasks={"metadata": True, "embedding": True},
    )
    db = MagicMock()

    with patch.object(media.storage, "validate_target_path"), \
            patch.object(media.storage, "delete_thumbnails") as delete_thumbnails, \
            patch.object(media.storage, "generate_thumbnail") as generate_thumbnail, \
            patch.object(media.storage, "get_image_dimensions", return_value=(640, 480, 12.5)), \
            patch.object(media.storage, "get_file_size", return_value=1234):
        result = media._finalize_backup_file_replacement(db, photo, str(temporary), user_id)

    assert target.read_bytes() == b"new"
    delete_thumbnails.assert_called_once_with(user_id, photo.id)
    generate_thumbnail.assert_called_once_with(user_id, str(target), photo.id)
    assert result is photo
    assert photo.size == 1234
    assert (photo.width, photo.height) == (640, 480)  # duration 12.5
    # The metadata cache must be invalidated so the new file is re-scanned.
    assert photo.processed_tasks["metadata"] is False
    assert photo.processed_tasks["embedding"] is True
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# _replace_backup_file_from_chunks
# ---------------------------------------------------------------------------


def test_replace_backup_file_from_chunks_assembles_and_finalizes(tmp_path):
    media = _media()
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"first-")
    (chunk_dir / "1").write_bytes(b"second")

    target = tmp_path / "original.jpg"
    target.write_bytes(b"old")
    photo = SimpleNamespace(id=uuid.uuid4(), file_path=str(target))
    db = MagicMock()
    user_id = uuid.uuid4()

    captured = {}

    def _finalize(_db, _photo, temporary_path, _user_id):
        captured["temporary"] = temporary_path
        captured["content"] = open(temporary_path, "rb").read()
        return _photo

    with patch.object(media.storage, "validate_target_path"), \
            patch.object(media, "_finalize_backup_file_replacement", side_effect=_finalize):
        result = media._replace_backup_file_from_chunks(
            db, photo, str(chunk_dir), [0, 1], user_id
        )

    assert captured["content"] == b"first-second"
    assert result is photo
    # The temporary file and the chunk directory are always cleaned up.
    assert not os.path.exists(captured["temporary"])
    assert not os.path.isdir(str(chunk_dir))


def test_replace_backup_file_from_chunks_cleans_up_after_a_failed_verification(tmp_path):
    media = _media()
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"payload")

    target = tmp_path / "original.jpg"
    target.write_bytes(b"old")
    photo = SimpleNamespace(id=uuid.uuid4(), file_path=str(target))
    db = MagicMock()

    with patch.object(media.storage, "validate_target_path"):
        with pytest.raises(HTTPException):
            media._replace_backup_file_from_chunks(
                db, photo, str(chunk_dir), [0], uuid.uuid4(), expected_size=999
            )

    assert not os.path.isdir(str(chunk_dir))
    assert target.read_bytes() == b"old"


# ---------------------------------------------------------------------------
# upload session lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_upload_status_lists_the_received_chunk_sizes(tmp_path):
    media = _media()
    user = _user()
    upload_id = uuid.uuid4()
    chunk_dir = tmp_path / str(upload_id)
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"1234")
    (chunk_dir / "1").write_bytes(b"56")
    (chunk_dir / "not-a-chunk").write_bytes(b"ignored")

    with patch.object(media, "_chunk_dir", return_value=str(chunk_dir)):
        response = await media.get_upload_status(upload_id, MagicMock(), user)

    assert response.data == {"chunks": {0: 4, 1: 2}}


@pytest.mark.asyncio
async def test_get_upload_status_reports_a_missing_session(tmp_path):
    media = _media()
    user = _user()

    with patch.object(media, "_chunk_dir", return_value=str(tmp_path / "absent")):
        with pytest.raises(HTTPException) as excinfo:
            await media.get_upload_status(uuid.uuid4(), MagicMock(), user)

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_discard_upload_removes_the_chunk_directory(tmp_path):
    media = _media()
    user = _user()
    chunk_dir = tmp_path / str(uuid.uuid4())
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"1234")

    with patch.object(media, "_chunk_dir", return_value=str(chunk_dir)):
        response = await media.discard_upload(uuid.uuid4(), MagicMock(), user)

    assert response.data == {"discarded": True}
    assert not os.path.isdir(str(chunk_dir))

