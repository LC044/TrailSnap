"""Unit tests for the AI service config manager (app/services/ai_config_manager.py).

Covers task validation, model selection, persistence guard, and the
default-config fallback when the on-disk file is missing or corrupt.
"""

import json
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from app.services import ai_config_manager as acm_module
from app.services.ai_config_manager import AIConfigManager


pytestmark = [pytest.mark.smoke]


def _fresh_manager(tmp_path, config_data=None, file_exists=True):
    """Build a fresh AIConfigManager with ``_config`` seeded and no I/O."""
    mgr = AIConfigManager.__new__(AIConfigManager)
    mgr._initialized = True
    mgr.config_path = str(tmp_path / "ai_config.json")
    mgr._config = config_data if config_data is not None else {
        "models": {
            "ocr": {"selected": "mobile", "available": ["mobile", "server"]},
            "face": {"selected": "buffalo_l", "available": ["buffalo_l"]},
            "classification": {"selected": "clip-ViT-B-32", "available": ["clip-ViT-B-32"]},
        }
    }
    return mgr


# ----------------------- get_model_selection -----------------------


def test_get_model_selection_returns_current(tmp_path):
    mgr = _fresh_manager(tmp_path)
    assert mgr.get_model_selection("ocr") == "mobile"
    assert mgr.get_model_selection("face") == "buffalo_l"


def test_get_model_selection_returns_none_for_unknown_task(tmp_path):
    mgr = _fresh_manager(tmp_path)
    assert mgr.get_model_selection("nonexistent") is None


# ----------------------- set_model_selection: validation -----------------------


def test_set_model_selection_raises_for_unknown_task(tmp_path):
    mgr = _fresh_manager(tmp_path)
    with pytest.raises(ValueError, match="Unknown task"):
        mgr.set_model_selection("nonexistent", "x")


def test_set_model_selection_raises_for_unavailable_model(tmp_path):
    mgr = _fresh_manager(tmp_path)
    with pytest.raises(ValueError, match="Invalid model"):
        mgr.set_model_selection("ocr", "does-not-exist")


# ----------------------- set_model_selection: success / no-op -----------------------


def test_set_model_selection_returns_false_when_unchanged(tmp_path):
    """Same value → False and no save call."""
    mgr = _fresh_manager(tmp_path)
    with patch.object(mgr, "_save_config") as save:
        changed = mgr.set_model_selection("ocr", "mobile")

    assert changed is False
    save.assert_not_called()


def test_set_model_selection_persists_and_returns_true(tmp_path):
    """Different value → True and _save_config is invoked."""
    mgr = _fresh_manager(tmp_path)
    with patch.object(mgr, "_save_config") as save:
        changed = mgr.set_model_selection("ocr", "server")

    assert changed is True
    save.assert_called_once()
    assert mgr.get_model_selection("ocr") == "server"


# ----------------------- get_config -----------------------


def test_get_config_returns_full_dict(tmp_path):
    mgr = _fresh_manager(tmp_path)
    cfg = mgr.get_config()
    assert "models" in cfg
    assert set(cfg["models"].keys()) == {"ocr", "face", "classification"}


# ----------------------- _load_config default-fallback -----------------------


def test_load_config_uses_defaults_when_file_missing(tmp_path):
    """If the on-disk file does not exist, defaults are used and saved."""
    mgr = AIConfigManager.__new__(AIConfigManager)
    mgr._initialized = False
    mgr.config_path = str(tmp_path / "does_not_exist.json")

    with patch.object(acm_module.os.path, "exists", return_value=False), \
         patch.object(mgr, "_save_config") as save:
        mgr._load_config()

    save.assert_called_once()
    assert mgr._config["models"]["ocr"]["selected"] == "mobile"
    assert mgr._config["models"]["face"]["selected"] == "buffalo_l"


def test_load_config_merges_missing_keys_from_disk(tmp_path):
    """Disk config missing a task gets the default for that task merged in."""
    mgr = AIConfigManager.__new__(AIConfigManager)
    mgr._initialized = False
    mgr.config_path = str(tmp_path / "partial.json")

    partial = {"models": {"ocr": {"selected": "server", "available": ["server"]}}}

    with patch.object(acm_module.os.path, "exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(partial))):
        mgr._load_config()

    # Merged defaults should fill in face and classification.
    assert mgr._config["models"]["ocr"]["selected"] == "server"
    assert mgr._config["models"]["face"]["selected"] == "buffalo_l"
    assert mgr._config["models"]["classification"]["selected"] == "clip-ViT-B-32"
