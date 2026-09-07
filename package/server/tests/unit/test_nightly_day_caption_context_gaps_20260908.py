"""Nightly gap tests for day-caption context preparation (2026-09-08)."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.db.models.photo import FileType

pytestmark = [pytest.mark.smoke]

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
DAY = date(2026, 9, 8)


def _photo(photo_id, file_type=FileType.image):
    return SimpleNamespace(id=photo_id, file_type=file_type)


def test_dedup_similar_photos_preserves_videos_and_unclustered_images():
    from app.service.moment import day_caption_service as svc

    photos = [
        _photo("representative"),
        _photo("duplicate"),
        _photo("video", FileType.video),
        _photo("no-embedding"),
    ]
    db = MagicMock()

    with patch.object(svc, "dedup_day_photo_ids", return_value=({"representative"}, {"total_candidates": 2})) as dedup:
        with patch.object(svc, "_fetch_clustered_photo_ids", return_value={"representative", "duplicate"}):
            result, original_count = svc._dedup_similar_photos(db, USER_ID, DAY, photos)

    dedup.assert_called_once_with(db, USER_ID, DAY)
    assert [p.id for p in result] == ["representative", "video", "no-embedding"]
    assert original_count == 3


def test_build_materials_aggregates_locations_people_descriptions_and_tags():
    from app.service.moment import day_caption_service as svc

    photos = [_photo("p1"), _photo("p2", FileType.video)]
    db = MagicMock()
    location_query = MagicMock()
    location_query.outerjoin.return_value.filter.return_value.all.return_value = [
        (SimpleNamespace(city="杭州", district="西湖", address="西湖景区"), "西湖"),
        (SimpleNamespace(city="杭州", district="余杭", address=""), None),
    ]
    people_query = MagicMock()
    people_query.join.return_value.filter.return_value.all.return_value = [("Alice",), ("Alice",), ("Bob",)]
    description_query = MagicMock()
    description_query.filter.return_value.all.return_value = [
        SimpleNamespace(narrative="西湖边的傍晚", description="", tags=["旅行", "旅行", "夜景"]),
        SimpleNamespace(narrative="", description="备用描述", tags=[]),
    ]
    db.query.side_effect = [location_query, people_query, description_query]

    materials = svc._build_materials(db, photos, image_original_count=3)

    assert materials["locations"] == ["西湖", "杭州 · 余杭"]
    assert materials["people"] == ["Alice", "Bob"]
    assert materials["descriptions"] == ["西湖边的傍晚", "备用描述"]
    assert materials["tags"] == ["旅行", "夜景"]
    assert materials["counts"] == {"image": 1, "video": 1, "image_original": 3}


def test_prepare_context_rejects_scope_and_returns_cached_caption():
    from app.service.moment import day_caption_service as svc

    db = MagicMock()
    with pytest.raises(ValueError, match="只支持全部照片视图"):
        svc._prepare_context(
            USER_ID, db, DAY, "Asia/Shanghai", "album", None,
            None, None, None, False,
        )

    cached = SimpleNamespace(caption="已有文案")
    with patch.object(svc.moment_crud, "get_caption", return_value=cached) as get_caption:
        result = svc._prepare_context(
            USER_ID, db, DAY, "Asia/Shanghai", "all", None,
            "poetic", "conn", "model", False,
        )

    get_caption.assert_called_once_with(db, USER_ID, "all", None, DAY)
    assert result == ("已有文案", {})
