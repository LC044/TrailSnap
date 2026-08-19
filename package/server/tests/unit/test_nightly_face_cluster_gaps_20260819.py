"""Unit tests covering 2026-08-19 nightly coverage gap scan.

Targets uncovered branches in app.service.face_cluster (previously 49.3%
covered, 182 of 359 lines missed). The existing test_nightly_crud_face_gaps_20260816
and test_nightly_crud_face_gaps_20260812 exercise the CRUD helpers but the
rescan/cluster service-level logic has no coverage; this file complements
them with numpy/algorithm paths and serialize helpers that can run against
an in-memory MagicMock DB.

All DB interactions are mocked via MagicMock + SimpleNamespace so the tests
run in isolation without a live Postgres. Constructor switches to the
no-user_id fallback path (default thresholds) so service.py can be imported
without resolving the live ``config_manager``.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np
import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _service():
    """Build a FaceClusterService with a stub DB and default thresholds."""
    from app.service.face_cluster import FaceClusterService

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return FaceClusterService(db=db, user_id=None)


def _unit_vec(dim=4, seed=0):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim)
    v /= np.linalg.norm(v)
    return v


def _face(**overrides):
    base = dict(
        id=1,
        photo_id=uuid4(),
        face_identity_id=None,
        face_feature=None,
        face_rect=[0.1, 0.2, 0.3, 0.4],
        recognize_confidence=None,
        is_deleted=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _fluent_chain(*, all_value=None, first_value=None):
    """Return a chain whose ``.filter/.join/.order_by`` return self.

    This mirrors SQLAlchemy query builder semantics; setting ``.filter`` etc.
    to return the same mock keeps chained calls composed correctly.
    """
    chain = MagicMock()
    chain.all = MagicMock(return_value=all_value if all_value is not None else [])
    chain.first = MagicMock(return_value=first_value)
    chain.filter = MagicMock(return_value=chain)
    chain.join = MagicMock(return_value=chain)
    chain.order_by = MagicMock(return_value=chain)
    return chain


# ---------------------------------------------------------------------------
# Constructor - fallback branch when user_id is None
# ---------------------------------------------------------------------------

def test_init_uses_default_thresholds_when_user_id_missing():
    svc = _service()
    assert svc.SIMILARITY_THRESHOLD == 0.7
    assert svc.DISTANCE_THRESHOLD == 0.4
    assert svc.DBSCAN_EPS == 0.4
    assert svc.CLUSTER_MERGE_THRESHOLD == pytest.approx(0.48)
    assert svc.MANUAL_ASSIGNMENT_CONFIDENCE == 0.999
    assert svc.MAX_RESCAN_PROTOTYPES == 12
    assert svc.MAX_RESCAN_REFERENCE_SAMPLE == 200


# ---------------------------------------------------------------------------
# normalize_embedding
# ---------------------------------------------------------------------------

def test_normalize_embedding_accepts_list():
    from app.service.face_cluster import FaceClusterService

    emb = [3.0, 4.0]
    out = FaceClusterService.normalize_embedding(emb)

    assert out.shape == (2,)
    assert np.allclose(out, [0.6, 0.8])


def test_normalize_embedding_accepts_ndarray_and_does_not_alias():
    from app.service.face_cluster import FaceClusterService

    arr = np.array([1.0, 0.0, 0.0])
    out = FaceClusterService.normalize_embedding(arr)

    assert out.shape == (3,)
    assert np.allclose(out, [1.0, 0.0, 0.0])
    assert np.allclose(arr, [1.0, 0.0, 0.0])


def test_normalize_embedding_returns_input_on_zero_norm():
    from app.service.face_cluster import FaceClusterService

    arr = np.array([0.0, 0.0, 0.0])
    out = FaceClusterService.normalize_embedding(arr)

    assert out.shape == (3,)
    assert np.allclose(out, [0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# _cosine_distance
# ---------------------------------------------------------------------------

def test_cosine_distance_identical_vectors_is_zero():
    svc = _service()
    v = _unit_vec(dim=5, seed=42)
    assert svc._cosine_distance(v, v) == pytest.approx(0.0)


def test_cosine_distance_orthogonal_is_one():
    svc = _service()
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert svc._cosine_distance(a, b) == pytest.approx(1.0)


def test_cosine_distance_opposite_clipped_to_two():
    svc = _service()
    a = np.array([1.0, 0.0])
    b = np.array([-1.0, 0.0])
    assert svc._cosine_distance(a, b) == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# _is_manually_confirmed
# ---------------------------------------------------------------------------

def test_is_manually_confirmed_true_above_threshold():
    svc = _service()
    assert svc._is_manually_confirmed(_face(recognize_confidence=0.999)) is True
    assert svc._is_manually_confirmed(_face(recognize_confidence=1.0)) is True


def test_is_manually_confirmed_false_below_threshold():
    svc = _service()
    assert svc._is_manually_confirmed(_face(recognize_confidence=0.5)) is False
    assert svc._is_manually_confirmed(_face(recognize_confidence=0.0)) is False


def test_is_manually_confirmed_false_when_none():
    svc = _service()
    assert svc._is_manually_confirmed(_face(recognize_confidence=None)) is False


# ---------------------------------------------------------------------------
# _select_consistent_component
# ---------------------------------------------------------------------------

def test_select_consistent_component_returns_all_for_trivial_sizes():
    svc = _service()
    for n in (0, 1, 2):
        embeddings = [_unit_vec(seed=i) for i in range(n)]
        face_ids = list(range(n))
        assert svc._select_consistent_component(embeddings, face_ids, default_face_id=None) == list(range(n))


def test_select_consistent_component_picks_largest_cluster():
    svc = _service()
    a = [_unit_vec(seed=0), _unit_vec(seed=0), _unit_vec(seed=0)]
    b = [_unit_vec(seed=100), _unit_vec(seed=100)]
    assert svc._cosine_distance(a[0], b[0]) >= svc.DISTANCE_THRESHOLD
    embeddings = a + b
    face_ids = list(range(5))
    selected = svc._select_consistent_component(embeddings, face_ids, default_face_id=None)
    assert sorted(selected) == [0, 1, 2]


def test_select_consistent_component_uses_default_face_id_as_tiebreaker():
    svc = _service()
    a = [_unit_vec(seed=0), _unit_vec(seed=0), _unit_vec(seed=0)]
    b = [_unit_vec(seed=100), _unit_vec(seed=100), _unit_vec(seed=100)]
    embeddings = a + b
    face_ids = [10, 11, 12, 13, 14, 15]
    selected = svc._select_consistent_component(embeddings, face_ids, default_face_id=13)
    assert sorted(selected) == [3, 4, 5]


# ---------------------------------------------------------------------------
# _select_diverse_prototypes
# ---------------------------------------------------------------------------

def test_select_diverse_prototypes_returns_input_when_small():
    svc = _service()
    embeddings = [_unit_vec(seed=i) for i in range(svc.MAX_RESCAN_PROTOTYPES)]
    assert svc._select_diverse_prototypes(embeddings) == embeddings


def test_select_diverse_prototypes_picks_max_count_when_large():
    svc = _service()
    embeddings = [_unit_vec(seed=i) for i in range(20)]
    selected = svc._select_diverse_prototypes(embeddings)
    assert len(selected) == svc.MAX_RESCAN_PROTOTYPES


def test_select_diverse_prototypes_first_is_anchor():
    svc = _service()
    embeddings = [_unit_vec(seed=i) for i in range(20)]
    selected = svc._select_diverse_prototypes(embeddings)
    assert np.allclose(selected[0], embeddings[0])


# ---------------------------------------------------------------------------
# _sample_reference_indices
# ---------------------------------------------------------------------------

def test_sample_reference_indices_returns_full_range_when_small():
    svc = _service()
    faces = [_face(id=i) for i in range(5)]
    out = svc._sample_reference_indices(face_count=5, faces=faces, default_face_id=None)
    assert out == [0, 1, 2, 3, 4]


def test_sample_reference_indices_sparse_when_large():
    svc = _service()
    n = svc.MAX_RESCAN_REFERENCE_SAMPLE + 50
    faces = [_face(id=i) for i in range(n)]
    out = svc._sample_reference_indices(face_count=n, faces=faces, default_face_id=None)
    assert len(out) == svc.MAX_RESCAN_REFERENCE_SAMPLE
    assert out == sorted(set(out))
    assert out[0] == 0
    assert out[-1] == n - 1


def test_sample_reference_indices_includes_default_face_when_present():
    svc = _service()
    n = svc.MAX_RESCAN_REFERENCE_SAMPLE + 50
    faces = [_face(id=i) for i in range(n)]
    default_face_id = 37
    out = svc._sample_reference_indices(face_count=n, faces=faces, default_face_id=default_face_id)
    assert 37 in out


def test_sample_reference_indices_ignores_unknown_default_face_id():
    svc = _service()
    n = svc.MAX_RESCAN_REFERENCE_SAMPLE + 50
    faces = [_face(id=i) for i in range(n)]
    out_unknown = svc._sample_reference_indices(face_count=n, faces=faces, default_face_id=99999)
    out_none = svc._sample_reference_indices(face_count=n, faces=faces, default_face_id=None)
    assert out_unknown == out_none


# ---------------------------------------------------------------------------
# _serialize_rescan_preview
# ---------------------------------------------------------------------------

def test_serialize_rescan_preview_empty_candidates_returns_summary():
    svc = _service()
    analysis = {
        "identity_id": uuid4(),
        "owner_id": None,
        "reason": "no_reference_faces",
        "prototypes": [],
        "add_candidates": [],
        "remove_candidates": [],
        "removal_threshold": svc.RESCAN_REMOVAL_THRESHOLD,
    }

    out = svc._serialize_rescan_preview(analysis)

    assert out["status"] == "success"
    assert out["reason"] == "no_reference_faces"
    assert out["reference_count"] == 0
    assert out["threshold"] == svc.RESCAN_AUTO_MATCH_THRESHOLD
    assert out["candidate_threshold"] == svc.RESCAN_CANDIDATE_THRESHOLD
    assert out["removal_threshold"] == svc.RESCAN_REMOVAL_THRESHOLD
    assert out["add_candidates"] == []
    assert out["remove_candidates"] == []
    assert out["summary"] == {"add_count": 0, "remove_count": 0, "reassign_count": 0}


def test_serialize_rescan_preview_assigns_remove_unassigned_reassign_labels():
    svc = _service()
    identity_id = uuid4()
    other_identity = uuid4()
    add_face = _face(id=10, face_identity_id=other_identity, recognize_confidence=0.7)
    add_face_unassigned = _face(id=11, face_identity_id=None)
    remove_face = _face(id=20, face_identity_id=identity_id)
    analysis = {
        "identity_id": identity_id,
        "owner_id": None,
        "reason": None,
        "prototypes": [_unit_vec()],
        "add_candidates": [
            {"face": add_face, "distance": 0.4},
            {"face": add_face_unassigned, "distance": 0.1},
        ],
        "remove_candidates": [
            {"face": remove_face, "distance": 0.9},
        ],
        "removal_threshold": svc.RESCAN_REMOVAL_THRESHOLD,
    }
    svc.db.query = MagicMock(return_value=_fluent_chain(all_value=[]))

    out = svc._serialize_rescan_preview(analysis)

    add_out = out["add_candidates"]
    assert len(add_out) == 2
    assert add_out[0]["assignment_type"] == "reassign"
    assert add_out[0]["recommended"] is False
    assert add_out[0]["current_identity_id"] == str(other_identity)
    assert add_out[1]["assignment_type"] == "unassigned"
    assert add_out[1]["recommended"] is True
    assert out["remove_candidates"][0]["assignment_type"] == "remove"
    assert 0.0 <= add_out[0]["confidence"] <= 1.0
    assert out["summary"] == {"add_count": 2, "remove_count": 1, "reassign_count": 1}


def test_serialize_rescan_preview_includes_identity_names_from_db():
    svc = _service()
    identity_id = uuid4()
    target_identity = uuid4()
    face_in_other = _face(id=42, face_identity_id=target_identity)
    analysis = {
        "identity_id": identity_id,
        "owner_id": uuid4(),
        "reason": None,
        "prototypes": [_unit_vec()],
        "add_candidates": [{"face": face_in_other, "distance": 0.3}],
        "remove_candidates": [],
        "removal_threshold": svc.RESCAN_REMOVAL_THRESHOLD,
    }

    chain = _fluent_chain(all_value=[(target_identity, "Bob")])
    svc.db.query = MagicMock(return_value=chain)

    out = svc._serialize_rescan_preview(analysis)

    assert out["add_candidates"][0]["current_identity_name"] == "Bob"
    assert chain.filter.called


def test_serialize_rescan_preview_skips_identity_query_when_no_add_candidates():
    svc = _service()
    analysis = {
        "identity_id": uuid4(),
        "owner_id": None,
        "reason": "no_reference_faces",
        "prototypes": [],
        "add_candidates": [],
        "remove_candidates": [],
        "removal_threshold": svc.RESCAN_REMOVAL_THRESHOLD,
    }
    svc.db.query = MagicMock()

    out = svc._serialize_rescan_preview(analysis)

    assert out["add_candidates"] == []
    svc.db.query.assert_not_called()


# ---------------------------------------------------------------------------
# _repair_default_faces (DB-driven, with mocked identity/face queries)
# ---------------------------------------------------------------------------

def test_repair_default_faces_leaves_valid_default_alone():
    svc = _service()
    identity_id = uuid4()
    identity = SimpleNamespace(id=identity_id, default_face_id=99)
    # First call: identity list lookup (returns identity, default_face_id truthy).
    # Second call: valid_default face lookup (returns truthy -> continue).
    identity_chain = _fluent_chain(all_value=[identity])
    valid_default_chain = _fluent_chain(first_value=(99,))
    svc.db.query = MagicMock(side_effect=[identity_chain, valid_default_chain])

    svc._repair_default_faces({identity_id})

    # The original default_face_id is preserved (continue short-circuits).
    assert identity.default_face_id == 99


def test_repair_default_faces_assigns_replacement_when_default_invalid():
    svc = _service()
    identity_id = uuid4()
    identity = SimpleNamespace(id=identity_id, default_face_id=42)
    # Q1: identity list -> .all() returns [identity].
    # Q2: valid_default lookup -> .first() returns None (default invalid).
    # Q3: replacement lookup -> .first() returns (101,).
    identity_chain = _fluent_chain(all_value=[identity])
    invalid_default_chain = _fluent_chain(first_value=None)
    replacement_chain = _fluent_chain(first_value=(101,))
    svc.db.query = MagicMock(side_effect=[identity_chain, invalid_default_chain, replacement_chain])

    svc._repair_default_faces({identity_id})

    assert identity.default_face_id == 101


def test_repair_default_faces_clears_default_when_no_replacement_available():
    svc = _service()
    identity_id = uuid4()
    identity = SimpleNamespace(id=identity_id, default_face_id=None)
    # Two calls only: identity (default_face_id falsy -> skip valid_default),
    # then replacement lookup -> None.
    identity_chain = _fluent_chain(all_value=[identity])
    replacement_chain = _fluent_chain(first_value=None)
    svc.db.query = MagicMock(side_effect=[identity_chain, replacement_chain])

    svc._repair_default_faces({identity_id})

    assert identity.default_face_id is None


# ---------------------------------------------------------------------------
# Constants & __init__ (sanity)
# ---------------------------------------------------------------------------

def test_class_level_constants_match_documented_values():
    from app.service.face_cluster import FaceClusterService

    assert FaceClusterService.MAX_RESCAN_PROTOTYPES == 12
    assert FaceClusterService.MAX_RESCAN_REFERENCE_SAMPLE == 200
    assert FaceClusterService.MANUAL_ASSIGNMENT_CONFIDENCE == 0.999
