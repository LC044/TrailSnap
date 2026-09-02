"""Regression tests for the vectorised SQLite face-clustering path.

Commit 8adff5d added a SQLite fallback that loaded every candidate ``Face``
entity and scored it in a Python loop. These tests lock down the behaviour
the vectorised replacement must preserve, plus the two defects the original
fallback shipped with:

* ``_find_matching_face_ids`` compared *raw* ``face_feature`` values against
  *normalised* prototypes, so the distance was scaled by the candidate's norm
  and real matches were dropped.
* ``_cluster_unassigned_faces`` had no ``owner_id`` filter, so DBSCAN mixed
  faces across accounts.

They run against a real SQLite engine because the code path streams a cursor
and multiplies matrices; a MagicMock would only assert the shape of the mock.
"""

from unittest.mock import patch

import numpy as np
import pytest

from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service.face_cluster import FaceClusterService
from app.service.face_vector_cache import FaceVectorCache, face_vector_cache

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]

DIM = 512


def _vec(*head):
    """Build a DIM-length vector from its leading components."""
    tail = [0.0] * (DIM - len(head))
    return list(head) + tail


def _make_user(session, name):
    user = User(username=name, email=f"{name}@example.com", hashed_password="unused")
    session.add(user)
    session.flush()
    return user


def _add_face(session, user, feature, *, identity_id=None, deleted=False, photo_deleted=False):
    photo = Photo(
        filename=f"{user.username}-{id(feature)}.jpg",
        file_path=f"/{user.username}-{id(feature)}.jpg",
        file_type=FileType.image,
        owner_id=user.id,
        is_deleted=photo_deleted,
    )
    session.add(photo)
    session.flush()
    face = Face(
        photo_id=photo.id,
        face_identity_id=identity_id,
        face_feature=feature,
        is_deleted=deleted,
    )
    session.add(face)
    session.flush()
    return face


# ---------------------------------------------------------------------------
# _find_matching_face_ids -- normalisation regression
# ---------------------------------------------------------------------------


def test_find_matching_face_ids_normalises_stored_vectors(face_sqlite_session):
    """A match must be found regardless of the stored vector's magnitude.

    The pre-fix code did ``1 - np.dot(raw_feature, prototype)``. With a stored
    norm of 10 that yields a distance of -9, and with a norm of 0.05 it yields
    0.95 -- the latter silently failing the threshold despite being the same
    direction as the prototype. Both must match now.
    """
    user = _make_user(face_sqlite_session, "norm-user")
    identity = FaceIdentity(identity_name="P", owner_id=user.id)
    face_sqlite_session.add(identity)
    face_sqlite_session.flush()

    large = _add_face(face_sqlite_session, user, _vec(10.0, 0.0), identity_id=identity.id)
    small = _add_face(face_sqlite_session, user, _vec(0.05, 0.0), identity_id=identity.id)
    orthogonal = _add_face(face_sqlite_session, user, _vec(0.0, 1.0), identity_id=identity.id)
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    prototype = np.array(_vec(1.0, 0.0), dtype=np.float64)

    matched = svc._find_matching_face_ids([prototype], user.id, threshold=0.4)

    assert large.id in matched, "large-norm vector must normalise to a match"
    assert small.id in matched, "small-norm vector must normalise to a match"
    assert orthogonal.id not in matched, "orthogonal vector must stay unmatched"


def test_find_matching_face_ids_excludes_deleted_faces_and_photos(face_sqlite_session):
    """Deleted rows are masked out even though the cache still holds them."""
    user = _make_user(face_sqlite_session, "mask-user")
    live = _add_face(face_sqlite_session, user, _vec(1.0, 0.0))
    dead_face = _add_face(face_sqlite_session, user, _vec(1.0, 0.0), deleted=True)
    dead_photo = _add_face(face_sqlite_session, user, _vec(1.0, 0.0), photo_deleted=True)
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    matched = svc._find_matching_face_ids([np.array(_vec(1.0, 0.0))], user.id, threshold=0.4)

    assert matched == {live.id}
    assert dead_face.id not in matched
    assert dead_photo.id not in matched


def test_find_matching_face_ids_scopes_to_owner(face_sqlite_session):
    """Another account's identical face must never be returned."""
    mine = _make_user(face_sqlite_session, "mine")
    theirs = _make_user(face_sqlite_session, "theirs")
    my_face = _add_face(face_sqlite_session, mine, _vec(1.0, 0.0))
    their_face = _add_face(face_sqlite_session, theirs, _vec(1.0, 0.0))
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    matched = svc._find_matching_face_ids([np.array(_vec(1.0, 0.0))], mine.id, threshold=0.4)

    assert matched == {my_face.id}
    assert their_face.id not in matched


# ---------------------------------------------------------------------------
# assign_face_to_identity
# ---------------------------------------------------------------------------


def _threshold_config(value):
    class _AI:
        face_cluster_threshold = value

    class _Config:
        ai = _AI()

    return _Config()


def test_assign_face_to_identity_excludes_self(face_sqlite_session):
    """A face must not be matched against itself."""
    user = _make_user(face_sqlite_session, "self-user")
    identity = FaceIdentity(identity_name="P", owner_id=user.id)
    face_sqlite_session.add(identity)
    face_sqlite_session.flush()
    lonely = _add_face(face_sqlite_session, user, _vec(1.0, 0.0), identity_id=identity.id)
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    with patch(
        "app.service.face_cluster.config_manager.get_user_config",
        return_value=_threshold_config(0.4),
    ), patch("app.service.face_cluster.crud_face.update_face") as update:
        result = svc.assign_face_to_identity(lonely.id, _vec(1.0, 0.0), user.id)

    assert result is None
    update.assert_not_called()


def test_assign_face_to_identity_ignores_other_owner(face_sqlite_session):
    """Cross-account nearest neighbours must not leak an identity."""
    mine = _make_user(face_sqlite_session, "a-user")
    theirs = _make_user(face_sqlite_session, "b-user")
    their_identity = FaceIdentity(identity_name="Theirs", owner_id=theirs.id)
    face_sqlite_session.add(their_identity)
    face_sqlite_session.flush()
    _add_face(face_sqlite_session, theirs, _vec(1.0, 0.0), identity_id=their_identity.id)
    target = _add_face(face_sqlite_session, mine, _vec(1.0, 0.0))
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    with patch(
        "app.service.face_cluster.config_manager.get_user_config",
        return_value=_threshold_config(0.4),
    ), patch("app.service.face_cluster.crud_face.update_face") as update:
        result = svc.assign_face_to_identity(target.id, _vec(1.0, 0.0), mine.id)

    assert result is None
    update.assert_not_called()


def test_assign_face_to_identity_picks_closest_of_many(face_sqlite_session):
    """With several identities present the closest one wins."""
    user = _make_user(face_sqlite_session, "multi-user")
    close = FaceIdentity(identity_name="Close", owner_id=user.id)
    far = FaceIdentity(identity_name="Far", owner_id=user.id)
    face_sqlite_session.add_all([close, far])
    face_sqlite_session.flush()

    _add_face(face_sqlite_session, user, _vec(0.0, 1.0), identity_id=far.id)
    _add_face(face_sqlite_session, user, _vec(0.98, 0.199), identity_id=close.id)
    target = _add_face(face_sqlite_session, user, _vec(1.0, 0.0))
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    with patch(
        "app.service.face_cluster.config_manager.get_user_config",
        return_value=_threshold_config(0.4),
    ), patch("app.service.face_cluster.crud_face.update_face"):
        result = svc.assign_face_to_identity(target.id, _vec(1.0, 0.0), user.id)

    assert result == close.id


# ---------------------------------------------------------------------------
# Complexity guard: the fix must not reload embeddings per face
# ---------------------------------------------------------------------------


def test_embeddings_are_loaded_once_across_repeated_lookups(face_sqlite_session):
    """The O(N^2) regression was one full embedding scan per processed face.

    The cache is append-only, so processing many faces must read each stored
    embedding exactly once no matter how many lookups happen.
    """
    user = _make_user(face_sqlite_session, "cache-user")
    identity = FaceIdentity(identity_name="P", owner_id=user.id)
    face_sqlite_session.add(identity)
    face_sqlite_session.flush()
    for index in range(25):
        _add_face(
            face_sqlite_session,
            user,
            _vec(1.0, index * 0.001),
            identity_id=identity.id,
        )
    targets = [_add_face(face_sqlite_session, user, _vec(1.0, 0.0)) for _ in range(10)]
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    rows_streamed = 0
    original = face_vector_cache.__class__.similarities

    from app.service import face_vector_cache as cache_module

    real_stream = cache_module._stream_rows

    def counting_stream(db, owner_id, after_id):
        nonlocal rows_streamed
        for ids, vectors in real_stream(db, owner_id, after_id):
            rows_streamed += len(ids)
            yield ids, vectors

    with patch.object(cache_module, "_stream_rows", counting_stream), patch(
        "app.service.face_cluster.config_manager.get_user_config",
        return_value=_threshold_config(0.4),
    ), patch("app.service.face_cluster.crud_face.update_face"):
        for target in targets:
            svc.assign_face_to_identity(target.id, _vec(1.0, 0.0), user.id)

    total_faces = 35
    assert rows_streamed == total_faces, (
        f"expected each embedding to be read once ({total_faces}), "
        f"got {rows_streamed}; the per-face full scan has regressed"
    )
    assert original is not None


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


def test_cache_picks_up_faces_added_after_first_load(face_sqlite_session):
    """Incremental loading must see rows inserted after the initial fill."""
    user = _make_user(face_sqlite_session, "incremental-user")
    first = _add_face(face_sqlite_session, user, _vec(1.0, 0.0))
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    assert svc._find_matching_face_ids([np.array(_vec(1.0, 0.0))], user.id, 0.4) == {first.id}

    second = _add_face(face_sqlite_session, user, _vec(1.0, 0.0))
    face_sqlite_session.commit()

    matched = svc._find_matching_face_ids([np.array(_vec(1.0, 0.0))], user.id, 0.4)
    assert matched == {first.id, second.id}


def test_oversized_library_falls_back_to_streaming_scan(face_sqlite_session):
    """Beyond the row cap the service must still return correct results."""
    user = _make_user(face_sqlite_session, "big-user")
    faces = [_add_face(face_sqlite_session, user, _vec(1.0, 0.0)) for _ in range(6)]
    face_sqlite_session.commit()

    tiny_cache = FaceVectorCache(max_rows=2)
    from app.service import face_cluster as cluster_module

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    with patch.object(cluster_module, "face_vector_cache", tiny_cache):
        matched = svc._find_matching_face_ids([np.array(_vec(1.0, 0.0))], user.id, 0.4)

    assert matched == {face.id for face in faces}
    assert tiny_cache.stats()["rows"] == 0, "oversized owner must not stay cached"


def test_zero_vector_never_matches(face_sqlite_session):
    """A zero embedding has no direction; it must not be a nearest neighbour."""
    user = _make_user(face_sqlite_session, "zero-user")
    zero = _add_face(face_sqlite_session, user, _vec(0.0, 0.0))
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    matched = svc._find_matching_face_ids([np.array(_vec(1.0, 0.0))], user.id, 0.4)

    assert zero.id not in matched


# ---------------------------------------------------------------------------
# _cluster_unassigned_faces -- owner scoping regression
# ---------------------------------------------------------------------------


def test_cluster_unassigned_faces_ignores_other_owners(face_sqlite_session):
    """DBSCAN input must be scoped to the owner being processed."""
    mine = _make_user(face_sqlite_session, "cluster-mine")
    theirs = _make_user(face_sqlite_session, "cluster-theirs")
    for _ in range(6):
        _add_face(face_sqlite_session, theirs, _vec(1.0, 0.0))
    face_sqlite_session.commit()

    svc = FaceClusterService(db=face_sqlite_session, user_id=None)
    svc.DBSCAN_MIN_SAMPLES = 5
    svc.MIN_CLUSTER_SIZE_FOR_IDENTITY = 5

    with patch("app.service.face_cluster.DBSCAN") as dbscan:
        svc._cluster_unassigned_faces(owner_id=mine.id)

    # Only the other account has faces, so our owner has nothing to cluster
    # and DBSCAN must never run.
    dbscan.assert_not_called()
    assert face_sqlite_session.query(FaceIdentity).filter(
        FaceIdentity.owner_id == mine.id
    ).count() == 0
