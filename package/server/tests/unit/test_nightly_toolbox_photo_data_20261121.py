"""夜间盲区补测：工具箱计划里的照片载荷序列化。

覆盖 app/service/toolbox_plans.py 的 ``photo_data``（此前未被任何单测按名引用）。
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.service import toolbox_plans

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

METADATA_KEYS = ("province", "city", "district", "address", "make", "model", "exif_info")


def _photo(metadata=None, tags=(), faces=()):
    return SimpleNamespace(
        photo_time=datetime(2026, 4, 5, 12, 30),
        upload_time=datetime(2026, 4, 6, 8, 0),
        metadata_info=metadata,
        tags=list(tags),
        faces=list(faces),
    )


def test_photo_data_serializes_metadata_keys():
    """元数据必须固定输出 7 个字段，缺失时为 None。"""
    photo = _photo(metadata=SimpleNamespace(city="北京", make="Canon"))

    payload = toolbox_plans.photo_data(photo)

    assert payload["time"] == "2026-04-05 12:30:00"
    assert payload["upload"] == "2026-04-06 08:00:00"
    assert set(payload["metadata"]) == set(METADATA_KEYS)
    assert payload["metadata"]["city"] == "北京"
    assert payload["metadata"]["province"] is None


def test_photo_data_handles_missing_metadata():
    """照片没有元数据行时，metadata 字典的每个键都应为 None。"""
    payload = toolbox_plans.photo_data(_photo(metadata=None))

    assert all(value is None for value in payload["metadata"].values())
    assert payload["tags"] == []
    assert payload["people"] == []


def test_photo_data_sorts_tags_and_people():
    """标签与人物必须按稳定顺序输出，避免提示词抖动。"""
    photo = _photo(
        tags=[SimpleNamespace(id="tag-2", tag_name="海边"), SimpleNamespace(id="tag-1", tag_name="旅行")],
        faces=[
            SimpleNamespace(identity=SimpleNamespace(id="p2", identity_name="乙")),
            SimpleNamespace(identity=SimpleNamespace(id="p1", identity_name="甲")),
        ],
    )

    payload = toolbox_plans.photo_data(photo)

    assert payload["tags"] == [("tag-1", "旅行"), ("tag-2", "海边")]
    assert payload["people"] == [("p1", "甲"), ("p2", "乙")]


def test_photo_data_skips_faces_without_identity():
    """未关联身份的人脸不得进入 people 列表。"""
    photo = _photo(faces=[SimpleNamespace(identity=None)])

    payload = toolbox_plans.photo_data(photo)

    assert payload["people"] == []
