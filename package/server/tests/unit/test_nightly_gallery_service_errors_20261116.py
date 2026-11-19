"""2026-11-16 nightly coverage for ``app/service/gallery_service.py``.

The 2026-11-16 backend coverage scan reported ``service/gallery_service.py``
at 95.7% with 9 missed lines:

* ``_get_external_directories`` degrading to an empty list when the user
  config cannot be read (lines 107-109);
* ``list_directory_tree`` skipping entries that raise ``OSError``
  (line 207-208) and skipping directories that resolve outside the
  gallery root (lines 200-201);
* ``validate_path`` reporting an unreadable directory (line 246).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.service import gallery_service as gallery


pytestmark = [pytest.mark.smoke]


def test_get_external_directories_degrades_to_an_empty_list(monkeypatch):
    def _boom(_user_id, _db):
        raise RuntimeError("config unavailable")

    monkeypatch.setattr(gallery.config_manager, "get_user_config", _boom)
    assert gallery._get_external_directories("user-1", MagicMock()) == []


def test_get_external_directories_reads_the_user_config(monkeypatch):
    config = SimpleNamespace(storage=SimpleNamespace(external_directories=["/a", "/b"]))
    monkeypatch.setattr(
        gallery.config_manager, "get_user_config", lambda _user_id, _db: config
    )
    assert gallery._get_external_directories("user-1", MagicMock()) == ["/a", "/b"]


def test_get_external_directories_tolerates_a_missing_setting(monkeypatch):
    config = SimpleNamespace(storage=SimpleNamespace(external_directories=None))
    monkeypatch.setattr(
        gallery.config_manager, "get_user_config", lambda _user_id, _db: config
    )
    assert gallery._get_external_directories("user-1", MagicMock()) == []


def test_list_directory_tree_skips_entries_that_raise_oserror(monkeypatch, tmp_path):
    root = tmp_path / "gallery"
    root.mkdir()
    (root / "good").mkdir()
    monkeypatch.setattr(gallery, "EXTERNAL_GALLERY_ROOT", str(root))
    monkeypatch.setattr(gallery, "normalize_path", lambda p: str(p))

    class _BrokenEntry:
        name = "broken"
        path = str(root / "broken")

        def is_dir(self, follow_symlinks=True):
            raise OSError("unreadable entry")

    class _GoodEntry:
        name = "good"
        path = str(root / "good")

        def is_dir(self, follow_symlinks=True):
            return True

    @contextmanager
    def _fake_scandir(_path):
        yield iter([_BrokenEntry(), _GoodEntry()])

    monkeypatch.setattr(os, "scandir", _fake_scandir)
    monkeypatch.setattr(gallery, "_has_visible_subdirectory", lambda _path, _root: False)

    result = gallery.list_directory_tree()

    assert [item["name"] for item in result["directories"]] == ["good"]

def test_list_directory_tree_rejects_a_path_outside_the_root(monkeypatch, tmp_path):
    root = tmp_path / "gallery"
    root.mkdir()
    monkeypatch.setattr(gallery, "EXTERNAL_GALLERY_ROOT", str(root))

    with pytest.raises(PermissionError):
        gallery.list_directory_tree(str(tmp_path / "elsewhere"))


def test_list_directory_tree_requires_an_existing_directory(monkeypatch, tmp_path):
    root = tmp_path / "gallery"
    root.mkdir()
    monkeypatch.setattr(gallery, "EXTERNAL_GALLERY_ROOT", str(root))

    with pytest.raises(FileNotFoundError):
        gallery.list_directory_tree(str(root / "missing"))




def test_list_directory_tree_skips_directories_outside_the_root(monkeypatch, tmp_path):
    root = tmp_path / "gallery"
    root.mkdir()
    (root / "inside").mkdir()
    monkeypatch.setattr(gallery, "EXTERNAL_GALLERY_ROOT", str(root))

    class _Entry:
        name = "inside"
        path = str(root / "inside")

        def is_dir(self, follow_symlinks=True):
            return True

    @contextmanager
    def _fake_scandir(_path):
        yield iter([_Entry()])

    monkeypatch.setattr(os, "scandir", _fake_scandir)
    # The entry resolves outside of the configured gallery root.
    monkeypatch.setattr(
        gallery,
        "normalize_path",
        lambda p: str(root) if p == str(root) else str(tmp_path / "outside"),
    )
    monkeypatch.setattr(gallery, "relation", lambda a, b: "equal" if a == b else "none")

    result = gallery.list_directory_tree()

    assert result["directories"] == []


def test_validate_path_reports_an_unreadable_directory(monkeypatch, tmp_path):
    target = tmp_path / "gallery"
    target.mkdir()
    monkeypatch.setattr(gallery, "normalize_path", lambda p: str(p))
    monkeypatch.setattr(gallery.os, "access", lambda *_args: False)

    result = gallery.validate_path(str(target), "user-1", MagicMock())

    assert result["valid"] is False
    assert result["error"] == gallery.ERR_NOT_READABLE

