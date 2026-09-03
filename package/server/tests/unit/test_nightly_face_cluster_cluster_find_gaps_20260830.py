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


def _cluster_db(rows, *, live_ids=None):
    """Fake Session for the scalar-select / bulk-update clustering flow.

    ``_cluster_unassigned_faces`` no longer hydrates ORM ``Face`` entities nor
    writes members one by one, so the old
    ``db.query().filter().all()`` stub no longer matches. Three query shapes
    are dispatched here:

    * ``query(Face.id, Face.face_feature)`` -- the unassigned scalar select,
      answered with ``rows`` of ``(face_id, embedding)``.
    * ``query(Face)`` -- the per-cluster bulk UPDATE.
    * anything else -- the live-member id select (and the owner subquery),
      answered with ``live_ids``.
    """
    from app.db.models.face import Face

    if live_ids is None:
        live_ids = [row[0] for row in rows]

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    update_calls = []

    def _query(*args):
        q = MagicMock()
        q.filter.return_value = q
        q.join.return_value = q
        q.order_by.return_value = q
        if len(args) == 2:
            q.all.return_value = list(rows)
        elif args and args[0] is Face:
            def _update(values, **kwargs):
                update_calls.append(values)
                return len(live_ids)
            q.update.side_effect = _update
        else:
            q.all.return_value = [(face_id,) for face_id in live_ids]
        return q

    db.query.side_effect = _query
    db.update_calls = update_calls
    return db


def _rows(count, *, start=1):
    """(face_id, embedding) pairs shaped like the scalar select's output."""
    return [(index + start, _unit_vec(dim=4, seed=index)) for index in range(count)]


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
    from app.db.models.face import Face

    rows = _rows(6)
    db = _cluster_db(rows)
    svc = _service(db)

    dbscan_cls = _patch_dbscan(np.array([0, 0, 0, 0, 0, 0]))

    new_identity_id = uuid4()
    new_identity = SimpleNamespace(id=new_identity_id)

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", return_value=new_identity) as create_identity, \
         patch("app.service.face_cluster.crud_face.update_identity") as update_identity:
        svc._cluster_unassigned_faces(owner_id=None)

    create_identity.assert_called_once()
    # One bulk UPDATE for the whole cluster, not one statement per member.
    assert len(db.update_calls) == 1
    values = db.update_calls[0]
    assert values[Face.face_identity_id] == new_identity_id
    assert values[Face.recognize_confidence] == 0.9

    update_identity.assert_called_once()
    call = update_identity.call_args
    if call.kwargs:
        assert call.kwargs["default_face_id"] == rows[0][0]
    else:
        assert call.args[2].default_face_id == rows[0][0]
    db.commit.assert_called()


def test_cluster_unassigned_faces_uses_per_user_eps_not_global_config():
    """eps must come from the user's resolved threshold.

    Reading ``config_manager.config`` here applied the global default to every
    user, silently ignoring a per-user face_cluster_threshold.
    """
    db = _cluster_db(_rows(6))
    svc = _service(db)
    svc.DBSCAN_EPS = 0.33

    dbscan_cls = _patch_dbscan(np.array([-1] * 6))

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity"):
        svc._cluster_unassigned_faces(owner_id=None)

    assert dbscan_cls.call_args.kwargs["eps"] == 0.33


def test_cluster_unassigned_faces_skips_small_cluster_below_min_size():
    """A cluster whose size < MIN_CLUSTER_SIZE_FOR_IDENTITY must NOT create
    an identity."""
    db = _cluster_db(_rows(6))
    svc = _service(db)

    dbscan_cls = _patch_dbscan(np.array([0, 0, -1, -1, -1, -1]))

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity") as create_identity, \
         patch("app.service.face_cluster.crud_face.update_identity") as update_identity:
        svc._cluster_unassigned_faces(owner_id=None)

    dbscan_cls.assert_called_once()
    create_identity.assert_not_called()
    update_identity.assert_not_called()
    assert db.update_calls == []


def test_cluster_unassigned_faces_handles_two_clusters():
    """Two DBSCAN clusters of sufficient size should each create their own
    identity (or be merged if centers are close)."""
    # MIN_CLUSTER_SIZE_FOR_IDENTITY defaults to 5; build 6 faces per cluster
    # plus 2 noise (14 total) so both clusters exceed the minimum.
    db = _cluster_db(_rows(14))
    svc = _service(db)

    labels = np.array([0] * 6 + [1] * 6 + [-1, -1])
    dbscan_cls = _patch_dbscan(labels)

    new_identity_a = SimpleNamespace(id=uuid4())
    new_identity_b = SimpleNamespace(id=uuid4())

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", side_effect=[new_identity_a, new_identity_b]) as create_identity, \
         patch("app.service.face_cluster.crud_face.update_identity"):
        svc._cluster_unassigned_faces(owner_id=None)

    # Two clusters of size 6 each, both >= MIN_CLUSTER_SIZE_FOR_IDENTITY=5;
    # random unit vectors will not be close enough to merge.
    assert 1 <= create_identity.call_count <= 2
    assert len(db.update_calls) == create_identity.call_count


def test_cluster_unassigned_faces_short_circuits_when_below_min_samples():
    """When there are fewer than DBSCAN_MIN_SAMPLES unassigned faces,
    the DBSCAN call should be skipped entirely."""
    db = _cluster_db(_rows(4))
    svc = _service(db)
    assert svc.DBSCAN_MIN_SAMPLES == 5

    dbscan_cls = MagicMock(name="DBSCAN-class")
    with patch("app.service.face_cluster.DBSCAN", dbscan_cls) as dbs, \
         patch("app.service.face_cluster.crud_face.create_identity") as create_identity:
        svc._cluster_unassigned_faces(owner_id=None)

    dbs.assert_not_called()
    create_identity.assert_not_called()


def test_cluster_unassigned_faces_rolls_back_on_pending_rollback_error():
    """PendingRollbackError triggers db.rollback() and re-raises."""
    from sqlalchemy.exc import PendingRollbackError

    db = _cluster_db(_rows(6))
    svc = _service(db)
    dbscan_cls = _patch_dbscan(np.array([0, 0, 0, 0, 0, 0]))

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", side_effect=PendingRollbackError("stmt", {}, Exception("orig"))):
        with pytest.raises(PendingRollbackError):
            svc._cluster_unassigned_faces(owner_id=None)

    db.rollback.assert_called_once()


def test_cluster_unassigned_faces_rolls_back_on_sqlalchemy_error():
    """SQLAlchemyError triggers db.rollback() and re-raises."""
    from sqlalchemy.exc import SQLAlchemyError

    db = _cluster_db(_rows(6))
    svc = _service(db)
    dbscan_cls = _patch_dbscan(np.array([0, 0, 0, 0, 0, 0]))

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", side_effect=SQLAlchemyError("boom")):
        with pytest.raises(SQLAlchemyError):
            svc._cluster_unassigned_faces(owner_id=None)

    db.rollback.assert_called_once()


def test_cluster_unassigned_faces_skips_vanished_face_member():
    """A member deleted between the select and the write is excluded.

    The live-id re-check replaces the old per-member ``get_face`` lookup, and
    the default face must come from the surviving members.
    """
    rows = _rows(6)
    # Face 1 disappeared (deleted) after the unassigned select ran.
    db = _cluster_db(rows, live_ids=[row[0] for row in rows[1:]])
    svc = _service(db)
    dbscan_cls = _patch_dbscan(np.array([0, 0, 0, 0, 0, 0]))

    new_identity = SimpleNamespace(id=uuid4())

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", return_value=new_identity), \
         patch("app.service.face_cluster.crud_face.update_identity") as update_identity:
        svc._cluster_unassigned_faces(owner_id=None)

    call = update_identity.call_args
    if call.kwargs:
        assert call.kwargs["default_face_id"] == rows[1][0]
    else:
        assert call.args[2].default_face_id == rows[1][0]


def test_cluster_unassigned_faces_skips_cluster_with_no_live_members():
    """If every member vanished, no identity write happens for that cluster."""
    db = _cluster_db(_rows(6), live_ids=[])
    svc = _service(db)
    dbscan_cls = _patch_dbscan(np.array([0, 0, 0, 0, 0, 0]))

    with patch("app.service.face_cluster.DBSCAN", dbscan_cls), \
         patch("app.service.face_cluster.crud_face.create_identity", return_value=SimpleNamespace(id=uuid4())), \
         patch("app.service.face_cluster.crud_face.update_identity") as update_identity:
        svc._cluster_unassigned_faces(owner_id=None)

    assert db.update_calls == []
    update_identity.assert_not_called()


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
