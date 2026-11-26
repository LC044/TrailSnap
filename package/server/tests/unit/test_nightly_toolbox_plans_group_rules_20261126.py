"""Nightly watch 2026-11-26 · app/service/toolbox_plans.py 的分组规则盲区。

覆盖率扫描显示 ``rule_groups`` / ``grouping_paths`` 里的若干分支从未被执行：
按「日」粒度拆分目录（第 82 行）、多规则歧义时的提示文案、以及分组数量超过
上限时的拒绝逻辑（第 119-124 行）。这些分支决定了「归档」会把照片放到哪个
目录、目录名长什么样，一旦算错就会把照片落到用户意料之外的位置。

本文件用最小化的假 photo / rule / config 驱动纯函数，覆盖：

- 时间策略：年 / 月 / 日三种粒度，以及缺时间时的 skip / placeholder / upload 兜底
- 地点策略：省市区组合与缺失兜底
- 分类 / 人物策略：多分组时按名称排序
- 指定分组过滤（rule.groups）后只剩被选中的那一组
- 归档路径：多规则笛卡尔积、嵌套开关、歧义提示与分组上限
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.toolbox import OrganizeRule, ToolConfig
from app.service.toolbox_plans import grouping_paths, rule_groups


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


def _tag(name, tag_id=None):
    return SimpleNamespace(id=tag_id or uuid4(), tag_name=name)


def _face(identity_name, identity_id=None):
    return SimpleNamespace(identity=SimpleNamespace(
        id=identity_id or uuid4(), identity_name=identity_name))


def _photo(photo_time=None, upload_time=None, metadata=None, tags=(), faces=()):
    return SimpleNamespace(
        id=uuid4(),
        photo_time=photo_time,
        upload_time=upload_time,
        metadata_info=metadata,
        tags=list(tags),
        faces=list(faces),
    )


def _config(**kwargs):
    base = {
        "kind": "organize",
        "action": "copy",
        "target": "/library/archive",
        "rules": [OrganizeRule(strategy="time", granularity="month")],
        "missing": "skip",
        "multi_group": "skip",
    }
    base.update(kwargs)
    return ToolConfig(**base)


# --- 时间策略 ---------------------------------------------------------------

def test_time_rule_groups_by_year_only():
    photo = _photo(photo_time=datetime(2024, 3, 7, 10, 30))
    rule = OrganizeRule(strategy="time", granularity="year")

    groups = rule_groups(photo, rule, _config())

    assert groups == [("2024", ["2024"])]


def test_time_rule_groups_by_month():
    photo = _photo(photo_time=datetime(2024, 3, 7, 10, 30))
    rule = OrganizeRule(strategy="time", granularity="month")

    groups = rule_groups(photo, rule, _config())

    assert groups == [("2024-03", ["2024", "03"])]


def test_time_rule_groups_by_day_include_the_day_segment():
    """按「日」归档时目录里必须多出日期段，否则同月的照片会混在一起。"""
    photo = _photo(photo_time=datetime(2024, 3, 7, 10, 30))
    rule = OrganizeRule(strategy="time", granularity="day")

    groups = rule_groups(photo, rule, _config())

    assert groups == [("2024-03-07", ["2024", "03", "07"])]


def test_time_rule_without_any_timestamp_yields_no_group_when_missing_is_skip():
    photo = _photo()
    rule = OrganizeRule(strategy="time", granularity="month")

    assert rule_groups(photo, rule, _config(missing="skip")) == []


def test_time_rule_uses_a_placeholder_group_when_missing_is_placeholder():
    photo = _photo()
    rule = OrganizeRule(strategy="time", granularity="month")

    groups = rule_groups(photo, rule, _config(missing="placeholder"))

    assert groups == [("unknown", ["未知时间"])]


def test_time_rule_falls_back_to_the_upload_time_when_missing_is_upload():
    photo = _photo(photo_time=None, upload_time=datetime(2022, 8, 9, 8, 0))
    rule = OrganizeRule(strategy="time", granularity="year")

    groups = rule_groups(photo, rule, _config(missing="upload"))

    assert groups == [("2022", ["2022"])]


def test_time_rule_keeps_only_the_requested_group():
    photo = _photo(photo_time=datetime(2024, 3, 7, 10, 30))
    rule = OrganizeRule(strategy="time", granularity="month", groups=["2024-03", "2020-01"])

    groups = rule_groups(photo, rule, _config())

    assert groups == [("2024-03", ["2024", "03"])]


# --- 地点 / 分类 / 人物策略 --------------------------------------------------

def test_location_rule_groups_by_the_requested_granularity():
    photo = _photo(metadata=SimpleNamespace(province="湖北省", city="武汉市", district="洪山区"))
    rule = OrganizeRule(strategy="location", granularity="province_city")

    groups = rule_groups(photo, rule, _config())

    key, parts = groups[0]
    assert parts == ["湖北省", "武汉市"]
    assert "湖北省" in key and "武汉市" in key


def test_location_rule_uses_a_placeholder_when_a_part_is_missing():
    photo = _photo(metadata=SimpleNamespace(province="湖北省", city=None, district="洪山区"))
    rule = OrganizeRule(strategy="location", granularity="province_city")

    groups = rule_groups(photo, rule, _config(missing="placeholder"))

    assert groups == [("unknown", ["未知位置"])]


def test_category_rule_groups_by_tag_and_sorts_by_name():
    photo = _photo(tags=[_tag("夜景"), _tag("风景")])
    rule = OrganizeRule(strategy="category", granularity="month")

    groups = rule_groups(photo, rule, _config())

    assert [parts[0] for _, parts in groups] == ["夜景", "风景"]


def test_person_rule_ignores_identities_without_a_name():
    photo = _photo(faces=[_face("张三"), SimpleNamespace(identity=None),
                          _face("李四")])
    rule = OrganizeRule(strategy="person", granularity="month")

    groups = rule_groups(photo, rule, _config())

    assert sorted(parts[0] for _, parts in groups) == ["张三", "李四"]


def test_person_rule_without_any_identity_uses_a_placeholder():
    photo = _photo()
    rule = OrganizeRule(strategy="person", granularity="month")

    groups = rule_groups(photo, rule, _config(missing="placeholder"))

    assert groups == [("unknown", ["未命名"])]


# --- 归档路径 ---------------------------------------------------------------

def test_grouping_paths_joins_the_parts_when_nested_is_disabled():
    photo = _photo(photo_time=datetime(2024, 3, 7, 10, 30))
    config = _config(
        rules=[OrganizeRule(strategy="time", granularity="month", nested=False)],
    )

    paths, reason = grouping_paths(photo, config)

    assert reason == ""
    assert paths == [["2024-03"]]


def test_grouping_paths_reports_missing_archive_information():
    photo = _photo()
    config = _config(rules=[OrganizeRule(strategy="time", granularity="month")])

    paths, reason = grouping_paths(photo, config)

    assert paths == []
    assert reason == "缺少归档信息或不在指定分组"


def test_grouping_paths_rejects_ambiguous_multi_group_photos():
    photo = _photo(tags=[_tag("夜景"), _tag("风景")])
    config = _config(
        rules=[OrganizeRule(strategy="category", granularity="month")],
        multi_group="skip",
    )

    paths, reason = grouping_paths(photo, config)

    assert paths == []
    assert reason == "多个分组存在歧义，请明确归属"


def test_grouping_paths_keeps_only_the_first_group_when_configured():
    photo = _photo(tags=[_tag("夜景"), _tag("风景")])
    config = _config(
        rules=[OrganizeRule(strategy="category", granularity="month")],
        multi_group="first",
    )

    paths, reason = grouping_paths(photo, config)

    assert reason == ""
    assert paths == [["夜景"]]


def test_grouping_paths_expands_every_rule_into_a_cartesian_product():
    photo = _photo(photo_time=datetime(2024, 3, 7, 10, 30), tags=[_tag("夜景"), _tag("风景")])
    config = _config(
        rules=[
            OrganizeRule(strategy="time", granularity="year"),
            OrganizeRule(strategy="category", granularity="month"),
        ],
        multi_group="all",
    )

    paths, reason = grouping_paths(photo, config)

    assert reason == ""
    assert paths == [["2024", "夜景"], ["2024", "风景"]]


def test_grouping_paths_refuses_to_build_more_than_one_hundred_folders():
    photo = _photo(tags=[_tag(f"标签{index}") for index in range(101)])
    config = _config(
        rules=[OrganizeRule(strategy="category", granularity="month")],
        multi_group="all",
    )

    paths, reason = grouping_paths(photo, config)

    assert paths == []
    assert reason == "单个影像匹配分组过多，请缩小分组"

