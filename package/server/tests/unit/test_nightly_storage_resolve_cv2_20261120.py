"""OpenCV resolution and its explicit override."""
import pytest

from app.service import storage

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_resolve_cv2_returns_the_pinned_module(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(storage, "cv2", sentinel, raising=False)
    assert storage._resolve_cv2() is sentinel


def test_resolve_cv2_returns_none_when_cv2_is_pinned_to_none(monkeypatch):
    monkeypatch.setattr(storage, "cv2", None, raising=False)
    assert storage._resolve_cv2() is None


def test_resolve_cv2_falls_back_to_the_loader(monkeypatch):
    monkeypatch.delattr(storage, "cv2", raising=False)
    monkeypatch.setattr(storage, "_load_cv2", lambda: "loaded")
    assert storage._resolve_cv2() == "loaded"
