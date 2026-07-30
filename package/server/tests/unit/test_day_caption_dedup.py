"""Unit tests for day_caption_service 的"相似照片去重进入文案素材"链路。

覆盖：
- ``_dedup_similar_photos``: 视频保留、无 embedding 保留、有 embedding burst 只留代表；
- ``_build_materials``: ``counts.image_original`` 记录原始图片数；
- ``_format_materials_for_prompt``: 发生去重时输出"N 个不同瞬间（当天共拍 M 张图）"。

不启动 sklearn；对 ``dedup_day_photo_ids`` 打桩，直接控制"哪些 id 是代表"，
让本文件专注在"去重后的照片如何被后续素材聚合消费"这条链路上。
"""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.db.models.photo import FileType
from app.service.moment import day_caption_service as svc


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _photo(pid, ftype=FileType.image, photo_time=None):
    return SimpleNamespace(
        id=pid,
        file_type=ftype,
        photo_time=photo_time or datetime(2025, 8, 5, 10, 0, 0),
    )


# ---------------------------------------------------------------------------
# _dedup_similar_photos
# ---------------------------------------------------------------------------

def test_dedup_returns_original_when_no_photos():
    """空输入原样返回，original_image_count=0。"""
    result, orig = svc._dedup_similar_photos(MagicMock(), uuid4(), date(2025, 8, 5), [])
    assert result == []
    assert orig == 0


def test_dedup_skipped_when_no_photos_in_cluster_pool():
    """当天没有图片进入相似聚类候选池（全是视频 / 全无 embedding）→ 原样返回。"""
    v1 = _photo(uuid4(), ftype=FileType.video)
    v2 = _photo(uuid4(), ftype=FileType.video)
    with patch.object(svc, "dedup_day_photo_ids", return_value=(set(), {"total_candidates": 0, "kept": 0})):
        result, orig = svc._dedup_similar_photos(MagicMock(), uuid4(), date(2025, 8, 5), [v1, v2])
    assert result == [v1, v2]
    # 视频不计入 original_image_count
    assert orig == 0


def test_dedup_keeps_representative_and_drops_similar_burst():
    """有 embedding 的 burst 组只保留代表，非代表的相似照被丢弃。"""
    rep, dup = uuid4(), uuid4()
    p_rep = _photo(rep)
    p_dup = _photo(dup)
    # kept_ids 只含 rep；clustered_ids 含两者 → dup 是"有 embedding 但被去重"→ 丢
    with patch.object(svc, "dedup_day_photo_ids", return_value=({rep}, {"total_candidates": 2, "kept": 1})):
        with patch.object(svc, "_fetch_clustered_photo_ids", return_value={rep, dup}):
            result, orig = svc._dedup_similar_photos(MagicMock(), uuid4(), date(2025, 8, 5), [p_rep, p_dup])
    assert [p.id for p in result] == [rep]
    assert orig == 2


def test_dedup_preserves_video_and_photos_without_embedding():
    """视频和无 embedding 图片都不属于聚类候选池，一律原样保留。"""
    rep = uuid4()
    no_emb = uuid4()  # 无 embedding：不在 clustered_ids 里
    video = uuid4()
    p_rep = _photo(rep, photo_time=datetime(2025, 8, 5, 10, 0, 0))
    p_no_emb = _photo(no_emb, photo_time=datetime(2025, 8, 5, 11, 0, 0))
    p_video = _photo(video, ftype=FileType.video, photo_time=datetime(2025, 8, 5, 12, 0, 0))

    with patch.object(svc, "dedup_day_photo_ids", return_value=({rep}, {"total_candidates": 1, "kept": 1})):
        with patch.object(svc, "_fetch_clustered_photo_ids", return_value={rep}):
            result, orig = svc._dedup_similar_photos(
                MagicMock(), uuid4(), date(2025, 8, 5),
                [p_rep, p_no_emb, p_video],
            )
    ids = [p.id for p in result]
    assert rep in ids and no_emb in ids and video in ids
    # 两张图（不含视频）算入 original
    assert orig == 2


# ---------------------------------------------------------------------------
# _build_materials: image_original 字段
# ---------------------------------------------------------------------------

def test_build_materials_records_image_original():
    """去重后剩 3 张，原始图片数 20 → counts.image_original=20。"""
    photos = [_photo(uuid4()) for _ in range(3)]
    db = MagicMock()
    # 让 db.query(...).filter(...).all() 都返回空，避免走到 metadata / face / desc 分支
    db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = []
    db.query.return_value.join.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.all.return_value = []

    materials = svc._build_materials(db, photos, image_original_count=20)
    counts = materials["counts"]
    assert counts["image"] == 3
    assert counts["image_original"] == 20
    assert counts["video"] == 0


def test_build_materials_defaults_image_original_to_image_when_absent():
    """未传 image_original_count → 与 image 相同（视为无去重发生）。"""
    photos = [_photo(uuid4()) for _ in range(3)]
    db = MagicMock()
    db.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = []
    db.query.return_value.join.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.all.return_value = []

    materials = svc._build_materials(db, photos)
    counts = materials["counts"]
    assert counts["image"] == 3
    assert counts["image_original"] == 3


def test_build_materials_empty_photos_still_returns_image_original():
    """空 photos + 传入 image_original_count → 也应记录，避免调用方拿不到该字段。"""
    materials = svc._build_materials(MagicMock(), [], image_original_count=15)
    assert materials["counts"]["image"] == 0
    assert materials["counts"]["image_original"] == 15


# ---------------------------------------------------------------------------
# _format_materials_for_prompt: 去重前后的展示文案
# ---------------------------------------------------------------------------

def test_prompt_shows_dedup_hint_when_dedup_happened():
    """image_original > image → 输出"X 个不同瞬间（当天共拍 Y 张图）"。"""
    materials = {
        "locations": [], "people": [], "descriptions": [], "tags": [],
        "counts": {"image": 5, "video": 0, "image_original": 30},
    }
    text = svc._format_materials_for_prompt(date(2025, 8, 5), materials, style=None)
    assert "5 个不同瞬间" in text
    assert "当天共拍 30 张图" in text


def test_prompt_shows_plain_count_when_no_dedup():
    """image_original == image → 走普通"X 张图 / Y 个视频"格式。"""
    materials = {
        "locations": [], "people": [], "descriptions": [], "tags": [],
        "counts": {"image": 5, "video": 1, "image_original": 5},
    }
    text = svc._format_materials_for_prompt(date(2025, 8, 5), materials, style=None)
    assert "5 张图 / 1 个视频" in text
    assert "不同瞬间" not in text


# ---------------------------------------------------------------------------
# day_highlight_service.dedup_day_photo_ids: 新导出的公开 API
# ---------------------------------------------------------------------------

def test_dedup_day_photo_ids_empty_when_no_candidates():
    from app.service.moment import day_highlight_service as hsvc
    db = MagicMock()
    result_mock = MagicMock()
    result_mock.all.return_value = []
    db.execute.return_value = result_mock

    kept, stats = hsvc.dedup_day_photo_ids(db, uuid4(), date(2025, 8, 5))
    assert kept == set()
    assert stats == {"total_candidates": 0, "kept": 0}


def test_dedup_day_photo_ids_returns_representatives_only():
    """两张相同 embedding 的连拍 → kept 只有 1 张（score 高的那个）。"""
    from app.service.moment import day_highlight_service as hsvc

    hi, lo = uuid4(), uuid4()
    rows = [
        SimpleNamespace(id=lo, photo_time=datetime(2025, 8, 5, 10, 0, 0),
                        embedding=[1.0, 0.0, 0.0], memory_score=10, quality_score=5),
        SimpleNamespace(id=hi, photo_time=datetime(2025, 8, 5, 10, 0, 30),
                        embedding=[1.0, 0.0, 0.0], memory_score=50, quality_score=40),
    ]
    db = MagicMock()
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    db.execute.return_value = result_mock

    kept, stats = hsvc.dedup_day_photo_ids(db, uuid4(), date(2025, 8, 5))
    assert kept == {hi}
    assert stats == {"total_candidates": 2, "kept": 1}
