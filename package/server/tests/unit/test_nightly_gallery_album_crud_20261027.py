"""Nightly coverage for the external-gallery service and the album CRUD helpers.

The 2026-10-27 backend coverage scan (round 2) reported:

* ``service/gallery_service.py`` at 84.1% -- 33 missed lines.  The missed code
  is the *conflict* half of the gallery rules: a candidate directory that
  lives below an already registered gallery, the read-only probe, the
  "cannot list" branches of the directory tree and the failed scan task.
* ``crud/album.py`` at 81.8% -- 53 missed lines, mostly the pure helpers that
  decode face rectangles and build the folder filter, plus the shared-user
  handling of ``update_album``.

None of these paths need a running service: the gallery service works against
a temporary directory and a stubbed config manager, the album helpers are
pure functions or run against a mocked session.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.crud import album as album_crud
from app.service import gallery_service


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# service/gallery_service.py -- normalize_path / relation
# ---------------------------------------------------------------------------


def test_normalize_path_returns_an_empty_string_for_an_empty_input():
    # Only a genuinely empty string short-circuits. A whitespace-only string is
    # stripped and then resolved like any other relative path.
    assert gallery_service.normalize_path("") == ""


def test_normalize_path_falls_back_to_abspath_when_resolve_fails(monkeypatch, tmp_path):
    """``Path.resolve`` can raise on a broken link chain; the display path must survive."""
    monkeypatch.chdir(tmp_path)

    def broken(self, *args, **kwargs):
        raise OSError("cannot resolve")

    monkeypatch.setattr("pathlib.Path.resolve", broken)
    result = gallery_service.normalize_path("Photos/./family")

    assert result
    assert os.path.isabs(result)
    assert result.endswith("family")


def test_relation_reports_none_for_paths_on_different_drives(monkeypatch):
    """``os.path.commonpath`` raises ValueError for a drive mismatch on Windows."""
    monkeypatch.setattr(gallery_service.os.path, "commonpath",
                        lambda paths: (_ for _ in ()).throw(ValueError("different drives")))

    assert gallery_service.relation("C:\\a", "D:\\b") == "none"


def test_is_within_root_accepts_the_root_itself(monkeypatch, tmp_path):
    monkeypatch.setattr(gallery_service, "EXTERNAL_GALLERY_ROOT", str(tmp_path))

    assert gallery_service.is_within_root(str(tmp_path)) is True
    assert gallery_service.is_within_root(str(tmp_path / "child")) is True


# ---------------------------------------------------------------------------
# service/gallery_service.py -- _probe_directory / list_candidates
# ---------------------------------------------------------------------------


def test_probe_directory_reports_a_missing_path():
    probe = gallery_service._probe_directory(os.path.join(os.sep, "definitely", "missing", "xyz"))

    assert probe["exists"] is False
    assert probe["is_dir"] is False
    assert probe["readable"] is False
    assert probe["read_only"] is None


def test_probe_directory_reports_read_only_for_a_read_only_folder(tmp_path, monkeypatch):
    folder = tmp_path / "locked"
    folder.mkdir()
    monkeypatch.setattr(gallery_service.os, "access",
                        lambda path, mode: mode == os.R_OK)

    probe = gallery_service._probe_directory(str(folder))

    assert probe["exists"] is True
    assert probe["readable"] is True
    assert probe["read_only"] is True


def test_list_candidates_flags_a_conflicting_registered_parent(tmp_path, monkeypatch):
    """A candidate that contains an already registered gallery is a conflict.

    ``list_candidates`` only enumerates the *direct* children of the discovery
    root, so the conflict is reported on the parent that contains the
    registered sub-folder.
    """
    root = tmp_path / "Photos"
    (root / "family" / "2024").mkdir(parents=True)
    registered = root / "family" / "2024"
    monkeypatch.setattr(gallery_service, "EXTERNAL_GALLERY_ROOT", str(root))
    monkeypatch.setattr(gallery_service, "_registered_keys",
                        lambda uid, db: [(gallery_service._key(str(registered)), str(registered))])

    data = gallery_service.list_candidates("u", db=None)

    entries = {item["name"]: item for item in data["directories"]}
    assert entries["family"]["conflict_path"] == str(registered)
    assert entries["family"]["registered"] is False


def test_list_candidates_survives_an_unreadable_root(tmp_path, monkeypatch):
    root = tmp_path / "Photos"
    (root / "family").mkdir(parents=True)
    monkeypatch.setattr(gallery_service, "EXTERNAL_GALLERY_ROOT", str(root))
    monkeypatch.setattr(gallery_service, "_registered_keys", lambda uid, db: [])

    def broken_scandir(path):
        raise OSError("cannot enumerate")

    monkeypatch.setattr(gallery_service.os, "scandir", broken_scandir)

    data = gallery_service.list_candidates("u", db=None)

    assert data["root_exists"] is True
    assert data["directories"] == []


# ---------------------------------------------------------------------------
# service/gallery_service.py -- list_directory_tree
# ---------------------------------------------------------------------------


def test_list_directory_tree_reports_a_missing_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(gallery_service, "EXTERNAL_GALLERY_ROOT", str(tmp_path))

    with pytest.raises(FileNotFoundError):
        gallery_service.list_directory_tree(str(tmp_path / "nope"))


def test_list_directory_tree_marks_a_leaf_directory(tmp_path, monkeypatch):
    root = tmp_path / "Photos"
    (root / "leaf").mkdir(parents=True)
    (root / "branch" / "nested").mkdir(parents=True)
    monkeypatch.setattr(gallery_service, "EXTERNAL_GALLERY_ROOT", str(root))

    tree = gallery_service.list_directory_tree()

    entries = {item["name"]: item for item in tree["directories"]}
    assert entries["leaf"]["is_leaf"] is True
    assert entries["branch"]["is_leaf"] is False


def test_has_visible_subdirectory_survives_a_broken_directory(tmp_path, monkeypatch):
    root = tmp_path / "Photos"
    root.mkdir(parents=True)
    monkeypatch.setattr(gallery_service, "EXTERNAL_GALLERY_ROOT", str(root))

    def broken_scandir(path):
        raise OSError("cannot enumerate")

    monkeypatch.setattr(gallery_service.os, "scandir", broken_scandir)

    assert gallery_service._has_visible_subdirectory(str(root), str(root)) is False


# ---------------------------------------------------------------------------
# service/gallery_service.py -- validate_path
# ---------------------------------------------------------------------------


def test_validate_path_rejects_an_empty_path():
    result = gallery_service.validate_path("   ", "u", db=None)

    assert result["valid"] is False
    assert result["error"] == gallery_service.ERR_INVALID


def test_validate_path_rejects_a_file(tmp_path):
    target = tmp_path / "photo.jpg"
    target.write_bytes(b"x")

    result = gallery_service.validate_path(str(target), "u", db=None)

    assert result["valid"] is False
    assert result["error"] == gallery_service.ERR_INVALID


def test_validate_path_reports_a_child_conflict(tmp_path, monkeypatch):
    """The candidate is a *parent* of an already registered gallery."""
    root = tmp_path / "Photos"
    registered = root / "family" / "2024"
    registered.mkdir(parents=True)
    candidate = root / "family"
    candidate.mkdir(exist_ok=True)
    monkeypatch.setattr(gallery_service, "EXTERNAL_GALLERY_ROOT", str(root))
    monkeypatch.setattr(gallery_service, "_registered_keys",
                        lambda uid, db: [(gallery_service._key(str(registered)), str(registered))])

    result = gallery_service.validate_path(str(candidate), "u", db=None)

    assert result["valid"] is False
    assert result["error"] == gallery_service.ERR_CHILD_CONFLICT
    assert result["conflict"] == str(registered)


# ---------------------------------------------------------------------------
# service/gallery_service.py -- batch_add
# ---------------------------------------------------------------------------


def _mock_config_manager(monkeypatch, existing):
    """Let ``batch_add`` read ``existing`` and record the merged directories."""
    cfg = MagicMock()
    cfg.storage.external_directories = list(existing)
    cfg.model_dump.return_value = {"storage": {"external_directories": list(existing)}}
    captured = {"merged": None}

    def fake_update(uid, settings, db):
        captured["merged"] = settings.get("storage", {}).get("external_directories")

    monkeypatch.setattr(gallery_service.config_manager, "get_user_config",
                        MagicMock(return_value=cfg))
    monkeypatch.setattr(gallery_service.config_manager, "update_user_config",
                        MagicMock(side_effect=fake_update))
    return captured


def test_batch_add_returns_an_empty_result_for_no_paths():
    assert gallery_service.batch_add([], "u", db=None) == {
        "added": [], "skipped": [], "task_id": None, "errors": [],
    }


def test_batch_add_returns_an_empty_result_when_every_path_is_blank():
    assert gallery_service.batch_add(["", "   ", None], "u", db=None) == {
        "added": [], "skipped": [], "task_id": None, "errors": [],
    }


def test_batch_add_reports_a_failed_scan_task(tmp_path, monkeypatch):
    """A scan task that cannot be created must not lose the added folders."""
    folder = tmp_path / "family"
    folder.mkdir()
    _mock_config_manager(monkeypatch, [])
    monkeypatch.setattr(gallery_service.TaskManager, "get_instance",
                        MagicMock(side_effect=RuntimeError("scanner offline")))

    result = gallery_service.batch_add([str(folder)], "u", db=None)

    assert result["task_id"] is None
    assert result["added"] == [str(folder)]
    assert result["errors"][0]["error"] == "SCAN_TASK_FAILED"


def test_batch_add_skips_duplicate_paths(tmp_path, monkeypatch):
    folder = tmp_path / "family"
    folder.mkdir()
    _mock_config_manager(monkeypatch, [])
    task = SimpleNamespace(id="task-1")
    monkeypatch.setattr(gallery_service.TaskManager, "get_instance",
                        MagicMock(return_value=SimpleNamespace(add_task=MagicMock(return_value=task))))

    result = gallery_service.batch_add([str(folder), str(folder)], "u", db=None)

    assert result["added"] == [str(folder)]
    assert result["task_id"] == "task-1"


# ---------------------------------------------------------------------------
# crud/album.py -- pure helpers
# ---------------------------------------------------------------------------


def test_decode_face_rect_returns_none_for_a_broken_payload():
    assert album_crud._decode_face_rect("{not json") is None
    assert album_crud._decode_face_rect(json.dumps({"x": 1})) is None
    assert album_crud._decode_face_rect(None) is None


def test_decode_face_rect_keeps_a_list_payload():
    payload = [{"x": 1, "y": 2}]
    assert album_crud._decode_face_rect(payload) == payload
    assert album_crud._decode_face_rect(json.dumps(payload)) == payload


def test_postgresql_cte_hint_depends_on_the_dialect():
    postgres = MagicMock()
    postgres.get_bind.return_value.dialect.name = "postgresql"
    assert album_crud._postgresql_cte_hint(postgres) == "MATERIALIZED"

    sqlite = MagicMock()
    sqlite.get_bind.return_value.dialect.name = "sqlite"
    assert album_crud._postgresql_cte_hint(sqlite) == ""


def test_postgresql_cte_hint_survives_a_broken_bind():
    db = MagicMock()
    db.get_bind.side_effect = RuntimeError("no bind")

    assert album_crud._postgresql_cte_hint(db) == ""


def test_build_folder_condition_ignores_a_non_list():
    assert album_crud._build_folder_condition(None) is None
    assert album_crud._build_folder_condition("Photos/Trips") is None
    assert album_crud._build_folder_condition([]) is None


def test_build_folder_condition_skips_blank_and_duplicate_entries():
    condition = album_crud._build_folder_condition(
        ["Photos/Trips", "  ", "Photos\\Trips", "Photos/Trips", 42]
    )

    assert condition is not None
    # The folder names are bound parameters, not literals in the SQL text.
    params = condition.compile().params
    assert "Photos/Trips/%" in params.values()
    assert "%/Photos/Trips/%" in params.values()


# ---------------------------------------------------------------------------
# crud/album.py -- update_album
# ---------------------------------------------------------------------------


def _album_schema(**overrides):
    from app.schemas import album as album_schemas

    return album_schemas.AlbumUpdate(**overrides)


def test_update_album_replaces_the_shared_users(tmp_path):
    db = MagicMock()
    db_album = MagicMock()
    db_album.name = "old"
    shared_id = uuid4()
    user = SimpleNamespace(id=shared_id)

    with patch.object(album_crud, "get_album", lambda *a, **k: db_album):
        db.query.return_value.filter.return_value.all.return_value = [user]
        result = album_crud.update_album(
            db, "album-1", _album_schema(name="new", shared_users=[shared_id])
        )

    assert result is db_album
    assert db_album.shared_users == [user]
    db.commit.assert_called_once()


def test_update_album_clears_the_shared_users(tmp_path):
    db = MagicMock()
    db_album = MagicMock()
    db_album.shared_users = [SimpleNamespace(id="u-1")]

    with patch.object(album_crud, "get_album", lambda *a, **k: db_album):
        album_crud.update_album(db, "album-1", _album_schema(shared_users=[]))

    assert db_album.shared_users == []


def test_update_album_returns_none_for_a_missing_album():
    db = MagicMock()

    with patch.object(album_crud, "get_album", lambda *a, **k: None):
        assert album_crud.update_album(db, "album-1", _album_schema(name="new")) is None


def test_delete_album_deletes_a_found_album():
    db = MagicMock()
    db_album = MagicMock()

    with patch.object(album_crud, "get_album", lambda *a, **k: db_album):
        assert album_crud.delete_album(db, "album-1") is db_album

    db.delete.assert_called_once_with(db_album)
    db.commit.assert_called_once()


def test_delete_album_is_a_no_op_for_a_missing_album():
    db = MagicMock()

    with patch.object(album_crud, "get_album", lambda *a, **k: None):
        assert album_crud.delete_album(db, "album-1") is None

    db.delete.assert_not_called()
