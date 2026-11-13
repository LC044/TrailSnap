"""Nightly watch 2026-11-13 (round 4) coverage gaps.

Targets the uncovered branches reported by the 2026-11-13 coverage snapshot:
- app/service/face_appearance_clusters.py  ClusterIndex capacity / candidate / margin logic
- app/service/moment/day_caption_service.py tz fallback, think stripper, day photo query
- app/service/tasks/metadata.py batch extraction result branches, dimension fill, release
- app/service/tasks/basic.py  PROCESS_BASIC failure reporting
"""
from datetime import date, datetime, timezone
from types import SimpleNamespace
import sys
import types
import uuid

import numpy as np
import pytest

from app.db.models.photo import FileType, ImageType, Photo
from app.crud import dashboard as dashboard_crud
from app.utils.color import CURRENT_COLOR_ANALYSIS_VERSION
from app.service.face_appearance_clusters import ClusterIndex
from app.service.moment import day_caption_service as caption
from app.service.tasks import basic as basic_tasks
from app.service.tasks import metadata as metadata_tasks


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# app/service/face_appearance_clusters.py :: ClusterIndex
# ---------------------------------------------------------------------------
def _unit_vector(seed: int, dim: int = 512) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vector = rng.normal(size=dim)
    return (vector / np.linalg.norm(vector)).astype(np.float32)


def _row(seed: int, identity: str, center=None, anchor=None) -> dict:
    center = _unit_vector(seed) if center is None else np.asarray(center, dtype=np.float32)
    anchor = _unit_vector(seed + 1) if anchor is None else np.asarray(anchor, dtype=np.float32)
    return {"identity": identity, "center": center.tolist(), "anchor": anchor.tolist()}


def test_cluster_index_grows_capacity_and_resizes_matrices():
    """upsert() past the initial capacity doubles the matrices and the ANN index."""
    index = ClusterIndex([_row(i, "id-a") for i in range(512)])
    assert index.capacity == 1024

    for i in range(513):
        index.upsert(_row(1000 + i, "id-b"))

    assert len(index.rows) == 1025
    assert index.capacity == 2048
    assert index.centers.shape == (2048, 512)
    assert index.anchors.shape == (2048, 512)
    assert index.rows[-1]["index"] == 1024
    assert "id-b" in index.identities


def test_cluster_index_batch_candidates_keep_competing_identity():
    """A near-duplicate of another identity must stay in the candidate set."""
    vector = _unit_vector(7)
    index = ClusterIndex([
        _row(7, "id-a", center=vector, anchor=vector),
        _row(8, "id-b", center=vector, anchor=vector),
    ])
    candidates = index.batch_candidates(vector.reshape(1, -1), 1.0)
    assert set(int(value) for value in candidates[0]) == {0, 1}


def test_cluster_index_batch_candidates_are_truncated_to_top_64():
    """More than 64 eligible rows are reduced to the 64 best scores."""
    vector = _unit_vector(11)
    index = ClusterIndex([_row(11, "id-a", center=vector, anchor=vector) for _ in range(70)])
    candidates = index.batch_candidates(vector.reshape(1, -1), 1.0)
    assert len(candidates[0]) == 64


def test_cluster_index_select_rejects_ambiguous_nearest_cluster():
    """A competing identity at the same distance blocks the match."""
    vector = _unit_vector(13)
    index = ClusterIndex([
        _row(13, "id-a", center=vector, anchor=vector),
        _row(14, "id-b", center=vector, anchor=vector),
    ])
    assert index.select(vector, 1.0) is None
    assert index.select(vector, 1.0, check_margin=False)["identity"] == "id-a"


def test_cluster_index_select_falls_back_to_all_identities_for_margin_check():
    """The margin check must consider identities missing from the candidate set."""
    vector = _unit_vector(17)
    rows = [_row(17, "id-a", center=vector, anchor=vector) for _ in range(259)]
    rows.append(_row(17, "id-b", center=vector, anchor=vector))
    index = ClusterIndex(rows)
    assert index.ann is not None  # the ANN path is active for large indexes

    # Only the first row is a candidate; the sibling identity is still nearby.
    assert index.select(vector, 1.0, candidates=np.array([0])) is None
    assert index.select(vector, 1.0, candidates=np.array([0]), check_margin=False)["identity"] == "id-a"


def test_cluster_index_without_rows_returns_no_candidates():
    index = ClusterIndex([])
    assert index.select(_unit_vector(19), 0.5) is None
    candidates = index.batch_candidates(_unit_vector(19).reshape(1, -1), 0.5)
    assert len(candidates) == 1
    assert len(candidates[0]) == 0


# ---------------------------------------------------------------------------
# app/service/moment/day_caption_service.py
# ---------------------------------------------------------------------------
def test_resolve_tz_falls_back_to_utc(monkeypatch):
    assert caption._resolve_tz("") is timezone.utc
    assert caption._resolve_tz("Not/AZone") is timezone.utc
    monkeypatch.setattr(caption, "ZoneInfo", None)
    assert caption._resolve_tz("Asia/Shanghai") is timezone.utc


def test_think_stripper_bounds_an_unterminated_reasoning_buffer():
    stripper = caption._ThinkStripper()
    assert stripper.feed("<think>" + "x" * 200) == ""
    # The buffer is trimmed to the closing-tag window, so flush() drops it.
    assert len(stripper._buf) <= len(caption._THINK_CLOSE) * 4
    assert stripper.flush() == ""


def test_think_stripper_keeps_text_before_and_after_a_closed_think_block():
    stripper = caption._ThinkStripper()
    assert stripper.feed("hello<think>secret</think>world") == "helloworld"
    assert stripper.flush() == ""


def test_day_bounds_utc_returns_a_naive_day_range():
    start, end = caption.day_bounds_utc(date(2026, 11, 13), "Asia/Shanghai")
    assert start == datetime(2026, 11, 13, 0, 0, 0)
    assert end == datetime(2026, 11, 14, 0, 0, 0)


def test_fetch_day_photos_only_returns_photos_of_that_day(face_sqlite_session):
    owner = uuid.uuid4()
    day = date(2026, 11, 13)
    inside = Photo(id=uuid.uuid4(), filename="a.jpg", file_type=FileType.image,
                   file_path="a.jpg", owner_id=owner, photo_time=datetime(2026, 11, 13, 9, 30))
    outside = Photo(id=uuid.uuid4(), filename="b.jpg", file_type=FileType.image,
                    file_path="b.jpg", owner_id=owner, photo_time=datetime(2026, 11, 14, 9, 30))
    deleted = Photo(id=uuid.uuid4(), filename="c.jpg", file_type=FileType.image,
                    file_path="c.jpg", owner_id=owner, photo_time=datetime(2026, 11, 13, 10, 0),
                    is_deleted=True)
    face_sqlite_session.add_all([inside, outside, deleted])
    face_sqlite_session.commit()

    photos = caption._fetch_day_photos(face_sqlite_session, owner, day, "Asia/Shanghai")
    assert [photo.id for photo in photos] == [inside.id]


# ---------------------------------------------------------------------------
# app/service/tasks/metadata.py
# ---------------------------------------------------------------------------
def _photo_row(**kwargs) -> Photo:
    defaults = dict(id=uuid.uuid4(), filename="a.jpg", file_type=FileType.image,
                    file_path="a.jpg", owner_id=None, photo_time=None,
                    width=None, height=None, duration=0, processed_tasks={})
    defaults.update(kwargs)
    return Photo(**defaults)


def test_update_photo_metadata_from_extract_fills_missing_dimensions():
    photo = _photo_row()
    db = _FakeDb()

    metadata_tasks.update_photo_metadata_from_extract(
        db, photo,
        {"exif_info": {"Make": "Canon"}, "width": 1920, "height": 1080, "duration": 12.5},
        commit=False,
    )

    assert photo.width == 1920
    assert photo.height == 1080
    assert photo.duration == 12.5
    assert photo.processed_tasks.get("metadata") is True
    assert photo.image_type is not None
    stored = [item for item in db.added if isinstance(item, type(photo)) is False]
    assert stored


def test_update_photo_metadata_from_extract_keeps_existing_dimensions():
    photo = _photo_row(width=800, height=600, duration=3.0)
    db = _FakeDb()

    metadata_tasks.update_photo_metadata_from_extract(
        db, photo,
        {"width": 1920, "height": 1080, "duration": 12.5},
        commit=False,
    )

    assert photo.width == 800
    assert photo.height == 600
    assert photo.duration == 3.0


def test_extract_metadata_batch_reports_each_outcome(face_sqlite_session):
    photo = _photo_row()
    face_sqlite_session.add(photo)
    face_sqlite_session.commit()

    task_data = [
        {"task_id": "t-error", "task_type": "EXTRACT_METADATA", "error": "boom"},
        {"task_id": "t-missing", "task_type": "EXTRACT_METADATA", "photo_id": None},
        {"task_id": "t-unknown", "task_type": "EXTRACT_METADATA", "photo_id": uuid.uuid4()},
        {"task_id": "t-ok", "task_type": "EXTRACT_METADATA", "photo_id": photo.id,
         "raw_metadata_version": 1, "raw_metadata": {"exif_info": {"Make": "Canon"}}},
    ]
    results = metadata_tasks._extract_metadata_batch(face_sqlite_session.get_bind(), task_data)
    by_id = {item["task_id"]: item for item in results}

    assert by_id["t-error"]["status"] == "failed"
    assert by_id["t-error"]["error"] == "boom"
    assert by_id["t-missing"]["result"] == {"status": "skipped", "reason": "missing photo_id"}
    assert by_id["t-unknown"]["result"] == {"status": "skipped", "reason": "photo not found"}
    assert by_id["t-ok"]["status"] == "completed"
    assert by_id["t-ok"]["result"] == {"status": "success"}


def test_release_resources_unloads_the_reverse_geocoder(monkeypatch):
    unloaded = []
    fake = types.ModuleType("reverse_geocoder")

    def _unload():
        unloaded.append(True)

    fake.unload = _unload
    monkeypatch.setitem(sys.modules, "reverse_geocoder", fake)
    metadata_tasks.release_resources()
    assert unloaded == [True]


# ---------------------------------------------------------------------------
# app/service/tasks/basic.py
# ---------------------------------------------------------------------------
def test_process_basic_cpu_job_reports_failure_for_an_unreadable_source(tmp_path):
    missing = tmp_path / "missing.jpg"
    result = basic_tasks.process_basic_cpu_job(
        str(missing), uuid.uuid4(), str(tmp_path), "user-1",
    )
    assert result["success"] is False
    assert result["error"]
    assert "thumb_path" not in result


# ---------------------------------------------------------------------------
# app/crud/dashboard.py
# ---------------------------------------------------------------------------
def _color_record(dominant_colors, hint="warm", brightness=0.6, saturation=0.4):
    return SimpleNamespace(dominant_colors=dominant_colors, emotion_hint=hint,
                            brightness=brightness, saturation=saturation,
                            analysis_version=CURRENT_COLOR_ANALYSIS_VERSION)


def test_representative_day_color_falls_back_to_a_plain_color_value():
    record = _color_record(["#ff8800"])
    color, hint, brightness, saturation = dashboard_crud._representative_day_color(
        ["p1"], {"p1": record},
        {"p1": (datetime(2026, 11, 13, 10, 5), ImageType.CAMERA)},
    )
    assert color == "#ff8800"
    assert hint == "warm"
    assert brightness == 0.6
    assert saturation == 0.4


def test_representative_day_color_ignores_an_unparsable_hex_value():
    record = _color_record([{"hex": "zzzzzz", "ratio": 1}])
    color, _hint, _brightness, _saturation = dashboard_crud._representative_day_color(
        ["p1"], {"p1": record},
        {"p1": (datetime(2026, 11, 13, 10, 5), ImageType.CAMERA)},
    )
    assert color == "zzzzzz"


def test_emotion_calendar_stats_defaults_to_the_last_365_days(face_sqlite_session):
    response = dashboard_crud.get_emotion_calendar_stats(face_sqlite_session, uuid.uuid4())
    assert response is not None
    assert response.total_photos == 0
    assert response.data == []

class _FakeDb:
    """Minimal Session stand-in for the metadata update helper."""

    def __init__(self):
        self.added = []
        self.committed = False

    @property
    def new(self):
        return []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def query(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None



