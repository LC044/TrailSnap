"""Unit tests covering 2026-08-16 nightly coverage gap scan (round 9).

Modules exercised:
* app/service/tasks/metadata.py -- determine_image_type (screenshot keyword /
  common resolution / EXIF camera / OTHER default), haversine_distance,
  is_point_in_polygon, rebuild_metadata_cpu_job + sync_rebuild_metadata_cpu_job
  success / failure branches, ExtractMetadataStrategy.task_category &
  EXTRACT_METADATA payload guard (missing / invalid uuid / missing photo),
  RebuildMetadataStrategy.task_category, identify_scene polygon/radius/match.
* app/service/tasks/image_embedding.py -- ImageEmbeddingStrategy.task_category,
  factory registration, process() early-return (photo not found, already
  processed when not force, force re-run when already processed), process
  generator mode (creates tasks, skips videos, force includes already-processed),
  release_resources no-op.
"""
import asyncio
import os
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _task(**kw):
    base = {
        "id": uuid4(),
        "type": None,
        "owner_id": uuid4(),
        "payload": {},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _photo(**kw):
    base = {
        "id": uuid4(),
        "owner_id": uuid4(),
        "file_type": 0,
        "file_path": "/tmp/p.jpg",
        "processed_tasks": {},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# metadata.py -- determine_image_type
# ---------------------------------------------------------------------------


def test_determine_image_type_screenshot_keyword_english():
    from app.service.tasks.metadata import determine_image_type
    from app.db.models.photo import ImageType

    assert determine_image_type("Screenshot 2024-01-01.png", 1920, 1080, {}) is ImageType.SCREENSHOT


def test_determine_image_type_screenshot_keyword_chinese():
    from app.service.tasks.metadata import determine_image_type
    from app.db.models.photo import ImageType

    assert determine_image_type("QQ\u622a\u56fe_001.jpg", 800, 600, {}) is ImageType.SCREENSHOT
    assert determine_image_type("\u5c4f\u5e55\u622a\u56fe.png", 800, 600, {}) is ImageType.SCREENSHOT


def test_determine_image_type_screenshot_by_resolution():
    from app.service.tasks.metadata import determine_image_type
    from app.db.models.photo import ImageType

    # iPhone 14 Pro Max 1290x2796 -> SCREENSHOT
    assert determine_image_type("IMG_001.heic", 1290, 2796, {}) is ImageType.SCREENSHOT
    # Samsung Ultra 1440x3088 -> SCREENSHOT
    assert determine_image_type("IMG_002.jpg", 1440, 3088, {}) is ImageType.SCREENSHOT


def test_determine_image_type_camera_by_make():
    from app.service.tasks.metadata import determine_image_type
    from app.db.models.photo import ImageType

    assert determine_image_type("DSC_0001.jpg", 6000, 4000, {"Make": "Canon"}) is ImageType.CAMERA


def test_determine_image_type_camera_by_model():
    from app.service.tasks.metadata import determine_image_type
    from app.db.models.photo import ImageType

    assert determine_image_type("IMG_1.jpg", 4032, 3024, {"Model": "iPhone 14"}) is ImageType.CAMERA


def test_determine_image_type_other_default():
    from app.service.tasks.metadata import determine_image_type
    from app.db.models.photo import ImageType

    # random resolution, no EXIF => OTHER
    assert determine_image_type("foo.jpg", 1234, 5678, {}) is ImageType.OTHER
    # EXIF but no Make/Model => OTHER
    assert determine_image_type("foo.jpg", 1234, 5678, {"ExposureTime": 0.5}) is ImageType.OTHER


def test_determine_image_type_screenshot_takes_priority_over_exif():
    from app.service.tasks.metadata import determine_image_type
    from app.db.models.photo import ImageType

    # even with camera EXIF, screenshot keyword should win
    assert determine_image_type("screenshot_001.jpg", 1290, 2796, {"Make": "Canon"}) is ImageType.SCREENSHOT


# ---------------------------------------------------------------------------
# metadata.py -- haversine_distance
# ---------------------------------------------------------------------------


def test_haversine_distance_zero_for_same_point():
    from app.service.tasks.metadata import haversine_distance

    assert haversine_distance(39.9, 116.4, 39.9, 116.4) == pytest.approx(0.0, abs=1e-3)


def test_haversine_distance_known_short_distance():
    from app.service.tasks.metadata import haversine_distance

    # ~111 km per degree latitude at equator
    d = haversine_distance(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111_195, rel=1e-3)


def test_haversine_distance_beijing_tokyo():
    from app.service.tasks.metadata import haversine_distance

    # Beijing (39.9042, 116.4074) -> Tokyo (35.6762, 139.6503), ~2,100 km
    d = haversine_distance(39.9042, 116.4074, 35.6762, 139.6503)
    assert 2_000_000 < d < 2_200_000


# ---------------------------------------------------------------------------
# metadata.py -- is_point_in_polygon (ray casting)
# ---------------------------------------------------------------------------


def test_is_point_in_polygon_inside_square():
    from app.service.tasks.metadata import is_point_in_polygon

    square = [[0, 0], [0, 10], [10, 10], [10, 0]]
    assert is_point_in_polygon(5, 5, square) is True


def test_is_point_in_polygon_outside_square():
    from app.service.tasks.metadata import is_point_in_polygon

    square = [[0, 0], [0, 10], [10, 10], [10, 0]]
    assert is_point_in_polygon(20, 20, square) is False
    assert is_point_in_polygon(-5, 5, square) is False


def test_is_point_in_polygon_empty_or_short():
    from app.service.tasks.metadata import is_point_in_polygon

    assert is_point_in_polygon(1, 1, []) is False
    assert is_point_in_polygon(1, 1, [[0, 0]]) is False
    assert is_point_in_polygon(1, 1, [[0, 0], [1, 1]]) is False  # < 3 vertices


def test_is_point_in_polygon_concave():
    from app.service.tasks.metadata import is_point_in_polygon

    # L-shape
    l_shape = [[0, 0], [0, 10], [5, 10], [5, 5], [10, 5], [10, 0]]
    assert is_point_in_polygon(2, 8, l_shape) is True  # upper-left
    assert is_point_in_polygon(7, 2, l_shape) is True  # lower-right
    assert is_point_in_polygon(7, 8, l_shape) is False  # outside the notch


# ---------------------------------------------------------------------------
# metadata.py -- rebuild helpers + strategy guards
# ---------------------------------------------------------------------------


def test_rebuild_metadata_cpu_job_returns_success_dict(monkeypatch):
    from app.service.tasks import metadata

    monkeypatch.setattr(metadata.exif, "extract_metadata",
                        lambda fp, fn: {"exif_info": {"Make": "Canon"}, "photo_time": None})
    res = metadata.rebuild_metadata_cpu_job("/tmp/x.jpg", uuid4())
    assert res["success"] is True
    assert res["meta"]["exif_info"]["Make"] == "Canon"


def test_rebuild_metadata_cpu_job_returns_error_dict(monkeypatch):
    from app.service.tasks import metadata

    def boom(*_a, **_kw):
        raise RuntimeError("exif boom")
    monkeypatch.setattr(metadata.exif, "extract_metadata", boom)
    res = metadata.rebuild_metadata_cpu_job("/tmp/x.jpg", uuid4())
    assert res["success"] is False
    assert "exif boom" in res["error"]


def test_sync_rebuild_metadata_cpu_job_returns_success_dict(monkeypatch):
    from app.service.tasks import metadata

    monkeypatch.setattr(metadata.exif, "extract_metadata",
                        lambda fp, fn: {"exif_info": {}, "photo_time": None})
    res = _run(metadata.sync_rebuild_metadata_cpu_job("/tmp/y.jpg", uuid4()))
    assert res["success"] is True


def test_sync_rebuild_metadata_cpu_job_returns_error_dict(monkeypatch):
    from app.service.tasks import metadata

    def boom(*_a, **_kw):
        raise RuntimeError("async boom")
    monkeypatch.setattr(metadata.exif, "extract_metadata", boom)
    res = _run(metadata.sync_rebuild_metadata_cpu_job("/tmp/y.jpg", uuid4()))
    assert res["success"] is False
    assert "async boom" in res["error"]


def test_extract_metadata_strategy_task_category_is_io():
    from app.service.tasks.metadata import ExtractMetadataStrategy
    assert ExtractMetadataStrategy.task_category.fget(None) == "IO"


def test_rebuild_metadata_strategy_task_category_is_io():
    from app.service.tasks.metadata import RebuildMetadataStrategy
    assert RebuildMetadataStrategy.task_category.fget(None) == "IO"


def test_extract_metadata_strategy_process_missing_photo_id():
    from app.service.tasks.metadata import ExtractMetadataStrategy

    worker = MagicMock()
    db = MagicMock()
    task = _task(payload={})
    res = _run(ExtractMetadataStrategy().process(worker, task, db))
    assert res["status"] == "skipped"
    assert res["reason"] == "missing photo_id"


def test_extract_metadata_strategy_process_invalid_uuid():
    from app.service.tasks.metadata import ExtractMetadataStrategy

    worker = MagicMock()
    db = MagicMock()
    task = _task(payload={"photo_id": "not-a-uuid"})
    res = _run(ExtractMetadataStrategy().process(worker, task, db))
    assert res["status"] == "failed"
    assert res["reason"] == "invalid uuid"


def test_extract_metadata_strategy_process_photo_not_found():
    from app.service.tasks.metadata import ExtractMetadataStrategy

    worker = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    task = _task(payload={"photo_id": str(uuid4())})
    res = _run(ExtractMetadataStrategy().process(worker, task, db))
    assert res["status"] == "skipped"
    assert res["reason"] == "photo not found"


# ---------------------------------------------------------------------------
# image_embedding.py -- ImageEmbeddingStrategy
# ---------------------------------------------------------------------------


def test_image_embedding_strategy_task_category_is_ai():
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy
    assert ImageEmbeddingStrategy.task_category.fget(None) == "AI"


def test_image_embedding_strategy_registered_in_factory():
    from app.db.models.task import TaskType
    from app.service.task_strategy import TaskStrategyFactory
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy

    cls = TaskStrategyFactory.get_strategy(TaskType.IMAGE_EMBEDDING)
    assert isinstance(cls, ImageEmbeddingStrategy)


def test_image_embedding_process_skips_missing_photo():
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    worker = MagicMock()
    task = _task(payload={"photo_id": str(uuid4())})
    res = _run(ImageEmbeddingStrategy().process(worker, task, db))
    assert res == {"status": "skipped", "reason": "photo not found"}


def test_image_embedding_process_skips_already_processed():
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy

    db = MagicMock()
    photo = _photo(processed_tasks={"image_embedding": True})
    db.query.return_value.filter.return_value.first.return_value = photo
    worker = MagicMock()
    task = _task(payload={"photo_id": str(photo.id)})
    res = _run(ImageEmbeddingStrategy().process(worker, task, db))
    assert res == {"status": "skipped", "reason": "already processed"}


def test_image_embedding_process_force_reruns_when_already_processed(monkeypatch):
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy

    db = MagicMock()
    photo = _photo(processed_tasks={"image_embedding": True})
    db.query.return_value.filter.return_value.first.return_value = photo
    worker = MagicMock()
    task = _task(payload={"photo_id": str(photo.id), "force": True})

    fake_coro = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(ImageEmbeddingStrategy, "process_single_photo", fake_coro)

    res = _run(ImageEmbeddingStrategy().process(worker, task, db))
    assert res == {"status": "success"}
    fake_coro.assert_awaited_once()


def test_image_embedding_process_generator_mode_creates_tasks():
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy
    from app.db.models.photo import FileType

    p1 = _photo(processed_tasks={})
    p2 = _photo(processed_tasks={"image_embedding": True})
    p3 = _photo(processed_tasks={}, file_type=FileType.video)  # videos skipped

    db = MagicMock()
    db.query.return_value.offset.return_value.limit.return_value.all.side_effect = [
        [p1, p2, p3],
        [],
    ]

    worker = MagicMock()
    task = _task(payload={})  # no photo_id => generator mode

    res = _run(ImageEmbeddingStrategy().process(worker, task, db))

    assert res["processed"] == 0
    assert res["generated_tasks"] == 1
    worker.add_tasks.assert_called_once()
    payload_list = worker.add_tasks.call_args[0][1]
    assert len(payload_list) == 1
    assert payload_list[0]["payload"]["photo_id"] == str(p1.id)


def test_image_embedding_process_generator_mode_force_includes_all():
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy
    from app.db.models.photo import FileType

    p1 = _photo(processed_tasks={"image_embedding": True})  # would skip without force
    p2 = _photo(processed_tasks={}, file_type=FileType.video)  # still skipped (video)

    db = MagicMock()
    db.query.return_value.offset.return_value.limit.return_value.all.side_effect = [
        [p1, p2],
        [],
    ]

    worker = MagicMock()
    task = _task(payload={"force": True})

    res = _run(ImageEmbeddingStrategy().process(worker, task, db))

    assert res["generated_tasks"] == 1
    payload_list = worker.add_tasks.call_args[0][1]
    assert len(payload_list) == 1
    assert payload_list[0]["payload"]["photo_id"] == str(p1.id)


def test_image_embedding_release_resources_noop():
    from app.service.tasks.image_embedding import ImageEmbeddingStrategy

    # Should not raise
    ImageEmbeddingStrategy().release_resources()


# ---------------------------------------------------------------------------
# metadata.py -- identify_scene (polygon + radius + parse-error)
# ---------------------------------------------------------------------------


def test_identify_scene_returns_polygon_match():
    from app.service.tasks import metadata

    scene = SimpleNamespace(
        id=42,
        polygon=json.dumps([[0, 0], [0, 10], [10, 10], [10, 0]]),
        radius=None,
        latitude=None,
        longitude=None,
    )
    db = MagicMock()
    db.query.return_value.all.return_value = [scene]

    assert metadata.identify_scene(db, 5.0, 5.0) == 42


def test_identify_scene_returns_radius_match():
    from app.service.tasks import metadata

    scene = SimpleNamespace(
        id=99,
        polygon=None,
        radius=50_000,  # 50km
        latitude=39.9,
        longitude=116.4,
    )
    db = MagicMock()
    db.query.return_value.all.return_value = [scene]

    # ~11 km north
    assert metadata.identify_scene(db, 39.99, 116.4) == 99


def test_identify_scene_returns_none_when_no_match():
    from app.service.tasks import metadata

    scene = SimpleNamespace(
        id=1,
        polygon=None,
        radius=100,  # 100 m
        latitude=39.9,
        longitude=116.4,
    )
    db = MagicMock()
    db.query.return_value.all.return_value = [scene]

    # far away (>100 m)
    assert metadata.identify_scene(db, 40.0, 117.0) is None


def test_identify_scene_swallows_polygon_parse_error():
    from app.service.tasks import metadata

    # malformed polygon JSON should be logged-and-skipped, not raise
    scene = SimpleNamespace(
        id=1,
        polygon="not-json",
        radius=None,
        latitude=None,
        longitude=None,
    )
    db = MagicMock()
    db.query.return_value.all.return_value = [scene]

    assert metadata.identify_scene(db, 0.0, 0.0) is None


# ---------------------------------------------------------------------------
# scan.py -- module-level helpers + strategy
# ---------------------------------------------------------------------------


def test_scan_compile_folder_patterns_returns_empty_for_none():
    from app.service.tasks.scan import _compile_folder_patterns
    assert _compile_folder_patterns(None) == []


def test_scan_compile_folder_patterns_skips_empty_strings():
    from app.service.tasks.scan import _compile_folder_patterns
    assert _compile_folder_patterns(["", None]) == []


def test_scan_compile_folder_patterns_swallows_invalid_regex():
    from app.service.tasks.scan import _compile_folder_patterns
    import re
    patterns = _compile_folder_patterns(["@eaDir", "[invalid", "@__thumb"])
    # [invalid is dropped, others survive
    assert len(patterns) == 2
    assert any(cp.pattern == "@eaDir" for cp in patterns)
    assert any(cp.pattern == "@__thumb" for cp in patterns)


def test_scan_is_folder_excluded_returns_false_for_empty_patterns():
    from app.service.tasks.scan import _is_folder_excluded
    assert _is_folder_excluded("@eaDir", []) is False
    assert _is_folder_excluded("@eaDir", None) is False


def test_scan_is_folder_excluded_matches_substring():
    from app.service.tasks.scan import _is_folder_excluded, _compile_folder_patterns
    patterns = _compile_folder_patterns(["@eaDir", "recycle"])
    assert _is_folder_excluded("@eaDir", patterns) is True
    assert _is_folder_excluded("my-recycle-bin", patterns) is True
    assert _is_folder_excluded("photos", patterns) is False


def test_scan_directory_recursive_returns_files_with_matching_ext(tmp_path):
    from app.service.tasks.scan import scan_directory_recursive
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    (tmp_path / "c.PNG").write_bytes(b"x")
    result = scan_directory_recursive(str(tmp_path), {".jpg", ".png"})
    names = {os.path.basename(p) for p in result}
    assert names == {"a.jpg", "c.PNG"}


def test_scan_directory_recursive_descends_into_subdirs(tmp_path):
    from app.service.tasks.scan import scan_directory_recursive
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.jpg").write_bytes(b"x")
    (tmp_path / "top.jpg").write_bytes(b"x")
    result = scan_directory_recursive(str(tmp_path), {".jpg"})
    assert len(result) == 2


def test_scan_directory_recursive_skips_excluded_subdirs(tmp_path):
    from app.service.tasks.scan import scan_directory_recursive, _compile_folder_patterns
    excluded = tmp_path / "@eaDir"
    excluded.mkdir()
    (excluded / "hidden.jpg").write_bytes(b"x")
    (tmp_path / "visible.jpg").write_bytes(b"x")
    patterns = _compile_folder_patterns(["@eaDir"])
    result = scan_directory_recursive(str(tmp_path), {".jpg"}, exclude_folder_patterns=patterns)
    names = {os.path.basename(p) for p in result}
    assert names == {"visible.jpg"}


def test_scan_directory_recursive_applies_filename_filter(tmp_path):
    from app.service.tasks.scan import scan_directory_recursive
    (tmp_path / "IMG_keep.jpg").write_bytes(b"x")
    (tmp_path / "IMG_skip.jpg").write_bytes(b"x")
    filter_settings = {"enable": True, "filename_patterns": ["^IMG_skip"]}
    result = scan_directory_recursive(str(tmp_path), {".jpg"}, filter_settings)
    names = {os.path.basename(p) for p in result}
    assert names == {"IMG_keep.jpg"}


def test_scan_directory_recursive_applies_min_size_filter(tmp_path):
    from app.service.tasks.scan import scan_directory_recursive
    small = tmp_path / "small.jpg"
    small.write_bytes(b"x" * 100)
    big = tmp_path / "big.jpg"
    big.write_bytes(b"x" * 5000)
    filter_settings = {"enable": True, "min_size_kb": 1}  # >= 1024 bytes
    result = scan_directory_recursive(str(tmp_path), {".jpg"}, filter_settings)
    names = {os.path.basename(p) for p in result}
    assert names == {"big.jpg"}


def test_scan_directory_recursive_handles_oserror(tmp_path):
    from app.service.tasks.scan import scan_directory_recursive
    # nonexistent path returns empty set, no exception
    result = scan_directory_recursive(str(tmp_path / "does-not-exist"), {".jpg"})
    assert result == set()


def test_scan_folder_strategy_task_category_is_io():
    from app.service.tasks.scan import ScanFolderStrategy
    assert ScanFolderStrategy.task_category.fget(None) == "IO"


def test_scan_folder_strategy_registered_in_factory():
    from app.db.models.task import TaskType
    from app.service.task_strategy import TaskStrategyFactory
    from app.service.tasks.scan import ScanFolderStrategy

    cls = TaskStrategyFactory.get_strategy(TaskType.SCAN_FOLDER)
    assert isinstance(cls, ScanFolderStrategy)

