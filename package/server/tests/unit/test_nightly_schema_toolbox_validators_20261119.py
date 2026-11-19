"""2026-11-19 nightly coverage for ``app/schemas/toolbox.py``.

``validate_source``, ``validate_rule``, ``validate_operation`` and
``unique_presets`` were never referenced by any test file.  They are the
preview-first safety net of the toolbox: they stop a run before it touches the
filesystem, so each rejection rule is asserted here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.toolbox import (
    MediaScope,
    OrganizeRule,
    ToolConfig,
    ToolboxPreferences,
    ToolPreset,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


ALBUM_ID = "11111111-2222-3333-4444-555555555555"
PHOTO_ID = "11111111-2222-3333-4444-666666666666"


def test_an_album_scope_without_albums_is_rejected():
    with pytest.raises(ValidationError, match="请明确选择处理范围"):
        MediaScope(source="albums")


def test_a_folder_scope_without_folders_is_rejected():
    with pytest.raises(ValidationError, match="请明确选择处理范围"):
        MediaScope(source="folders")


def test_a_selected_scope_without_photos_is_rejected():
    with pytest.raises(ValidationError, match="请明确选择处理范围"):
        MediaScope(source="selected")


def test_an_album_scope_with_albums_is_accepted():
    scope = MediaScope(source="albums", album_ids=[ALBUM_ID])

    assert [str(item) for item in scope.album_ids] == [ALBUM_ID]


def test_a_filter_scope_without_any_date_is_rejected():
    with pytest.raises(ValidationError, match="条件筛选至少需要指定日期"):
        MediaScope(source="filter")


def test_a_filter_scope_with_one_date_is_accepted():
    assert MediaScope(source="filter", start_date="2026-01-01").start_date is not None


def test_an_inverted_date_range_is_rejected():
    with pytest.raises(ValidationError, match="开始日期不能晚于结束日期"):
        MediaScope(source="all", start_date="2026-06-01", end_date="2026-01-01")


def test_an_empty_group_selection_is_rejected():
    with pytest.raises(ValidationError, match="指定分组至少需要选择一项"):
        OrganizeRule(strategy="time", groups=[])


def test_a_time_strategy_rejects_a_location_granularity():
    with pytest.raises(ValidationError, match="日期粒度无效"):
        OrganizeRule(strategy="time", granularity="city")


def test_a_location_strategy_rejects_a_time_granularity():
    with pytest.raises(ValidationError, match="地点粒度无效"):
        OrganizeRule(strategy="location", granularity="year")


def test_a_location_strategy_accepts_a_city_granularity():
    assert OrganizeRule(strategy="location", granularity="city").granularity == "city"


def test_an_organize_config_without_a_target_is_rejected():
    with pytest.raises(ValidationError, match="请选择目标目录和移动/复制方式"):
        ToolConfig(kind="organize", action="move", target="")


def test_an_organize_config_without_an_action_is_rejected():
    with pytest.raises(ValidationError, match="请选择目标目录和移动/复制方式"):
        ToolConfig(kind="organize", action=None, target="/photos")


def test_multi_group_output_requires_copy():
    with pytest.raises(ValidationError, match="多个分组分别生成文件仅支持复制"):
        ToolConfig(kind="organize", action="move", target="/photos", multi_group="all")


def test_multi_group_output_is_allowed_for_copy():
    config = ToolConfig(kind="organize", action="copy", target="/photos", multi_group="all")

    assert config.multi_group == "all"


def test_a_metadata_config_without_any_capture_info_is_rejected():
    with pytest.raises(ValidationError, match="请至少设置一项拍摄信息"):
        ToolConfig(kind="metadata", time_mode="none")


def test_a_metadata_config_with_a_custom_time_must_carry_a_value():
    with pytest.raises(ValidationError, match="请选择指定时间"):
        ToolConfig(kind="metadata", time_mode="custom")


def test_a_metadata_config_with_a_custom_time_must_be_iso_formatted():
    with pytest.raises(ValueError):
        ToolConfig(kind="metadata", time_mode="custom", custom_time="2026/01/01")


def test_duplicate_preset_ids_are_rejected():
    presets = [
        ToolPreset(id="same", name="A", config=ToolConfig(kind="rename")),
        ToolPreset(id="same", name="B", config=ToolConfig(kind="rename")),
    ]

    with pytest.raises(ValidationError, match="模板标识重复"):
        ToolboxPreferences(version=1, presets=presets)


def test_duplicate_preset_names_are_rejected():
    presets = [
        ToolPreset(id="a", name="Same", config=ToolConfig(kind="rename")),
        ToolPreset(id="b", name="Same", config=ToolConfig(kind="rename")),
    ]

    with pytest.raises(ValidationError, match="模板名称重复"):
        ToolboxPreferences(version=1, presets=presets)


def test_the_default_rename_preset_must_exist_and_be_a_rename_preset():
    presets = [ToolPreset(id="a", name="A", config=ToolConfig(kind="organize", action="copy", target="/p"))]

    with pytest.raises(ValidationError, match="默认命名模板不存在"):
        ToolboxPreferences(version=1, presets=presets, default_rename_id="a")


def test_the_default_rename_preset_must_point_at_an_existing_preset():
    presets = [ToolPreset(id="a", name="A", config=ToolConfig(kind="rename"))]

    with pytest.raises(ValidationError, match="默认命名模板不存在"):
        ToolboxPreferences(version=1, presets=presets, default_rename_id="missing")


def test_a_valid_rename_default_is_accepted():
    presets = [ToolPreset(id="a", name="A", config=ToolConfig(kind="rename"))]

    preferences = ToolboxPreferences(version=1, presets=presets, default_rename_id="a")

    assert preferences.default_rename_id == "a"

