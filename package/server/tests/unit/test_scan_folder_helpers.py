"""Unit tests for ``app/service/tasks/scan.py`` pure helpers.

Why this file exists:

* The nightly gap scan flagged ``service/tasks/scan.py`` as uncovered.
  The file owns two pure helpers (``_compile_folder_patterns``,
  ``_is_folder_excluded``) and the recursive scanner
  (``scan_directory_recursive``) that runs across every user folder
  on every scan.  A silent regression in any of them (e.g. dropping
  the ``@eaDir`` exclusion for Synology NAS) would either over-index
  thousands of system files or under-index user photos.

* The public ``ScanFolderStrategy.process`` is tightly coupled to
  SQLAlchemy + APScheduler + the worker process; we leave it to the
  integration layer and only cover the pure pieces here.

Coverage:

* ``_compile_folder_patterns`` -- compiles valid regexes, ignores
  invalid ones, drops empty strings.
* ``_is_folder_excluded`` -- returns True iff a name matches any
  compiled pattern; bypasses the loop when no patterns exist.
* ``scan_directory_recursive`` -- collects supported extensions,
  honours filename / min-size filters when ``enable=True``, and
  skips excluded sub-folders regardless of the filter flag.
"""

import os
import re
from pathlib import Path

import pytest

from app.service.tasks.scan import (
    _compile_folder_patterns,
    _is_folder_excluded,
    scan_directory_recursive,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ---------------------------------------------------------------------------
# _compile_folder_patterns
# ---------------------------------------------------------------------------


class TestCompileFolderPatterns:
    """``_compile_folder_patterns`` returns compiled regex objects for every
    valid entry; ``None`` / empty / invalid-regex entries are silently
    dropped so a single typo in the config does not crash the scanner.
    """

    def test_none_input_returns_empty_list(self):
        assert _compile_folder_patterns(None) == []

    def test_empty_list_returns_empty_list(self):
        assert _compile_folder_patterns([]) == []

    def test_empty_strings_are_skipped(self):
        # ``["", "@eaDir"]`` must drop the empty entry and keep the valid one.
        out = _compile_folder_patterns(["", "@eaDir"])
        assert len(out) == 1
        assert out[0].search("@eaDir") is not None

    def test_invalid_regex_is_silently_skipped(self):
        # ``[`` is an unfinished character class -> ``re.error``.
        out = _compile_folder_patterns(["[", "@eaDir"])
        assert len(out) == 1
        assert out[0].search("@eaDir") is not None

    def test_returns_compiled_objects(self):
        out = _compile_folder_patterns(["#recycle", "@eaDir"])
        assert all(isinstance(p, re.Pattern) for p in out)


# ---------------------------------------------------------------------------
# _is_folder_excluded
# ---------------------------------------------------------------------------


class TestIsFolderExcluded:
    """``_is_folder_excluded`` is the actual gate; the compile step only
    turns strings into patterns.  The contract is: when no patterns are
    configured (the default for fresh installs) every folder is allowed.
    """

    def test_no_patterns_means_nothing_excluded(self):
        assert _is_folder_excluded("@eaDir", []) is False

    def test_pattern_match_returns_true(self):
        pat = _compile_folder_patterns(["@eaDir"])
        assert _is_folder_excluded("@eaDir", pat) is True

    def test_partial_match_via_search_returns_true(self):
        # ``re.search`` semantics, not ``fullmatch`` -- ``@eaDir`` should
        # also exclude ``.recycle@eaDir.bak`` because the pattern appears
        # inside the name.  This guards against accidentally using
        # ``fullmatch`` during a future refactor.
        pat = _compile_folder_patterns(["@eaDir"])
        assert _is_folder_excluded(".recycle@eaDir.bak", pat) is True

    def test_non_match_returns_false(self):
        pat = _compile_folder_patterns(["@eaDir", "#recycle"])
        assert _is_folder_excluded("Photos", pat) is False


# ---------------------------------------------------------------------------
# scan_directory_recursive
# ---------------------------------------------------------------------------


@pytest.fixture
def photo_tree(tmp_path: Path) -> Path:
    """Build a temporary tree::

        root/
          IMG_0001.jpg
            sub/IMG_0002.png
            .@eaDir/   <- excluded
              junk.jpg
            Photos/IMG_0003.heic
        small.jpg         <- below min-size when configured
        README.txt        <- wrong extension
    """
    root = tmp_path
    (root / "IMG_0001.jpg").write_bytes(b"x" * 10)
    sub = root / "sub"
    sub.mkdir()
    (sub / "IMG_0002.png").write_bytes(b"x" * 10)
    excluded = sub / ".@eaDir"
    excluded.mkdir()
    (excluded / "junk.jpg").write_bytes(b"x" * 10)
    photos = root / "Photos"
    photos.mkdir()
    (photos / "IMG_0003.heic").write_bytes(b"x" * 10)
    (root / "small.jpg").write_bytes(b"x")
    (root / "README.txt").write_text("hi")
    return root


class TestScanDirectoryRecursive:
    """End-to-end of the helper using real ``tmp_path``.  We avoid mocks so
    a regression in ``os.scandir`` handling (e.g. dropping the
    ``is_dir`` branch) shows up immediately.
    """

    def test_collects_supported_extensions(self, photo_tree: Path):
        exts = {".jpg", ".png", ".heic"}
        found = scan_directory_recursive(str(photo_tree), exts)
        names = {os.path.basename(p) for p in found}
        assert "IMG_0001.jpg" in names
        assert "IMG_0002.png" in names
        assert "IMG_0003.heic" in names
        assert "README.txt" not in names

    def test_excluded_folders_are_pruned(self, photo_tree: Path):
        # ``.@eaDir`` is the Synology NAS metadata folder; it must never
        # appear in the result even though it contains a .jpg file.
        patterns = _compile_folder_patterns(["@eaDir"])
        found = scan_directory_recursive(
            str(photo_tree), {".jpg"}, exclude_folder_patterns=patterns
        )
        assert all("@eaDir" not in p for p in found)

    def test_min_size_filter_drops_small_files(self, photo_tree: Path):
        # 1-byte ``small.jpg`` must be dropped when the filter is enabled.
        found = scan_directory_recursive(
            str(photo_tree),
            {".jpg"},
            filter_settings={"enable": True, "min_size_kb": 1, "filename_patterns": []},
        )
        assert "small.jpg" not in {os.path.basename(p) for p in found}

    def test_filename_pattern_filter_drops_matching(self, photo_tree: Path):
        # Filter that matches IMG_0001.jpg must exclude only that file.
        found = scan_directory_recursive(
            str(photo_tree),
            {".jpg"},
            filter_settings={
                "enable": True,
                "filename_patterns": ["IMG_0001"],
                "min_size_kb": 0,
            },
        )
        names = {os.path.basename(p) for p in found}
        assert "IMG_0001.jpg" not in names
        assert "small.jpg" in names

    def test_filter_disabled_keeps_everything(self, photo_tree: Path):
        # ``enable=False`` means no filters applied; small.jpg stays.
        found = scan_directory_recursive(
            str(photo_tree),
            {".jpg"},
            filter_settings={"enable": False, "min_size_kb": 1, "filename_patterns": ["IMG_0001"]},
        )
        names = {os.path.basename(p) for p in found}
        assert "small.jpg" in names
        assert "IMG_0001.jpg" in names

    def test_missing_root_returns_empty_set(self, tmp_path: Path):
        # ``os.scandir`` raises ``OSError`` (FileNotFoundError) on a
        # non-existent root; the helper must swallow it and return ``set()``
        # rather than crashing the scan worker.
        missing = tmp_path / "does-not-exist"
        assert scan_directory_recursive(str(missing), {".jpg"}) == set()

    def test_invalid_filename_pattern_is_silently_ignored(self, photo_tree: Path):
        # A bad regex (``[``) in the filter list must not abort the scan;
        # valid patterns continue to apply.
        found = scan_directory_recursive(
            str(photo_tree),
            {".jpg"},
            filter_settings={
                "enable": True,
                "filename_patterns": ["[", "small"],
                "min_size_kb": 0,
            },
        )
        names = {os.path.basename(p) for p in found}
        assert "small.jpg" not in names
        assert "IMG_0001.jpg" in names
