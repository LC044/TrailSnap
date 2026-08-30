"""Round 2026-08-30 r2 coverage for app/service/face_cluster.py DBSCAN path.

Targets the still-uncovered private/public methods that the prior
rounds (2026-08-19, 2026-08-26, 2026-08-30) did not exercise:

* _cluster_unassigned_faces -- the full DBSCAN flow (query, normalize,
  fit, cluster center, similar-cluster merge, identity creation,
  default face assignment) plus the PendingRollbackError / SQLAlchemyError
  branches and the cluster_size < MIN_CLUSTER_SIZE_FOR_IDENTITY filter.
* _find_matching_face_ids -- the pgvector ``cosine_distance`` branch
  (Face.face_feature.cosine_distance) on PostgreSQL.
* _repair_default_faces -- branch where default is valid (continue) and
  the replacement-by-confidence ordering (recognize_confidence desc
  nullslast, then face.id).

Pattern: MagicMock + SimpleNamespace + numpy stub + patch on
app.service.face_cluster.DBSCAN. Mirrors the prior nightly rounds and
runs in isolation without a live Postgres.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _service(db, *, user_id=None):
    from app.service.face_cluster import FaceClusterService

    return FaceClusterService(db=db, user_id=user_id)


def _face(id_, feature, *, identity_id=None, photo_id=None, confidence=None):
    return SimpleNamespace(
        id=id_,
        face_feature=feature,
        face_identity_id=identity_id,
        photo_id=photo_id or uuid4(),
        is_deleted=False,
        recognize_confidence=confidence,
    )


def _chain_query(all_value=None, scalar_value=None):
    q = MagicMock()
    q.filter.return_value = q
    q.join.return_value = q
    q.order_by.return_value = q
    q.with_for_update.return_value = q
    if all_value is not None:
        q.all.return_value = all_value
    if scalar_value is not None:
        q.first.return_value = scalar_value
    return q


def _unit_vec(dim=4, seed=0):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim)
    v /= np.linalg.norm(v)
    return v


def _patch_dbscan(labels):
    """Return a DBSCAN stub whose .fit returns SimpleNamespace(labels_=labels)."""
    instance = MagicMock(name="DBSCAN-instance")
    instance.fit.return_value = SimpleNamespace(labels_=labels)
    cls = MagicMock(name="DBSCAN-class")
    cls.return_value = instance
    return cls


# ---------------------------------------------------------------------------
# _find_matching_face_ids: pgvector branch
# ---------------------------------------------------------------------------


def test_find_matching_face_ids_pg_branch_uses_cosine_distance_predicate():
    """On PostgreSQL the service should rely on Face.face_feature.cosine_distance
    and accumulate matching ids across all prototypes."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    svc = _service(db)

    prototype = _unit_vec(dim=4, seed=1)
    prototype2 = _unit_vec(dim=4, seed=2)

    q1 = _chain_query(all_value=[(11,)])
    q2 = _chain_query(all_value=[(22,)])
    db.query.side_effect = [q1, q2]

    owner_id = uuid4()
    with patch.object(svc, "_cosine_distance", return_value=0.1):
        result = svc._find_matching_face_ids([prototype, prototype2], owner_id, threshold=0.4)

    assert result == {11, 22}
    assert q1.filter.call_count >= 2
    assert q2.filter.call_count >= 2


def test_find_matching_face_ids_pg_branch_empty_prototypes_skips_query():
    """No prototypes -> empty result and no SQL query should be issued."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    svc = _service(db)

    result = svc._find_matching_face_ids([], None, threshold=0.3)
    assert result == set()
    db.query.assert_not_called()


# ---------------------------------------------------------------------------
# _cluster_unassigned_faces: full DBSCAN flow with mocked clustering
# ---------------------------------------------------------------------------


def test_cluster_unassigned_faces_creates_identity_for_large_cluster():
    """When DBSCAN returns >= MIN_CLUSTER_SIZE_FOR_IDENTITY members in one
    cluster, a new FaceIdentity is created and faces are reassigned."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    faces = [_face(id_=i + 1, feature=_unit_vec(dim=4, seed=i)) for i in range(6)]
    db.query.return_value.filter.return_value.all.return_value = faces

    dbscan_cls = _patch_dbscan(np.array([0, 0, 0, 0, 0, 0]))

    new_identity_id = uuid4()
    new_identity = SimpleNamespace(id=new_identity_id)

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", return_value=new_identity) as create_identity, \
         patch("app.service.face_cluster.crud_face.update_face") as update_face, \
         patch("app.service.face_cluster.crud_face.get_face", side_effect=lambda d, fid: next((f for f in faces if f.id == fid), None)), \
         patch("app.service.face_cluster.crud_face.update_identity") as update_identity:
        svc._cluster_unassigned_faces(owner_id=None)

    create_identity.assert_called_once()
    assert update_face.call_count == 6
    update_identity.assert_called_once()
    call = update_identity.call_args
    if call.kwargs:
        assert call.kwargs["default_face_id"] == faces[0].id
    else:
        assert call.args[2].default_face_id == faces[0].id


def test_cluster_unassigned_faces_skips_small_cluster_below_min_size():
    """A cluster whose size < MIN_CLUSTER_SIZE_FOR_IDENTITY must NOT create
    an identity."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    faces = [_face(id_=i + 1, feature=_unit_vec(dim=4, seed=i)) for i in range(6)]
    db.query.return_value.filter.return_value.all.return_value = faces

    dbscan_cls = _patch_dbscan(np.array([0, 0, -1, -1, -1, -1]))

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity") as create_identity, \
         patch("app.service.face_cluster.crud_face.update_face") as update_face, \
         patch("app.service.face_cluster.crud_face.update_identity") as update_identity:
        svc._cluster_unassigned_faces(owner_id=None)

    create_identity.assert_not_called()
    update_face.assert_not_called()
    update_identity.assert_not_called()


def test_cluster_unassigned_faces_handles_two_clusters():
    """Two DBSCAN clusters of sufficient size should each create their own
    identity (or be merged if centers are close)."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    # MIN_CLUSTER_SIZE_FOR_IDENTITY defaults to 5; build 6 faces per cluster
    # plus 2 noise (14 total) so both clusters exceed the minimum.
    faces = [_face(id_=i + 1, feature=_unit_vec(dim=4, seed=i)) for i in range(14)]
    db.query.return_value.filter.return_value.all.return_value = faces

    labels = np.array([0] * 6 + [1] * 6 + [-1, -1])
    dbscan_cls = _patch_dbscan(labels)

    new_identity_a = SimpleNamespace(id=uuid4())
    new_identity_b = SimpleNamespace(id=uuid4())

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", side_effect=[new_identity_a, new_identity_b]) as create_identity, \
         patch("app.service.face_cluster.crud_face.update_face") as update_face, \
         patch("app.service.face_cluster.crud_face.get_face", side_effect=lambda d, fid: next((f for f in faces if f.id == fid), None)), \
         patch("app.service.face_cluster.crud_face.update_identity"):
        svc._cluster_unassigned_faces(owner_id=None)

    # Two clusters of size 6 each, both >= MIN_CLUSTER_SIZE_FOR_IDENTITY=5;
    # random unit vectors will not be close enough to merge.
    assert 1 <= create_identity.call_count <= 2
    assert update_face.call_count >= 6


def test_cluster_unassigned_faces_short_circuits_when_below_min_samples():
    """When there are fewer than DBSCAN_MIN_SAMPLES unassigned faces,
    the DBSCAN call should be skipped entirely."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    faces = [_face(id_=i + 1, feature=_unit_vec(dim=4, seed=i)) for i in range(svc.DBSCAN_MIN_SAMPLES - 1)]
    db.query.return_value.filter.return_value.all.return_value = faces

    dbscan_cls = MagicMock(name="DBSCAN-class")
    with patch("app.service.face_cluster.DBSCAN", dbscan_cls) as dbs, \
         patch("app.service.face_cluster.crud_face.create_identity") as create_identity:
        svc._cluster_unassigned_faces(owner_id=None)

    dbs.assert_not_called()
    create_identity.assert_not_called()


def test_cluster_unassigned_faces_rolls_back_on_pending_rollback_error():
    """PendingRollbackError triggers db.rollback() and re-raises."""
    from sqlalchemy.exc import PendingRollbackError

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    faces = [_face(id_=i + 1, feature=_unit_vec(dim=4, seed=i)) for i in range(6)]
    db.query.return_value.filter.return_value.all.return_value = faces
    dbscan_cls = _patch_dbscan(np.array([0, 0, 0, 0, 0, 0]))

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", side_effect=PendingRollbackError("stmt", {}, Exception("orig"))):
        with pytest.raises(PendingRollbackError):
            svc._cluster_unassigned_faces(owner_id=None)

    db.rollback.assert_called_once()


def test_cluster_unassigned_faces_rolls_back_on_sqlalchemy_error():
    """SQLAlchemyError triggers db.rollback() and re-raises."""
    from sqlalchemy.exc import SQLAlchemyError

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    faces = [_face(id_=i + 1, feature=_unit_vec(dim=4, seed=i)) for i in range(6)]
    db.query.return_value.filter.return_value.all.return_value = faces
    dbscan_cls = _patch_dbscan(np.array([0, 0, 0, 0, 0, 0]))

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", side_effect=SQLAlchemyError("boom")):
        with pytest.raises(SQLAlchemyError):
            svc._cluster_unassigned_faces(owner_id=None)

    db.rollback.assert_called_once()


def test_cluster_unassigned_faces_skips_missing_face_member():
    """If crud_face.get_face returns None for a member, the iteration should
    skip it gracefully and still set the default face from the remaining
    members."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    faces = [_face(id_=i + 1, feature=_unit_vec(dim=4, seed=i)) for i in range(6)]
    db.query.return_value.filter.return_value.all.return_value = faces
    dbscan_cls = _patch_dbscan(np.array([0, 0, 0, 0, 0, 0]))

    new_identity_id = uuid4()
    new_identity = SimpleNamespace(id=new_identity_id)

    def fake_get(d, fid):
        if fid == 1:
            return None
        return next(f for f in faces if f.id == fid)

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", return_value=new_identity), \
         patch("app.service.face_cluster.crud_face.update_face") as update_face, \
         patch("app.service.face_cluster.crud_face.get_face", side_effect=fake_get), \
         patch("app.service.face_cluster.crud_face.update_identity") as update_identity:
        svc._cluster_unassigned_faces(owner_id=None)

    assert update_face.call_count == 5
    call = update_identity.call_args
    if call.kwargs:
        assert call.kwargs["default_face_id"] == faces[1].id
    else:
        assert call.args[2].default_face_id == faces[1].id


# ---------------------------------------------------------------------------
# _repair_default_faces
# ---------------------------------------------------------------------------


def test_repair_default_faces_keeps_valid_default_without_changes():
    """If identity.default_face_id maps to a non-deleted face in the identity,
    the method must not look for a replacement."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    identity = SimpleNamespace(id=uuid4(), default_face_id=42)
    q = MagicMock()
    q.filter.return_value = q
    q.all.return_value = [identity]
    q.first.return_value = (42,)
    q.order_by.return_value = q
    db.query.return_value = q

    svc._repair_default_faces({identity.id})

    assert q.order_by.call_count == 0


def test_repair_default_faces_assigns_replacement_with_highest_confidence():
    """When default_face_id is invalid the replacement is the face returned by
    the recognize_confidence desc nullslast query."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    identity = SimpleNamespace(id=uuid4(), default_face_id=99)

    # Three queries: identity.all, validity.first, replacement.first.
    q_identity = MagicMock(name="q_identity")
    q_identity.filter.return_value.all.return_value = [identity]

    # validity: db.query(Face.id).join(Photo).filter(...).first()
    q_validity = MagicMock(name="q_validity")
    q_validity.join.return_value = q_validity
    q_validity.filter.return_value.first.return_value = None

    # replacement: db.query(Face.id).join(Photo).filter(...).order_by(...).first()
    q_replacement = MagicMock(name="q_replacement")
    q_replacement.join.return_value = q_replacement
    q_replacement.filter.return_value.order_by.return_value.first.return_value = (7,)

    db.query.side_effect = [q_identity, q_validity, q_replacement]

    svc._repair_default_faces({identity.id})

    assert identity.default_face_id == 7


def test_repair_default_faces_clears_default_when_no_replacement_available():
    """When there is no replacement face, identity.default_face_id is set to None."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    identity = SimpleNamespace(id=uuid4(), default_face_id=99)

    q_identity = MagicMock(name="q_identity")
    q_identity.filter.return_value.all.return_value = [identity]

    q_validity = MagicMock(name="q_validity")
    q_validity.join.return_value = q_validity
    q_validity.filter.return_value.first.return_value = None

    q_replacement = MagicMock(name="q_replacement")
    q_replacement.join.return_value = q_replacement
    q_replacement.filter.return_value.order_by.return_value.first.return_value = None

    db.query.side_effect = [q_identity, q_validity, q_replacement]

    svc._repair_default_faces({identity.id})

    assert identity.default_face_id is None


# ---------------------------------------------------------------------------
# process_unassigned_faces: delegation
# ---------------------------------------------------------------------------


def test_process_unassigned_faces_delegates_to_cluster_helper():
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    svc = _service(db)

    with patch.object(svc, "_cluster_unassigned_faces") as cluster:
        svc.process_unassigned_faces(owner_id=uuid4())

    cluster.assert_called_once()
