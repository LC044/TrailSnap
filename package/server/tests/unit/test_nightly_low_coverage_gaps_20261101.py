"""Nightly watch 2026-11-01 guards for remaining low-coverage server modules."""
import json
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import media as media_api
from app.api import photo as photo_api
from app.crud import annual_report as annual_report_crud
from app.service import chapter_days, user_storage
from app.schemas.photo import BatchDownloadRequest

pytestmark = [pytest.mark.smoke]


def test_media_content_hash_helpers_skip_and_filter_dead_files(monkeypatch):
    db = MagicMock()

    assert media_api._existing_content_hashes(db, uuid4(), []) == []
    db.query.assert_not_called()

    query = MagicMock()
    query.filter.return_value.all.return_value = [
        ("a" * 32, "exists"),
        ("b" * 32, "missing"),
        ("a" * 32, "exists"),
    ]
    db.query.reset_mock()
    db.query.return_value = query
    monkeypatch.setattr(media_api.os.path, "isfile", lambda value: value == "exists")

    assert media_api._existing_content_hashes(db, uuid4(), ["a" * 32, "b" * 32]) == ["a" * 32]


def test_media_stream_md5_reads_chunks_until_eof():
    assert media_api._stream_md5(BytesIO(b"trail")) == (
        "c6b8b33047926e58b9393538e37b8bf0"
    )


def test_user_storage_portable_mode_moves_legacy_default_to_instance(tmp_path, monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_PORTABLE", "1")
    monkeypatch.setenv("TS_DESKTOP_ROOT", str(tmp_path))

    result = user_storage.configured_storage_base(
        {"storage": {"photo_storage_path": "./data/uploads"}}
    )

    assert Path(result) == (tmp_path / "data").resolve()


def test_write_user_config_writes_atomically_and_caches_root(tmp_path, monkeypatch):
    user_id = uuid4()
    settings = {"storage": {"photo_storage_path": str(tmp_path)}}
    user_storage._STORAGE_BASE_CACHE.clear()

    target = user_storage.write_user_config(user_id, settings)

    assert Path(target) == tmp_path / "users" / str(user_id) / "config" / "settings.json"
    assert json.loads(Path(target).read_text(encoding="utf-8")) == settings
    assert user_storage.get_cached_storage_base(user_id) == str(tmp_path)


def test_annual_report_photos_groups_ranked_rows_by_month():
    first_id, second_id = uuid4(), uuid4()
    first_photo = SimpleNamespace(id=first_id)
    second_photo = SimpleNamespace(id=second_id)
    ranked = SimpleNamespace(c=SimpleNamespace(id=MagicMock(), month=MagicMock(), rn=10))
    base_query = MagicMock()
    base_query.join.return_value = base_query
    base_query.filter.return_value = base_query
    base_query.with_entities.return_value = base_query
    base_query.subquery.return_value = ranked
    top_query = MagicMock()
    top_query.filter.return_value = top_query
    top_query.order_by.return_value = top_query
    top_query.all.return_value = [(first_id, 1), (second_id, 2)]
    photo_query = MagicMock()
    photo_query.filter.return_value = photo_query
    photo_query.all.return_value = [first_photo, second_photo]
    db = MagicMock()
    db.query.side_effect = [base_query, top_query, photo_query]

    result = annual_report_crud.get_annual_report_photos(
        datetime(2026, 1, 1), datetime(2026, 12, 31), db, user_id=uuid4()
    )

    assert result == {1: [first_photo], 2: [second_photo]}
    assert db.query.call_count == 3


@pytest.mark.parametrize(
    "status,day,start,end,has_photo,status_code",
    [
        ("draft", date(2026, 7, 1), date(2026, 1, 1), date(2026, 12, 31), True, 400),
        ("confirmed", date(2025, 12, 31), date(2026, 1, 1), date(2026, 12, 31), True, 400),
        ("candidate", date(2026, 7, 1), date(2026, 1, 1), date(2026, 12, 31), False, 404),
    ],
)
def test_chapter_day_scope_rejects_invalid_state_range_and_empty_day(
    status, day, start, end, has_photo, status_code
):
    chapter = SimpleNamespace(status=status, start_date=start, end_date=end)
    photo_query = MagicMock()
    photo_query.first.return_value = object() if has_photo else None
    db = MagicMock()

    with (
        patch.object(chapter_days.chapter, "_owned", return_value=chapter),
        patch.object(chapter_days.chapter, "_photo_query", return_value=photo_query),
    ):
        with pytest.raises(HTTPException) as exc_info:
            chapter_days.day_scope(db, uuid4(), uuid4(), day)

    assert exc_info.value.status_code == status_code


def test_photo_export_cleans_temp_file_when_zip_creation_fails(tmp_path):
    temporary = tmp_path / "failed.zip"
    temporary.write_bytes(b"")
    photos = [SimpleNamespace(id=uuid4(), file_path=str(tmp_path / "photo.jpg"), filename="photo.jpg")]
    request = BatchDownloadRequest(photo_ids=[photos[0].id])
    db = MagicMock()

    with (
        patch.object(photo_api.app.crud.photo, "get_photos_by_ids", return_value=photos),
        patch.object(photo_api.tempfile, "mkstemp", return_value=(999, str(temporary))),
        patch.object(photo_api.os, "close"),
        patch.object(photo_api.zipfile, "ZipFile", MagicMock(side_effect=OSError("disk full"))),
        patch.object(photo_api.os.path, "exists", lambda value: value == str(temporary)),
        patch.object(photo_api.os, "remove") as remove,
    ):
        with pytest.raises(HTTPException) as exc_info:
            photo_api.batch_download_photos(request, db, SimpleNamespace(id=uuid4()))

    assert exc_info.value.status_code == 500
    assert "disk full" in exc_info.value.detail
    remove.assert_called_once_with(str(temporary))


class _FakeAIBatchSession:
    def __init__(self):
        self.begin_writes = 0
        self.commits = 0
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
        self._query = MagicMock()
        self._query.filter.return_value = self._query
        self._query.order_by.return_value = self._query
        self._query.limit.return_value = self._query
        self._query.all.return_value = []

    def begin_write(self):
        self.begin_writes += 1

    def commit(self):
        self.commits += 1

    def get_bind(self):
        return self._bind

    def query(self, *_args, **_kwargs):
        return self._query


def test_ticket_recovery_opens_ai_write_session_before_scanning(monkeypatch):
    session = _FakeAIBatchSession()

    monkeypatch.setattr(
        "app.service.tasks.ai_runtime.AIBatchSession", _FakeAIBatchSession
    )

    from app.service.ticket_recovery import recover_ticket_recognition

    assert recover_ticket_recognition(session, MagicMock(), uuid4()) == 0
    assert session.begin_writes == 1
    assert session.commits == 1


def test_ticket_recovery_locks_owner_on_postgresql():
    from app.service.ticket_recovery import recover_ticket_recognition

    owner_id = uuid4()

    def chain(**terminals):
        query = MagicMock()
        for name, value in terminals.items():
            setattr(query, name, value)
        query.filter.return_value = query
        return query

    user_query = chain()
    user_query.with_for_update.return_value = user_query
    user_query.one.return_value = owner_id
    photo_query = chain()
    photo_query.order_by.return_value = photo_query
    photo_query.limit.return_value = photo_query
    photo_query.all.return_value = []
    ticket_query = chain(exists=MagicMock())
    flight_query = chain(exists=MagicMock())
    task_query = chain(exists=MagicMock())
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.query.side_effect = [user_query, photo_query, ticket_query, flight_query, task_query]

    assert recover_ticket_recognition(db, MagicMock(), owner_id) == 0
    user_query.with_for_update.assert_called_once()
    db.commit.assert_called_once()



