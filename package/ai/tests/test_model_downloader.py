"""Unit tests for ModelDownloader (app/services/model_downloader.py).

The downloader is a small but tricky piece of state: it spawns background
threads and uses a global singleton.  These tests construct a fresh
``ModelDownloader`` per case (no shared singleton) and exercise the public
state transitions synchronously by stubbing ``threading.Thread`` so the
worker body runs inline.
"""

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.model_downloader import ModelDownloader, ModelStatus


pytestmark = [pytest.mark.smoke]


class _SyncThread:
    """Drop-in replacement for ``threading.Thread`` that runs ``target`` inline.

    The production code passes ``(target, args, daemon)``.  We honour the
    same API so the real downloader doesn't notice the swap.
    """

    instances: list = []

    def __init__(self, target=None, args=(), daemon=None, **_):
        self._target = target
        self._args = args
        self.instances.append(self)

    def start(self):
        # Run inline on the caller; capture any exception so assertions
        # can distinguish "thread crashed" vs "thread succeeded".
        try:
            self._target(*self._args)
            self._error = None
        except Exception as exc:  # pragma: no cover - surfaced via get_status
            self._error = exc


@pytest.fixture
def downloader(tmp_path, monkeypatch):
    """Fresh ModelDownloader that writes into a tmp dir and runs threads inline."""
    monkeypatch.setattr("app.services.model_downloader.settings", type("S", (), {"MODEL_PATH": str(tmp_path)})())
    dl = ModelDownloader()
    monkeypatch.setattr(threading, "Thread", _SyncThread)
    _SyncThread.instances = []
    return dl


def test_register_initializes_pending_status(downloader):
    dl = downloader
    dl.register_model("foo", check_fn=lambda: False, download_fn=lambda: "/tmp/foo")

    assert dl.get_status("foo") == ModelStatus.PENDING
    assert dl.is_ready("foo") is False
    assert "foo" in dl.models


def test_start_downloads_marks_model_ready_when_check_fn_already_true(downloader):
    dl = downloader
    dl.register_model("foo", check_fn=lambda: True, download_fn=lambda: "/tmp/foo")
    dl.start_downloads()

    assert dl.is_ready("foo")
    assert len(_SyncThread.instances) == 1


def test_start_downloads_downloads_all_models_sequentially(downloader):
    calls = []
    downloader.register_model(
        "first", lambda: "first" in calls, lambda: calls.append("first") or "first"
    )
    downloader.register_model(
        "second", lambda: "second" in calls, lambda: calls.append("second") or "second"
    )

    downloader.start_downloads()

    assert calls == ["first", "second"]
    assert downloader.is_ready("first")
    assert downloader.is_ready("second")
    assert len(_SyncThread.instances) == 1


def test_download_worker_invokes_download_fn_and_records_ready(downloader):
    dl = downloader
    captured = {}

    def fake_download():
        captured["called"] = True
        return "/models/foo/weights.bin"

    dl.register_model("foo", check_fn=lambda: False, download_fn=fake_download)
    dl.trigger_download("foo")  # uses _SyncThread.start() inline

    assert captured["called"] is True
    assert dl.is_ready("foo")
    assert dl.get_status("foo") == ModelStatus.READY


def test_download_failure_records_status_and_error_message(downloader, tmp_path):
    dl = downloader
    cleanup = tmp_path / "cleanup-target"
    cleanup.mkdir()

    def boom():
        raise RuntimeError("network unreachable")

    dl.register_model(
        "foo",
        check_fn=lambda: False,
        download_fn=boom,
        cleanup_dir=str(cleanup),
    )
    dl.trigger_download("foo")

    status = dl.get_status("foo")
    assert status == ModelStatus.FAILED
    assert "network unreachable" in dl.models["foo"]["error"]
    # cleanup_dir should be removed after a failed download
    assert not cleanup.exists()


def test_reset_status_returns_to_pending_and_clears_error(downloader):
    dl = downloader
    dl.register_model("foo", check_fn=lambda: True, download_fn=lambda: "x")
    dl.start_downloads()  # becomes READY
    assert dl.is_ready("foo")

    dl.reset_status("foo")

    assert dl.get_status("foo") == ModelStatus.PENDING
    assert dl.models["foo"]["error"] is None


def test_wait_for_model_returns_true_when_already_ready(downloader):
    dl = downloader
    dl.register_model("foo", check_fn=lambda: True, download_fn=lambda: "x")
    dl.start_downloads()

    assert dl.wait_for_model("foo", timeout=1) is True


def test_wait_for_model_times_out_when_never_ready(downloader):
    dl = downloader
    dl.register_model("foo", check_fn=lambda: False, download_fn=lambda: "x")
    # Don't trigger any download — stays PENDING forever.

    # Patch the inner sleep to keep the test fast.
    with patch("time.sleep", lambda *_a, **_k: None):
        assert dl.wait_for_model("foo", timeout=0) is False


def test_get_status_returns_failed_for_unknown_key(downloader):
    assert downloader.get_status("never-registered") == ModelStatus.FAILED
    assert downloader.is_ready("never-registered") is False


def test_managed_model_can_be_listed_and_deleted(downloader, tmp_path):
    model_file = tmp_path / "managed.bin"
    model_file.write_bytes(b"model")

    downloader.register_model(
        "managed",
        check_fn=model_file.exists,
        download_fn=lambda: str(model_file),
        delete_fn=model_file.unlink,
        metadata={"name": "Managed model", "capabilities": ["ocr"]},
        managed=True,
    )

    listed = downloader.list_models(managed_only=True)
    assert listed == [{
        "id": "managed",
        "name": "Managed model",
        "capabilities": ["ocr"],
        "status": "ready",
        "error": None,
        "managed": True,
        "canDelete": True,
    }]

    downloader.delete_model("managed")
    assert not model_file.exists()
    assert downloader.get_status("managed") == ModelStatus.PENDING


def test_refresh_downgrades_ready_status_when_files_are_removed(downloader, tmp_path):
    model_file = tmp_path / "managed.bin"
    model_file.write_bytes(b"model")
    downloader.register_model("managed", model_file.exists, lambda: str(model_file))
    downloader.refresh_statuses()
    assert downloader.is_ready("managed")

    model_file.unlink()
    downloader.refresh_statuses()
    assert downloader.get_status("managed") == ModelStatus.PENDING
