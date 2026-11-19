"""Face feature normalisation and SQLite similarity filtering."""
import hashlib
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import HTTPException

from app.service import similar_faces
from app.service.similar_faces import _feature_signature, _normalised_feature, _sqlite_scores

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def _face(feature):
    return SimpleNamespace(face_feature=feature)


def test_normalised_feature_returns_a_unit_length_vector():
    vector = _normalised_feature(_face([1.0] * 512))
    assert vector.shape == (512,)
    assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-6)


def test_normalised_feature_keeps_the_direction_of_the_input():
    feature = [0.0] * 512
    feature[0] = 3.0
    vector = _normalised_feature(_face(feature))
    assert float(vector[0]) == pytest.approx(1.0)


@pytest.mark.parametrize("feature", [
    [1.0] * 511,
    [0.0] * 512,
    [float("nan")] + [0.0] * 511,
    [float("inf")] + [0.0] * 511,
])
def test_normalised_feature_rejects_unusable_vectors(feature):
    with pytest.raises(HTTPException) as error:
        _normalised_feature(_face(feature))
    assert error.value.status_code == 422


def test_feature_signature_is_stable_and_content_addressed():
    vector = np.asarray([1.0, 2.0], dtype=np.float32)
    assert _feature_signature(vector) == _feature_signature(vector)
    assert _feature_signature(vector) == hashlib.sha256(vector.tobytes()).hexdigest()
    assert _feature_signature(vector) != _feature_signature(np.asarray([2.0, 1.0], dtype=np.float32))


def _stub_cache(monkeypatch, ids, scores):
    def similarities(*args, **kwargs):
        return [(np.asarray(ids), np.asarray(scores, dtype=float).reshape(len(ids), 1))]

    monkeypatch.setattr(similar_faces.face_vector_cache, "similarities", similarities)


def test_sqlite_scores_keeps_only_candidates_within_the_threshold(monkeypatch):
    _stub_cache(monkeypatch, [1, 2, 3], [[0.95], [0.5], [float("nan")]])
    matches = _sqlite_scores(None, None, np.zeros((1, 512), dtype=np.float32), 0.2)
    assert set(matches) == {1}
    assert matches[1] == pytest.approx(0.05)


def test_sqlite_scores_inverts_the_comparison_for_low_similarity(monkeypatch):
    _stub_cache(monkeypatch, [1, 2, 3], [[0.95], [0.5], [float("nan")]])
    matches = _sqlite_scores(None, None, np.zeros((1, 512), dtype=np.float32), 0.2, low_similarity=True)
    assert set(matches) == {2}
    assert matches[2] == pytest.approx(0.5)


def test_sqlite_scores_returns_an_empty_mapping_without_candidates(monkeypatch):
    _stub_cache(monkeypatch, [], [])
    assert _sqlite_scores(None, None, np.zeros((1, 512), dtype=np.float32), 0.2) == {}

