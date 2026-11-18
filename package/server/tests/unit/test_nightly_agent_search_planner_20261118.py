"""2026-11-18 nightly coverage for ``app/service/agent/search_planner.py``.

No test file referenced ``app/service/agent/search_planner.py``.  The planner
turns a model answer into a validated, owner-scoped search plan, so the two
pure helpers are the safety net of the whole feature:

* ``_parse_model_json`` copes with the many shapes a small model returns -
  a plain object, a list of content blocks, a fenced code block, a reasoning
  model that leaked ``<think>`` and a single-quoted literal;
* ``_clean_plan`` normalises what the model extracted: blank strings become
  ``None``, duplicated people are collapsed, a visual environment such as
  "海边" must not become a place filter, and a description that merely repeats
  the location must lose it.
"""

from __future__ import annotations

import pytest

from app.service.agent.search_planner import SearchPlan, _clean_plan, _parse_model_json


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def test_a_plain_json_object_is_parsed():
    assert _parse_model_json('{"location": "杭州"}') == {"location": "杭州"}


def test_a_list_of_content_blocks_is_joined():
    content = [
        {"type": "text", "text": '{"location":'},
        {"type": "text", "text": ' "杭州"}'},
        {"type": "tool_use", "text": "ignored"},
    ]

    assert _parse_model_json(content) == {"location": "杭州"}


def test_a_fenced_code_block_is_unwrapped():
    content = '```json\n{"location": "杭州"}\n```'

    assert _parse_model_json(content) == {"location": "杭州"}


def test_a_reasoning_model_answer_keeps_only_the_part_after_think():
    content = '<think>the user wants a city</think>{"location": "杭州"}'

    assert _parse_model_json(content) == {"location": "杭州"}


def test_a_single_quoted_literal_is_accepted():
    assert _parse_model_json("{'location': '杭州'}") == {"location": "杭州"}


def test_null_and_blank_fields_are_dropped():
    parsed = _parse_model_json('{"location": "杭州", "description": null, "ocr_text": "   "}')

    assert parsed == {"location": "杭州"}


def test_a_non_object_answer_is_rejected():
    with pytest.raises(ValueError):
        _parse_model_json("[1, 2, 3]")


def test_blank_text_fields_become_none():
    plan = _clean_plan(SearchPlan(location="  ", description=" 海边 ", ocr_text=" "))

    assert plan.location is None
    assert plan.description == "海边"
    assert plan.ocr_text is None


def test_duplicated_people_are_collapsed():
    plan = _clean_plan(SearchPlan(people=[" 小明 ", "小明", "小红"]))

    assert plan.people == ["小明", "小红"]


def test_a_visual_environment_becomes_a_description_instead_of_a_place():
    plan = _clean_plan(SearchPlan(location="海边"))

    assert plan.location is None
    assert plan.description == "海边"


def test_a_visual_environment_is_kept_only_once_in_the_description():
    plan = _clean_plan(SearchPlan(location="海边", description="海边日落"))

    assert plan.location is None
    assert plan.description == "海边日落"


def test_a_description_that_only_repeats_the_location_is_dropped():
    plan = _clean_plan(SearchPlan(location="杭州", description="杭州"))

    assert plan.description is None


def test_a_description_that_adds_information_keeps_the_extra_part():
    plan = _clean_plan(SearchPlan(location="杭州", description="杭州西湖"))

    assert plan.description == "西湖"
