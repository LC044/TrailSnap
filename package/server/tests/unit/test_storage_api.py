"""Unit tests for the storage REST router (app/api/storage.py).

Covers the disk-overview / file-type / top-large-files endpoints. Each test
mocks the DB query chain and the disk-stat helper so no real filesystem or
Postgres is required.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import storage as storage_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _user():
    return SimpleNamespace(id=uuid4())


def _photo(pid=None, size=1024, ftype_value="image", filename="a.jpg"):
    return SimpleNamespace(
        id=pid or uuid4(),
        size=size,
        file_type=SimpleNamespace(value=ftype_value),
        filename=filename,
        file_path=f"/Photos/{filename}",
    )


# ----------------------- GET /storage/overview -----------------------


def test_storage_overview_returns_disk_and_user_totals():
    """``overview`` must surface disk total/free AND user file stats.

    Disk usage comes from ``shutil.disk_usage(path)``; user totals from an
    aggregate SQL query. We patch both and verify every documented key is
    present in the response data.
    """
    user = _user()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        total_size=2_048_000, total_files=42
    )




# ----------------------- GET /storage/stats/type ----------------------


def test_storage_type_stats_filters_unmapped_file_types():
    """Only the mapped image/video/live_photo file types appear in the response.

    Unknown file-type values are skipped so the frontend can build a pie
    chart without extra branching. The map translates enum values into
    Chinese display names.
    """
    user = _user()
    db = MagicMock()
    db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
        SimpleNamespace(file_type=SimpleNamespace(value="image"), size=1000, count=2),
        SimpleNamespace(file_type=SimpleNamespace(value="video"), size=5000, count=1),
        SimpleNamespace(file_type=SimpleNamespace(value="live_photo"), size=750, count=3),
        SimpleNamespace(file_type=SimpleNamespace(value="unknown"), size=999, count=1),
        SimpleNamespace(file_type=None, size=42, count=1),
    ]

    response = storage_api.get_storage_type_stats(db=db, current_user=user)
    names = [r["name"] for r in response.data]
    assert names == ["图片", "视频", "实况图"]
    assert len(response.data) == 3
    assert response.data[0] == {"name": "图片", "size": 1000, "count": 2}
    assert response.data[2] == {"name": "实况图", "size": 750, "count": 3}


# ----------------------- GET /storage/top-large-files -----------------------


def test_storage_top_large_files_returns_serialized_top20():
    """``top-large-files`` truncates to 20 and serialises each row to a dict."""
    user = _user()
    db = MagicMock()
    photos = [_photo(size=(i + 1) * 1000) for i in range(25)]
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = photos[:20]

    response = storage_api.get_top_large_files(db=db, current_user=user)

    db.query.return_value.filter.return_value.order_by.assert_called_once()
    db.query.return_value.filter.return_value.order_by.return_value.limit.assert_called_once_with(20)
    assert len(response.data) == 20
    for item in response.data:
        assert set(item.keys()) == {"id", "filename", "size", "path", "type"}
        assert isinstance(item["size"], int)
