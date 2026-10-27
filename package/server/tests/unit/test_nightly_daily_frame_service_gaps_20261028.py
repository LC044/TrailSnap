"""2026-10-28 nightly coverage for ``app/service/daily_frame.py`` selection rules.

The 2026-10-28 backend coverage scan reported ``service/daily_frame.py`` at
78.3% with 73 uncovered lines.  The uncovered functions are the *rules* that
decide whether a photo may be used for a given day:

* ``check_range`` -- the 366-day window and the "no future dates" rule;
* ``photo_day`` -- the day a photo belongs to, honouring the calendar timezone;
* ``source_path`` -- whether the source file (and its motion part) is readable;
* ``serialize_photo`` / ``serialize_frame`` -- the client-facing payload;
* ``validate_selection`` -- the guards that reject a mismatched day, a missing
  file or a non-zero segment start on a still image.

A regression here silently lets a user build a daily-frame film out of the
wrong photos, so each rule is asserted on both the accept and the reject side.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _service():
    from app.service import daily_frame

    return daily_frame


def _calendar(name="Asia/Shanghai"):
    return SimpleNamespace(timezone=name, revision=1, locked=False)


def _photo(tmp_path, *, file_type="image", name="a.jpg", day=date(2024, 5, 6)):
    from app.db.models.photo import FileType

    path = tmp_path / name
    path.write_bytes(b"payload")
    return SimpleNamespace(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        file_path=str(path),
        file_type=FileType(file_type),
        photo_time=datetime.combine(day, datetime.min.time()),
        duration=None,
        is_deleted=False,
    )


# ---------------------------------------------------------------------------
# check_range
# ---------------------------------------------------------------------------


def test_check_range_rejects_a_year_before_1900():
    service = _service()

    with pytest.raises(HTTPException) as excinfo:
        service.check_range(date(1899, 12, 31), date(1900, 1, 1), _calendar())

    assert excinfo.value.status_code == 400


def test_check_range_rejects_a_year_after_2200():
    service = _service()

    with pytest.raises(HTTPException) as excinfo:
        service.check_range(date(2200, 1, 1), date(2200, 6, 1), _calendar())

    assert excinfo.value.status_code == 400


def test_check_range_rejects_an_inverted_range():
    service = _service()

    with pytest.raises(HTTPException) as excinfo:
        service.check_range(date(2024, 5, 6), date(2024, 5, 1), _calendar())

    assert excinfo.value.status_code == 400


def test_check_range_rejects_a_range_of_366_days_or_more():
    service = _service()

    with pytest.raises(HTTPException) as excinfo:
        service.check_range(date(2024, 1, 1), date(2025, 1, 1), _calendar())

    assert excinfo.value.status_code == 400


def test_check_range_accepts_a_range_of_exactly_365_days():
    service = _service()

    service.check_range(date(2024, 1, 1), date(2024, 12, 31), _calendar())


def test_check_range_rejects_a_future_day_unless_it_is_allowed():
    service = _service()
    future = date.today() + timedelta(days=30)

    with pytest.raises(HTTPException) as excinfo:
        service.check_range(future, future, _calendar())
    assert excinfo.value.status_code == 400

    service.check_range(future, future, _calendar(), allow_future=True)


# ---------------------------------------------------------------------------
# photo_day
# ---------------------------------------------------------------------------


def test_photo_day_returns_none_without_a_photo_time(tmp_path):
    service = _service()
    photo = _photo(tmp_path)
    photo.photo_time = None

    assert service.photo_day(photo, _calendar()) is None


def test_photo_day_uses_the_naive_photo_time_as_local_wall_clock(tmp_path):
    service = _service()
    photo = _photo(tmp_path, day=date(2024, 5, 6))

    assert service.photo_day(photo, _calendar()) == date(2024, 5, 6)


def test_photo_day_converts_an_aware_photo_time_into_the_calendar_timezone(tmp_path):
    service = _service()
    photo = _photo(tmp_path)
    # 2024-05-06 20:00 UTC is already 2024-05-07 in Asia/Shanghai.
    photo.photo_time = datetime(2024, 5, 6, 20, 0, tzinfo=timezone.utc)

    assert service.photo_day(photo, _calendar()) == date(2024, 5, 7)
    assert service.photo_day(photo, _calendar("UTC")) == date(2024, 5, 6)


# ---------------------------------------------------------------------------
# source_path
# ---------------------------------------------------------------------------


def test_source_path_reports_a_deleted_photo():
    service = _service()

    path, reason = service.source_path(None, "still")

    assert path is None
    assert reason


def test_source_path_reports_an_unreadable_source_file(tmp_path):
    service = _service()
    photo = _photo(tmp_path)
    os.remove(photo.file_path)

    path, reason = service.source_path(photo, "still")

    assert path is None
    assert reason


def test_source_path_returns_the_file_for_a_readable_still(tmp_path):
    service = _service()
    photo = _photo(tmp_path)

    path, reason = service.source_path(photo, "still")

    assert path == photo.file_path
    assert reason is None


def test_source_path_rejects_a_motion_request_for_a_still_photo(tmp_path):
    service = _service()
    photo = _photo(tmp_path)

    path, reason = service.source_path(photo, "motion")

    assert path is None
    assert reason == "这张照片没有动态片段"


def test_source_path_rejects_a_still_request_for_a_video(tmp_path):
    service = _service()
    photo = _photo(tmp_path, file_type="video", name="a.mp4")

    path, reason = service.source_path(photo, "still")

    assert path is None
    assert reason == "视频需要选择动态片段"


def test_source_path_reports_a_live_photo_without_its_motion_part(tmp_path):
    service = _service()
    photo = _photo(tmp_path, file_type="live_photo", name="a.heic")

    with patch("app.service.storage.get_live_photo_vide", return_value=None):
        path, reason = service.source_path(photo, "motion")

    assert path is None
    assert reason == "动态文件不可用，可更换为静态照片"


def test_source_path_returns_the_motion_part_of_a_live_photo(tmp_path):
    service = _service()
    photo = _photo(tmp_path, file_type="live_photo", name="a.heic")
    motion = tmp_path / "a.mov"
    motion.write_bytes(b"video")

    with patch("app.service.storage.get_live_photo_vide", return_value=str(motion)):
        path, reason = service.source_path(photo, "motion")

    assert path == str(motion)
    assert reason is None


# ---------------------------------------------------------------------------
# serialize_photo / serialize_frame
# ---------------------------------------------------------------------------


def test_serialize_photo_reports_a_readable_still_as_available(tmp_path):
    service = _service()
    photo = _photo(tmp_path)

    payload = service.serialize_photo(photo)

    assert payload["available"] is True
    assert payload["reason"] is None
    assert payload["has_motion"] is False
    assert payload["file_type"] == "image"


def test_serialize_photo_exposes_a_video_as_a_motion_capable_source(tmp_path):
    service = _service()
    photo = _photo(tmp_path, file_type="video", name="a.mp4")

    payload = service.serialize_photo(photo)

    # A video is asked for in "motion" mode, which resolves to the file itself.
    assert payload["available"] is True
    assert payload["reason"] is None
    assert payload["has_motion"] is True
    assert payload["file_type"] == "video"


def test_serialize_frame_hides_the_reason_of_a_removed_frame(tmp_path):
    service = _service()
    calendar = _calendar()
    owner_id = uuid.uuid4()
    photo = _photo(tmp_path)
    photo.owner_id = owner_id
    row = SimpleNamespace(
        id=uuid.uuid4(), owner_id=owner_id, photo_id=photo.id, day=date(2024, 5, 6),
        mode="still", start_seconds=0.0, caption="", version=3, removed=True,
    )

    payload = service.serialize_frame(MagicMock(), row, calendar, photo, loaded=True)

    assert payload["removed"] is True
    assert payload["available"] is False
    assert payload["reason"] is None


def test_serialize_frame_drops_a_photo_belonging_to_another_owner(tmp_path):
    service = _service()
    calendar = _calendar()
    row = SimpleNamespace(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), photo_id=uuid.uuid4(), day=date(2024, 5, 6),
        mode="still", start_seconds=0.0, caption="", version=1, removed=False,
    )
    foreign = _photo(tmp_path)
    foreign.owner_id = uuid.uuid4()

    payload = service.serialize_frame(MagicMock(), row, calendar, foreign, loaded=True)

    assert payload["photo"] is None
    assert payload["photo_id"] is None
    assert payload["available"] is False


def test_serialize_frame_flags_a_photo_whose_day_no_longer_matches(tmp_path):
    service = _service()
    calendar = _calendar()
    owner_id = uuid.uuid4()
    photo = _photo(tmp_path, day=date(2024, 5, 6))
    photo.owner_id = owner_id
    row = SimpleNamespace(
        id=uuid.uuid4(), owner_id=owner_id, photo_id=photo.id, day=date(2024, 5, 7),
        mode="still", start_seconds=0.0, caption="", version=1, removed=False,
    )

    payload = service.serialize_frame(MagicMock(), row, calendar, photo, loaded=True)

    assert payload["date_changed"] is True


# ---------------------------------------------------------------------------
# validate_selection
# ---------------------------------------------------------------------------


def _selection(photo_id, *, mode="still", start_seconds=0.0):
    from app.schemas.daily_frame import FrameSelection

    return FrameSelection(photo_id=photo_id, mode=mode, start_seconds=start_seconds)


def test_validate_selection_rejects_a_photo_the_owner_cannot_reach(tmp_path):
    service = _service()
    calendar = _calendar()
    owner_id = uuid.uuid4()
    photo = _photo(tmp_path)

    with patch.object(service, "owned_photo", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            service.validate_selection(
                MagicMock(), owner_id, date(2024, 5, 6), _selection(photo.id), calendar
            )

    assert excinfo.value.status_code == 404


def test_validate_selection_rejects_a_photo_taken_on_another_day(tmp_path):
    service = _service()
    calendar = _calendar()
    owner_id = uuid.uuid4()
    photo = _photo(tmp_path, day=date(2024, 5, 6))

    with patch.object(service, "owned_photo", return_value=photo):
        with pytest.raises(HTTPException) as excinfo:
            service.validate_selection(
                MagicMock(), owner_id, date(2024, 5, 7), _selection(photo.id), calendar
            )

    assert excinfo.value.status_code == 400


def test_validate_selection_rejects_an_unreadable_source_file(tmp_path):
    service = _service()
    calendar = _calendar()
    owner_id = uuid.uuid4()
    photo = _photo(tmp_path)
    os.remove(photo.file_path)

    with patch.object(service, "owned_photo", return_value=photo):
        with pytest.raises(HTTPException) as excinfo:
            service.validate_selection(
                MagicMock(), owner_id, date(2024, 5, 6), _selection(photo.id), calendar
            )

    assert excinfo.value.status_code == 400


def test_validate_selection_rejects_a_non_zero_segment_start_for_a_still(tmp_path):
    service = _service()
    calendar = _calendar()
    owner_id = uuid.uuid4()
    photo = _photo(tmp_path)

    with patch.object(service, "owned_photo", return_value=photo):
        with pytest.raises(HTTPException) as excinfo:
            service.validate_selection(
                MagicMock(), owner_id, date(2024, 5, 6),
                _selection(photo.id, start_seconds=1.5), calendar
            )

    assert excinfo.value.status_code == 400


def test_validate_selection_accepts_a_photo_taken_on_the_requested_day(tmp_path):
    service = _service()
    calendar = _calendar()
    owner_id = uuid.uuid4()
    photo = _photo(tmp_path, day=date(2024, 5, 6))

    with patch.object(service, "owned_photo", return_value=photo):
        with patch.object(service, "check_range"):
            result = service.validate_selection(
                MagicMock(), owner_id, date(2024, 5, 6), _selection(photo.id), calendar
            )

    assert result is photo
