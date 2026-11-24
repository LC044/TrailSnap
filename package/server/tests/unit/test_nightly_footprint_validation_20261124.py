"""Nightly watch 2026-11-24 · app/crud/footprint.py 的入参校验盲区。

覆盖扫描显示 footprint.py 只剩两行未覆盖，都是对外的入参护栏：

- get_map_routes(): 开始日期晚于结束日期 (L207)
- get_footprint(): max_points 超出 200..2000 (L223)

这两条必须在任何 SQL 之前抛出，否则会带着非法区间去跑整段 visits CTE。
"""

from datetime import date

import pytest

from app.crud import footprint

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def test_get_map_routes_rejects_an_inverted_date_range():
    with pytest.raises(ValueError) as failure:
        footprint.get_map_routes(
            None,
            None,
            start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 1),
        )
    assert str(failure.value) == "开始日期不得晚于结束日期"


def test_get_map_routes_accepts_an_equal_date_range():
    # 相同日期是合法的单日区间，不应在校验阶段抛错。
    try:
        footprint.get_map_routes(
            None,
            None,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 1),
        )
    except ValueError as error:
        assert str(error) != "开始日期不得晚于结束日期"
    except Exception:
        # 校验通过后才可能因为没有数据库连接而失败，这里不关心。
        pass


def test_get_footprint_rejects_too_few_points():
    with pytest.raises(ValueError) as failure:
        footprint.get_footprint(None, None, max_points=199)
    assert str(failure.value) == "max_points 必须在 200..2000 之间"


def test_get_footprint_rejects_too_many_points():
    with pytest.raises(ValueError) as failure:
        footprint.get_footprint(None, None, max_points=2001)
    assert str(failure.value) == "max_points 必须在 200..2000 之间"
