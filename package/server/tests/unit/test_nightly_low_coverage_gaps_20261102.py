"""Nightly watch 2026-11-02 guards for lowest-coverage server modules."""
import errno
import hashlib
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.api import media as media_api
from app.service import chapter
from app.service.face_cluster import FaceClusterService

pytestmark = [pytest.mark.smoke]


def _configure_media_destination(tmp_path, monkeypatch):
    final_path = tmp_path / "final.bin"
    monkeypatch.setattr(
        media_api.storage, "prepare_upload_path", lambda *_args, **_kwargs: str(final_path)
    )
    monkeypatch.setattr(
        media_api.storage, "validate_target_path", lambda _path: None
    )
    return final_path


def test_media_finalize_chunk_upload_falls_back_to_copy_after_cross_device_rename(
    tmp_path, monkeypatch
):
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"trail")
    final_path = _configure_media_destination(tmp_path, monkeypatch)
    real_replace = media_api.os.replace
    replace_calls = 0

    def cross_device_then_real(source, destination):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 1:
            error = OSError("cross-device link")
            error.errno = errno.EXDEV
            error.winerror = 17
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr(media_api.os, "replace", cross_device_then_real)

    result = media_api._finalize_chunk_upload(
        str(chunk_dir), [0], "final.bin", uuid4(), None, MagicMock()
    )

    assert result == str(final_path)
    assert final_path.read_bytes() == b"trail"
    assert not chunk_dir.exists()


def test_media_finalize_chunk_upload_rejects_bad_md5_and_cleans_temporary_files(
    tmp_path, monkeypatch
):
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"trail")
    final_path = _configure_media_destination(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="MD5"):
        media_api._finalize_chunk_upload(
            str(chunk_dir),
            [0],
            "final.bin",
            uuid4(),
            None,
            MagicMock(),
            expected_size=5,
            expected_sha256=hashlib.sha256(b"trail").hexdigest(),
            expected_md5="0" * 32,
        )

    assert not final_path.exists()
    assert not chunk_dir.exists()


def test_face_cluster_preview_rescan_without_reference_faces_returns_empty_result():
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []
    db = MagicMock()
    db.query.return_value = query
    service = FaceClusterService(db=db)
    identity_id = uuid4()
    owner_id = uuid4()

    result = service.preview_identity_rescan(identity_id, owner_id)

    assert result == {
        "status": "success",
        "reason": "no_reference_faces",
        "reference_count": 0,
        "threshold": service.RESCAN_AUTO_MATCH_THRESHOLD,
        "candidate_threshold": service.RESCAN_CANDIDATE_THRESHOLD,
        "removal_threshold": service.RESCAN_REMOVAL_THRESHOLD,
        "add_candidates": [],
        "remove_candidates": [],
        "summary": {"add_count": 0, "remove_count": 0, "reassign_count": 0},
    }
    query.with_for_update.assert_not_called()
    db.rollback.assert_not_called()


@pytest.mark.parametrize(
    "status,is_hidden,evidence_type,expected",
    [
        ("confirmed", False, "city", False),
        ("ignored", True, "travel", False),
        ("ignored", True, "city", True),
    ],
)
def test_chapter_similar_suppressed_requires_matching_suppressed_evidence(
    status, is_hidden, evidence_type, expected
):
    row = SimpleNamespace(
        status=status,
        is_hidden=is_hidden,
        title="上海影像",
        evidence=[{"type": evidence_type}],
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 10),
    )

    result = chapter._similar_suppressed(
        row, date(2026, 1, 1), date(2026, 1, 10), "上海影像", "city"
    )

    assert result is expected
