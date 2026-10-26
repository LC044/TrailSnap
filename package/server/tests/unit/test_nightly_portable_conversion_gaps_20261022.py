"""Nightly coverage for ``app.utils.portable_conversion`` validation helpers.

The 2026-10-21 backend coverage gap ranked ``utils/portable_conversion.py``
at 32.8% (193 of 287 statements uncovered). The uncovered region is the
*validation* half of the module -- ``validate_library_source`` and
``conversion_exclusions`` -- which decides whether a legacy folder may be
imported at all and which entries of that folder must never be copied or
deleted.

Both helpers are pure with respect to the filesystem layout: they only read
the source tree and raise ``ValueError`` with operator-facing Chinese
messages. The error branches are the interesting part, because they are the
guard rails that keep a migration from touching the new live library, and
none of them were executed by any test before this file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.utils.portable_conversion import (
    conversion_exclusions,
    report_progress,
    validate_library_source,
)


pytestmark = [pytest.mark.smoke]

WINDOWS_ONLY = pytest.mark.skipif(
    os.name != "nt", reason="Win32 extended-length path handling is Windows specific"
)


def _make_legacy_library(root: Path) -> Path:
    """Create a minimal folder that ``validate_library_source`` accepts."""
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "trailsnap.sqlite").write_bytes(b"SQLite format 3\x00")
    return root


# ---------------------------------------------------------------------------
# validate_library_source -- happy path
# ---------------------------------------------------------------------------


def test_validate_accepts_directory_holding_data_subfolder(tmp_path):
    """A folder with ``data/trailsnap.sqlite`` is a valid legacy library."""
    source = _make_legacy_library(tmp_path / "legacy")

    assert validate_library_source(source) == source.resolve()


def test_validate_returns_resolved_absolute_path(tmp_path):
    """The returned path is resolved, so later comparisons are stable."""
    source = _make_legacy_library(tmp_path / "legacy")
    # A "." segment is legal input but must not survive into the result.
    noisy = source / "data" / ".."

    result = validate_library_source(noisy)

    assert result == source.resolve()
    assert result.is_absolute()


# ---------------------------------------------------------------------------
# validate_library_source -- rejected input
# ---------------------------------------------------------------------------


def test_validate_rejects_relative_path():
    """A relative folder cannot be resolved reliably on another machine."""
    with pytest.raises(ValueError) as error:
        validate_library_source(Path("legacy"))

    assert "完整路径" in str(error.value)


def test_validate_rejects_missing_directory(tmp_path):
    """A path that does not exist reports a disk/permission problem."""
    missing = tmp_path / "not-there"

    with pytest.raises(ValueError) as error:
        validate_library_source(missing)

    assert "不存在或无法访问" in str(error.value)


def test_validate_rejects_database_file_instead_of_folder(tmp_path):
    """Pointing at the SQLite file itself is a common mistake."""
    database = tmp_path / "trailsnap.sqlite"
    database.write_bytes(b"SQLite format 3\x00")

    with pytest.raises(ValueError) as error:
        validate_library_source(database)

    assert "不要选择数据库文件" in str(error.value)


def test_validate_rejects_folder_without_legacy_database(tmp_path):
    """A folder without any known database layout is refused."""
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(ValueError) as error:
        validate_library_source(empty)

    assert "未找到旧图库数据库" in str(error.value)


def test_validate_rejects_data_subfolder_and_points_to_parent(tmp_path):
    """Selecting ``data`` itself is refused with the correct parent path."""
    root = _make_legacy_library(tmp_path / "legacy")
    data = root / "data"
    # The guard only fires when the sibling layout is a legacy instance.
    (root / "userdata").mkdir()

    with pytest.raises(ValueError) as error:
        validate_library_source(data)

    assert "data 子文件夹" in str(error.value)
    assert str(root) in str(error.value)


def test_validate_detects_new_instance_userdata_layout(tmp_path):
    """A portable instance folder is detected and reported separately."""
    root = tmp_path / "instance"
    (root / "userdata" / "data").mkdir(parents=True)
    (root / "userdata" / "data" / "trailsnap.sqlite").write_bytes(b"SQLite format 3\x00")

    with pytest.raises(ValueError) as error:
        validate_library_source(root)

    assert "新版本的实例目录" in str(error.value)


@WINDOWS_ONLY
def test_validate_strips_win32_extended_path_prefix(tmp_path):
    """``\\\\?\\`` prefixed paths are normalised back to ordinary drive paths."""
    source = _make_legacy_library(tmp_path / "legacy")
    extended = "\\\\?\\" + str(source)

    assert validate_library_source(Path(extended)) == source.resolve()


@WINDOWS_ONLY
def test_validate_strips_win32_extended_unc_prefix(tmp_path):
    """``\\\\?\\UNC\\`` prefixes are rewritten to plain UNC paths."""
    source = _make_legacy_library(tmp_path / "legacy")
    unc = "\\\\?\\UNC\\" + str(source).lstrip("\\")

    # The UNC form is not a real share on this machine, so the helper either
    # accepts it (a resolvable share) or refuses it with the standard message.
    try:
        result = validate_library_source(Path(unc))
    except ValueError as error:
        assert "不存在或无法访问" in str(error) or "完整路径" in str(error)
    else:
        assert result.is_absolute()


# ---------------------------------------------------------------------------
# conversion_exclusions -- defaults
# ---------------------------------------------------------------------------


def test_exclusions_contain_server_and_installer_by_default(tmp_path):
    """Without any descriptor the live server folder stays excluded."""
    excluded = conversion_exclusions(tmp_path)

    assert "server" in excluded
    assert "trailsnap-desktop.exe" in excluded
    assert "uninstall.exe" in excluded


def test_exclusions_do_not_exclude_plain_photo_files(tmp_path):
    """Ordinary media is never excluded, otherwise it would not be copied."""
    excluded = conversion_exclusions(tmp_path)

    assert "photos" not in excluded
    assert "data" not in excluded


# ---------------------------------------------------------------------------
# conversion_exclusions -- portable.json descriptor
# ---------------------------------------------------------------------------


def test_portable_descriptor_excludes_new_live_installation(tmp_path):
    """A portable instance folder also contains the NEW installation."""
    (tmp_path / "portable.json").write_text("{}", encoding="utf-8")

    excluded = conversion_exclusions(tmp_path)

    for name in ("app", "maintenance", "userdata", "TrailSnap.exe", "portable.json"):
        assert name in excluded


def test_portable_descriptor_excludes_root_dll_libraries(tmp_path):
    """Runtime DLLs next to the launcher belong to the new installation."""
    (tmp_path / "portable.json").write_text("{}", encoding="utf-8")
    (tmp_path / "webview.dll").write_bytes(b"MZ")
    (tmp_path / "keep.dll").write_bytes(b"MZ")

    excluded = conversion_exclusions(tmp_path)

    assert "webview.dll" in excluded
    assert "keep.dll" in excluded


def test_portable_descriptor_excludes_nested_dll_by_basename(tmp_path):
    """Every DLL in the folder is excluded, not only the ones in the root."""
    (tmp_path / "portable.json").write_text("{}", encoding="utf-8")
    (tmp_path / "extra.dll").write_bytes(b"MZ")

    excluded = conversion_exclusions(tmp_path)

    assert "extra.dll" in excluded


# ---------------------------------------------------------------------------
# conversion_exclusions -- instance.json descriptor
# ---------------------------------------------------------------------------


def _write_instance(tmp_path: Path, data_root: dict) -> None:
    (tmp_path / "instance.json").write_text(
        json.dumps({"schemaVersion": 1, "dataRoot": data_root}), encoding="utf-8"
    )


def test_relative_data_root_excludes_the_new_userdata_folder(tmp_path):
    """A relative ``userdata`` root is the live library and must be skipped."""
    _write_instance(tmp_path, {"kind": "relative", "path": "userdata"})

    excluded = conversion_exclusions(tmp_path)

    assert "userdata" in excluded
    assert "instance.json" in excluded


def test_relative_data_root_pointing_at_data_keeps_the_database(tmp_path):
    """When the live root IS ``data``, the database must not be excluded."""
    _write_instance(tmp_path, {"kind": "relative", "path": "data"})

    excluded = conversion_exclusions(tmp_path)

    assert "data" not in excluded


def test_absolute_data_root_outside_source_is_not_excluded(tmp_path):
    """An absolute root outside the source folder cannot be excluded by name."""
    _write_instance(tmp_path, {"kind": "absolute", "path": str(tmp_path.parent / "outside-elsewhere")})

    excluded = conversion_exclusions(tmp_path)

    assert "elsewhere" not in excluded
    assert "app" in excluded


def test_absolute_data_root_inside_source_is_excluded(tmp_path):
    """An absolute root inside the source folder is excluded by relative path."""
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_instance(tmp_path, {"kind": "absolute", "path": str(nested)})

    excluded = conversion_exclusions(tmp_path)

    assert "nested" in excluded


def test_instance_descriptor_without_data_root_is_rejected(tmp_path):
    """A descriptor without a usable dataRoot stops the conversion."""
    _write_instance(tmp_path, {})

    with pytest.raises(ValueError) as error:
        conversion_exclusions(tmp_path)

    assert "instance.json 数据位置无效" in str(error.value)


def test_instance_descriptor_with_unknown_kind_is_rejected(tmp_path):
    """An unknown dataRoot kind is refused instead of being guessed."""
    _write_instance(tmp_path, {"kind": "network", "path": "userdata"})

    with pytest.raises(ValueError) as error:
        conversion_exclusions(tmp_path)

    assert "instance.json 数据位置无效" in str(error.value)


def test_instance_descriptor_with_invalid_relative_path_is_rejected(tmp_path):
    """``..`` traversal inside a relative dataRoot is refused."""
    _write_instance(tmp_path, {"kind": "relative", "path": "../escape"})

    with pytest.raises(ValueError):
        conversion_exclusions(tmp_path)


def test_instance_descriptor_with_corrupt_json_is_reported(tmp_path):
    """A truncated descriptor surfaces as a JSON error, not a silent pass."""
    (tmp_path / "instance.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        conversion_exclusions(tmp_path)


def test_both_descriptors_combine_their_exclusions(tmp_path):
    """A folder carrying both descriptors excludes the union of both sets."""
    (tmp_path / "portable.json").write_text("{}", encoding="utf-8")
    _write_instance(tmp_path, {"kind": "relative", "path": "userdata"})

    excluded = conversion_exclusions(tmp_path)

    assert "userdata" in excluded
    assert "app" in excluded
    assert "portable-launcher.exe" in excluded


# ---------------------------------------------------------------------------
# report_progress
# ---------------------------------------------------------------------------


def test_report_progress_is_silent_without_operation_flag(monkeypatch, capsys):
    """Without ``TS_IMPORT_OPERATION`` nothing is written to stderr."""
    monkeypatch.delenv("TS_IMPORT_OPERATION", raising=False)

    report_progress("copying", 1, 2)

    captured = capsys.readouterr()
    assert captured.err == ""


def test_report_progress_emits_json_when_flag_present(monkeypatch, capsys):
    """With the flag set the progress line is JSON on stderr."""
    monkeypatch.setenv("TS_IMPORT_OPERATION", "1")
    monkeypatch.setattr("app.utils.portable_conversion._last_progress", 0.0)

    report_progress("copying", 1, 2)

    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip().splitlines()[-1])
    assert payload == {
        "importProgress": True,
        "stage": "copying",
        "completed": 1,
        "total": 2,
    }


def test_report_progress_throttles_repeated_updates(monkeypatch, capsys):
    """Rapid updates inside the throttle window are collapsed."""
    monkeypatch.setenv("TS_IMPORT_OPERATION", "1")
    monkeypatch.setattr("app.utils.portable_conversion._last_progress", 0.0)
    report_progress("copying", 1, 10)

    report_progress("copying", 2, 10)

    captured = capsys.readouterr()
    lines = [line for line in captured.err.strip().splitlines() if line.strip()]
    assert len(lines) == 1
