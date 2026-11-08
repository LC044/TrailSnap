"""Nightly watch 2026-11-08 (round 3): storage-path / logging / intent gaps.

Targets uncovered branches reported by the 2026-11-08 coverage snapshot:

* ``app/service/storage_paths.py`` - portable-library path guards
* ``app/core/logger.py``          - daily rotating handler cleanup / error paths
* ``app/service/journey.py``      - discovery time-window guard
* ``app/service/agent/photo_search.py`` - intent classification payload shaping

Every test below exercises an already-implemented behaviour; no production
code is changed.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.logger import DailySizeRotatingFileHandler
from app.service import storage_paths
from app.service.agent.photo_search import classify_photo_intent
from app.service.journey import discover as discover_journey

pytestmark = [pytest.mark.smoke]


# --------------------------------------------------------------------------- #
# app/service/storage_paths.py
# --------------------------------------------------------------------------- #


def test_instance_root_requires_configured_library(monkeypatch):
    """A portable library without a configured root must fail loudly."""
    monkeypatch.delenv("TS_DESKTOP_ROOT", raising=False)

    with pytest.raises(ValueError, match="Portable library root is not configured"):
        storage_paths.instance_root()


def test_managed_root_that_escapes_the_library_is_rejected(tmp_path, monkeypatch):
    """A managed root must never resolve outside the portable library."""
    anchor = tmp_path / "library"
    anchor.mkdir()
    monkeypatch.setenv("TS_DESKTOP_ROOT", str(anchor))
    # Simulate a location that passed validation but resolves outside the anchor.
    monkeypatch.setattr(storage_paths, "validate_relative", lambda value, allow_dot=False: "../escape")

    root = {"id": str(uuid4()), "owner_id": "owner-1", "kind": "managed", "location": "photos"}
    with pytest.raises(ValueError, match="escapes the library"):
        storage_paths.root_path(root)


def test_external_root_must_be_absolute(tmp_path):
    """External roots are only accepted when they carry an absolute location."""
    root = {"id": str(uuid4()), "owner_id": "owner-1", "kind": "external", "location": "relative/dir"}

    with pytest.raises(ValueError, match="Invalid external storage root"):
        storage_paths.root_path(root)


def test_resolve_path_rejects_paths_leaving_the_root(tmp_path, monkeypatch):
    """A resolved path outside the root anchor is refused."""
    anchor = tmp_path / "external"
    anchor.mkdir()
    root = {"id": str(uuid4()), "owner_id": "owner-1", "kind": "external", "location": str(anchor)}
    storage_paths.cache_root(SimpleNamespace(id=root["id"], owner_id="owner-1",
                                             kind="external", location=str(anchor)))
    monkeypatch.setattr(storage_paths, "validate_relative", lambda value, allow_dot=False: "../outside.jpg")

    with pytest.raises(ValueError, match="escapes its root"):
        storage_paths.resolve_path("owner-1", root["id"], "photo.jpg")


def test_encode_path_only_considers_roots_of_the_same_owner(tmp_path, monkeypatch):
    """Another user's library is never used to encode a path."""
    mine = tmp_path / "mine"
    other = tmp_path / "other"
    mine.mkdir()
    other.mkdir()
    storage_paths.cache_root(SimpleNamespace(id=str(uuid4()), owner_id="owner-1",
                                             kind="external", location=str(mine)))
    storage_paths.cache_root(SimpleNamespace(id=str(uuid4()), owner_id="owner-2",
                                             kind="external", location=str(other)))

    encoded = storage_paths.encode_path("owner-1", str(other / "photo.jpg"))

    assert encoded is None
    assert storage_paths.encode_path("owner-1", str(mine / "photo.jpg")) is not None


def test_photo_without_owned_root_is_reported(tmp_path, monkeypatch):
    """A photo path outside every owned root must not be silently dropped."""
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_PORTABLE", "1")
    storage_paths._roots.clear()
    photo = SimpleNamespace(owner_id="owner-1", _file_path=str(tmp_path / "outside.jpg"),
                             storage_root_id=None, storage_relative_path=None)

    with pytest.raises(ValueError, match="no owned storage root"):
        storage_paths.apply_photo_reference(photo)


def test_register_user_roots_requires_an_existing_owner(tmp_path):
    """Registering roots for an unknown user is an explicit error."""
    db = SimpleNamespace(get=lambda model, key: None)

    with pytest.raises(ValueError, match="Storage owner does not exist"):
        storage_paths.register_user_roots(db, str(uuid4()))


# --------------------------------------------------------------------------- #
# app/core/logger.py
# --------------------------------------------------------------------------- #


def test_cleanup_removes_the_oldest_log_files(tmp_path):
    """Only the newest log files survive the global cleanup pass."""
    handler = DailySizeRotatingFileHandler("main", str(tmp_path), maxBytes=1024, backupCount=2)
    try:
        old = tmp_path / "old.log"
        middle = tmp_path / "middle.log"
        new = tmp_path / "new.log"
        for path in (old, middle, new):
            path.write_text("x", encoding="utf-8")
        now = time.time()
        os.utime(old, (now - 300, now - 300))
        os.utime(middle, (now - 200, now - 200))
        os.utime(new, (now - 100, now - 100))

        handler._cleanup_logs()

        assert not old.exists()
        assert not middle.exists()
        assert new.exists()
    finally:
        handler.close()


def test_cleanup_ignores_files_that_cannot_be_removed(tmp_path, monkeypatch):
    """A locked log file must not abort the cleanup pass."""
    handler = DailySizeRotatingFileHandler("main", str(tmp_path), maxBytes=1024, backupCount=0)
    try:
        locked = tmp_path / "locked.log"
        locked.write_text("x", encoding="utf-8")

        def boom(self, *args, **kwargs):
            raise OSError("file is locked")

        monkeypatch.setattr(Path, "unlink", boom)
        handler._cleanup_logs()
    finally:
        handler.close()


def test_cleanup_swallows_unexpected_errors(tmp_path, monkeypatch):
    """Cleanup failures never break logging."""
    handler = DailySizeRotatingFileHandler("main", str(tmp_path), maxBytes=1024, backupCount=1)
    try:
        class Boom:
            def glob(self, *_args, **_kwargs):
                raise RuntimeError("cannot list the log directory")

        handler.log_dir_path = Boom()
        handler._cleanup_logs()
    finally:
        handler.close()


def test_emit_failure_is_forwarded_to_handle_error(tmp_path, monkeypatch):
    """A broken stream is reported through the standard logging error hook."""
    handler = DailySizeRotatingFileHandler("main", str(tmp_path), maxBytes=1024, backupCount=1)
    try:
        seen = []
        monkeypatch.setattr(handler, "handleError", lambda record: seen.append(record))
        monkeypatch.setattr(logging.handlers.RotatingFileHandler, "emit",
                            lambda self, record: (_ for _ in ()).throw(RuntimeError("broken stream")))

        handler.emit(logging.LogRecord("test", logging.INFO, __file__, 1, "msg", None, None))

        assert len(seen) == 1
    finally:
        handler.close()


# --------------------------------------------------------------------------- #
# app/service/journey.py
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("before_hours,after_hours", [(0, 24), (24, 0), (200, 24), (24, 200)])
def test_discovery_rejects_windows_outside_one_to_168_hours(before_hours, after_hours):
    """The discovery window is limited to 1..168 hours on both sides."""
    with pytest.raises(ValueError, match="1 至 168 小时"):
        discover_journey(None, uuid4(), before_hours=before_hours, after_hours=after_hours)


# --------------------------------------------------------------------------- #
# app/service/agent/photo_search.py
# --------------------------------------------------------------------------- #


def test_intent_classification_keeps_only_user_and_assistant_turns():
    """System/tool turns never enter the classifier context."""

    class StubLLM:
        def __init__(self):
            self.messages = None

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content="find")

    class Message:
        def __init__(self, type_, content):
            self.type = type_
            self.content = content

    llm = StubLLM()
    intent = classify_photo_intent(
        llm,
        "找去年西安的合照",
        history=[Message("human", "问题"), Message("system", "指令"), Message("ai", "回答")],
    )

    assert intent == "find"
    payload = llm.messages[-1].content
    assert "问题" in payload
    assert "回答" in payload
    assert "指令" not in payload


def test_intent_classification_joins_structured_model_content():
    """A list-shaped model response is flattened before the intent is read."""

    class StubLLM:
        def invoke(self, _messages):
            return SimpleNamespace(content=[
                {"type": "text", "text": "<think>reasoning</think>"},
                {"type": "text", "text": "use"},
            ])

    assert classify_photo_intent(StubLLM(), "把照片整理成相册") == "use"


def test_intent_classification_falls_back_to_other_for_unknown_answers():
    """An unexpected answer never selects a workflow."""

    class StubLLM:
        def invoke(self, _messages):
            return SimpleNamespace(content="maybe")

    assert classify_photo_intent(StubLLM(), "你好") == "other"
