"""2026-11-19 nightly coverage for ``app/service/clip_catalog.py``.

No test file referenced ``app/service/clip_catalog.py`` even though
``app/api/clip_classification.py`` and ``app/service/clip_classification.py``
both load the built-in catalog through it.  The catalog is the shared identity
of every built-in category, so the invariants asserted here are the ones the
rest of the app relies on: one version, one identity per category name, and
thresholds that are usable by the classifier.
"""

from __future__ import annotations

import json

import pytest

from app.service import clip_catalog


pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


CLIP_MODEL = "chinese-clip-ViT-B-16"


@pytest.fixture()
def catalog():
    return clip_catalog.load_catalog()


def test_catalog_file_is_valid_json_with_the_three_top_level_sections():
    raw = json.loads(clip_catalog.CATALOG_PATH.read_text(encoding="utf-8"))

    assert set(raw.keys()) == {"version", "groups", "categories"}
    assert isinstance(raw["version"], int)
    assert isinstance(raw["groups"], list)
    assert isinstance(raw["categories"], list)


def test_load_catalog_is_cached_so_callers_share_one_identity():
    clip_catalog.load_catalog.cache_clear()

    first = clip_catalog.load_catalog()
    second = clip_catalog.load_catalog()

    assert first is second
    assert clip_catalog.load_catalog.cache_info().hits >= 1


def test_catalog_contains_built_in_categories_grouped_by_the_declared_groups(catalog):
    assert catalog["version"] >= 1
    assert len(catalog["groups"]) > 0
    assert len(catalog["categories"]) > 0

    known_groups = set(catalog["groups"])
    for category in catalog["categories"]:
        assert category["groups"], f"{category['key']} declares no group"
        assert set(category["groups"]) <= known_groups


def test_a_shared_category_name_has_exactly_one_identity(catalog):
    names = [category["name"] for category in catalog["categories"]]
    keys = [category["key"] for category in catalog["categories"]]

    assert len(names) == len(set(names)), "duplicate category name in the catalog"
    assert len(keys) == len(set(keys)), "duplicate category key in the catalog"


def test_every_category_carries_a_usable_threshold_for_the_clip_model(catalog):
    for category in catalog["categories"]:
        thresholds = category.get("thresholds") or {}

        assert CLIP_MODEL in thresholds, f"{category['key']} has no {CLIP_MODEL} threshold"
        value = thresholds[CLIP_MODEL]
        assert isinstance(value, (int, float))
        assert 0.0 < value < 1.0


def test_reviewed_categories_record_their_calibration_provenance(catalog):
    reviewed = [
        category
        for category in catalog["categories"]
        if (category.get("calibration") or {}).get("status") == "reviewed"
    ]

    assert reviewed, "expected at least one reviewed category"

    for category in reviewed:
        calibration = category["calibration"]
        assert calibration.get("description_sha256"), f"{category['key']} lost its description hash"
        assert calibration.get("model") == CLIP_MODEL
        assert calibration.get("date")
