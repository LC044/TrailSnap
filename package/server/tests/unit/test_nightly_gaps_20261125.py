"""Nightly watch 2026-11-25: cover remaining blind spots.

Targets (measured gaps from the 2026-11-25 coverage pass):
- ``app/service/tasks/visual_description.py``: the JSON-repair loop
  (``parse_visual_result_with_repair``) had no coverage at all.
- ``app/service/cleanup_index.py``: the on-disk manifest bootstrap
  (``file_lock`` / ``CleanupIndex.__enter__`` / ``_initialize_cache``) and the
  empty-cache lookups (``vector`` / ``shards``) were never exercised.

These are pure/offline units: no database, no network, no service process.
"""
import json

import pytest

from app.service.cleanup_index import CleanupIndex, file_lock
from app.service.tasks.visual_description import (
    VISUAL_JSON_REPAIR_ATTEMPTS,
    VisualDescriptionFormatError,
    _response_content_to_text,
    parse_visual_result_with_repair,
)

VALID_PAYLOAD = {
    "description": "海边的日落",
    "tags": ["海边", "日落"],
    "memory_score": 88,
    "beauty_score": 91,
    "reason": "光线与构图都很出色",
    "narrative": "那天在海边等到了日落。",
}


class _Response:
    def __init__(self, content):
        self.content = content


class _FakeClient:
    """Minimal stand-in for a LangChain chat client."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        reply = self._replies.pop(0) if self._replies else "not a json"
        return _Response(reply)


# --------------------------------------------------------------------------
# app/service/tasks/visual_description.py
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_visual_repair_returns_valid_payload_without_calling_the_model():
    client = _FakeClient([])

    result = await parse_visual_result_with_repair(client, json.dumps(VALID_PAYLOAD), "photo-1")

    assert result == VALID_PAYLOAD
    assert client.calls == []


@pytest.mark.asyncio
async def test_visual_repair_asks_the_model_once_and_accepts_the_fixed_json():
    client = _FakeClient([json.dumps(VALID_PAYLOAD)])

    result = await parse_visual_result_with_repair(client, "这不是 JSON", "photo-2")

    assert result == VALID_PAYLOAD
    assert len(client.calls) == 1
    system_prompt = client.calls[0][0]["content"]
    user_prompt = client.calls[0][-1]["content"]
    assert "JSON 格式修复器" in system_prompt
    assert "这不是 JSON" in user_prompt  # the raw model output is handed back to the repairer


@pytest.mark.asyncio
async def test_visual_repair_gives_up_after_the_configured_attempts():
    client = _FakeClient(["still broken"] * (VISUAL_JSON_REPAIR_ATTEMPTS + 1))

    with pytest.raises(VisualDescriptionFormatError):
        await parse_visual_result_with_repair(client, "broken", "photo-3")

    assert len(client.calls) == VISUAL_JSON_REPAIR_ATTEMPTS


@pytest.mark.asyncio
async def test_visual_repair_keeps_the_last_error_as_the_cause():
    client = _FakeClient(["{}"] * (VISUAL_JSON_REPAIR_ATTEMPTS + 1))

    with pytest.raises(VisualDescriptionFormatError) as excinfo:
        await parse_visual_result_with_repair(client, "{}", "photo-4")

    assert "缺少字段" in str(excinfo.value)


def test_response_content_to_text_normalizes_every_common_shape():
    assert _response_content_to_text("plain") == "plain"
    assert _response_content_to_text(["a", {"text": "b"}]) == "ab"
    assert _response_content_to_text({"text": "ignored"}) == "{'text': 'ignored'}"
    assert _response_content_to_text(None) == ""


# --------------------------------------------------------------------------
# app/service/cleanup_index.py
# --------------------------------------------------------------------------

class _FakeURL:
    def render_as_string(self, hide_password=False):
        return "sqlite:///:memory:"


class _FakeBind:
    url = _FakeURL()


class _FakeDB:
    def get_bind(self):
        return _FakeBind()


def test_file_lock_creates_the_lock_file(tmp_path):
    lock_path = tmp_path / "lock"

    with file_lock(lock_path):
        assert lock_path.exists()

    assert lock_path.read_bytes()[:1] == b"0"


def test_cleanup_index_bootstraps_its_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("TS_CLEANUP_CACHE_DIR", str(tmp_path / "cache"))

    index = CleanupIndex(_FakeDB(), "owner-1", "model-a")

    assert index.root.exists()
    with index as opened:
        tables = {
            row[0]
            for row in opened.cache.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"vectors", "dirty"} <= tables
        columns = {row[1] for row in opened.cache.execute("PRAGMA table_info(vectors)")}
        assert "revision" in columns
        # An empty manifest has no shard and no vector to serve.
        assert opened.shards() == []
        assert opened.vector("missing-photo") is None


def test_cleanup_index_adds_the_revision_column_to_a_legacy_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("TS_CLEANUP_CACHE_DIR", str(tmp_path / "cache"))
    index = CleanupIndex(_FakeDB(), "owner-1", "model-a")

    with index as opened:
        opened.cache.execute("DROP INDEX IF EXISTS vectors_photo_revision")
        opened.cache.execute("ALTER TABLE vectors DROP COLUMN revision")
        opened.cache.commit()
        columns = {row[1] for row in opened.cache.execute("PRAGMA table_info(vectors)")}
        assert "revision" not in columns

    # Re-entering recreates the manifest and re-adds the missing column.
    with index as reopened:
        columns = {row[1] for row in reopened.cache.execute("PRAGMA table_info(vectors)")}
        assert "revision" in columns

