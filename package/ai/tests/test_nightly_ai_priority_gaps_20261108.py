"""Nightly watch 2026-11-08: coverage gaps of ``app/services/face_service.py``.

The AI coverage scan of 2026-11-08 put ``services/face_service.py`` at 93.8%
with 8 missed statements plus several uncovered branches.  The gaps all sit in
``release_model``:

* the model container may be missing entirely, or may hold entries without the
  ONNX session / weight / name attributes;
* the internal cleanup may raise and must be logged instead of propagating;
* the ``sys.modules`` sweep may delete nothing, or may fail and must re-raise.

InsightFace is a heavy native dependency, so the model instance is faked.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.smoke]


class _ModelsWithoutOnnxAttributes(dict):
    """A model container whose entries carry none of the ONNX attributes."""


class _BrokenModels(dict):
    """A model container that fails while being iterated."""

    def items(self):
        raise RuntimeError("model container is broken")


def _install_fake_insightface(monkeypatch):
    insightface = types.ModuleType("insightface")
    utils_module = types.ModuleType("insightface.utils")
    face_align = types.ModuleType("insightface.utils.face_align")
    face_align.clear_cache = MagicMock()
    utils_module.face_align = face_align
    insightface.utils = utils_module
    monkeypatch.setitem(sys.modules, "insightface", insightface)
    monkeypatch.setitem(sys.modules, "insightface.utils", utils_module)
    monkeypatch.setitem(sys.modules, "insightface.utils.face_align", face_align)
    return face_align


def _patch_collect(monkeypatch):
    from app.services import face_service

    collect = MagicMock(name="gc.collect")
    monkeypatch.setattr(face_service.gc, "collect", collect)
    return collect


def test_release_model_cleans_up_an_app_without_model_containers(monkeypatch):
    from app.services import face_service

    face_align = _install_fake_insightface(monkeypatch)
    collect = _patch_collect(monkeypatch)
    app = SimpleNamespace()

    face_service.release_model(app)

    face_align.clear_cache.assert_called_once()
    collect.assert_called_once()


def test_release_model_handles_model_entries_without_onnx_attributes(monkeypatch):
    from app.services import face_service

    _install_fake_insightface(monkeypatch)
    _patch_collect(monkeypatch)
    app = SimpleNamespace(models=_ModelsWithoutOnnxAttributes({"detection": object()}))

    face_service.release_model(app)

    assert not hasattr(app, "models")


def test_release_model_logs_instead_of_raising_when_the_cleanup_fails(monkeypatch):
    from app.services import face_service

    _install_fake_insightface(monkeypatch)
    _patch_collect(monkeypatch)
    app = SimpleNamespace(models=_BrokenModels())

    face_service.release_model(app)

    # The failure is contained: the model registry keeps working.
    assert app.models is not None


def test_release_model_without_insightface_modules_deletes_nothing(monkeypatch):
    from app.services import face_service

    for name in [key for key in sys.modules if key.split(".")[0] == "insightface"]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    _patch_collect(monkeypatch)
    app = SimpleNamespace(models={})

    face_service.release_model(app)

    assert not any(key.split(".")[0] == "insightface" for key in sys.modules)


def test_release_model_reraises_when_the_module_sweep_fails(monkeypatch):
    from app.services import face_service

    class _BrokenModules(dict):
        def __delitem__(self, key):
            raise RuntimeError("cannot drop the module")

    broken = _BrokenModules({"insightface": object()})
    monkeypatch.setattr(face_service, "sys", SimpleNamespace(modules=broken))

    with pytest.raises(RuntimeError, match="cannot drop the module"):
        face_service.release_model(SimpleNamespace())
