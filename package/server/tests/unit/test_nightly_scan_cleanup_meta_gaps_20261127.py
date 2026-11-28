"""Nightly watch 2026-11-27 (round 2) - scan / cleanup-scan / video-meta backfill.

Targeted coverage measured on 2026-11-27 showed these confirmed gaps:

- ``app/service/tasks/scan.py`` (L236-241): the ``.HEIC``/``.MOV`` live-photo
  pairing.  Only the ``.jpg``/``.mp4`` pairing was ever asserted, so a HEIC
  live photo silently lost its MOV companion during a scan.
- ``app/service/tasks/scan.py`` (L197): a top-level folder matching the
  ``exclude_folders`` filter must be skipped instead of being descended into.
- ``app/service/tasks/scan.py`` (L165-166): a path that lives on another drive
  must never be treated as contained by a root; the helper compares the drive
  letters before it ever calls ``os.path.commonpath``.
- ``app/service/cleanup_scan.py`` (L143-144): a file that changes size or
  mtime while it is being hashed must never keep a usable md5.
- ``app/utils/video_meta.py`` (L254-255): ``parse_iso6709`` must return
  ``None`` for a coordinate pair that is not a valid float, and (L534-535)
  ``_parse_mdhd`` must read the 64-bit version-1 layout.

Everything here is offline: SQLite in-memory, tmp_path, no service process.
"""


from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  register every ORM model
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.task import Task
from app.db.models.toolbox import CleanupScope, ToolboxPlan
from app.db.models.user import User
from app.schemas.toolbox import MediaScope, PlanRequest, ToolConfig
from app.service import cleanup_scan
from app.service.tasks import scan as scan_module
from app.service.tasks.scan import ScanFolderStrategy
from app.utils import video_meta

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


# ---------------------------------------------------------------------------
# app/service/tasks/scan.py
# ---------------------------------------------------------------------------
def _filter_config(exclude_folders=None):
    config = MagicMock()
    config.filter.model_dump.return_value = {
        "enable": True,
        "min_size_kb": 0,
        "min_width": 0,
        "min_height": 0,
        "filename_patterns": [],
        "exclude_folders": list(exclude_folders or []),
    }
    return config


def _scan_worker():
    return SimpleNamespace(scan_status={"message": "", "total_files": 0, "deleted": 0})


def _fake_scan(files_by_root):
    def fake(path, exts, filter_settings=None, exclude_folder_patterns=None,
             *, recursive=True, strict=False):
        return set(files_by_root.get(path, set()))
    return fake


@pytest.mark.asyncio
async def test_scan_pairs_a_heic_live_photo_with_its_mov_companion(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    heic = str(root / "clip.HEIC")
    mov = str(root / "clip.MOV")
    user = SimpleNamespace(id="u-1", settings={"storage": {"external_directories": [str(root)]}})
    db = MagicMock()

    # The HEIC is a known live photo; its MOV companion still has to be indexed.
    with patch.object(scan_module, "config_manager") as config_manager, \
         patch.object(scan_module, "scan_directory_recursive",
                      side_effect=_fake_scan({str(root): {mov}})), \
         patch.object(ScanFolderStrategy, "_get_existing_files",
                      return_value=(set(), {heic})), \
         patch.object(ScanFolderStrategy, "_handle_deleted_files"), \
         patch.object(ScanFolderStrategy, "_create_tasks_for_new_files", new=AsyncMock()) as create_tasks, \
         patch("app.service.gallery_sync.lock_user", lambda *_: user), \
         patch("app.service.gallery_sync.cancel_path_tasks", lambda *_: 0):
        config_manager.get_user_config.return_value = _filter_config()
        result = await ScanFolderStrategy()._scan_for_user(
            _scan_worker(), db, user, [str(root)]
        )

    # The MOV companion is indexed next to the HEIC, and both rows are refreshed.
    created = create_tasks.await_args.args[1]
    assert mov in created
    assert heic in created
    assert result["new_files"] == 2


@pytest.mark.asyncio
async def test_scan_pairs_a_mov_live_photo_with_its_heic_companion(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    heic = str(root / "clip.HEIC")
    mov = str(root / "clip.MOV")
    user = SimpleNamespace(id="u-1", settings={"storage": {"external_directories": [str(root)]}})
    db = MagicMock()

    # The MOV is a known live photo; its HEIC companion still has to be indexed.
    with patch.object(scan_module, "config_manager") as config_manager, \
         patch.object(scan_module, "scan_directory_recursive",
                      side_effect=_fake_scan({str(root): {heic}})), \
         patch.object(ScanFolderStrategy, "_get_existing_files",
                      return_value=(set(), {mov})), \
         patch.object(ScanFolderStrategy, "_handle_deleted_files"), \
         patch.object(ScanFolderStrategy, "_create_tasks_for_new_files", new=AsyncMock()) as create_tasks, \
         patch("app.service.gallery_sync.lock_user", lambda *_: user), \
         patch("app.service.gallery_sync.cancel_path_tasks", lambda *_: 0):
        config_manager.get_user_config.return_value = _filter_config()
        result = await ScanFolderStrategy()._scan_for_user(
            _scan_worker(), db, user, [str(root)]
        )

    created = create_tasks.await_args.args[1]
    assert heic in created
    assert mov in created
    assert result["new_files"] == 2


@pytest.mark.asyncio
async def test_scan_skips_an_excluded_top_level_folder(tmp_path):
    root = tmp_path / "photos"
    (root / "@eaDir").mkdir(parents=True)
    (root / "keep").mkdir()
    user = SimpleNamespace(id="u-1", settings={"storage": {"external_directories": [str(tmp_path)]}})
    db = MagicMock()
    scanned = []

    def fake_scan(path, exts, filter_settings=None, exclude_folder_patterns=None,
                  *, recursive=True, strict=False):
        scanned.append(path)
        return set()

    with patch.object(scan_module, "config_manager") as config_manager, \
         patch.object(scan_module, "scan_directory_recursive", side_effect=fake_scan), \
         patch("app.service.gallery_sync.lock_user", lambda *_: user), \
         patch("app.service.gallery_sync.cancel_path_tasks", lambda *_: 0):
        config_manager.get_user_config.return_value = _filter_config(["@eaDir"])
        result = await ScanFolderStrategy()._scan_for_user(
            _scan_worker(), db, user, [str(root)]
        )

    assert result["new_files"] == 0
    assert str(root / "@eaDir") not in scanned
    assert str(root / "keep") in scanned


def test_scan_contains_helper_rejects_a_path_on_another_drive():
    # A path that lives on another drive is never contained: the helper compares
    # the drive letters first, so commonpath is never reached for a different root.
    assert scan_module._within_roots("C:/other/photo.jpg", ["D:/root"]) is False

    same_drive_root = os.path.normpath("C:/root")
    assert scan_module._within_roots(
        os.path.join(same_drive_root, "photo.jpg"), [same_drive_root]) is True


# ---------------------------------------------------------------------------
# app/service/cleanup_scan.py
# ---------------------------------------------------------------------------
@pytest.fixture()
def scan_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'cleanup-nightly.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


@pytest.fixture()
def scan_owner(scan_db):
    user = User(id=uuid.uuid4(), username="cleanup-nightly", hashed_password="x", settings={})
    scan_db.add(user)
    scan_db.commit()
    return user


def _scan_plan(scan_db, owner, photo_id):
    plan = ToolboxPlan(id=uuid.uuid4(), owner_id=owner.id, kind="cleanup", status="scanning",
                       version=1, request={},
                       summary={"total": 0, "processed": 0, "phase": "hash",
                                "snapshot_upper": str(photo_id)},
                       expires_at=datetime.utcnow() + timedelta(days=1))
    scan_db.add(plan)
    scan_db.commit()
    return plan


def test_cleanup_scan_drops_the_md5_of_a_file_that_changes_while_hashing(scan_db, scan_owner, tmp_path):
    source = tmp_path / "moving.jpg"
    source.write_bytes(b"first-version")
    photo = Photo(id=uuid.uuid4(), owner_id=scan_owner.id, filename="moving.jpg",
                  file_path=str(source), file_type=FileType.image, size=12, is_deleted=False,
                  photo_time=datetime(2024, 1, 1), md5="stale-md5")
    scan_db.add(photo)
    plan = _scan_plan(scan_db, scan_owner, photo.id)
    scan_db.add(CleanupScope(plan_id=plan.id, photo_id=photo.id, in_scope=True))
    scan_db.commit()

    real_stat = os.stat

    def flaky_stat(path, *args, **kwargs):
        # The second stat (after hashing) reports a different size, so the
        # scanner must treat the file as changed and drop its md5.
        stat_result = real_stat(path, *args, **kwargs)
        if getattr(flaky_stat, "seen", False):
            return SimpleNamespace(st_size=stat_result.st_size + 5,
                                   st_mtime_ns=stat_result.st_mtime_ns)
        flaky_stat.seen = True
        return stat_result

    with patch("app.service.cleanup_scan.os.stat", side_effect=flaky_stat):
        cleanup_scan.hash_population(scan_db, plan)

    scan_db.refresh(photo)
    assert photo.md5 is None
    assert plan.summary["hash_failed"] == 1
    assert plan.summary["hashed"] == 0


def test_cleanup_scan_skips_a_vector_model_that_was_already_compared(scan_db, scan_owner):
    photo = Photo(id=uuid.uuid4(), owner_id=scan_owner.id, filename="a.jpg", file_path="/tmp/a.jpg",
                  file_type=FileType.image, size=1, is_deleted=False, photo_time=datetime(2024, 1, 1))
    scan_db.add(photo)
    plan = _scan_plan(scan_db, scan_owner, photo.id)
    # "aaa-model" sorts before "zzz-model", so the resumed scan must skip it.
    plan.summary = {**plan.summary, "phase": "groups", "model_cursor": "zzz-model"}
    scan_db.add(CleanupScope(plan_id=plan.id, photo_id=photo.id, in_scope=True))
    scan_db.commit()
    # A vector row makes "aaa-model" appear in the model list.
    scan_db.execute(
        text("INSERT INTO image_vectors (photo_id, model_name, embedding, content_revision) "
             "VALUES (:photo_id, :model, :embedding, :revision)"),
        {"photo_id": str(photo.id), "model": "aaa-model",
         "embedding": "[0.0]", "revision": "rev-1"},
    )
    scan_db.commit()

    opened = []

    class _NeverUsedIndex:
        def __init__(self, *args, **kwargs):
            opened.append(args)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch("app.service.cleanup_index.CleanupIndex", _NeverUsedIndex):
        cleanup_scan.similar_groups(scan_db, plan, ToolConfig(kind="cleanup", cleanup_mode="similar"))

    # The already-compared model was skipped, so no index was ever opened.
    assert opened == []


# ---------------------------------------------------------------------------
# app/utils/video_meta.py
# ---------------------------------------------------------------------------
def test_parse_iso6709_rejects_a_coordinate_that_is_not_a_number():
    assert video_meta.parse_iso6709("not a coordinate") is None


def test_parse_iso6709_rejects_an_out_of_range_coordinate():
    assert video_meta.parse_iso6709("+999.0000+999.0000/") is None


def test_parse_iso6709_rejects_the_null_island_coordinate():
    assert video_meta.parse_iso6709("+00.0000+00.0000/") is None


def test_parse_iso6709_reads_a_valid_coordinate():
    assert video_meta.parse_iso6709("+34.0522-118.2437+000.000/") == {
        "latitude": 34.0522, "longitude": -118.2437,
    }


def test_parse_mdhd_reads_the_version_1_layout():
    payload = bytearray(32)
    payload[0] = 1
    payload[20:24] = (1000).to_bytes(4, "big")
    payload[24:32] = (5000).to_bytes(8, "big")

    info = video_meta._parse_mdhd(bytes(payload))

    assert info["duration"] == 5.0


def test_parse_mdhd_rejects_a_truncated_version_1_payload():
    payload = bytearray(20)
    payload[0] = 1

    assert video_meta._parse_mdhd(bytes(payload)) == {}




