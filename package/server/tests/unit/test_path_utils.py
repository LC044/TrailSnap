"""Nightly watch gap coverage for app.utils.path.

Targets compute_relative_path, compute_browse_path, build_folder_list,
build_folder_tree_level and the private _normalize helper (135 lines,
106 missed in nightly coverage scan).

* Happy path: absolute paths under a known root strip to relative form.
* Edge: empty path returns empty; mixed input row types accepted.
* Error: paths not under any root fall back to parent dir basename.
"""

from __future__ import annotations

import os

import pytest

from app.utils.path import (
    _normalize,
    compute_relative_path,
    compute_relative_folder,
    compute_browse_path,
    build_folder_list,
    build_folder_tree_level,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture
def photo_root():
    return _normalize("/data")


def test_normalize_unifies_separators_and_strips_trailing_slash():
    norm = _normalize("/tmp/uploads/")
    assert norm.endswith("/tmp/uploads")
    assert norm.endswith("/tmp/uploads") and not norm.endswith("//")
    assert _normalize("") == ""


def test_compute_relative_path_strips_matching_root(photo_root):
    folder, fname = compute_relative_path("/data/travel/beach.jpg", [photo_root])
    assert fname == "beach.jpg"
    assert folder == "travel"


def test_compute_relative_path_falls_back_when_no_root_match():
    roots = [_normalize("/somewhere/else")]
    folder, fname = compute_relative_path("/var/photos/holiday/sunset.jpg", roots)
    assert fname == "sunset.jpg"
    assert folder == "holiday"


def test_compute_relative_path_handles_path_equal_to_root(photo_root):
    folder, fname = compute_relative_path(photo_root, [photo_root])
    assert fname == os.path.basename(photo_root)
    assert folder == ""


def test_compute_relative_path_empty_input(photo_root):
    folder, fname = compute_relative_path("", [photo_root])
    assert folder == "" and fname == ""


def test_compute_browse_path_prepends_root_label(photo_root):
    folder, fname = compute_browse_path("/data/2024/photo.jpg", [photo_root])
    assert fname == "photo.jpg"
    assert folder.endswith("/2024")


def test_compute_relative_folder_is_just_the_folder(photo_root):
    folder = compute_relative_folder("/data/travel/sunset.jpg", [photo_root])
    assert folder == "travel"


def test_build_folder_list_groups_and_orders(photo_root):
    rows = [
        "/data/2024/beach.jpg",
        "/data/2024/sunset.jpg",
        "/data/2023/winter.jpg",
    ]
    result = build_folder_list(rows, [photo_root])
    by_rel = {entry["rel_path"]: entry for entry in result}
    assert by_rel["2024"]["count"] == 2
    assert by_rel["2023"]["count"] == 1
    rels = [entry["rel_path"] for entry in result]
    assert rels == sorted(rels)


def test_build_folder_list_accepts_tuples_and_ignores_bad_rows(photo_root):
    rows = [
        ("/data/2024/a.jpg", "meta1"),
        ("/data/2024/b.jpg", "meta2"),
        ("", "missing"),
        (None, "skip"),
    ]
    result = build_folder_list(rows, [photo_root])
    assert len(result) == 1
    assert result[0]["count"] == 2


def test_build_folder_tree_level_root_aggregates_all_under_root_label(photo_root):
    rows = [
        "/data/travel/beach.jpg",
        "/data/food/dinner.jpg",
        "/data/travel/paris.jpg",
    ]
    tree = build_folder_tree_level(rows, [photo_root])
    # root_label is basename(photo_root). All photos roll up to that single
    # top-level child at the root level with has_children=True.
    assert len(tree["children"]) == 1
    child = tree["children"][0]
    assert child["count"] == 3
    assert child["has_children"] is True


def test_build_folder_tree_level_nested(photo_root):
    rows = ["/data/travel/beach.jpg", "/data/travel/iceland/aurora.jpg"]
    tree = build_folder_tree_level(rows, [photo_root], parent="data/travel")
    names = sorted(c["name"] for c in tree["children"])
    assert names == ["iceland"]  # beach.jpg is own_count
    iceland = next(c for c in tree["children"] if c["name"] == "iceland")
    assert iceland["count"] == 1
    assert iceland["has_children"] is False
    expected_breadcrumb = [
        {
            "name": "data", "path": "data"
        },
        {
            "name": "travel", "path": "data/travel"
        },
    ]
    assert tree["breadcrumb"] == expected_breadcrumb
    assert tree["parent"] == "data/travel"
