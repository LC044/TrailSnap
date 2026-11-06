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

    * ``query(Face.id, Face.face_feature)`` -- the unassigned scalar select.
      It is now consumed by streaming rather than ``.all()``, so both
      ``count()`` and ``yield_per()`` are answered from ``rows``.
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
            q.count.return_value = len(rows)
            q.yield_per.return_value = list(rows)
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


def test_cluster_dispatch_requires_owner():
    from app.service.face_cluster import FaceClusterService
    with pytest.raises(ValueError, match="owner"):
        FaceClusterService(MagicMock())._cluster_unassigned_faces(None)


def test_cluster_dispatch_uses_appearance_service():
    from app.service.face_cluster import FaceClusterService
    owner = uuid4()
    db = MagicMock()
    with patch("app.service.face_appearance_clusters.process_faces") as process:
        FaceClusterService(db)._cluster_unassigned_faces(owner)
    process.assert_called_once_with(db, owner)
