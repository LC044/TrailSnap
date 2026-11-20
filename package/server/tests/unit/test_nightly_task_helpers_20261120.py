"""Helper guards inside the background task strategies."""
import json
import os

import pytest

from app.service.tasks.basic import _json_safe_metadata
from app.service.tasks.face import _validate_face_embeddings
from app.service.tasks.scan import (
    _compile_folder_patterns,
    _is_folder_excluded,
    _within_roots,
)

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_json_safe_metadata_replaces_non_finite_floats():
    result = _json_safe_metadata({"a": float("nan"), "b": [float("inf"), 1.0]})
    assert result == {"a": None, "b": [None, 1.0]}


def test_json_safe_metadata_drops_invalid_gps_location():
    result = _json_safe_metadata({"location": {"latitude": 999.0, "longitude": 0.0}})
    assert result["location"] is None


def test_json_safe_metadata_keeps_valid_gps_location():
    gps = {"latitude": 30.0, "longitude": 120.0}
    assert _json_safe_metadata({"location": gps})["location"] == gps


def test_json_safe_metadata_stays_json_serialisable():
    payload = _json_safe_metadata({"x": float("nan"), "y": {"z": float("-inf")}})
    assert json.dumps(payload, allow_nan=False)


def test_within_roots_accepts_descendants(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    assert _within_roots(str(root / "sub" / "a.jpg"), [str(root)]) is True


def test_within_roots_rejects_sibling_with_shared_prefix(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    other = tmp_path / "root_other"
    other.mkdir()
    assert _within_roots(str(other / "a.jpg"), [str(root)]) is False


def test_within_roots_rejects_other_drive():
    if os.name != "nt":
        pytest.skip("drive semantics are Windows-specific")
    assert _within_roots("Z:\\photos\\a.jpg", ["C:\\photos"]) is False


def test_within_roots_requires_at_least_one_root(tmp_path):
    assert _within_roots(str(tmp_path / "a.jpg"), []) is False


def test_compile_folder_patterns_skips_invalid_regex():
    compiled = _compile_folder_patterns([r"\.tmp$", "["])
    assert len(compiled) == 1
    assert _is_folder_excluded("cache.tmp", compiled) is True
    assert _is_folder_excluded("photos", compiled) is False


def test_compile_folder_patterns_handles_missing_patterns():
    assert _compile_folder_patterns(None) == []


def test_is_folder_excluded_without_patterns():
    assert _is_folder_excluded("photos", []) is False


def test_validate_face_embeddings_accepts_valid_detection():
    _validate_face_embeddings([{"det_score": 0.9, "embedding": [0.0] * 511 + [1.0]}], 0.5)


def test_validate_face_embeddings_ignores_low_score_detections():
    _validate_face_embeddings([{"det_score": 0.1, "embedding": [1.0]}], 0.5)


def test_validate_face_embeddings_ignores_missing_embedding():
    _validate_face_embeddings([{"det_score": 0.9, "embedding": None}], 0.5)


@pytest.mark.parametrize(
    "embedding",
    [[0.0] * 512, [float("nan")] * 512, [1.0] * 256],
)
def test_validate_face_embeddings_rejects_invalid_vectors(embedding):
    with pytest.raises(ValueError):
        _validate_face_embeddings([{"det_score": 0.9, "embedding": embedding}], 0.5)
