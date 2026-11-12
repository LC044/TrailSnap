"""Nightly watch 2026-11-12 · app/schemas/chapter.py 校验器盲区补测。

被测模块：app/schemas/chapter.py
覆盖点（2026-11-12 覆盖率基线中未触达的校验分支）：
- ChapterDefinition.valid_range：结束日期早于开始日期、章节名称仅空白、日记年份非法。
- ChapterDiaryGenerate.valid_scope：scope=year 但未提供年份。
- ChapterPreview.valid_range：结束日期早于开始日期。

这些分支属于纯 pydantic 校验，不依赖 DB / 网络。
"""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.chapter import (
    ChapterDefinition,
    ChapterDiaryGenerate,
    ChapterPreview,
    ChapterUpdate,
)

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _definition(**kwargs):
    payload = {"title": "三月", "start_date": date(2025, 3, 1)}
    payload.update(kwargs)
    return ChapterDefinition(**payload)


def test_chapter_definition_rejects_end_date_before_start_date():
    with pytest.raises(ValidationError) as excinfo:
        _definition(end_date=date(2025, 2, 28))
    assert "结束日期不能早于开始日期" in str(excinfo.value)


def test_chapter_definition_rejects_whitespace_only_title():
    with pytest.raises(ValidationError) as excinfo:
        _definition(title="   ")
    assert "章节名称不能为空" in str(excinfo.value)


@pytest.mark.parametrize("year", ["24", "1899", "2201", "abc", "2024.0"])
def test_chapter_definition_rejects_invalid_diary_year(year):
    with pytest.raises(ValidationError) as excinfo:
        _definition(diary_entries={year: {"title": "一月", "body": "记录"}})
    assert "日记年份无效" in str(excinfo.value)


def test_chapter_definition_accepts_valid_diary_year():
    chapter = _definition(diary_entries={"2024": {"title": "一月", "body": "记录"}})
    assert list(chapter.diary_entries) == ["2024"]


def test_chapter_diary_generate_requires_year_for_year_scope():
    with pytest.raises(ValidationError) as excinfo:
        ChapterDiaryGenerate(scope="year", version=1)
    assert "请选择日记年份" in str(excinfo.value)


def test_chapter_diary_generate_allows_introduction_without_year():
    draft = ChapterDiaryGenerate(scope="introduction", version=1)
    assert draft.year is None


def test_chapter_preview_rejects_end_date_before_start_date():
    with pytest.raises(ValidationError) as excinfo:
        ChapterPreview(start_date=date(2025, 3, 1), end_date=date(2025, 2, 1))
    assert "结束日期不能早于开始日期" in str(excinfo.value)


def test_chapter_update_inherits_definition_validation():
    with pytest.raises(ValidationError) as excinfo:
        ChapterUpdate(title="三月", start_date=date(2025, 3, 1), version=1,
                      end_date=date(2025, 1, 1))
    assert "结束日期不能早于开始日期" in str(excinfo.value)

