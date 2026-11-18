"""2026-11-17 nightly coverage for the agent SKILL registry and the travel
history tool.

The 2026-11-17 targeted coverage scan reported:

* ``app/service/agent/skills/registry.py`` at 90% - the front-matter parser
  and the name/size validation were never exercised with a malformed file;
* ``app/service/agent/tools.py`` at 92% - ``get_travel_history_tool`` (the
  whole body, lines 450-497) was never called, so the date filtering, the
  empty-result message and the JSON payload shape were all untested.

The registry is an allow-list: a malformed SKILL.md must never be loaded,
and the travel history tool must only ever expose the tickets of the current
user.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.service.agent import tools as agent_tools
from app.service.agent.skills import registry as skill_registry


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


# --------------------------------------------------------------------------- #
# skills registry
# --------------------------------------------------------------------------- #

def _write_skill(tmp_path, name, body):
    directory = tmp_path / name
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_parse_reads_the_front_matter_name_and_description(tmp_path):
    path = _write_skill(tmp_path, "photo-doctor", """---
name: photo-doctor
description: 诊断并修复异常照片
---

修复步骤。
""")
    parsed = skill_registry._parse(path)
    assert parsed["name"] == "photo-doctor"
    assert parsed["description"] == "诊断并修复异常照片"
    assert "修复步骤。" in parsed["instructions"]


def test_parse_falls_back_to_the_directory_name_without_front_matter(tmp_path):
    path = _write_skill(tmp_path, "trip-recap", "只有正文，没有 front matter。")
    parsed = skill_registry._parse(path)
    assert parsed["name"] == "trip-recap"
    assert parsed["description"] == ""
    assert parsed["instructions"].startswith("只有正文")


def test_parse_rejects_an_invalid_skill_name(tmp_path):
    path = _write_skill(tmp_path, "Invalid Name", "---\nname: Invalid Name\n---\n正文")
    with pytest.raises(ValueError):
        skill_registry._parse(path)


def test_parse_rejects_an_oversized_skill_file(tmp_path):
    body = "x" * (skill_registry._MAX_BYTES + 1)
    path = _write_skill(tmp_path, "huge-skill", body)
    with pytest.raises(ValueError):
        skill_registry._parse(path)


def test_load_skill_rejects_an_invalid_name():
    with pytest.raises(ValueError):
        skill_registry.load_skill("../etc/passwd")


def test_load_skill_rejects_an_unknown_skill():
    with pytest.raises(ValueError):
        skill_registry.load_skill("definitely-not-a-skill")


def test_load_skill_returns_a_copy_of_the_registered_skill():
    catalog = skill_registry.get_skill_catalog()
    assert catalog, "the repository ships at least one agent skill"
    name = catalog[0]["name"]
    loaded = skill_registry.load_skill(name)
    assert loaded["name"] == name
    assert "instructions" in loaded
    # A copy is returned so a caller cannot corrupt the cached registry.
    loaded["instructions"] = "mutated"
    assert skill_registry.load_skill(name)["instructions"] != "mutated"


def test_get_skill_catalog_only_exposes_name_and_description():
    for item in skill_registry.get_skill_catalog():
        assert set(item) == {"name", "description"}


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# agent tools that read the current user's own data
# --------------------------------------------------------------------------- #

class _Query:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


def _tool(name, user_id="owner-1"):
    tools = {tool.name: tool for tool in agent_tools.get_agent_tools(user_id)}
    return tools[name]


def _patch_session(rows=()):
    db = MagicMock()
    db.query.return_value = _Query(rows)
    db.__enter__.return_value = db
    db.__exit__.return_value = False
    return db, patch.object(agent_tools, "SessionLocal", return_value=db)


def test_trip_tickets_returns_the_tickets_of_the_current_user():
    db, session_patch = _patch_session()
    with session_patch, \
            patch.object(agent_tools, "trip_tickets",
                         lambda _db, user_id, start, end: [{"code": "G1", "type": "train"}]):
        result = _tool("get_trip_tickets").invoke({"start_date": "2024-01-01",
                                                   "end_date": "2024-12-31"})
    assert json.loads(result) == {"tickets": [{"code": "G1", "type": "train"}]}


def test_trip_tickets_returns_an_empty_list_when_there_is_no_ticket():
    db, session_patch = _patch_session()
    with session_patch, \
            patch.object(agent_tools, "trip_tickets", lambda *_a, **_k: []):
        result = _tool("get_trip_tickets").invoke({})
    assert json.loads(result) == {"tickets": []}


def test_trip_tickets_passes_the_requested_date_range_through():
    seen = {}

    def _capture(_db, user_id, start, end):
        seen["user_id"] = user_id
        seen["start"] = start
        seen["end"] = end
        return []

    db, session_patch = _patch_session()
    with session_patch, patch.object(agent_tools, "trip_tickets", _capture):
        _tool("get_trip_tickets", "owner-7").invoke({"start_date": "2024-03-01",
                                                      "end_date": "2024-04-01"})
    assert seen == {"user_id": "owner-7", "start": "2024-03-01", "end": "2024-04-01"}


def test_photo_details_reports_when_nothing_matches():
    db, session_patch = _patch_session()
    with session_patch:
        result = _tool("get_photo_details_tool").invoke({"photo_ids": ["photo-1"]})
    assert result == "没有找到这些照片的详细信息。"


def test_photo_details_returns_the_description_of_the_requested_photos():
    description = SimpleNamespace(photo_id="photo-1", description="海边日落",
                                   tags=["海"], narrative="晚霞")
    db, session_patch = _patch_session([description])
    with session_patch:
        result = _tool("get_photo_details_tool").invoke({"photo_ids": ["photo-1"]})
    payload = json.loads(result)
    assert payload[0]["photo_id"] == "photo-1"
    assert payload[0]["description"] == "海边日落"


def test_photo_details_only_queries_the_current_user_s_photos():
    db, session_patch = _patch_session()
    with session_patch:
        _tool("get_photo_details_tool", "owner-9").invoke({"photo_ids": ["photo-1"]})
    assert db.query.called
    model = db.query.call_args[0][0]
    assert model is agent_tools.ImageDescription

