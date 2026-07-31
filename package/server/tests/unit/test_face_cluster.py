"""Unit tests for ``app/service/face_cluster.py``.

The cluster service is mostly a thin wrapper over pgvector / DBSCAN. The
parts that are pure numpy math are easy to lock down without a database:

* ``FaceClusterService.normalize_embedding`` -- L2-normalises a list/array
  and is safe against zero vectors.
* Constructor defaults when ``user_id`` is None -- these are the fallback
  thresholds used for the "should not happen" path.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


# ----------------------------- normalize_embedding -----------------------------

def test_normalize_embedding_from_list_produces_unit_vector():
    from app.service.face_cluster import FaceClusterService

    raw = [3.0, 4.0]  # norm = 5
    out = FaceClusterService.normalize_embedding(raw)

    assert isinstance(out, np.ndarray)
    assert np.allclose(out, np.array([0.6, 0.8]))
    assert np.isclose(np.linalg.norm(out), 1.0)


def test_normalize_embedding_from_array_returns_copy_not_view():
    """Input arrays should never be mutated in place."""
    from app.service.face_cluster import FaceClusterService

    raw = np.array([1.0, 1.0, 1.0])
    out = FaceClusterService.normalize_embedding(raw)

    assert np.allclose(out, raw / np.sqrt(3))
    # Original untouched.
    assert np.allclose(raw, [1.0, 1.0, 1.0])


def test_normalize_embedding_zero_vector_is_returned_unchanged():
    """Zero norm should not raise; instead the original vector is returned."""
    from app.service.face_cluster import FaceClusterService

    raw = [0.0, 0.0, 0.0]
    out = FaceClusterService.normalize_embedding(raw)

    assert np.allclose(out, [0.0, 0.0, 0.0])
    # The zero vector cannot be normalised; norm stays 0.
    assert np.linalg.norm(out) == 0


# ----------------------------- constructor defaults -----------------------------

def test_constructor_falls_back_to_safe_thresholds_without_user_id():
    """Without a user_id we should get the documented fallback thresholds."""
    from app.service.face_cluster import FaceClusterService

    svc = FaceClusterService(db=MagicMock(), user_id=None)

    assert svc.SIMILARITY_THRESHOLD == 0.7
    assert svc.DISTANCE_THRESHOLD == 0.4
    assert svc.MIN_CLUSTER_SIZE_FOR_IDENTITY == 5
    # Derived constants must follow the documented formula.
    assert svc.DBSCAN_EPS == 0.4
    assert svc.CLUSTER_MERGE_THRESHOLD == pytest.approx(0.48)


def test_constructor_pulls_thresholds_from_user_config():
    """When user_id is supplied, the service should consult config_manager."""
    from app.service.face_cluster import FaceClusterService

    cfg = SimpleNamespace(
        ai=SimpleNamespace(
            face_recognition_threshold=0.55,
            face_cluster_threshold=0.33,
            face_recognition_min_photos=7,
        )
    )
    db = MagicMock()
    with patch("app.service.face_cluster.config_manager.get_user_config", return_value=cfg):
        svc = FaceClusterService(db=db, user_id="user-1")

    assert svc.SIMILARITY_THRESHOLD == 0.55
    assert svc.DISTANCE_THRESHOLD == 0.33
    assert svc.MIN_CLUSTER_SIZE_FOR_IDENTITY == 7
    assert svc.DBSCAN_EPS == 0.33
    assert svc.DBSCAN_MIN_SAMPLES == 5
