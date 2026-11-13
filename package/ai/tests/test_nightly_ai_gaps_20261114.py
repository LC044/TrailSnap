"""Nightly watch 2026-11-14: coverage gaps for AI services.

Targets (from tests/artifacts/nightly/2026-11-14/cov-ai.log):

- app/services/unified_model_manager.py (5 missed lines: get_model_file success
  path, trigger_download status bookkeeping, delete_model pending-selection
  cleanup).
- app/services/ticket_parser.py: the remaining uncovered lines in the legacy
  datetime/seat pattern chain are *shadowed* by the earlier compact-pattern
  matcher (``parse_ticket_info`` line 1150) and by the neighbouring rules, so
  they cannot be reached from the public entry point.  The behaviour that
  actually wins is locked down here instead.

Every case is a pure unit test over synthetic OCR blocks / a temp catalog; no
model download and no network access is performed.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.services.ticket_parser import parse_ticket_info
from app.services.unified_model_manager import UnifiedModelManager


pytestmark = pytest.mark.smoke


def _blocks(*items):
    """Build (texts, polys) from (text, x, y) triples."""
    texts, polys = [], []
    for text, x, y in items:
        texts.append(text)
        polys.append([[x, y], [x + 60, y], [x + 60, y + 20], [x, y + 20]])
    return texts, polys


# ---------------------------------------------------------------------------
# ticket_parser -- effective behaviour of the shadowed pattern chain
# ---------------------------------------------------------------------------


def test_compact_datetime_pattern_wins_over_the_legacy_pattern_chain():
    """``parse_ticket_info`` resolves ``202404月07456:30`` through the compact
    matcher, not through the legacy ``(\\d{4})(\\d{2})月...`` chain.

    The legacy chain would read the three-digit hour group as ``56`` while the
    compact matcher reads the same digits as ``07`` + ``04``.  The compact
    matcher runs first, so the compact reading is the effective behaviour and
    the legacy branches below it are unreachable.
    """
    texts, polys = _blocks(("202404月07456:30开", 20, 100))

    info = parse_ticket_info(texts, polys)

    assert info["datetime"] == "2404年07月04日 56:30"


def test_station_names_are_resolved_from_the_geometry_of_the_ticket():
    """A ticket block that lists two stations resolves them left-to-right."""
    texts, polys = _blocks(("北京站 上海站", 20, 100))

    info = parse_ticket_info(texts, polys)

    assert info["departure_station"] == "北京"
    assert info["arrival_station"] == "上海"


# ---------------------------------------------------------------------------
# unified_model_manager
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path, monkeypatch):
    catalog = {
        "version": 1,
        "tasks": {
            "face": {"name": "Face", "default": "large", "runtimeKeys": ["face"]},
        },
        "models": [
            {
                "id": "large", "tasks": ["face"], "name": "Large", "runtimeName": "large",
                "repoId": "owner/large", "localDir": "large", "requiredFiles": ["model.onnx"],
                "available": True,
            },
            {
                "id": "small", "tasks": ["face"], "name": "Small", "runtimeName": "small",
                "repoId": "owner/small", "localDir": "small", "requiredFiles": ["model.onnx"],
                "available": True,
            },
        ],
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setenv("AI_MODEL_CATALOG_PATH", str(catalog_path))
    monkeypatch.setenv("AI_CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(
        "app.services.unified_model_manager.settings.MODEL_PATH",
        str(tmp_path / "models"),
    )
    return UnifiedModelManager()


def test_get_model_file_returns_path_inside_the_model_root(manager):
    model_dir = manager.get_model_dir("face", task=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.onnx").write_bytes(b"onnx")

    resolved = manager.get_model_file("face", "model.onnx")

    assert resolved == (model_dir / "model.onnx").resolve()
    assert resolved.is_file()


def test_get_model_file_rejects_paths_escaping_the_model_root(manager):
    with pytest.raises(ValueError):
        manager.get_model_file("face", "../../../etc/passwd")


def test_trigger_download_marks_the_model_as_downloading(manager):
    manager._errors["small"] = "previous failure"

    with patch("app.services.unified_model_manager.threading.Thread") as thread:
        manager.trigger_download("small")

    thread.assert_called_once()
    assert manager._status["small"] == "downloading"
    assert manager._errors["small"] is None


def test_trigger_download_is_a_no_op_while_a_download_is_running(manager):
    manager._status["small"] = "downloading"

    with patch("app.services.unified_model_manager.threading.Thread") as thread:
        manager.trigger_download("small")

    thread.assert_not_called()


def test_delete_model_clears_a_pending_selection_for_that_model(manager):
    with patch("app.services.unified_model_manager.threading.Thread"):
        manager.select_model("face", "small")

    assert manager._pending_selections["face"] == "small"
    manager._status.pop("small", None)

    manager.delete_model("small")

    assert "face" not in manager._pending_selections
