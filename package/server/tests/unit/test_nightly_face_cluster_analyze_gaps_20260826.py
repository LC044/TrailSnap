"""Round 2026-08-26 coverage for app/service/face_cluster.py analyze_identity_rescan."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.usefixtures("mock_appearance_for_fake_sessions")]


def _service(db):
    from app.service.face_cluster import FaceClusterService

    return FaceClusterService(db=db, user_id=None)


def _face(id_, feature):
    return SimpleNamespace(
        id=id_,
        face_feature=feature,
        is_deleted=False,
        is_manually_confirmed=False,
        recognize_confidence=None,
    )


def _chain_query(all_value):
    q = MagicMock()
    q.filter.return_value = q
    q.join.return_value = q
    q.order_by.return_value = q
    q.with_for_update.return_value = q
    q.all.return_value = all_value
    return q


def test_analyze_identity_rescan_returns_no_reference_faces_summary_when_empty():
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    db.query.return_value = _chain_query([])

    svc = _service(db)
    identity_id = "ident-1"
    summary = svc._analyze_identity_rescan(identity_id, owner_id=None, lock=False)

    assert summary["identity_id"] == identity_id
    assert summary["reason"] == "no_reference_faces"
    assert summary["prototypes"] == []
    assert summary["add_candidates"] == []
    assert summary["remove_candidates"] == []
    assert summary["removal_threshold"] == svc.RESCAN_REMOVAL_THRESHOLD


def test_analyze_identity_rescan_no_remove_candidates_when_under_threshold():
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    faces = [
        _face(101, np.array([1.0, 0.0, 0.0])),
        _face(102, np.array([1.0, 0.0, 0.0])),
    ]
    db.query.return_value = _chain_query(faces)

    identity = SimpleNamespace(default_face_id=None)

    with patch("app.service.face_cluster.crud_face.get_identity", return_value=identity):
        svc = _service(db)
        # Candidate discovery is exercised against a real SQLite engine in
        # test_face_cluster_sqlite_vectorized.py; stub it out here so this test
        # stays focused on the removal-threshold branch.
        with patch.object(svc, "_find_matching_face_ids", return_value=set()):
            out = svc._analyze_identity_rescan("ident-2", owner_id=None, lock=False)

    assert out["remove_candidates"] == []
    assert isinstance(out["prototypes"], list)


def test_analyze_identity_rescan_sorts_candidates_by_similarity():
    """Add candidates rank most-similar first; removals rank least-similar first."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    # Two trusted reference faces at angle 0 form the prototypes; two outliers
    # assigned to the identity become removal candidates. 103 (d≈0.55) is
    # delivered before 104 (d≈1.0) so the removal sort is observable.
    faces = [
        _face(101, np.array([1.0, 0.0, 0.0])),
        _face(102, np.array([1.0, 0.0, 0.0])),
        _face(103, np.array([0.45, 0.89, 0.0])),   # distance ~0.55
        _face(104, np.array([0.0, 1.0, 0.0])),     # distance ~1.0
    ]
    for face in faces:
        face.face_identity_id = "ident-2"
    # Candidates delivered in database (id) order: far, middle, close.
    candidate_features = {
        203: np.array([0.6, 0.8, 0.0]),          # distance ~0.4
        202: np.array([0.85, 0.5, 0.0]),         # distance ~0.15
        201: np.array([1.0, 0.0, 0.0]),          # distance ~0
    }
    candidates = [
        SimpleNamespace(
            id=face_id, face_feature=feature, is_deleted=False,
            is_manually_confirmed=False, recognize_confidence=None,
            face_identity_id=None,
        )
        for face_id, feature in candidate_features.items()
    ]
    # db.query serves the assigned-faces query first and the candidate-faces
    # query second; give each its own result list via side_effect.
    assigned_query = _chain_query(faces)
    candidate_query = _chain_query(candidates)
    db.query = MagicMock(side_effect=[assigned_query, candidate_query])

    identity = SimpleNamespace(default_face_id=None)

    with patch("app.service.face_cluster.crud_face.get_identity", return_value=identity):
        svc = _service(db)
        # Keep both outlier distances (0.55, 1.0) above the removal threshold
        # while the closest add candidate (0.0) stays under the candidate one.
        svc.RESCAN_REMOVAL_THRESHOLD = 0.5
        with patch.object(svc, "_find_matching_face_ids", return_value={201, 202, 203}), \
             patch.object(svc, "_cosine_distance", side_effect=lambda left, right: float(1.0 - np.dot(left, right))):
            out = svc._analyze_identity_rescan("ident-2", owner_id=None, lock=False)

    add_distances = [item["distance"] for item in out["add_candidates"]]
    assert add_distances == sorted(add_distances)
    # The database order was 203 (~0.4), 202 (~0.15), 201 (~0); the output must
    # be re-ordered most-similar first, which only holds if the sort happened.
    assert [item["face"].id for item in out["add_candidates"]] == [201, 202, 203]
    remove_distances = [item["distance"] for item in out["remove_candidates"]]
    assert remove_distances == sorted(remove_distances, reverse=True)
    # Delivered as 103 (~0.4) then 104 (~1.0); least-similar 104 must lead.
    assert [item["face"].id for item in out["remove_candidates"]] == [104, 103]


@pytest.mark.parametrize("removal_threshold", [0, .3])
@pytest.mark.module_face
def test_custom_removal_threshold_preserves_trusted_and_confirmed_faces(removal_threshold):
    db = MagicMock()
    faces = [_face(1, [1., 0., 0.]), _face(2, [1., 0., 0.]),
             _face(3, [.6, .8, 0.]), _face(4, [0., 1., 0.])]
    faces[3].recognize_confidence = 1.0
    db.query.return_value = _chain_query(faces)
    svc = _service(db)
    with patch("app.service.face_cluster.crud_face.get_identity", return_value=SimpleNamespace(default_face_id=1)), \
         patch.object(svc, "_select_rescan_references", return_value=([0, 1], [np.array([1., 0., 0.])])), \
         patch.object(svc, "_find_matching_face_ids", return_value=set()):
        default = svc._analyze_identity_rescan("identity", None, False)
        custom = svc._analyze_identity_rescan("identity", None, False, removal_threshold=removal_threshold)
    assert default["remove_candidates"] == []
    assert custom["removal_threshold"] == removal_threshold
    assert [item["face"].id for item in custom["remove_candidates"]] == [3]
    assert svc.RESCAN_REMOVAL_THRESHOLD == .52


def test_analyze_identity_rescan_with_owner_id_adds_extra_filter():
    """owner_id set -> the query gains an extra ``.filter(Photo.owner_id == ...)``."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    q = _chain_query([])
    db.query.return_value = q

    svc = _service(db)
    # Baseline: no owner_id -> 1 filter call.
    svc._analyze_identity_rescan("ident-3", owner_id=None, lock=False)
    baseline = q.filter.call_count
    # With owner_id -> the owner branch adds exactly one extra filter.
    svc._analyze_identity_rescan("ident-4", owner_id="owner-xyz", lock=False)
    delta = q.filter.call_count - baseline
    # Filter by owner_id adds at least one extra filter call.
    assert delta >= 1
