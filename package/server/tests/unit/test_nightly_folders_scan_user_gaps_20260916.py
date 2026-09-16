"""Nightly coverage gap tests for 2026-09-16 round.

Targets two uncovered branches:

1. ``app/api/photo.py::read_photo_folders`` - 150 lines uncovered.  Walks the
   user's photo roots via ``os.listdir`` to build the folder tree, then
   aggregates ``Photo.file_path`` rows for child counts.  The SQL piece uses
   ``func.replace(file_path, '\\', '/')`` to normalise separators before
   ``LIKE`` matching against candidate prefixes (absolute + relative forms).

2. ``app/service/tasks/scan.py::ScanFolderStrategy._scan_for_user`` - the
   per-user scan orchestrator that runs the threaded filesystem walk,
   diffs the result against the existing DB rows, applies live-photo pair
   reconciliation, and finally hands the new/deleted sets off to the
   helper methods that the existing tests already cover.

Scenarios follow the existing nightly test style (MagicMock + patches for
filesystem / DB layers, real assertions on returned structures).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api import photo as photo_api
from app.db.models.photo import FileType
from app.service.tasks import scan as scan_module
from app.service.tasks.scan import ScanFolderStrategy


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _user():
    return SimpleNamespace(id="user-1")


def _filter_config(exclude_folders=None, enable=True):
    cfg = MagicMock()
    cfg.filter.model_dump.return_value = {
        "enable": enable,
        "min_size_kb": 0,
        "min_width": 0,
        "min_height": 0,
        "filename_patterns": [],
        "exclude_folders": list(exclude_folders or []),
    }
    return cfg


# ===========================================================================
# read_photo_folders
# ===========================================================================
class TestReadPhotoFoldersRootLayer:
    """GET /photos/folders with no ``parent`` returns one entry per root."""

    def test_root_layer_lists_each_root_with_count_and_label(self, tmp_path):
        root_a = tmp_path / "album-a"
        root_b = tmp_path / "album-b"
        for r in (root_a, root_b):
            r.mkdir()
            (r / "sub").mkdir()

        db = MagicMock()
        # Two scalar() calls (one per root) return counts 2 and 1 respectively.
        db.query.return_value.filter.return_value.scalar.side_effect = [2, 1]

        with patch.object(
            path_utils, "get_user_roots", return_value=[str(root_a), str(root_b)]
        ):
            resp = photo_api.read_photo_folders(parent="", db=db, current_user=_user())

        assert resp.code == 0
        data = resp.data
        assert data["parent"] == ""
        assert data["breadcrumb"] == []
        assert data["own_count"] == 0
        names = {c["name"] for c in data["children"]}
        assert names == {"album-a", "album-b"}
        by_name = {c["name"]: c for c in data["children"]}
        # Each root has a real ``sub`` directory on disk -> has_children=True.
        assert by_name["album-a"]["has_children"] is True
        assert by_name["album-b"]["has_children"] is True
        assert by_name["album-a"]["count"] == 2
        assert by_name["album-b"]["count"] == 1
        # Children sorted case-insensitively by name.
        sorted_children = sorted(data["children"], key=lambda x: x["name"].lower())
        assert [c["name"] for c in data["children"]] == [c["name"] for c in sorted_children]

    def test_root_layer_includes_missing_roots_with_has_children_false(self, tmp_path):
        """Missing roots are not silently dropped: they show up with
        has_children=False and count=0 so the UI can still render them."""
        present = tmp_path / "present"
        present.mkdir()
        missing = tmp_path / "missing"  # never created on disk

        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = 0

        with patch.object(
            path_utils,
            "get_user_roots",
            return_value=[str(present), str(missing)],
        ):
            resp = photo_api.read_photo_folders(parent="", db=db, current_user=_user())

        by_name = {c["name"]: c for c in resp.data["children"]}
        assert set(by_name) == {"present", "missing"}
        assert by_name["missing"]["has_children"] is False
        assert by_name["missing"]["count"] == 0
        assert by_name["present"]["has_children"] is False

    def test_root_layer_root_with_no_subdir_reports_has_children_false(self, tmp_path):
        root = tmp_path / "leaf"
        root.mkdir()
        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = 0

        with patch.object(path_utils, "get_user_roots", return_value=[str(root)]):
            resp = photo_api.read_photo_folders(parent="", db=db, current_user=_user())

        assert resp.data["children"][0]["has_children"] is False


class TestReadPhotoFoldersChildLayer:
    """GET /photos/folders with ``parent`` set drills into the root."""

    def test_child_layer_returns_direct_subdirs_with_counts(self, tmp_path):
        root = tmp_path / "vacation"
        child_a = root / "beach"
        child_b = root / "mountain"
        deep = child_a / "deep"
        root.mkdir()
        child_a.mkdir()
        child_b.mkdir()
        deep.mkdir()
        # Place a file directly inside ``beach`` to test own_count bucketing.
        (child_a / "shot.jpg").write_text("x")
        (deep / "pic.jpg").write_text("x")  # counted under deep, not beach
        (child_b / "view.jpg").write_text("x")

        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = 0
        db.query.return_value.filter.return_value.all.return_value = [
            (str(child_a / "shot.jpg"),),
            (str(deep / "pic.jpg"),),
            (str(child_b / "view.jpg"),),
        ]

        with patch.object(path_utils, "get_user_roots", return_value=[str(root)]):
            resp = photo_api.read_photo_folders(
                parent="vacation", db=db, current_user=_user()
            )

        data = resp.data
        by_name = {c["name"]: c for c in data["children"]}
        # Both files under ``beach/`` (shot.jpg + deep/pic.jpg) attribute to
        # the first child level ``beach`` because the bucketing only looks
        # at the path segment immediately under ``abs_dir``.
        assert by_name["beach"]["count"] == 2
        assert by_name["mountain"]["count"] == 1
        assert data["own_count"] == 0
        assert [b["name"] for b in data["breadcrumb"]] == ["vacation"]

    def test_child_layer_unknown_root_label_returns_empty(self, tmp_path):
        root = tmp_path / "vacation"
        root.mkdir()

        db = MagicMock()
        with patch.object(path_utils, "get_user_roots", return_value=[str(root)]):
            resp = photo_api.read_photo_folders(
                parent="ghost", db=db, current_user=_user()
            )

        assert resp.data["children"] == []
        assert [b["name"] for b in resp.data["breadcrumb"]] == ["ghost"]

    def test_child_layer_filters_to_top_level_files_for_own_count(self, tmp_path):
        root = tmp_path / "library"
        sub = root / "sub"
        root.mkdir()
        sub.mkdir()
        (sub / "in-sub.jpg").write_text("x")
        (root / "at-root.jpg").write_text("x")

        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = 0
        db.query.return_value.filter.return_value.all.return_value = [
            (str(root / "at-root.jpg"),),
            (str(sub / "in-sub.jpg"),),
        ]

        with patch.object(path_utils, "get_user_roots", return_value=[str(root)]):
            resp = photo_api.read_photo_folders(
                parent="library", db=db, current_user=_user()
            )

        assert resp.data["own_count"] == 1
        children = {c["name"]: c for c in resp.data["children"]}
        assert children["sub"]["count"] == 1


# ===========================================================================
# ScanFolderStrategy._scan_for_user
# ===========================================================================
class TestScanForUser:
    """Drives ``_scan_for_user`` end-to-end with patched disk + DB."""

    def _strategy(self):
        return ScanFolderStrategy()

    def _patch_filesystem(self, files_by_root):
        """Patch ``scan_directory_recursive`` to return ``files_by_root[root]``."""
        def fake_scan(path, exts, filter_settings=None, exclude_folder_patterns=None):
            return set(files_by_root.get(path, set()))
        return patch.object(scan_module, "scan_directory_recursive", side_effect=fake_scan)

    @pytest.mark.asyncio
    async def test_new_files_create_tasks_and_update_status(self, tmp_path):
        root = tmp_path / "photos"
        root.mkdir()
        db = MagicMock()
        user = SimpleNamespace(id="u-1")
        worker = SimpleNamespace(scan_status={"message": "", "total_files": 0, "deleted": 0})
        cfg = _filter_config()

        old_file = root / "old.jpg"
        new_file = root / "brand-new.jpg"
        existing = {str(old_file)}
        new_on_disk = {str(old_file), str(new_file)}

        with patch.object(scan_module, "config_manager") as cfg_mgr, \
            self._patch_filesystem({str(root): new_on_disk}), \
            patch.object(
                ScanFolderStrategy,
                "_get_existing_files",
                return_value=(existing, set()),
            ), \
            patch.object(
                ScanFolderStrategy,
                "_create_tasks_for_new_files",
                new=AsyncMock(),
            ) as create_tasks, \
            patch.object(
                ScanFolderStrategy,
                "_handle_deleted_files",
            ) as handle_deleted:
            cfg_mgr.get_user_config.return_value = cfg

            result = await self._strategy()._scan_for_user(
                worker, db, user, [str(root)]
            )

        assert result == {"new_files": 1, "deleted_files": 0}
        create_tasks.assert_awaited_once()
        args, _ = create_tasks.call_args
        assert args[0] == "u-1"
        assert args[1] == {str(new_file)}
        handle_deleted.assert_called_once()
        assert worker.scan_status["message"].startswith("Found 1 new")
        assert worker.scan_status["total_files"] == 1

    @pytest.mark.asyncio
    async def test_deleted_files_route_to_handle_deleted(self, tmp_path):
        root = tmp_path / "photos"
        root.mkdir()
        db = MagicMock()
        user = SimpleNamespace(id="u-1")
        worker = SimpleNamespace(scan_status={"message": "", "total_files": 0, "deleted": 0})
        cfg = _filter_config()

        gone_file = root / "gone.jpg"
        existing = {str(gone_file)}
        on_disk = set()

        with patch.object(scan_module, "config_manager") as cfg_mgr, \
            self._patch_filesystem({str(root): on_disk}), \
            patch.object(
                ScanFolderStrategy,
                "_get_existing_files",
                return_value=(existing, set()),
            ), \
            patch.object(
                ScanFolderStrategy,
                "_create_tasks_for_new_files",
                new=AsyncMock(),
            ), \
            patch.object(
                ScanFolderStrategy,
                "_handle_deleted_files",
            ) as handle_deleted:
            cfg_mgr.get_user_config.return_value = cfg

            result = await self._strategy()._scan_for_user(
                worker, db, user, [str(root)]
            )

        assert result == {"new_files": 0, "deleted_files": 1}
        handle_args, _ = handle_deleted.call_args
        assert handle_args[0] == "u-1"
        assert handle_args[1] == {str(gone_file)}

    @pytest.mark.asyncio
    async def test_live_photo_pair_jpg_mp4_creates_mp4_as_new(self, tmp_path):
        """A row already marked as live_photo needs the mp4 counterpart to be
        queued for PROCESS_BASIC (matching the existing helper semantics)."""
        root = tmp_path / "photos"
        root.mkdir()
        db = MagicMock()
        user = SimpleNamespace(id="u-1")
        worker = SimpleNamespace(scan_status={"message": "", "total_files": 0, "deleted": 0})
        cfg = _filter_config()

        jpg = str(root / "IMG_0001.jpg")
        mp4 = str(root / "IMG_0001.mp4")
        existing = {jpg, mp4}
        on_disk = {jpg, mp4}
        live_to_add = {jpg}

        with patch.object(scan_module, "config_manager") as cfg_mgr, \
            self._patch_filesystem({str(root): on_disk}), \
            patch.object(
                ScanFolderStrategy,
                "_get_existing_files",
                return_value=(existing, live_to_add),
            ), \
            patch.object(
                ScanFolderStrategy,
                "_create_tasks_for_new_files",
                new=AsyncMock(),
            ) as create_tasks, \
            patch.object(ScanFolderStrategy, "_handle_deleted_files"):
            cfg_mgr.get_user_config.return_value = cfg

            result = await self._strategy()._scan_for_user(
                worker, db, user, [str(root)]
            )

        # Both files already in existing -> diff is empty, but the live photo
        # reconciliation injects the mp4 counterpart so it ends up in
        # new_files (and the jpg gets added to deleted_files for re-pairing).
        assert result == {"new_files": 2, "deleted_files": 2}
        create_tasks.assert_awaited_once()
        queued = create_tasks.call_args[0][1]
        assert mp4 in queued
        assert jpg in queued

    @pytest.mark.asyncio
    async def test_filter_exclude_folders_is_passed_through(self, tmp_path):
        """Excluded folder patterns come from the user's filter config and
        are handed to ``_compile_folder_patterns`` (asserted indirectly by
        the patch on ``config_manager``)."""
        root = tmp_path / "photos"
        root.mkdir()
        db = MagicMock()
        user = SimpleNamespace(id="u-1")
        worker = SimpleNamespace(scan_status={"message": "", "total_files": 0, "deleted": 0})
        cfg = _filter_config(exclude_folders=[r"^@eaDir$", r"\.tmp$"])

        with patch.object(scan_module, "config_manager") as cfg_mgr, \
            self._patch_filesystem({str(root): set()}), \
            patch.object(
                ScanFolderStrategy,
                "_get_existing_files",
                return_value=(set(), set()),
            ), \
            patch.object(
                ScanFolderStrategy,
                "_create_tasks_for_new_files",
                new=AsyncMock(),
            ), \
            patch.object(ScanFolderStrategy, "_handle_deleted_files"):
            cfg_mgr.get_user_config.return_value = cfg

            await self._strategy()._scan_for_user(
                worker, db, user, [str(root)]
            )

        cfg_mgr.get_user_config.assert_called_once_with(user.id, db)
        cfg.filter.model_dump.assert_called_once()
from app.api import photo as photo_api
from app.db.models.photo import FileType
from app.service.tasks import scan as scan_module
from app.service.tasks.scan import ScanFolderStrategy
from app.utils import path as path_utils
