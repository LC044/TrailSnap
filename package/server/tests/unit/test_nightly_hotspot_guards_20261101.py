"""Nightly hotspot guards for the 2026-11-01 coverage scan.

These tests target five modules that still had uncovered helper branches after
the full unit suite: deterministic agent parsing/search normalization, memory
extraction guards, saved-palette normalization, and desktop media proofs.
They intentionally use no external service and no mutable user data.
"""

import json
import sqlite3
from uuid import uuid4

import pytest

from app.service.agent import memory, photo_search, search_planner
from app.utils import desktop_verification
from app.utils.color import saved_palette_metrics

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def test_photo_search_normalizes_redundant_place_prefixes():
    """Descriptions may not repeat an already extracted location."""

    assert photo_search._remove_redundant_location("武汉 市的夜景", "武汉") == "夜景"
    assert photo_search._remove_redundant_location("武汉市江滩", "武汉") == "江滩"
    assert photo_search._remove_redundant_location("武汉,、的", "武汉") is None
    assert photo_search._remove_redundant_location(None, "武汉") is None
    assert photo_search._remove_redundant_location("黄鹤楼", "武汉") == "黄鹤楼"


def test_search_planner_accepts_model_wrappers_but_requires_object():
    content = [
        {"type": "text", "text": "```json\n{\"location\":\"\", \"people\":[\"  \",\"小李\"]}\n```"},
        {"type": "unused"},
    ]

    assert search_planner._parse_model_json(content) == {"people": ["  ", "小李"]}
    assert search_planner._parse_model_json("{'tags': ['山'], 'ocr_text': None}") == {
        "tags": ["山"]
    }

    with pytest.raises(ValueError, match="搜索条件必须是对象"):
        search_planner._parse_model_json("[1, 2, 3]")

    assert search_planner._place_forms("武汉市") == {"武汉市", "武汉"}
    assert search_planner._place_forms("北京") == {"北京"}


def test_memory_photo_id_collection_and_extraction_parse_are_conservative():
    photo_id = str(uuid4())
    reply = f"看这张 /medias/{photo_id}/thumbnail 和说明文字"
    calls = [{"tool_return": {"photos": [{"photo_id": photo_id}, {"photo_id": photo_id}]}}]

    assert memory._collect_photo_ids(reply, calls) == {photo_id}
    assert memory._collect_photo_ids("普通回复", [{"tool_return": "no id"}]) == set()
    assert memory._collect_photo_ids(None, None) == set()

    fenced = "```json\n前置文本 {\"memories\":[{\"photo_id\":\"x\",\"note\":\"n\"}]} 尾部 ```"
    assert memory._parse_extraction_result(fenced) == [
        {"photo_id": "x", "note": "n"}
    ]
    assert memory._parse_extraction_result("```json\n{\"memories\": {}}\n```") == []
    assert memory._parse_extraction_result("") == []


def test_saved_palette_metrics_skip_invalid_colors_and_normalize_valid_weights():
    colors = [
        {"hex": "#FFFFFF", "ratio": 0.8},
        {"hex": "#000000", "ratio": 0.2},
        {"hex": "#12345", "ratio": 1.0},
        {"hex": "#GGGGGG", "ratio": 1.0},
        {"hex": "#123456", "ratio": 0.0},
        "not-a-dict",
    ]

    brightness, saturation, warm, cool, total = saved_palette_metrics(colors)

    assert total == pytest.approx(1.0)
    assert brightness == pytest.approx(0.8)
    assert saturation == 0.0
    assert warm == 0.0
    assert cool == 0.0
    assert saved_palette_metrics([{"hex": "#12345", "ratio": -1}]) is None


@pytest.mark.parametrize("create_database", [False, True])
def test_media_baseline_returns_empty_for_missing_library_or_photos_table(tmp_path, create_database):
    root = tmp_path / "portable"
    root.mkdir()
    if create_database:
        database = root / "data/trailsnap.sqlite"
        database.parent.mkdir()
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE other (id TEXT)")

    assert desktop_verification.media_baseline(root, limit=None) == []


