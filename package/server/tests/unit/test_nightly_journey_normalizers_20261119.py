"""覆盖 app/service/journey.py 中此前没有测试引用的三个归一化/判定函数。

盲区来源：函数级静态引用扫描命中 _city / _station / _editable。
- _city / _station 负责把「杭州市」「上海站」这类带后缀的地名归一化，
  是 load_stations 与 discover 建立「城市 -> (省, 市)」映射的前提；
- _editable 决定一条自动生成的行程候选记忆是否仍可被系统刷新，
  误判会让用户的确认结果被系统覆盖，或让已忽略的候选复活。

既有测试只走 discover 的整体流程，从未直接断言这三个函数的边界行为。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.db.models.memory import MemoryOrigin, MemoryStatus
from app.service import journey

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _memory(**overrides):
    base = dict(
        origin=MemoryOrigin.AUTO,
        algorithm_version=journey.ALGORITHM_VERSION,
        status=MemoryStatus.CANDIDATE,
        version=1,
        title_source="system",
        cover_source="system",
        story_source="system",
        photo_links=[],
        tickets=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_city_strips_the_municipality_suffix_and_surrounding_space():
    assert journey._city("杭州市") == "杭州"
    assert journey._city("  北京  ") == "北京"
    assert journey._city("上海市") == "上海"


def test_city_tolerates_missing_values():
    assert journey._city(None) == ""
    assert journey._city("") == ""
    # 只有一个「市」时后缀被去掉后不应留下残字。
    assert journey._city("市") == ""


def test_station_only_strips_the_station_suffix():
    assert journey._station("上海站") == "上海"
    assert journey._station("杭州东") == "杭州东"
    assert journey._station(None) == ""
    # 「站」结尾的车站名归一化后不应残留后缀字符。
    assert journey._station("站") == ""


def test_editable_accepts_an_untouched_system_candidate():
    assert journey._editable(_memory()) is True
    # 被系统取代的候选同样可以被刷新。
    assert journey._editable(_memory(status=MemoryStatus.SUPERSEDED)) is True


def test_editable_rejects_candidates_the_user_or_another_origin_owns():
    assert journey._editable(_memory(origin=MemoryOrigin.MANUAL)) is False
    assert journey._editable(_memory(origin=MemoryOrigin.AGENT)) is False
    assert journey._editable(_memory(algorithm_version="journey-v0-other")) is False
    assert journey._editable(_memory(status=MemoryStatus.CONFIRMED)) is False
    assert journey._editable(_memory(status=MemoryStatus.IGNORED)) is False
    assert journey._editable(_memory(version=2)) is False


def test_editable_rejects_candidates_with_user_written_text():
    assert journey._editable(_memory(title_source="user")) is False
    assert journey._editable(_memory(cover_source="user")) is False
    assert journey._editable(_memory(story_source="user")) is False


def test_editable_rejects_candidates_with_confirmed_or_manual_links():
    confirmed_link = SimpleNamespace(is_confirmed=True, source="inferred")
    manual_link = SimpleNamespace(is_confirmed=False, source="manual")
    confirmed_ticket = SimpleNamespace(is_confirmed=True, source="inferred")
    manual_ticket = SimpleNamespace(is_confirmed=False, source="manual")

    assert journey._editable(_memory(photo_links=[confirmed_link])) is False
    assert journey._editable(_memory(photo_links=[manual_link])) is False
    assert journey._editable(_memory(tickets=[confirmed_ticket])) is False
    assert journey._editable(_memory(tickets=[manual_ticket])) is False
    assert journey._editable(
        _memory(photo_links=[SimpleNamespace(is_confirmed=False, source="inferred")])
    ) is True
