"""Nightly watch 2026-11-24: ``app/service/tasks/visual_description.py`` 盲区。

2026-11-24 的后端覆盖率报告里 ``service/tasks/visual_description.py`` 为 88.5%，
39 行从未执行，涉及四类分支：

* ``_batch_prompt``：自定义提示词里给出的 JSON 示例无法解析时，必须原样保留
  用户的分析标准，不能把示例一起丢掉；
* ``_validate_visual_result`` / ``parse_visual_result``：顶层不是对象、内容为空
  时必须抛 ``VisualDescriptionFormatError``，让调用方走重试而不是写脏数据；
* ``_task_photo``：照片不存在、``only_if_missing`` 已有描述、已处理标记三种跳过
  分支；
* ``_save_result``：照片不存在、已处理过、以及正常写入三条分支。

这些分支直接决定「重复描述」和「脏数据」会不会进库。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.service.tasks import visual_description as vd


pytestmark = [pytest.mark.smoke]


VALID_RESULT = {
    "description": "一张海边的日落照片",
    "tags": ["海边", "日落"],
    "memory_score": 80,
    "beauty_score": 90,
    "reason": "构图完整",
    "narrative": "晚霞落在海面上",
}


# --------------------------------------------------------------------------- #
# 提示词拼装
# --------------------------------------------------------------------------- #

def test_batch_prompt_keeps_the_custom_criteria_when_the_example_is_valid_json():
    criteria = "按构图打分"
    example = json.dumps({"description": "自定义示例描述"}, ensure_ascii=False)
    prompt = f"{criteria}\n请严格只输出 JSON，格式如下：\n{example}"

    result = vd._batch_prompt(prompt, ["1", "2"])

    assert criteria in result
    assert "自定义示例描述" not in result, "示例应被真实结构替换"
    assert "本次共有 2 张照片" in result


def test_batch_prompt_keeps_the_whole_prompt_when_the_example_is_not_json():
    prompt = "按构图打分\n请严格只输出 JSON，格式如下：\n这不是 JSON"

    result = vd._batch_prompt(prompt, ["1"])

    assert "按构图打分" in result
    assert "这不是 JSON" in result, "示例无法解析时不能把它丢掉"


def test_batch_prompt_without_the_marker_keeps_the_prompt():
    result = vd._batch_prompt("只输出 JSON", ["1", "2", "3"])

    assert "只输出 JSON" in result
    assert "本次共有 3 张照片" in result
    assert '"1"' in result and '"3"' in result


# --------------------------------------------------------------------------- #
# 结果校验
# --------------------------------------------------------------------------- #

def test_validate_visual_result_rejects_a_non_object():
    with pytest.raises(vd.VisualDescriptionFormatError):
        vd._validate_visual_result("一段文字")


def test_validate_visual_result_rejects_a_missing_field():
    broken = dict(VALID_RESULT)
    broken.pop("narrative")

    with pytest.raises(vd.VisualDescriptionFormatError) as error:
        vd._validate_visual_result(broken)

    assert "narrative" in str(error.value)


def test_validate_visual_result_rejects_a_score_out_of_range():
    broken = dict(VALID_RESULT, beauty_score=120)

    with pytest.raises(vd.VisualDescriptionFormatError):
        vd._validate_visual_result(broken)


def test_validate_visual_result_accepts_a_complete_result():
    assert vd._validate_visual_result(dict(VALID_RESULT)) == VALID_RESULT


def test_parse_visual_result_rejects_empty_content():
    with pytest.raises(vd.VisualDescriptionFormatError):
        vd.parse_visual_result("   ")


def test_parse_visual_result_accepts_a_fenced_json_block():
    content = "```json\n" + json.dumps(VALID_RESULT, ensure_ascii=False) + "\n```"

    assert vd.parse_visual_result(content)["description"] == VALID_RESULT["description"]


def test_parse_visual_result_accepts_a_prose_wrapper():
    content = "好的，这是结果：\n" + json.dumps(VALID_RESULT, ensure_ascii=False)

    assert vd.parse_visual_result(content)["tags"] == VALID_RESULT["tags"]


# --------------------------------------------------------------------------- #
# _task_photo 的三条跳过分支
# --------------------------------------------------------------------------- #

def _db_for(photo=None, description=None):
    db = MagicMock()

    def _query(model):
        if model is vd.Photo:
            query = MagicMock()
            query.filter.return_value = query
            query.first.return_value = photo
            return query
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = description
        return query

    db.query.side_effect = _query
    return db


def _task(payload=None, owner_id="owner-1", photo_id="photo-1"):
    return SimpleNamespace(id="task-1", owner_id=owner_id, payload=payload if payload is not None else {"photo_id": "photo-1"})


def test_task_photo_skips_when_the_photo_does_not_exist():
    db = _db_for(photo=None)

    photo, skipped = vd.VisualDescriptionStrategy()._task_photo(_task(), db)

    assert photo is None
    assert skipped == {"status": "skipped", "reason": "photo not found"}


def test_task_photo_skips_when_only_if_missing_and_a_description_exists():
    existing = SimpleNamespace(id="desc-1")
    db = _db_for(photo=SimpleNamespace(id="photo-1"), description=existing)

    photo, skipped = vd.VisualDescriptionStrategy()._task_photo(
        _task({"photo_id": "photo-1", "only_if_missing": True}), db)

    assert photo is None
    assert skipped == {"status": "skipped", "reason": "already processed"}


def test_task_photo_skips_when_the_photo_was_already_processed():
    photo = SimpleNamespace(id="photo-1", processed_tasks={"visual_description": True})
    db = _db_for(photo=photo, description=None)

    photo, skipped = vd.VisualDescriptionStrategy()._task_photo(
        _task({"photo_id": "photo-1"}), db)

    assert photo is None
    assert skipped == {"status": "skipped", "reason": "already processed"}


def test_task_photo_returns_the_photo_when_force_is_set():
    photo = SimpleNamespace(id="photo-1", processed_tasks={"visual_description": True})
    db = _db_for(photo=photo, description=None)

    found, skipped = vd.VisualDescriptionStrategy()._task_photo(
        _task({"photo_id": "photo-1", "force": True}), db)

    assert found is photo
    assert skipped is None


# --------------------------------------------------------------------------- #
# _save_result 的三条分支
# --------------------------------------------------------------------------- #

def _save_db(photo=None, existing=None):
    db = MagicMock()

    def _query(model):
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = photo if model is vd.Photo else existing
        return query

    db.query.side_effect = _query
    return db


def test_save_result_skips_when_the_photo_no_longer_exists():
    db = _save_db(photo=None)

    result = vd.VisualDescriptionStrategy()._save_result(db, "photo-1", dict(VALID_RESULT))

    assert result == {"status": "skipped", "reason": "photo not found"}
    assert db.rollback.called


def test_save_result_skips_when_only_if_missing_and_a_description_exists():
    photo = SimpleNamespace(id="photo-1", processed_tasks={})
    existing = SimpleNamespace(id="desc-1", description="旧描述")
    db = _save_db(photo=photo, existing=existing)

    result = vd.VisualDescriptionStrategy()._save_result(
        db, "photo-1", dict(VALID_RESULT), {"only_if_missing": True})

    assert result == {"status": "skipped", "reason": "already processed"}
    assert db.rollback.called


def test_save_result_skips_when_the_task_was_already_processed():
    photo = SimpleNamespace(id="photo-1", processed_tasks={"visual_description": True})
    db = _save_db(photo=photo, existing=None)

    result = vd.VisualDescriptionStrategy()._save_result(
        db, "photo-1", dict(VALID_RESULT), {"photo_id": "photo-1"})

    assert result == {"status": "skipped", "reason": "already processed"}


def test_save_result_stores_the_description_and_marks_the_task():
    photo = SimpleNamespace(id="photo-1", processed_tasks={})
    db = _save_db(photo=photo, existing=None)

    result = vd.VisualDescriptionStrategy()._save_result(
        db, "photo-1", dict(VALID_RESULT), {"photo_id": "photo-1", "force": True})

    assert result["status"] == "completed"
    assert result["description"] == VALID_RESULT["description"]
    assert photo.processed_tasks["visual_description"] is True
    assert db.commit.called
