"""Unit tests for the storage REST router (app/api/storage.py).

Covers the disk-overview / file-type / top-large-files / device /
recoverable endpoints. Each test mocks the DB query chain and the
disk-stat helper so no real filesystem or Postgres is required.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import storage as storage_api
from app.core import config_manager as _config_mod
from app.db.models.photo import ImageType, FileType


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

    with patch.object(_config_mod.config_manager, "get_user_config",
                      return_value=SimpleNamespace(storage=SimpleNamespace(photo_storage_path="/Photos"))), \
         patch("shutil.disk_usage",
               return_value=SimpleNamespace(total=10_000_000, free=4_000_000, used=6_000_000)), \
         patch("time.strftime", return_value="2026-08-03T10:00:00"):
        response = storage_api.get_storage_overview(db=db, current_user=user)

    assert response.code == 0
    payload = response.data
    assert payload["total_size"] == 2_048_000
    assert payload["total_files"] == 42
    assert payload["disk_total_size"] == 10_000_000
    assert payload["disk_free_size"] == 4_000_000
    assert payload["scan_date"] == "2026-08-03T10:00:00"


def test_storage_overview_falls_back_to_zero_when_disk_usage_raises():
    """如果配置路径不存在，shutil 会抛 FileNotFoundError；这里验证兜底为 0."""
    user = _user()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        total_size=None, total_files=None
    )

    with patch.object(_config_mod.config_manager, "get_user_config",
                      return_value=SimpleNamespace(storage=SimpleNamespace(photo_storage_path="/missing"))), \
         patch("shutil.disk_usage", side_effect=FileNotFoundError):
        response = storage_api.get_storage_overview(db=db, current_user=user)

    assert response.data["disk_total_size"] == 0
    assert response.data["disk_free_size"] == 0
    assert response.data["total_size"] == 0
    assert response.data["total_files"] == 0


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


# ----------------------- GET /storage/stats/device ----------------------


def test_storage_device_stats_groups_by_model_and_filters_unknowns():
    """Camera-model groups: skip blanks / 'unknown' / '未知' / '未知设备'."""
    user = _user()
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = [
        SimpleNamespace(model="iPhone 15 Pro", size=4000, count=10),
        SimpleNamespace(model="Canon EOS R5", size=8000, count=5),
        SimpleNamespace(model=None, size=1, count=1),
        SimpleNamespace(model="", size=1, count=1),
        SimpleNamespace(model="unknown", size=1, count=1),
        SimpleNamespace(model="未知", size=1, count=1),
        SimpleNamespace(model="未知设备", size=1, count=1),
    ]

    response = storage_api.get_storage_device_stats(db=db, current_user=user)
    by_name = {r["name"]: r for r in response.data}
    assert set(by_name) == {"iPhone 15 Pro", "Canon EOS R5"}
    # size desc 排序
    assert response.data[0]["name"] == "Canon EOS R5"
    assert response.data[0]["size"] == 8000
    assert response.data[1]["name"] == "iPhone 15 Pro"


def test_storage_device_stats_returns_empty_when_no_models():
    user = _user()
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = []

    response = storage_api.get_storage_device_stats(db=db, current_user=user)
    assert response.data == []


# ----------------------- GET /storage/stats/recoverable ----------------------


def test_storage_recoverable_stats_aggregates_each_category():
    """screenshot / video / duplicate / similar 四类聚合."""
    user = _user()
    db = MagicMock()

    first_results = iter([SimpleNamespace(size=200, count=3), SimpleNamespace(size=4000, count=2)])
    db.query.return_value.filter.return_value.first.side_effect = lambda: next(first_results)
    md5_rows = [SimpleNamespace(md5="abc", count=3, size=900, max_size=400)]
    db.query.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = md5_rows

    cluster = SimpleNamespace(cluster_id=1)
    db.query.return_value.join.return_value.join.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = [cluster]
    db.query.return_value.join.return_value.filter.return_value.all.return_value = [
        _photo(size=200), _photo(size=150), _photo(size=100),
    ]

    response = storage_api.get_storage_recoverable_stats(db=db, current_user=user)

    payload = response.data
    assert payload["screenshot"] == {"size": 200, "count": 3}
    assert payload["video"] == {"size": 4000, "count": 2}
    # duplicate: 900 - 400 = 500 size, count = 3 - 1 = 2
    assert payload["duplicate"] == {"size": 500, "count": 2}
    # similar: 3 张照片排序后取最大 200，剩下 150 + 100 = 250
    assert payload["similar"] == {"size": 250, "count": 2}


def test_storage_recoverable_stats_handles_empty_db():
    """没有任何照片/无重复时，每类都返回 0."""
    user = _user()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [SimpleNamespace(size=0, count=0), SimpleNamespace(size=0, count=0)]
    db.query.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = []
    db.query.return_value.join.return_value.join.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = []

    response = storage_api.get_storage_recoverable_stats(db=db, current_user=user)
    assert response.data == {
        "similar": {"size": 0, "count": 0},
        "duplicate": {"size": 0, "count": 0},
        "screenshot": {"size": 0, "count": 0},
        "video": {"size": 0, "count": 0},
    }


# ----------------------- GET /storage/top-large-files -----------------------


def test_storage_top_large_files_returns_serialized_top20():
    user = _user()
    photos = sorted([_photo(size=1024 * i, filename=f"img_{i}.jpg") for i in range(1, 6)], key=lambda p: p.size, reverse=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = photos

    response = storage_api.get_top_large_files(db=db, current_user=user)
    assert response.code == 0
    assert len(response.data) == 5
    # 默认 desc 排序：最大在前
    assert response.data[0]["size"] == 1024 * 5
    assert response.data[-1]["size"] == 1024
