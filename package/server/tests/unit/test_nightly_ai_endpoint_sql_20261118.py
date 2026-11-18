"""Nightly 2026-11-18: app/core/ai_endpoint.py 与 app/db/sql.py 盲区。"""
import sys
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.ai_endpoint import normalize_ai_api_url
from app.db.sql import as_date, as_date_string, date_only, location_summary

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture()
def sqlite_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'sql.sqlite').as_posix()}")
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_normalize_ai_api_url_migrates_local_default_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert normalize_ai_api_url("http://localhost:8001") == "http://127.0.0.1:8001"
    assert normalize_ai_api_url("http://localhost:8001/v1") == "http://127.0.0.1:8001/v1"


def test_normalize_ai_api_url_keeps_custom_endpoints(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    for value in (
        "http://localhost:8002",
        "https://localhost:8001",
        "http://[::1]:8001",
        "http://192.168.1.10:8001",
    ):
        assert normalize_ai_api_url(value) == value
    # 末尾斜杠属于路径部分，netloc 仍被迁移
    assert normalize_ai_api_url("http://localhost:8001/") == "http://127.0.0.1:8001/"


def test_normalize_ai_api_url_is_noop_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert normalize_ai_api_url("http://localhost:8001") == "http://localhost:8001"


def test_location_summary_returns_model_for_non_sqlite():
    from app.db.models.photo_metadata import PhotoMetadata

    class _Bind:
        class dialect:
            name = "postgresql"

    class _Db:
        def get_bind(self):
            return _Bind()

    assert location_summary(_Db()) is PhotoMetadata


def test_location_summary_returns_aliased_cte_for_sqlite(sqlite_db):
    from app.db.models.photo_metadata import PhotoMetadata

    aliased_model = location_summary(sqlite_db)
    assert aliased_model is not PhotoMetadata
    # SQLite 分支必须走 MATERIALIZED CTE，覆盖窄索引
    statement = sqlite_db.query(aliased_model).statement
    assert "location_metadata_summary" in str(statement)


def test_date_only_differs_per_dialect(sqlite_db):
    from app.db.models.photo import Photo

    sqlite_expr = str(date_only(sqlite_db, Photo.upload_time))
    assert "date(" in sqlite_expr.lower()

    class _Bind:
        class dialect:
            name = "postgresql"

    class _Db:
        def get_bind(self):
            return _Bind()

    pg_expr = str(date_only(_Db(), Photo.upload_time))
    assert "CAST" in pg_expr.upper()


def test_as_date_normalizes_backend_results():
    assert as_date(datetime(2021, 6, 1, 10, 30)) == date(2021, 6, 1)
    assert as_date(date(2021, 6, 1)) == date(2021, 6, 1)
    assert as_date("2021-06-01") == date(2021, 6, 1)
    assert as_date_string("2021-06-01") == "2021-06-01"
    assert as_date_string(datetime(2021, 6, 1)) == "2021-06-01"

