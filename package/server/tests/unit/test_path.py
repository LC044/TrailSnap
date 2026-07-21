"""Unit tests for folder / relative-path utilities (Issue #78 folder management)."""

import os

import pytest

from app.utils.path import compute_relative_path, compute_browse_path

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def test_compute_relative_path_longest_root_wins(tmp_path):
    """A file under a nested root is attributed to the deeper root, not the parent.

    Reproduces the bug that motivated ``get_user_roots`` returning roots sorted by
    descending length: a shallow parent root must not shadow a deeper child root.
    """
    shallow_root = tmp_path / "mnt" / "nas"
    deep_root = shallow_root / "scans" / "travel"
    deep_root.mkdir(parents=True)

    # Normalize both roots and the file path the same way ``_normalize`` does.
    shallow = os.path.abspath(str(shallow_root)).replace("\\", "/")
    deep = os.path.abspath(str(deep_root)).replace("\\", "/")
    file_path = (deep + "/landmarks/IMG_001.jpg").replace("\\", "/")

    # Caller is expected to pass roots sorted longest-first (see ``get_user_roots``).
    roots = sorted([shallow, deep], key=len, reverse=True)

    folder, filename = compute_relative_path(file_path, roots)

    assert filename == "IMG_001.jpg"
    # Attributed to the deep root, so the "scans/travel" prefix is stripped.
    assert folder == "landmarks"


def test_compute_relative_path_falls_back_when_outside_roots(tmp_path):
    """A file that does not match any root falls back to its parent's basename.

    Without a matching root, returning the full path would leak absolute storage
    details into the API; the fallback keeps the response uniform.
    """
    on_disk_root = tmp_path / "mnt" / "nas"
    on_disk_root.mkdir(parents=True)
    elsewhere = tmp_path / "external" / "photos" / "vacation"
    elsewhere.mkdir(parents=True)

    roots = [os.path.abspath(str(on_disk_root)).replace("\\", "/")]
    file_path = os.path.abspath(str(elsewhere / "IMG_002.jpg")).replace("\\", "/")

    folder, filename = compute_relative_path(file_path, roots)

    assert filename == "IMG_002.jpg"
    # Fallback uses the parent directory's basename, not an absolute path.
    assert folder == "vacation"


def test_empty_file_path_returns_empty_strings():
    """Both helpers short-circuit empty input so downstream code never sees a None."""
    assert compute_relative_path("", ["/mnt/nas"]) == ("", "")
    assert compute_browse_path("", ["/mnt/nas"]) == ("", "")
