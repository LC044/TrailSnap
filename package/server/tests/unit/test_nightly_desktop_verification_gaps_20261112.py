"""Nightly watch 2026-11-12 · app/utils/desktop_verification.py 盲区补测。

被测模块：app/utils/desktop_verification.py
覆盖点（2026-11-12 覆盖率基线中未触达的分支）：
- photo_paths：photos 表缺少必需列时直接返回；storage_root_id 引用无效；
  存储根 kind 非法；legacy（ref 与 relative 均为空）记录按原路径产出。
- media_baseline：达到 limit 后停止收集。
- verify_media：进度回调被触发、校验通过计数、基线中缺失的记录报错。

全部使用 tmp_path 下的真实 sqlite 文件，不依赖 Postgres。
"""

import sqlite3
from pathlib import Path

import pytest

from app.utils.desktop_verification import media_baseline, photo_paths, verify_media

pytestmark = [pytest.mark.smoke, pytest.mark.module_automatic_upgrade]


def _make_library(root: Path, rows=(), roots=(), legacy_table=False) -> Path:
    """构造一个最小的桌面图库：root/data/trailsnap.sqlite。"""
    database = root / "data" / "trailsnap.sqlite"
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as db:
        if legacy_table:
            db.execute("CREATE TABLE photos (id TEXT, owner_id TEXT, file_path TEXT)")
        else:
            db.execute(
                "CREATE TABLE photos (id TEXT, owner_id TEXT, file_path TEXT,"
                " storage_root_id TEXT, storage_relative_path TEXT)"
            )
            db.execute("CREATE TABLE storage_roots (id TEXT, owner_id TEXT, kind TEXT, location TEXT)")
            for root_row in roots:
                db.execute("INSERT INTO storage_roots VALUES (?,?,?,?)", root_row)
        for photo in rows:
            db.execute("INSERT INTO photos VALUES (?,?,?,?,?)", photo)
    return database


def test_photo_paths_skips_table_without_required_columns(tmp_path):
    _make_library(tmp_path, legacy_table=True)
    with sqlite3.connect((tmp_path / "data/trailsnap.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        assert list(photo_paths(db, tmp_path)) == []


def test_photo_paths_rejects_invalid_storage_root_reference(tmp_path):
    _make_library(tmp_path,
                  rows=[("p1", "owner-1", "legacy.jpg", "missing-root", "a.jpg")],
                  roots=[("root-1", "owner-1", "managed", "photos")])
    with sqlite3.connect((tmp_path / "data/trailsnap.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        with pytest.raises(ValueError) as excinfo:
            list(photo_paths(db, tmp_path))
    assert "存储目录引用无效" in str(excinfo.value)


def test_photo_paths_rejects_unknown_storage_root_kind(tmp_path):
    _make_library(tmp_path,
                  rows=[("p1", "owner-1", "legacy.jpg", "root-1", "a.jpg")],
                  roots=[("root-1", "owner-1", "mystery", "photos")])
    with sqlite3.connect((tmp_path / "data/trailsnap.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        with pytest.raises(ValueError) as excinfo:
            list(photo_paths(db, tmp_path))
    assert "存储目录配置无效" in str(excinfo.value)


def test_photo_paths_yields_legacy_rows_without_references(tmp_path):
    _make_library(tmp_path,
                  rows=[("p1", "owner-1", "legacy.jpg", None, None)],
                  roots=[])
    with sqlite3.connect((tmp_path / "data/trailsnap.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        rows = list(photo_paths(db, tmp_path))
    assert rows == [("p1", "owner-1", "legacy.jpg")]


def test_media_baseline_stops_at_limit(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    for index in range(3):
        (media / f"{index}.jpg").write_bytes(b"data")
    _make_library(tmp_path,
                  rows=[(f"p{i}", "owner-1", str(media / f"{i}.jpg"), None, None) for i in range(3)],
                  roots=[])
    baseline = media_baseline(tmp_path, limit=2)
    assert len(baseline) == 2
    assert {item["id"] for item in baseline} == {"p0", "p1"}
    assert all(item["copied"] for item in baseline)


def test_verify_media_reports_progress_and_counts(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    target = media / "a.jpg"
    target.write_bytes(b"payload")
    _make_library(tmp_path,
                  rows=[("p1", "owner-1", str(target), None, None)],
                  roots=[])
    baseline = media_baseline(tmp_path)
    seen = []
    verified = verify_media(tmp_path, baseline, progress=lambda current, total: seen.append((current, total)))
    assert verified == 1
    assert seen and seen[-1] == (1, 1)


def test_verify_media_rejects_missing_records(tmp_path):
    _make_library(tmp_path, rows=[], roots=[])
    with pytest.raises(ValueError) as excinfo:
        verify_media(tmp_path, [{"id": "ghost", "copied": True, "sha256Prefix": "0" * 64}])
    assert "缺少原有照片记录" in str(excinfo.value)
