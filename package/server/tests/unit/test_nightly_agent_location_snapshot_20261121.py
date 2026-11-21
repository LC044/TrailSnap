"""夜间盲区补测：Agent 位置快照落地与上下文修复预览。

覆盖 app/service/agent/actions.py 的 ``_apply_location_snapshot`` 与
``_context_repair_preview``（此前未被任何单测按名引用）。
"""
from uuid import UUID, uuid4

import pytest

from app.db.models.photo_metadata import PhotoMetadata
from app.service.agent import actions

pytestmark = [pytest.mark.smoke, pytest.mark.regression]


def test_apply_location_snapshot_writes_all_location_fields():
    """快照中的经纬度与行政区划必须整体写入元数据。"""
    metadata = PhotoMetadata()
    scene_id = str(uuid4())

    actions._apply_location_snapshot(metadata, {
        "longitude": 116.4, "latitude": 39.9, "city": "北京", "district": "朝阳区",
        "province": "北京市", "country": "中国", "address": "建国路",
        "location_api": "amap", "scene_id": scene_id,
    })

    assert metadata.longitude == 116.4
    assert metadata.latitude == 39.9
    assert metadata.city == "北京"
    assert metadata.district == "朝阳区"
    assert metadata.province == "北京市"
    assert metadata.country == "中国"
    assert metadata.address == "建国路"
    assert metadata.location_api == "amap"
    assert metadata.scene_id == UUID(scene_id)


def test_apply_location_snapshot_without_scene_id_clears_scene():
    """缺少 scene_id 时必须把场景置空，而不是保留旧值。"""
    metadata = PhotoMetadata()
    metadata.scene_id = uuid4()

    actions._apply_location_snapshot(metadata, {"city": "上海"})

    assert metadata.city == "上海"
    assert metadata.scene_id is None
    assert metadata.latitude is None


def test_apply_location_snapshot_rejects_invalid_scene_id():
    """非法 scene_id 必须抛 ValueError，避免把脏数据写进元数据。"""
    metadata = PhotoMetadata()

    with pytest.raises(ValueError):
        actions._apply_location_snapshot(metadata, {"scene_id": "not-a-uuid"})


def _candidate(index):
    return {
        "id": f"cand-{index}",
        "photo_id": f"photo-{index % 3}",
        "thumbnail_url": f"http://thumb/{index}",
        "reason": "时间接近",
    }


def test_context_repair_preview_reports_counts_and_selection():
    """预览必须区分候选数、修复数与涉及照片数，并按候选顺序给出选中项。"""
    candidates = [_candidate(i) for i in range(4)]

    preview = actions._context_repair_preview(candidates, ["cand-3", "cand-1"])

    assert preview["mode"] == "context_repair"
    assert preview["candidate_count"] == 4
    assert preview["repair_count"] == 2
    assert preview["photo_count"] == 2
    assert preview["selected_repair_ids"] == ["cand-1", "cand-3"]
    assert preview["reversible"] is True
    assert preview["repairs"] == candidates


def test_context_repair_preview_caps_sample_photos():
    """样本缩略图最多返回 12 条，避免响应体过大。"""
    candidates = [_candidate(i) for i in range(20)]

    preview = actions._context_repair_preview(candidates, [c["id"] for c in candidates])

    assert len(preview["sample_photos"]) == 12
    assert preview["sample_photos"][0]["photo_id"] == "photo-0"


def test_context_repair_preview_with_empty_selection():
    """没有选中任何候选时不得产生修复项。"""
    preview = actions._context_repair_preview([_candidate(0)], [])

    assert preview["repair_count"] == 0
    assert preview["photo_count"] == 0
    assert preview["selected_repair_ids"] == []
    assert preview["sample_photos"] == []
