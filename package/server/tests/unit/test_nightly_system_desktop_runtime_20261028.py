"""2026-10-28 nightly coverage for ``app/api/system.py`` desktop runtime identity.

The 2026-10-28 backend coverage scan reported ``api/system.py`` at 85.4% with
35 uncovered lines.  The uncovered block is the ``/desktop/runtime`` identity
endpoint, which the desktop shell calls on every launch:

* it refuses every request unless ``TS_DESKTOP=1`` and the shared
  ``TS_DESKTOP_SESSION_SECRET`` matches (the 404 is deliberate: the endpoint
  must not advertise itself);
* it runs the optional media verification against the launch baseline and
  reports a structured failure;
* it samples a handful of photos to prove the library is actually readable.

The endpoint returning a 200 while the library is unreadable would make the
desktop shell start into a broken state, so every branch is asserted here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _system():
    from app.api import system

    return system


def _desktop_env(monkeypatch, secret="s3cret"):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", secret)


class _PhotoQuery:
    """Minimal stand-in for ``db.query(Photo).limit(8).all()``."""

    def __init__(self, photos):
        self._photos = photos

    def limit(self, _count):
        return self

    def all(self):
        return self._photos


class _Session:
    def __init__(self, photos):
        self._photos = photos
        self.entered = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *_exc):
        return False

    def query(self, _model):
        return _PhotoQuery(self._photos)


# ---------------------------------------------------------------------------
# _require_desktop_secret
# ---------------------------------------------------------------------------


def test_desktop_secret_is_required_when_the_desktop_flag_is_off(monkeypatch):
    system = _system()
    monkeypatch.setenv("TS_DESKTOP", "0")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", "s3cret")

    with pytest.raises(HTTPException) as excinfo:
        system._require_desktop_secret("s3cret")

    assert excinfo.value.status_code == 404


def test_desktop_secret_is_required_when_the_header_is_missing(monkeypatch):
    system = _system()
    _desktop_env(monkeypatch)

    with pytest.raises(HTTPException) as excinfo:
        system._require_desktop_secret(None)

    assert excinfo.value.status_code == 404


def test_desktop_secret_is_required_when_the_secret_does_not_match(monkeypatch):
    system = _system()
    _desktop_env(monkeypatch)

    with pytest.raises(HTTPException) as excinfo:
        system._require_desktop_secret("wrong")

    assert excinfo.value.status_code == 404


def test_desktop_secret_accepts_the_matching_secret(monkeypatch):
    system = _system()
    _desktop_env(monkeypatch)

    system._require_desktop_secret("s3cret")


# ---------------------------------------------------------------------------
# desktop_runtime_identity
# ---------------------------------------------------------------------------


def _prepare_library(tmp_path):
    """Create ``<root>/library.json`` plus the ``<root>/uploads`` data dir."""
    root = tmp_path / "library"
    data_dir = root / "uploads"
    data_dir.mkdir(parents=True)
    (root / "library.json").write_text(
        json.dumps({"libraryId": "lib-1", "pathFormat": 2}), encoding="utf-8"
    )
    return root, data_dir


def test_desktop_runtime_identity_reports_the_library_metadata_and_sample_count(monkeypatch, tmp_path):
    system = _system()
    root, data_dir = _prepare_library(tmp_path)
    sample = data_dir / "a.jpg"
    sample.write_bytes(b"x")

    _desktop_env(monkeypatch)
    monkeypatch.setenv("TS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TS_DESKTOP_START_NONCE", "nonce-1")

    photos = [SimpleNamespace(file_path=str(sample))]
    with patch("app.db.session.SessionLocal", return_value=_Session(photos)):
        response = system.desktop_runtime_identity(secret="s3cret")

    assert response.code == 0  # BaseResponse.success uses code 0
    assert response.data["libraryId"] == "lib-1"
    assert response.data["pathFormat"] == 2
    assert response.data["nonce"] == "nonce-1"
    assert response.data["verified"] is True
    assert response.data["sampleAvailable"] == 1


def test_desktop_runtime_identity_ignores_photos_outside_the_library_root(monkeypatch, tmp_path):
    system = _system()
    root, data_dir = _prepare_library(tmp_path)
    outside = tmp_path / "elsewhere.jpg"
    outside.write_bytes(b"x")

    _desktop_env(monkeypatch)
    monkeypatch.setenv("TS_DATA_DIR", str(data_dir))

    photos = [SimpleNamespace(file_path=str(outside))]
    with patch("app.db.session.SessionLocal", return_value=_Session(photos)):
        response = system.desktop_runtime_identity(secret="s3cret")

    assert response.data["sampleAvailable"] == 0


def test_desktop_runtime_identity_tolerates_a_missing_library_file(monkeypatch, tmp_path):
    system = _system()
    data_dir = tmp_path / "uploads"
    data_dir.mkdir()

    _desktop_env(monkeypatch)
    monkeypatch.setenv("TS_DATA_DIR", str(data_dir))

    with patch("app.db.session.SessionLocal", return_value=_Session([])):
        response = system.desktop_runtime_identity(secret="s3cret")

    assert response.data["libraryId"] is None
    assert response.data["pathFormat"] == 0


def test_desktop_runtime_identity_reports_a_failed_media_verification(monkeypatch, tmp_path):
    system = _system()
    root, data_dir = _prepare_library(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")
    instance_root = tmp_path / "instance"
    instance_root.mkdir()

    _desktop_env(monkeypatch)
    monkeypatch.setenv("TS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TS_DESKTOP_VERIFY", "1")
    monkeypatch.setenv("TS_UPDATE_BASELINE", str(baseline))
    monkeypatch.setenv("TS_INSTANCE_ROOT", str(instance_root))
    monkeypatch.setenv("TS_DESKTOP_START_NONCE", "nonce-2")

    with patch("app.utils.desktop_verification.verify_runtime_media", side_effect=ValueError("broken")):
        with patch("app.db.session.SessionLocal", return_value=_Session([])):
            response = system.desktop_runtime_identity(secret="s3cret")

    assert response.code == 500
    assert "broken" in response.msg

    report = instance_root / "maintenance" / "validation-error.json"
    assert report.is_file()
    assert json.loads(report.read_text(encoding="utf-8"))["error"] == "broken"


def test_desktop_runtime_identity_skips_verification_without_a_baseline(monkeypatch, tmp_path):
    system = _system()
    root, data_dir = _prepare_library(tmp_path)

    _desktop_env(monkeypatch)
    monkeypatch.setenv("TS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TS_DESKTOP_VERIFY", "1")
    monkeypatch.delenv("TS_UPDATE_BASELINE", raising=False)

    with patch("app.utils.desktop_verification.verify_runtime_media") as verify:
        with patch("app.db.session.SessionLocal", return_value=_Session([])):
            response = system.desktop_runtime_identity(secret="s3cret")

    verify.assert_not_called()
    assert response.code == 0  # BaseResponse.success uses code 0


# ---------------------------------------------------------------------------
# tianditu proxy delegation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proxy_server_tianditu_resource_delegates_with_the_map_token():
    system = _system()
    request = MagicMock()
    db = MagicMock()

    async def _fake(host, path, req, *, map_token=None, db=None):
        return {"host": host, "path": path, "map_token": map_token, "same_request": req is request}

    with patch.object(system, "_proxy_tianditu_resource", side_effect=_fake):
        result = await system.proxy_server_tianditu_resource("tok", "tile.example", "a/b.png", request, db)

    assert result == {
        "host": "tile.example",
        "path": "a/b.png",
        "map_token": "tok",
        "same_request": True,
    }


@pytest.mark.asyncio
async def test_proxy_tianditu_resource_keeps_the_legacy_signature():
    system = _system()
    request = MagicMock()

    async def _fake(host, path, req, *, map_token=None, db=None):
        return {"host": host, "path": path, "map_token": map_token}

    with patch.object(system, "_proxy_tianditu_resource", side_effect=_fake):
        result = await system.proxy_tianditu_resource("tile.example", "a/b.png", request)

    assert result == {"host": "tile.example", "path": "a/b.png", "map_token": None}

