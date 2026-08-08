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
    assert svc.RESCAN_AUTO_MATCH_THRESHOLD == 0.35
    assert svc.RESCAN_CANDIDATE_THRESHOLD == 0.45
    assert svc.RESCAN_REMOVAL_THRESHOLD == 0.52
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
            face_rescan_auto_match_threshold=0.31,
            face_rescan_candidate_threshold=0.44,
            face_rescan_removal_threshold=0.54,
            face_recognition_min_photos=7,
        )
    )
    db = MagicMock()
    with patch("app.service.face_cluster.config_manager.get_user_config", return_value=cfg):
        svc = FaceClusterService(db=db, user_id="user-1")

    assert svc.SIMILARITY_THRESHOLD == 0.55
    assert svc.DISTANCE_THRESHOLD == 0.33
    assert svc.RESCAN_AUTO_MATCH_THRESHOLD == 0.31
    assert svc.RESCAN_CANDIDATE_THRESHOLD == 0.44
    assert svc.RESCAN_REMOVAL_THRESHOLD == 0.54
    assert svc.MIN_CLUSTER_SIZE_FOR_IDENTITY == 7
    assert svc.DBSCAN_EPS == 0.33
    assert svc.DBSCAN_MIN_SAMPLES == 5


# ----------------------------- identity rescan -----------------------------

def test_consistent_component_keeps_largest_matching_group():
    from app.service.face_cluster import FaceClusterService

    svc = FaceClusterService(db=MagicMock())
    embeddings = [
        FaceClusterService.normalize_embedding([1.0, 0.0, 0.0]),
        FaceClusterService.normalize_embedding([0.98, 0.1, 0.0]),
        FaceClusterService.normalize_embedding([0.96, -0.1, 0.0]),
        FaceClusterService.normalize_embedding([0.0, 1.0, 0.0]),
    ]

    selected = svc._select_consistent_component(embeddings, [10, 11, 12, 13], default_face_id=13)

    assert selected == [0, 1, 2]


def test_consistent_component_is_conservative_with_two_faces():
    from app.service.face_cluster import FaceClusterService

    svc = FaceClusterService(db=MagicMock())
    embeddings = [
        FaceClusterService.normalize_embedding([1.0, 0.0]),
        FaceClusterService.normalize_embedding([0.0, 1.0]),
    ]

    assert svc._select_consistent_component(embeddings, [1, 2], default_face_id=1) == [0, 1]


def test_diverse_prototypes_do_not_collapse_to_one_center():
    from app.service.face_cluster import FaceClusterService

    svc = FaceClusterService(db=MagicMock())
    svc.MAX_RESCAN_PROTOTYPES = 3
    embeddings = [
        FaceClusterService.normalize_embedding([1.0, float(index) / 20.0, 0.1])
        for index in range(8)
    ]

    prototypes = svc._select_diverse_prototypes(embeddings)

    assert len(prototypes) == 3
    assert not np.allclose(prototypes[0], prototypes[1])


def test_rescan_rolls_back_and_raises_when_query_fails():
    from app.service.face_cluster import FaceClusterService, FaceRescanError

    db = MagicMock()
    db.query.side_effect = RuntimeError("database unavailable")
    svc = FaceClusterService(db=db)

    with pytest.raises(FaceRescanError):
        svc.rescan_identity(identity_id="identity-1", owner_id="user-1")

    db.rollback.assert_called_once()


def test_manual_assignments_are_protected_from_automatic_reassignment():
    from app.service.face_cluster import FaceClusterService

    svc = FaceClusterService(db=MagicMock())

    assert svc._is_manually_confirmed(SimpleNamespace(recognize_confidence=1.0)) is True
    assert svc._is_manually_confirmed(SimpleNamespace(recognize_confidence=0.8)) is False
    assert svc._is_manually_confirmed(SimpleNamespace(recognize_confidence=None)) is False


def test_reference_sampling_is_bounded_and_keeps_default_face():
    from app.service.face_cluster import FaceClusterService

    svc = FaceClusterService(db=MagicMock())
    svc.MAX_RESCAN_REFERENCE_SAMPLE = 10
    faces = [SimpleNamespace(id=index) for index in range(100)]

    indices = svc._sample_reference_indices(100, faces, default_face_id=57)

    assert 57 in indices
    assert len(indices) <= 11


def test_apply_rescan_only_mutates_confirmed_candidates_and_commits_once():
    from app.service.face_cluster import FaceClusterService

    db = MagicMock()
    svc = FaceClusterService(db=db)
    target_id = "target"
    other_id = "other"
    add_selected = SimpleNamespace(id=10, photo_id="photo-add", face_identity_id=other_id, recognize_confidence=0.7)
    add_skipped = SimpleNamespace(id=11, photo_id="photo-skip", face_identity_id=None, recognize_confidence=None)
    remove_selected = SimpleNamespace(id=20, photo_id="photo-remove", face_identity_id=target_id, recognize_confidence=0.4)
    analysis = {
        "identity_id": target_id,
        "owner_id": "owner",
        "reason": None,
        "prototypes": [np.array([1.0, 0.0])],
        "add_candidates": [
            {"face": add_selected, "distance": 0.1},
            {"face": add_skipped, "distance": 0.2},
        ],
        "remove_candidates": [{"face": remove_selected, "distance": 0.6}],
        "removal_threshold": 0.52,
    }

    with patch.object(svc, "_analyze_identity_rescan", return_value=analysis), \
         patch.object(svc, "_repair_default_faces") as repair:
        result = svc.apply_identity_rescan(target_id, "owner", [10], [20])

    assert add_selected.face_identity_id == target_id
    assert add_selected.recognize_confidence == pytest.approx(0.9)
    assert add_skipped.face_identity_id is None
    assert remove_selected.face_identity_id is None
    assert remove_selected.recognize_confidence is None
    assert result["added_count"] == 1
    assert result["removed_count"] == 1
    assert result["reassigned_count"] == 1
    repair.assert_called_once_with({target_id, other_id})
    db.flush.assert_called_once()
    db.commit.assert_called_once()


def test_apply_rescan_rejects_stale_selection_and_rolls_back():
    from app.service.face_cluster import FaceClusterService, FaceRescanConflictError

    db = MagicMock()
    svc = FaceClusterService(db=db)
    analysis = {
        "identity_id": "target",
        "owner_id": "owner",
        "reason": None,
        "prototypes": [],
        "add_candidates": [],
        "remove_candidates": [],
        "removal_threshold": 0.52,
    }

    with patch.object(svc, "_analyze_identity_rescan", return_value=analysis):
        with pytest.raises(FaceRescanConflictError):
            svc.apply_identity_rescan("target", "owner", [999], [])

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_rescan_compatibility_only_auto_applies_high_confidence_additions():
    from app.service.face_cluster import FaceClusterService

    db = MagicMock()
    svc = FaceClusterService(db=db)
    strong = SimpleNamespace(id=1)
    review_only = SimpleNamespace(id=2)
    analysis = {
        "add_candidates": [
            {"face": strong, "distance": 0.34},
            {"face": review_only, "distance": 0.40},
        ],
        "remove_candidates": [],
    }

    with patch.object(svc, "_analyze_identity_rescan", return_value=analysis), \
         patch.object(svc, "_apply_rescan_analysis", return_value={"status": "success"}) as apply:
        svc.rescan_identity("target", "owner")

    apply.assert_called_once_with(analysis, {1}, set())


def test_preview_marks_only_strong_candidates_as_recommended():
    from app.service.face_cluster import FaceClusterService

    svc = FaceClusterService(db=MagicMock())
    strong = SimpleNamespace(id=1, photo_id="photo-1", face_rect=None, face_identity_id=None)
    review_only = SimpleNamespace(id=2, photo_id="photo-2", face_rect=None, face_identity_id=None)
    analysis = {
        "identity_id": "target",
        "owner_id": "owner",
        "reason": None,
        "prototypes": [np.array([1.0, 0.0])],
        "add_candidates": [
            {"face": strong, "distance": 0.35},
            {"face": review_only, "distance": 0.40},
        ],
        "remove_candidates": [],
        "removal_threshold": 0.52,
    }

    preview = svc._serialize_rescan_preview(analysis)

    assert preview["threshold"] == 0.35
    assert preview["candidate_threshold"] == 0.45
    assert preview["removal_threshold"] == 0.52
    assert preview["add_candidates"][0]["recommended"] is True
    assert preview["add_candidates"][1]["recommended"] is False
