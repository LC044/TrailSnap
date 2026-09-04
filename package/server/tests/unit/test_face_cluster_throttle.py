"""The CLUSTER_FACES throttle.

A pass re-clusters the owner's entire unassigned pool. With clustering split
out of recognition it runs once per import round, which is still once per
"drop three photos into the watched folder". These tests pin the rule that
decides whether a round is worth a pass, and the two ways it must never fail
closed: an owner who never reaches the increment threshold still gets a pass
once ``MAX_SKIP_AGE`` elapses, and broken bookkeeping clusters rather than
skips.
"""
import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _task(owner_id, payload=None):
    return SimpleNamespace(
        id=uuid4(),
        type="CLUSTER_FACES",
        owner_id=owner_id,
        # Auto-enqueued unless a test says otherwise: that is the shape
        # ``enqueue_cluster_faces`` produces, and the only one the throttle
        # applies to.
        payload=payload if payload is not None else {"auto": True},
        status="processing",
        attempt_count=1,
        next_retry_at=None,
        error=None,
    )


def _owner(session):
    from app.db.models.user import User

    user = User(id=uuid4(), username=f"u{uuid4().hex[:8]}", email=f"{uuid4().hex[:8]}@x.com",
                hashed_password="x")
    session.add(user)
    session.commit()
    return user.id


def _add_faces(session, owner_id, count, *, assigned=False):
    """Insert ``count`` faces owned by ``owner_id``."""
    from app.db.models.face import Face, FaceIdentity
    from app.db.models.photo import Photo

    photo = Photo(
        id=uuid4(),
        filename="p.jpg",
        file_path=f"/{uuid4().hex}.jpg",
        file_type="image",
        owner_id=owner_id,
        is_deleted=False,
    )
    session.add(photo)
    session.flush()

    identity_id = None
    if assigned:
        identity = FaceIdentity(id=uuid4(), identity_name="someone", owner_id=owner_id)
        session.add(identity)
        session.flush()
        identity_id = identity.id

    for _ in range(count):
        session.add(
            Face(
                photo_id=photo.id,
                face_identity_id=identity_id,
                face_feature=[0.1] * 512,
                is_deleted=False,
            )
        )
    session.commit()
    return photo


def _write_baseline(session, owner_id, unassigned, *, age=timedelta(minutes=1)):
    from app.db.models.system import SystemState
    from app.service.tasks.face_cluster import _baseline_key

    session.add(
        SystemState(
            key=_baseline_key(owner_id),
            value=json.dumps(
                {
                    "unassigned": unassigned,
                    "at": (datetime.now() - age).isoformat(),
                }
            ),
        )
    )
    session.commit()


# ---------------------------------------------------------------------------
# should_cluster
# ---------------------------------------------------------------------------


def test_first_pass_runs_with_no_baseline(face_sqlite_session):
    from app.service.tasks.face_cluster import should_cluster

    owner_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 3)

    proceed, _ = should_cluster(face_sqlite_session, owner_id)
    assert proceed is True


def test_small_import_is_skipped(face_sqlite_session):
    """The case the throttle exists for: a few photos must not re-cluster."""
    from app.service.tasks.face_cluster import MIN_NEW_UNASSIGNED, should_cluster

    owner_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 100)
    _write_baseline(face_sqlite_session, owner_id, 100 - (MIN_NEW_UNASSIGNED - 1))

    proceed, reason = should_cluster(face_sqlite_session, owner_id)
    assert proceed is False
    assert str(MIN_NEW_UNASSIGNED - 1) in reason


def test_growth_at_the_threshold_runs(face_sqlite_session):
    from app.service.tasks.face_cluster import MIN_NEW_UNASSIGNED, should_cluster

    owner_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 100)
    _write_baseline(face_sqlite_session, owner_id, 100 - MIN_NEW_UNASSIGNED)

    proceed, _ = should_cluster(face_sqlite_session, owner_id)
    assert proceed is True


def test_stale_baseline_runs_regardless_of_growth(face_sqlite_session):
    """No threshold is lossless.

    A single new face can bridge four previously isolated ones into a cluster,
    so an owner sitting just under the threshold would otherwise never have a
    person created again.
    """
    from app.service.tasks.face_cluster import MAX_SKIP_AGE, should_cluster

    owner_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 100)
    _write_baseline(
        face_sqlite_session, owner_id, 100, age=MAX_SKIP_AGE + timedelta(minutes=1)
    )

    proceed, _ = should_cluster(face_sqlite_session, owner_id)
    assert proceed is True


def test_shrinking_pool_does_not_wedge_the_throttle(face_sqlite_session):
    """Faces deleted or hand-assigned push the pool below the baseline.

    The delta must clamp at zero rather than go negative, and the stale check
    is what eventually re-anchors it.
    """
    from app.service.tasks.face_cluster import should_cluster

    owner_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 10)
    _write_baseline(face_sqlite_session, owner_id, 500)

    proceed, reason = should_cluster(face_sqlite_session, owner_id)
    assert proceed is False
    assert "0 new" in reason


def test_unreadable_baseline_clusters_instead_of_skipping(face_sqlite_session):
    from app.db.models.system import SystemState
    from app.service.tasks.face_cluster import _baseline_key, should_cluster

    owner_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 100)
    face_sqlite_session.add(
        SystemState(key=_baseline_key(owner_id), value="not json")
    )
    face_sqlite_session.commit()

    proceed, _ = should_cluster(face_sqlite_session, owner_id)
    assert proceed is True


def test_other_owners_faces_do_not_count_towards_the_threshold(face_sqlite_session):
    from app.service.tasks.face_cluster import MIN_NEW_UNASSIGNED, should_cluster

    owner_id = _owner(face_sqlite_session)
    other_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 20)
    _write_baseline(face_sqlite_session, owner_id, 20)
    _add_faces(face_sqlite_session, other_id, MIN_NEW_UNASSIGNED * 10)

    proceed, _ = should_cluster(face_sqlite_session, owner_id)
    assert proceed is False


def test_assigned_faces_do_not_count_towards_the_threshold(face_sqlite_session):
    """The count must match the pool a pass would actually cluster."""
    from app.service.tasks.face_cluster import (
        MIN_NEW_UNASSIGNED,
        count_unassigned_faces,
        should_cluster,
    )

    owner_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 20)
    _write_baseline(face_sqlite_session, owner_id, 20)
    _add_faces(face_sqlite_session, owner_id, MIN_NEW_UNASSIGNED * 10, assigned=True)

    assert count_unassigned_faces(face_sqlite_session, owner_id) == 20
    proceed, _ = should_cluster(face_sqlite_session, owner_id)
    assert proceed is False


# ---------------------------------------------------------------------------
# Baseline bookkeeping
# ---------------------------------------------------------------------------


def test_baseline_records_the_pool_left_behind(face_sqlite_session):
    """Leftovers are noise the pass already examined, not new information."""
    from app.service.tasks.face_cluster import (
        _load_baseline,
        count_unassigned_faces,
        record_baseline,
    )

    owner_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 7)

    record_baseline(
        face_sqlite_session, owner_id, count_unassigned_faces(face_sqlite_session, owner_id)
    )
    stored, at = _load_baseline(face_sqlite_session, owner_id)
    assert stored == 7
    assert isinstance(at, datetime)


def test_baseline_is_overwritten_not_duplicated(face_sqlite_session):
    from app.db.models.system import SystemState
    from app.service.tasks.face_cluster import _baseline_key, _load_baseline, record_baseline

    owner_id = _owner(face_sqlite_session)
    record_baseline(face_sqlite_session, owner_id, 3)
    record_baseline(face_sqlite_session, owner_id, 9)

    rows = (
        face_sqlite_session.query(SystemState)
        .filter(SystemState.key == _baseline_key(owner_id))
        .all()
    )
    assert len(rows) == 1
    assert _load_baseline(face_sqlite_session, owner_id)[0] == 9


def test_baselines_are_per_owner(face_sqlite_session):
    from app.service.tasks.face_cluster import _load_baseline, record_baseline

    first = _owner(face_sqlite_session)
    second = _owner(face_sqlite_session)
    record_baseline(face_sqlite_session, first, 3)
    record_baseline(face_sqlite_session, second, 9)

    assert _load_baseline(face_sqlite_session, first)[0] == 3
    assert _load_baseline(face_sqlite_session, second)[0] == 9


def test_failed_pass_leaves_the_baseline_alone(face_sqlite_session):
    """A crashed pass must not look like a completed one.

    Recording the baseline anyway would make the next round skip and leave the
    library unclustered until MAX_SKIP_AGE.
    """
    from app.service.tasks import face_cluster

    owner_id = _owner(face_sqlite_session)
    service = MagicMock()
    service.process_unassigned_faces.side_effect = RuntimeError("boom")

    with patch("app.db.session.SessionLocal", return_value=face_sqlite_session), \
         patch("app.service.face_cluster.FaceClusterService", return_value=service), \
         patch.object(face_sqlite_session, "close"), \
         pytest.raises(RuntimeError):
        face_cluster._cluster_in_thread(owner_id)

    assert face_cluster._load_baseline(face_sqlite_session, owner_id) == (None, None)


def test_completed_pass_records_the_baseline(face_sqlite_session):
    from app.service.tasks import face_cluster

    owner_id = _owner(face_sqlite_session)
    _add_faces(face_sqlite_session, owner_id, 4)

    with patch("app.db.session.SessionLocal", return_value=face_sqlite_session), \
         patch("app.service.face_cluster.FaceClusterService", return_value=MagicMock()), \
         patch.object(face_sqlite_session, "close"):
        face_cluster._cluster_in_thread(owner_id)

    assert face_cluster._load_baseline(face_sqlite_session, owner_id)[0] == 4


# ---------------------------------------------------------------------------
# Strategy wiring
# ---------------------------------------------------------------------------


def _db_without_pending_recognition():
    db = MagicMock(name="db")
    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = None
    db.query.return_value = query
    return db


def _process(task, *, proceed, reason="stub"):
    from app.service.tasks.face_cluster import ClusterFacesStrategy

    db = _db_without_pending_recognition()
    with patch(
        "app.service.tasks.face_cluster.should_cluster", return_value=(proceed, reason)
    ) as gate, \
         patch("app.service.tasks.face_cluster._cluster_in_thread") as cluster:
        result = _run(ClusterFacesStrategy().process(MagicMock(), task, db))
    return result, cluster, gate


def test_strategy_skips_when_the_throttle_says_so():
    result, cluster, _ = _process(_task(uuid4()), proceed=False, reason="only 2 new")
    cluster.assert_not_called()
    assert result == {"status": "skipped", "reason": "only 2 new"}


def test_strategy_clusters_when_the_throttle_allows_it():
    result, cluster, _ = _process(_task(uuid4()), proceed=True)
    cluster.assert_called_once()
    assert result == {"status": "success"}


def test_a_hand_created_task_bypasses_the_throttle():
    """``POST /tasks/`` lets a user ask for a re-cluster directly.

    Such a row carries no ``payload['auto']``. Throttling it would make the
    button look broken: the task completes, the logs are clean, and no new
    people appear.
    """
    task = _task(uuid4(), payload={})
    result, cluster, gate = _process(task, proceed=False)
    gate.assert_not_called()
    cluster.assert_called_once()
    assert result == {"status": "success"}


def test_enqueue_marks_its_task_as_auto():
    """The pipeline's own rows must be throttleable.

    Without the flag every auto-enqueued pass would take the bypass above and
    the throttle would never fire at all.
    """
    from app.service.tasks.face_cluster import enqueue_cluster_faces

    owner_id = uuid4()
    db = MagicMock()
    with patch("app.crud.task.get_latest_task_by_type_and_owner", return_value=None), \
         patch("app.crud.task.add_task", return_value="created") as add_task:
        enqueue_cluster_faces(db, owner_id)

    assert add_task.call_args.args[2]["auto"] is True


def test_broken_throttle_clusters_rather_than_skipping():
    from sqlalchemy.exc import SQLAlchemyError

    from app.service.tasks.face_cluster import ClusterFacesStrategy

    db = _db_without_pending_recognition()
    with patch(
        "app.service.tasks.face_cluster.should_cluster",
        side_effect=SQLAlchemyError("no such table"),
    ), patch("app.service.tasks.face_cluster._cluster_in_thread") as cluster:
        result = _run(ClusterFacesStrategy().process(MagicMock(), _task(uuid4()), db))

    cluster.assert_called_once()
    assert result == {"status": "success"}
    db.rollback.assert_called_once()


def test_throttle_runs_after_the_recognition_defer_guard():
    """Order matters.

    Mid-import the pool is still growing, so evaluating the threshold before
    recognition finishes would measure a moving target and could burn the
    owner's increment on a partial pool.
    """
    from app.service.tasks.face_cluster import ClusterFacesStrategy

    db = MagicMock(name="db")
    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = object()  # recognition still in flight
    db.query.return_value = query

    task = _task(uuid4())
    with patch("app.service.tasks.face_cluster.should_cluster") as gate, \
         patch("app.service.tasks.face_cluster._cluster_in_thread") as cluster:
        result = _run(ClusterFacesStrategy().process(MagicMock(), task, db))

    assert result is None
    gate.assert_not_called()
    cluster.assert_not_called()
