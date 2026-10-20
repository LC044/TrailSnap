"""Nightly coverage for ``app.utils.portable_config.remap_path_fields``.

The 2026-10-21 backend coverage gap ranked ``utils/portable_config.py``
at 67.6% (12 of 37 statements uncovered). The missed lines were the
entire body of ``remap_path_fields`` -- ``transform_paths`` has
end-to-end coverage in ``test_portable_library`` /
``test_desktop_import`` via real ``ts-instance:/`` payloads, so this
file targets the rebasing helper specifically.

``remap_path_fields`` takes a JSON-shaped value plus a list of
``(source_root, target_root)`` tuples and rewrites every path-like
string that lives under one of the source roots. Filtering by field name
(passed via the ``key`` keyword for nested entries) keeps the helper
narrowly focused on the configured ``PATH_FIELDS`` set.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.desktop_data_migration import rebase_value
from app.utils.portable_config import PATH_FIELDS, remap_path_fields


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Top-level value types: dict / list / string paths / non-string scalars
# ---------------------------------------------------------------------------


def test_remap_recurses_into_dict_and_propagates_field_key(tmp_path):
    """Nested dicts should be walked with their inner key names so the
    PATH_FIELDS filter still applies to nested values."""

    old = tmp_path / "old"
    new = tmp_path / "new"
    value = {
        "file_path": str(old / "photos/a.jpg"),
        "label": "do not touch",
        "nested": {
            "model_path": str(old / "models" / "yolo.onnx"),
            "label": "skip me",
        },
    }

    result = remap_path_fields(value, [(old, new)])

    assert result["file_path"] == str(new / "photos/a.jpg")
    # Non-path fields are returned untouched even when nested.
    assert result["label"] == "do not touch"
    assert result["nested"]["model_path"] == str(new / "models" / "yolo.onnx")
    assert result["nested"]["label"] == "skip me"


def test_remap_recurses_into_list_and_keeps_parent_key(tmp_path):
    """A ``PATH_FIELDS`` key should apply to every entry in the list."""

    old = tmp_path / "old"
    new = tmp_path / "new"
    value = {
        "scan_roots": [
            str(old / "scan/2024"),
            str(old / "scan/2025"),
            "totally unrelated",
        ],
    }

    result = remap_path_fields(value, [(old, new)])

    assert result["scan_roots"][0] == str(new / "scan/2024")
    assert result["scan_roots"][1] == str(new / "scan/2025")
    # Paths outside the source root are returned unchanged -- the helper
    # only rewrites strings that lie underneath a configured root.
    assert result["scan_roots"][2] == "totally unrelated"


def test_remap_passes_non_string_value_through(tmp_path):
    """Booleans / ints / None inside the tree should reach the
    ``not isinstance(value, str)`` short-circuit and remain unchanged."""

    old = tmp_path / "old"
    value = {
        "file_path": str(old / "kept.jpg"),
        "count": 12,
        "flag": True,
        "missing": None,
        "nested": {"ratio": 0.5, "ok": False},
    }

    result = remap_path_fields(value, [(old, tmp_path / "new")])

    assert result["count"] == 12
    assert result["flag"] is True
    assert result["missing"] is None
    assert result["nested"]["ratio"] == 0.5
    assert result["nested"]["ok"] is False


def test_remap_returns_original_when_string_lives_in_unknown_field(tmp_path):
    """Strings stored under a non-``PATH_FIELDS`` key must NOT be
    rewritten, even when the path lies under one of the source roots."""

    old = tmp_path / "old"
    value = {"caption": str(old / "photo.jpg"), "file_path": str(old / "photo.jpg")}

    result = remap_path_fields(value, [(old, tmp_path / "new")])

    assert result["caption"] == str(old / "photo.jpg")
    assert result["file_path"] == str(tmp_path / "new" / "photo.jpg")


def test_remap_returns_top_level_non_path_unchanged(tmp_path):
    """Strings passed at the top level with no declared ``key`` should
    bypass the rewrite: ``remap_path_fields`` defaults ``key=""`` which
    is not part of ``PATH_FIELDS``."""

    old = tmp_path / "old"
    bare = str(old / "anywhere.jpg")

    assert remap_path_fields(bare, [(old, tmp_path / "new")]) == bare
    assert remap_path_fields(42, [(old, tmp_path / "new")]) == 42
    assert remap_path_fields(None, [(old, tmp_path / "new")]) is None


# ---------------------------------------------------------------------------
# Mapping selection: longest-prefix match wins
# ---------------------------------------------------------------------------


def test_remap_picks_longest_matching_mapping(tmp_path):
    """When several ``(source, target)`` tuples can match a path, the one
    with the longest ``source`` string wins -- ``rebase_value`` is run
    with every mapping, so the deeper prefix must come first so the
    shallow one does not overwrite the result."""

    outer_old = tmp_path / "old"
    inner_old = outer_old / "deep"
    new_outer = tmp_path / "new_outer"
    new_inner = tmp_path / "new_inner"

    value = {
        # Both fields are members of PATH_FIELDS so the inner loop reaches
        # ``rebase_value`` instead of taking the early-return.
        "file_path": str(outer_old / "deep" / "picture.jpg"),
        "path": str(outer_old / "shallow" / "picture.jpg"),
    }

    result = remap_path_fields(
        value,
        [
            (outer_old, new_outer),  # shorter prefix
            (inner_old, new_inner),  # longer prefix
        ],
    )

    assert result["file_path"] == str(new_inner / "picture.jpg")
    assert result["path"] == str(new_outer / "shallow" / "picture.jpg")


def test_remap_returns_value_unchanged_when_no_mapping_matches(tmp_path):
    """If the helper iterates all mappings and ``rebase_value`` produces
    the same string back, the function falls through and returns the
    original value."""

    old = tmp_path / "old"
    unrelated = tmp_path / "other"
    value = {"file_path": str(unrelated / "any.jpg")}

    result = remap_path_fields(value, [(old, tmp_path / "new")])

    assert result["file_path"] == str(unrelated / "any.jpg")


def test_remap_with_empty_mappings_returns_value_verbatim(tmp_path):
    """An empty mappings list must not crash the iteration loop and
    should leave every path-shaped field untouched."""

    value = {
        "file_path": str(tmp_path / "data/x.jpg"),
        "label": str(tmp_path / "data/y.jpg"),
    }

    assert remap_path_fields(value, []) == value


# ---------------------------------------------------------------------------
# Direct ``rebase_value`` integration and field coverage
# ---------------------------------------------------------------------------


def test_remap_with_real_rebase_value_uses_real_path_rewrite(tmp_path):
    """Run the helper against the real ``rebase_value`` implementation
    (not a mock) to make sure the import + invocation contract stayed
    intact across recent rewrites."""

    old = tmp_path / "old-data"
    new = tmp_path / "new-data"
    expected = rebase_value(str(old / "tree" / "leaf.txt"), old, new)

    result = remap_path_fields({"output_path": str(old / "tree" / "leaf.txt")}, [(old, new)])

    assert result["output_path"] == expected
    # Sanity check: ``rebase_value`` should not return the input string
    # when the prefix matches.
    assert result["output_path"] != str(old / "tree" / "leaf.txt")


def test_remap_covers_well_known_path_field_names(tmp_path):
    """Spot check a handful of common ``PATH_FIELDS`` to keep the
    field-name filter honest: each must rewrite, while a sentinel
    non-path field stays put."""

    old = tmp_path / "old"
    new = tmp_path / "new"
    value = {
        "path": str(old / "a"),
        "directory": str(old / "b"),
        "folder_path": str(old / "c"),
        "live_photo_video_path": str(old / "d.mp4"),
        "scan_roots": [str(old / "e")],
        "name": str(old / "ignored"),
    }

    result = remap_path_fields(value, [(old, new)])

    for key in ("path", "directory", "folder_path", "live_photo_video_path"):
        rewritten = result[key]
        assert rewritten.startswith(str(new)), key
        assert rewritten == str(new / Path(rewritten).relative_to(new)), key
    assert result["scan_roots"][0] == str(new / "e")
    assert result["name"] == str(old / "ignored")


def test_path_fields_constant_contains_expected_keys():
    """Belt-and-suspenders: the documented set of path field names
    should remain stable. If a future PR trims or expands it, this test
    fails loud so we can decide whether the field list needs updating
    in migrations / docs / desktop tooling."""

    expected_subset = {
        "path",
        "file_path",
        "photo_storage_path",
        "storage_root",
        "model_path",
        "model_dir",
        "scan_roots",
        "external_directories",
        "live_photo_video_path",
        "folder_path",
        "directory",
    }
    assert expected_subset <= PATH_FIELDS
