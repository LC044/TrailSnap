"""Offline cleanup preserves user metadata and creates a restorable backup."""

import json
import sqlite3

import pytest

from scripts.clean_video_metadata_sqlite import clean_database


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def make_database(tmp_path):
    path = tmp_path / "library.sqlite"
    original = json.dumps({"MediaType": "video", "mcvr": "X" * 100000,
                           "covr": "cover", "tnal": "preview", "snal": "vendor",
                           "CreateDate": "2024-05-01", "GPSCoordinates": "+30+114/",
                           "Model": "手机", "Duration": 10, "custom": {"a": 1}})
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE photos(id TEXT PRIMARY KEY, file_type TEXT);"
            "CREATE TABLE photo_metadata(photo_id TEXT PRIMARY KEY, exif_info TEXT, city TEXT);"
            "CREATE TABLE notes(content TEXT);"
            "INSERT INTO photos VALUES('v', 'video'), ('i', 'image');"
            "INSERT INTO notes VALUES('user note');"
        )
        connection.executemany("INSERT INTO photo_metadata VALUES(?, ?, ?)",
                               [("v", original, "武汉"), ("i", original, "北京")])
    return path, original


def test_dry_run_leaves_database_unchanged(tmp_path):
    path, original = make_database(tmp_path)
    before = path.read_bytes()
    result = clean_database(path, tmp_path / "backups")
    assert result["changed_rows"] == 1
    assert path.read_bytes() == before
    assert not (tmp_path / "backups").exists()


def test_apply_backs_up_and_only_removes_binary_video_fields(tmp_path):
    path, original = make_database(tmp_path)
    result = clean_database(path, tmp_path / "backups", apply=True, vacuum=True)
    assert result["changed_rows"] == 1
    assert result["removed_keys"] == {"mcvr": 1, "covr": 1, "tnal": 1, "snal": 1}
    with sqlite3.connect(result["backup"]) as backup:
        assert backup.execute("SELECT exif_info FROM photo_metadata WHERE photo_id='v'").fetchone()[0] == original
    with sqlite3.connect(path) as connection:
        saved, city = connection.execute("SELECT exif_info, city FROM photo_metadata WHERE photo_id='v'").fetchone()
        expected = json.loads(original)
        for key in ("mcvr", "snal", "tnal", "covr"):
            del expected[key]
        assert json.loads(saved) == expected
        assert city == "武汉"
        assert connection.execute("SELECT exif_info FROM photo_metadata WHERE photo_id='i'").fetchone()[0] == original
        assert connection.execute("SELECT content FROM notes").fetchone()[0] == "user note"
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_invalid_json_rolls_back_all_updates(tmp_path):
    path, original = make_database(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO photos VALUES('bad', 'video')")
        connection.execute("INSERT INTO photo_metadata VALUES('bad', '{bad', NULL)")
    with pytest.raises(json.JSONDecodeError):
        clean_database(path, tmp_path / "backups", apply=True)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT exif_info FROM photo_metadata WHERE photo_id='v'").fetchone()[0] == original
