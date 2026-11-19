"""覆盖 app/utils/desktop_data_migration.py 中的 _rewrite_database。

盲区来源：函数级静态引用扫描命中 _rewrite_database——它是离线迁移里唯一
负责把旧数据目录路径改写到新目录的入口，但既有测试
（test_desktop_data_migration.py）只通过 migrate_data_directory 整体流程
间接使用，从未直接断言它对「路径列 / JSON 列 / 非 JSON 列 / 非法 JSON」
四种列的处理差异。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app.utils.desktop_data_migration import _rewrite_database

pytestmark = [pytest.mark.smoke]


def build_database(path: Path, source: Path) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(
            "CREATE TABLE photos (id TEXT PRIMARY KEY, file_path TEXT, filename TEXT);"
            "CREATE TABLE users (id TEXT PRIMARY KEY, settings JSON);"
            "CREATE TABLE system_state (key TEXT PRIMARY KEY, value TEXT);"
        )
        db.execute("INSERT INTO photos VALUES ('p1', ?, 'photo.jpg')",
                   (str(source / "data" / "users" / "u" / "photo.jpg"),))
        db.execute("INSERT INTO users VALUES ('u', ?)",
                   (json.dumps({"storage": {"photo_storage_path": str(source / "data")}}),))
        db.execute("INSERT INTO system_state VALUES ('paths', ?)",
                   (json.dumps({"paths": [str(source / "models")]}),))
        # 非 JSON 文本：位于 system_state.value，但内容不是合法 JSON。
        db.execute("INSERT INTO system_state VALUES ('plain', ?)", ("not-json",))


def read_rows(path: Path):
    with closing(sqlite3.connect(path)) as db:
        photos = db.execute("SELECT id, file_path, filename FROM photos").fetchall()
        settings = db.execute("SELECT settings FROM users").fetchone()[0]
        state = dict(db.execute("SELECT key, value FROM system_state").fetchall())
    return photos, settings, state


def test_rewrite_database_rebases_path_and_json_columns(tmp_path):
    source = tmp_path / "旧数据"
    target = tmp_path / "新数据"
    database = tmp_path / "trailsnap.sqlite"
    build_database(database, source)

    _rewrite_database(database, source, target)

    photos, settings, state = read_rows(database)
    assert photos[0][1] == str(target / "data" / "users" / "u" / "photo.jpg")
    assert json.loads(settings)["storage"]["photo_storage_path"] == str(target / "data")
    assert json.loads(state["paths"])["paths"] == [str(target / "models")]


def test_rewrite_database_leaves_unmanaged_columns_untouched(tmp_path):
    source = tmp_path / "旧数据"
    target = tmp_path / "新数据"
    database = tmp_path / "trailsnap.sqlite"
    build_database(database, source)

    _rewrite_database(database, source, target)

    photos, _settings, state = read_rows(database)
    assert photos[0][2] == "photo.jpg"
    # 非法 JSON 的列被跳过，而不是被清空或改写。
    assert state["plain"] == "not-json"


def test_rewrite_database_keeps_external_paths_outside_source(tmp_path):
    source = tmp_path / "旧数据"
    target = tmp_path / "新数据"
    outside = tmp_path / "外部" / "photo.jpg"
    database = tmp_path / "trailsnap.sqlite"
    build_database(database, source)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("INSERT INTO photos VALUES ('p2', ?, 'other.jpg')", (str(outside),))

    _rewrite_database(database, source, target)

    photos, _settings, _state = read_rows(database)
    values = {row[0]: row[1] for row in photos}
    assert values["p2"] == str(outside)


def test_rewrite_database_rejects_corrupted_database(tmp_path):
    source = tmp_path / "旧数据"
    target = tmp_path / "新数据"
    database = tmp_path / "trailsnap.sqlite"
    build_database(database, source)
    # 写入非法页头使 PRAGMA quick_check 失败。
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("PRAGMA writable_schema=ON")
        db.execute("UPDATE sqlite_master SET sql='garbage' WHERE name='photos'")

    # 损坏的库在 quick_check 阶段就被拒绝（sqlite 报 schema 错误）。
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        _rewrite_database(database, source, target)
