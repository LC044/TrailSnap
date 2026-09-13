"""2026-09-13 round-3 nightly tests for current high-priority gaps.

Targets selected from the latest Cobertura scan after round 2:

* ``app.api.photo`` -- root-level direct folder filtering.
* ``app.service.tasks.scan`` -- existing-file and live-photo companion logic.
* ``app.core.system_config`` -- concurrency resolution and schedule cron forms.
* ``app.service.mcp_server`` -- endpoint URL and transport-security selection.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

import app.crud.photo
from app.api import photo as photo_api
from app.core import system_config
from app.db.models.photo import FileType
from app.service import mcp_server
from app.service.tasks import scan as scan_task


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# app/api/photo.py
# ---------------------------------------------------------------------------


def test_read_all_photos_resolves_roots_for_blank_direct_folder():
    db, user = MagicMock(), SimpleNamespace(id=uuid4())
    roots = [r"C:\Photos", r"D:\Travel"]
    rows = [SimpleNamespace(id=uuid4())]

    with (
        patch.object(app.crud.photo, "get_all_photos", return_value=rows) as crud_call,
        patch("app.utils.path.get_user_roots", return_value=roots) as get_user_roots,
    ):
        result = photo_api.read_all_photos(
            folder="",
            folder_direct=True,
            db=db,
            current_user=user,
        )

    assert result is rows
    get_user_roots.assert_called_once_with(user.id, db)
    kwargs = crud_call.call_args.kwargs
    assert kwargs["folder"] == ""
    assert kwargs["folder_direct"] is True
    assert kwargs["folder_roots"] == roots
    assert kwargs["user_id"] == user.id


# ---------------------------------------------------------------------------
# app/service/tasks/scan.py
# ---------------------------------------------------------------------------


def _existing_files_db(rows):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = rows
    return db


def _patch_photo_columns():
    return patch.object(
        scan_task,
        "Photo",
        SimpleNamespace(file_path="file_path", file_type="file_type", owner_id="owner_id"),
    )


def test_get_existing_files_filters_photos_outside_requested_roots(tmp_path: Path):
    root, outside = tmp_path / "Photos", tmp_path / "Other"
    inside_a, inside_b, outside_file = (
        str(root / "a.jpg"),
        str(root / "nested" / "b.png"),
        str(outside / "c.jpg"),
    )
    db = _existing_files_db([
        (inside_a, FileType.image),
        (outside_file, FileType.image),
        (inside_b, FileType.image),
    ])

    with _patch_photo_columns():
        existing, live = scan_task.ScanFolderStrategy()._get_existing_files(
            db, "user-1", [str(root)]
        )

    assert existing == {inside_a, inside_b}
    assert live == set()


def test_get_existing_files_builds_lowercase_live_photo_companion(tmp_path: Path):
    root = tmp_path / "Photos"
    image = str(root / "live.jpg")
    companion = str(root / "live.mp4")
    db = _existing_files_db([
        (image, FileType.live_photo),
        (image, FileType.image),
    ])

    with _patch_photo_columns():
        existing, live = scan_task.ScanFolderStrategy()._get_existing_files(
            db, "user-1", [str(root)]
        )

    assert image in existing
    assert companion in existing
    assert live == {image}


def test_get_existing_files_builds_uppercase_live_photo_companion(tmp_path: Path):
    root = tmp_path / "Photos"
    image = str(root / "live.HEIC")
    companion = str(root / "live.MOV")
    db = _existing_files_db([
        (image, FileType.live_photo),
        (image, FileType.image),
    ])

    with _patch_photo_columns():
        existing, live = scan_task.ScanFolderStrategy()._get_existing_files(
            db, "user-1", [str(root)]
        )

    assert image in existing
    assert companion in existing
    assert live == {image}


# ---------------------------------------------------------------------------
# app/core/system_config.py
# ---------------------------------------------------------------------------


def test_resolve_concurrency_level_maps_auto_and_keeps_explicit_choice(monkeypatch):
    monkeypatch.setattr(system_config, "get_default_concurrency_level", lambda: "high")

    assert system_config.resolve_concurrency_level("auto") == "high"
    assert system_config.resolve_concurrency_level("low") == "low"


def test_schedule_settings_render_interval_and_weekly_cron_expressions():
    scan = system_config.ScanScheduleSettings(mode="interval", interval=15)
    caption = system_config.MomentCaptionScheduleSettings(
        mode="weekly", weekdays=[0, 4], time="09:30"
    )
    memory = system_config.ProactiveMemoryScheduleSettings(
        mode="weekly", weekdays=[1, 3], time="08:15"
    )

    assert scan.to_cron_expression() == "*/15 * * * *"
    assert caption.to_cron_expression() == "30 9 * * 0,4"
    assert memory.to_cron_expression() == "15 8 * * 1,3"


def test_schedule_settings_return_none_for_invalid_time_or_unknown_mode():
    invalid_scan = system_config.ScanScheduleSettings(mode="weekly", time="not-a-time")
    invalid_caption = system_config.MomentCaptionScheduleSettings(
        mode="weekly", time="not-a-time"
    )
    invalid_memory = system_config.ProactiveMemoryScheduleSettings(
        mode="weekly", time="not-a-time"
    )
    unknown = system_config.ScanScheduleSettings(mode="daily")

    assert invalid_scan.to_cron_expression() is None
    assert invalid_caption.to_cron_expression() is None
    assert invalid_memory.to_cron_expression() is None
    assert unknown.to_cron_expression() is None


# ---------------------------------------------------------------------------
# app/service/mcp_server.py
# ---------------------------------------------------------------------------


def _clear_mcp_env(monkeypatch):
    for name in (
        "TRAILSNAP_MCP_URL",
        "TRAILSNAP_PUBLIC_URL",
        "TRAILSNAP_MCP_ALLOWED_HOSTS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_mcp_endpoint_urls_prefer_explicit_mcp_url(monkeypatch):
    _clear_mcp_env(monkeypatch)
    monkeypatch.setenv("TRAILSNAP_MCP_URL", "https://mcp.example.com/base/")

    assert mcp_server._endpoint_urls() == (
        "https://mcp.example.com",
        "https://mcp.example.com/base/",
    )


def test_mcp_endpoint_urls_derive_api_paths_from_public_url(monkeypatch):
    _clear_mcp_env(monkeypatch)
    monkeypatch.setenv("TRAILSNAP_PUBLIC_URL", "https://photos.example.com")

    assert mcp_server._endpoint_urls() == (
        "https://photos.example.com/api",
        "https://photos.example.com/api/mcp/",
    )


def test_mcp_transport_security_defaults_off_and_allows_public_host(monkeypatch):
    _clear_mcp_env(monkeypatch)
    assert mcp_server._transport_security() is None

    monkeypatch.setenv("TRAILSNAP_PUBLIC_URL", "https://photos.example.com")
    security = mcp_server._transport_security()

    assert security is not None
    assert "photos.example.com" in security.allowed_hosts
    assert "photos.example.com:*" in security.allowed_hosts
    assert security.allowed_origins == ["https://photos.example.com"]
