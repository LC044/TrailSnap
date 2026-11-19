"""2026-11-16 nightly coverage for the CLIP rule input validators.

The 2026-11-16 backend coverage scan reported ``api/clip_classification.py``
at 80.1% and showed that two pydantic validators were never exercised by
any test in ``tests/unit``:

* ``RuleInput.clean_name`` - a whitespace-only rule name must be rejected
  and a padded name must be stored trimmed.
* ``RuleInput.valid_thresholds`` - the threshold map must be non-empty and
  every value must stay inside ``[-1, 1]``.

The neighbouring validators (``clean_texts``, ``has_description`` and
``valid_images``) share the same request model, so they are covered here
as well to lock the current contract of the rule editor.
"""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from PIL import Image
from pydantic import ValidationError

from app.api import clip_classification as clip_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def _jpeg_data_url(size=(8, 8)) -> str:
    buffer = BytesIO()
    Image.new("RGB", size, (120, 140, 160)).save(buffer, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _rule(**overrides):
    payload = {"name": "猫", "descriptions": ["描述"], "thresholds": {"猫": 0.5}}
    payload.update(overrides)
    return clip_api.RuleInput(**payload)


def test_clean_name_trims_surrounding_whitespace():
    assert _rule(name="  猫  ").name == "猫"


def test_clean_name_rejects_a_whitespace_only_name():
    with pytest.raises(ValidationError):
        _rule(name="   ")


def test_valid_thresholds_keeps_a_valid_map():
    rule = _rule(thresholds={"猫": 0.5, "狗": -0.25})
    assert rule.thresholds == {"猫": 0.5, "狗": -0.25}


@pytest.mark.parametrize("thresholds", [{}, {"猫": 1.5}, {"猫": -1.5}])
def test_valid_thresholds_rejects_empty_or_out_of_range_maps(thresholds):
    with pytest.raises(ValidationError):
        _rule(thresholds=thresholds)


@pytest.mark.parametrize("value", [1.0, -1.0, 0.0])
def test_valid_thresholds_accepts_the_inclusive_bounds(value):
    assert _rule(thresholds={"猫": value}).thresholds == {"猫": value}


def test_clean_texts_deduplicates_and_trims():
    rule = _rule(descriptions=[" 猫 ", "猫", "狗"], groups=[" 自动 "])
    assert rule.descriptions == ["猫", "狗"]
    assert rule.groups == ["自动"]


@pytest.mark.parametrize("descriptions", [[""], ["x" * 101]])
def test_clean_texts_rejects_empty_or_oversized_entries(descriptions):
    with pytest.raises(ValidationError):
        _rule(descriptions=descriptions)


def test_has_description_requires_a_description_or_a_reference_image():
    with pytest.raises(ValidationError):
        _rule(descriptions=[])


def test_has_description_accepts_a_rule_with_only_a_reference_image():
    rule = _rule(descriptions=[], reference_images=[_jpeg_data_url()])
    assert rule.reference_images


def test_valid_images_rejects_a_remote_reference_image():
    with pytest.raises(ValidationError):
        _rule(reference_images=["https://example.com/cat.jpg"])


def test_preview_input_rejects_an_out_of_range_sample_size():
    with pytest.raises(ValidationError):
        clip_api.PreviewInput(name="猫", descriptions=["描述"], thresholds={"猫": 0.5},
                              sample_size=0)

