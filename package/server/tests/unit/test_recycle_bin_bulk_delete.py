"""Tests for the bulk recycle-bin purge path.

Covers the pieces that make emptying a large recycle bin fast instead of
apparently hanging the server:

* ``batch_delete_photos_db`` reaps every child row via DB-level FK cascade
  instead of per-photo ORM cascades, and only ever touches the caller's photos.
* the purge is chunked, so a large batch commits progressively and reports
  progress rather than holding one long write transaction.
* face identities keep a valid avatar: ``default_face_id`` is re-pointed at a
  surviving face (or nulled) instead of being left dangling.
* cluster counters are decremented by the real number of removed photos, which
  the old per-photo helper got wrong when several photos shared a cluster.
* ``count_recycle_bin_photos`` / ``get_recycle_bin_photo_ids`` let the UI offer
  "select all N" and "empty bin" without paging the whole list into the browser.
* the API routes big batches to a background job and small ones inline.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import photo as photo_api
from app.crud import photo as photo_crud
from app.db.base import Base
from app.db.models.album import Album, AlbumPhoto
from app.db.models.cluster import ImageCluster, PhotoCluster
from app.db.models.face import Face, FaceIdentity
from app.db.models.image_description import ImageDescription
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.schemas.photo import RecycleBinPurge


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # The production engine turns this on in app/db/session.py. The bulk delete
    # relies on ON DELETE CASCADE, and SQLite ignores FK actions without it, so
    # the fixture must mirror that or the test would validate nothing.
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _user(db, username):
    user = User(username=username, email=f"{username}@example.com", hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _photo(db, owner, name, deleted=True):
    photo = Photo(
        filename=name,
        file_path=f"/tmp/{owner.id}/{name}",
        file_type=FileType.image,
        size=1,
        owner_id=owner.id,
        is_deleted=deleted,
        deleted_at=None,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


# `storage` performs real filesystem work; every test here stubs it out so the
# assertions are about SQL, not about temp files.
def _no_storage():
    return patch.multiple(
        photo_crud.storage,
        delete_file=MagicMock(),
        delete_thumbnails=MagicMock(),
    )


# --------------------------- cascade correctness ---------------------------


def test_bulk_delete_cascades_all_child_rows(db):
    owner = _user(db, "cascade-owner")
    first = _photo(db, owner, "a.jpg")
    second = _photo(db, owner, "b.jpg")

    for photo in (first, second):
        db.add(PhotoMetadata(photo_id=photo.id))
        db.add(ImageDescription(photo_id=photo.id, description="d"))
        db.add(Face(photo_id=photo.id, face_rect=[0, 0, 1, 1]))
    db.commit()

    with _no_storage(), patch("app.crud.album.trigger_conditional_albums_update"):
        deleted = photo_crud.batch_delete_photos_db(
            db, [first.id, second.id], is_delete_file=True, user_id=owner.id
        )

    assert deleted == 2
    assert db.query(Photo).count() == 0
    # Children go away through the FK cascade, not through per-photo ORM loads.
    assert db.query(PhotoMetadata).count() == 0
    assert db.query(ImageDescription).count() == 0
    assert db.query(Face).count() == 0


def test_bulk_delete_is_scoped_to_the_owner(db):
    owner = _user(db, "mine")
    intruder = _user(db, "theirs")
    # Read the ids up front: after the bulk DELETE the ORM instances are expired
    # and touching `.id` would trigger a refresh of a row that no longer exists.
    mine_id = _photo(db, owner, "mine.jpg").id
    theirs_id = _photo(db, intruder, "theirs.jpg").id

    with _no_storage(), patch("app.crud.album.trigger_conditional_albums_update"):
        deleted = photo_crud.batch_delete_photos_db(
            db, [mine_id, theirs_id], is_delete_file=True, user_id=owner.id
        )

    # Passing someone else's id must be a silent no-op, never a cross-user delete.
    assert deleted == 1
    assert db.query(Photo).filter(Photo.id == theirs_id).first() is not None
    assert db.query(Photo).filter(Photo.id == mine_id).first() is None


def test_bulk_delete_refreshes_album_counts(db):
    owner = _user(db, "album-owner")
    album = Album(name="Trip", owner_id=owner.id, type="user", num_photos=2)
    db.add(album)
    db.commit()
    db.refresh(album)

    kept = _photo(db, owner, "kept.jpg", deleted=False)
    doomed = _photo(db, owner, "doomed.jpg")
    db.add_all([
        AlbumPhoto(album_id=album.id, photo_id=kept.id),
        AlbumPhoto(album_id=album.id, photo_id=doomed.id),
    ])
    db.commit()

    with _no_storage(), patch("app.crud.album.trigger_conditional_albums_update"):
        photo_crud.batch_delete_photos_db(
            db, [doomed.id], is_delete_file=True, user_id=owner.id
        )

    db.refresh(album)
    assert album.num_photos == 1
    assert db.query(AlbumPhoto).count() == 1


# --------------------------- face identity avatars ---------------------------


def test_default_face_is_repointed_to_a_surviving_face(db):
    owner = _user(db, "face-owner")
    doomed_photo = _photo(db, owner, "doomed.jpg")
    kept_photo = _photo(db, owner, "kept.jpg", deleted=False)

    identity = FaceIdentity(identity_name="Alice", owner_id=owner.id)
    db.add(identity)
    db.commit()
    db.refresh(identity)

    doomed_face = Face(photo_id=doomed_photo.id, face_identity_id=identity.id, face_rect=[0, 0, 1, 1])
    kept_face = Face(photo_id=kept_photo.id, face_identity_id=identity.id, face_rect=[0, 0, 1, 1])
    db.add_all([doomed_face, kept_face])
    db.commit()
    db.refresh(doomed_face)
    db.refresh(kept_face)

    identity.default_face_id = doomed_face.id
    db.commit()

    with _no_storage(), patch("app.crud.album.trigger_conditional_albums_update"):
        photo_crud.batch_delete_photos_db(
            db, [doomed_photo.id], is_delete_file=True, user_id=owner.id
        )

    db.refresh(identity)
    # Falling back to NULL would silently drop the person's avatar.
    assert identity.default_face_id == kept_face.id


def test_default_face_is_nulled_when_no_face_survives(db):
    owner = _user(db, "lonely-face-owner")
    photo = _photo(db, owner, "only.jpg")

    identity = FaceIdentity(identity_name="Bob", owner_id=owner.id)
    db.add(identity)
    db.commit()
    db.refresh(identity)

    face = Face(photo_id=photo.id, face_identity_id=identity.id, face_rect=[0, 0, 1, 1])
    db.add(face)
    db.commit()
    db.refresh(face)
    identity.default_face_id = face.id
    db.commit()

    with _no_storage(), patch("app.crud.album.trigger_conditional_albums_update"):
        photo_crud.batch_delete_photos_db(
            db, [photo.id], is_delete_file=True, user_id=owner.id
        )

    db.refresh(identity)
    assert identity.default_face_id is None


# ------------------------------- clusters -------------------------------


def test_cluster_counter_drops_by_the_number_of_removed_photos(db):
    owner = _user(db, "cluster-owner")
    first = _photo(db, owner, "c1.jpg")
    second = _photo(db, owner, "c2.jpg")
    survivor = _photo(db, owner, "c3.jpg", deleted=False)

    cluster_id = str(uuid4())
    db.add(ImageCluster(cluster_id=cluster_id, cluster_type="similar", count=3))
    db.add_all([
        PhotoCluster(cluster_id=cluster_id, photo_id=first.id),
        PhotoCluster(cluster_id=cluster_id, photo_id=second.id),
        PhotoCluster(cluster_id=cluster_id, photo_id=survivor.id),
    ])
    db.commit()
    doomed_ids = [first.id, second.id]

    with _no_storage(), patch("app.crud.album.trigger_conditional_albums_update"):
        photo_crud.batch_delete_photos_db(
            db, doomed_ids, is_delete_file=True, user_id=owner.id
        )

    cluster = db.query(ImageCluster).filter(ImageCluster.cluster_id == cluster_id).first()
    # The old per-photo helper decremented once per call, leaving count == 2 here.
    assert cluster is not None
    assert cluster.count == 1
    assert db.query(PhotoCluster).count() == 1


def test_cluster_is_dropped_when_every_member_is_deleted(db):
    owner = _user(db, "cluster-drop-owner")
    first = _photo(db, owner, "d1.jpg")
    second = _photo(db, owner, "d2.jpg")

    cluster_id = str(uuid4())
    db.add(ImageCluster(cluster_id=cluster_id, cluster_type="similar", count=2))
    db.add_all([
        PhotoCluster(cluster_id=cluster_id, photo_id=first.id),
        PhotoCluster(cluster_id=cluster_id, photo_id=second.id),
    ])
    db.commit()
    doomed_ids = [first.id, second.id]

    with _no_storage(), patch("app.crud.album.trigger_conditional_albums_update"):
        photo_crud.batch_delete_photos_db(
            db, doomed_ids, is_delete_file=True, user_id=owner.id
        )

    assert db.query(ImageCluster).count() == 0
    assert db.query(PhotoCluster).count() == 0


# ------------------------------- chunking -------------------------------


def test_large_batch_is_chunked_and_reports_progress(db, monkeypatch):
    owner = _user(db, "chunk-owner")
    photos = [_photo(db, owner, f"p{i}.jpg") for i in range(7)]

    monkeypatch.setattr(photo_crud, "DELETE_CHUNK_SIZE", 3)
    progress = []

    with _no_storage(), patch("app.crud.album.trigger_conditional_albums_update"):
        deleted = photo_crud.batch_delete_photos_db(
            db,
            [p.id for p in photos],
            is_delete_file=True,
            user_id=owner.id,
            progress_cb=lambda done, total: progress.append((done, total)),
        )

    assert deleted == 7
    assert db.query(Photo).count() == 0
    # 7 photos / chunk of 3 => 3 commits, and progress must end at the total so
    # the UI can show a truthful bar.
    assert progress == [(3, 7), (6, 7), (7, 7)]


def test_empty_input_is_a_no_op(db):
    with _no_storage():
        assert photo_crud.batch_delete_photos_db(db, [], is_delete_file=True) == 0


# --------------------------- stats / id enumeration ---------------------------


def test_count_and_ids_only_cover_the_users_recycle_bin(db):
    owner = _user(db, "stats-owner")
    other = _user(db, "stats-other")
    trashed = [_photo(db, owner, f"t{i}.jpg") for i in range(3)]
    _photo(db, owner, "live.jpg", deleted=False)
    _photo(db, other, "other-trashed.jpg")

    assert photo_crud.count_recycle_bin_photos(db, owner.id) == 3
    assert set(photo_crud.get_recycle_bin_photo_ids(db, owner.id)) == {p.id for p in trashed}
    assert len(photo_crud.get_recycle_bin_photo_ids(db, owner.id, limit=2)) == 2


# ------------------------------- API routing -------------------------------


def _api_user():
    return SimpleNamespace(id=uuid4())


def test_purge_resolves_all_ids_when_photo_ids_is_null():
    db = MagicMock()
    user = _api_user()
    ids = [uuid4(), uuid4()]

    with patch.object(
        photo_api.app.crud.photo, "get_recycle_bin_photo_ids", return_value=ids
    ) as resolve, patch.object(
        photo_api.app.crud.photo, "batch_delete_photos_db", return_value=2
    ) as delete:
        result = photo_api.purge_recycle_bin(
            payload=RecycleBinPurge(photo_ids=None), db=db, current_user=user
        )

    # This is the whole point of the endpoint: the client sent no ids at all.
    resolve.assert_called_once_with(db, user_id=user.id)
    delete.assert_called_once_with(db, ids, is_delete_file=True, user_id=user.id)
    assert result.data["mode"] == "sync"
    assert result.data["deleted"] == 2


def test_purge_of_empty_bin_succeeds_without_deleting():
    db = MagicMock()
    with patch.object(
        photo_api.app.crud.photo, "get_recycle_bin_photo_ids", return_value=[]
    ), patch.object(photo_api.app.crud.photo, "batch_delete_photos_db") as delete:
        result = photo_api.purge_recycle_bin(
            payload=RecycleBinPurge(photo_ids=None), db=db, current_user=_api_user()
        )

    delete.assert_not_called()
    assert result.data["total"] == 0


def test_purge_switches_to_background_job_above_threshold():
    from app.service import recycle_bin_purge

    db = MagicMock()
    user = _api_user()
    ids = [uuid4() for _ in range(recycle_bin_purge.ASYNC_PURGE_THRESHOLD + 1)]
    fake_job = recycle_bin_purge.PurgeJob(id="job-1", user_id=str(user.id), total=len(ids))

    with patch.object(
        photo_api.app.crud.photo, "batch_delete_photos_db"
    ) as delete, patch.object(
        recycle_bin_purge, "active_job_for_user", return_value=None
    ), patch.object(
        recycle_bin_purge, "start_purge_job", return_value=fake_job
    ) as start:
        result = photo_api.purge_recycle_bin(
            payload=RecycleBinPurge(photo_ids=ids), db=db, current_user=user
        )

    # A batch this size must never block the request thread.
    delete.assert_not_called()
    start.assert_called_once()
    assert result.data["mode"] == "async"
    assert result.data["job_id"] == "job-1"
    assert result.data["total"] == len(ids)


def test_purge_returns_the_existing_job_instead_of_starting_a_second_one():
    from app.service import recycle_bin_purge

    user = _api_user()
    ids = [uuid4() for _ in range(recycle_bin_purge.ASYNC_PURGE_THRESHOLD + 1)]
    running = recycle_bin_purge.PurgeJob(
        id="job-running", user_id=str(user.id), total=len(ids), status="running"
    )

    with patch.object(
        recycle_bin_purge, "active_job_for_user", return_value=running
    ), patch.object(recycle_bin_purge, "start_purge_job") as start:
        result = photo_api.purge_recycle_bin(
            payload=RecycleBinPurge(photo_ids=ids), db=MagicMock(), current_user=user
        )

    start.assert_not_called()
    assert result.data["job_id"] == "job-running"


def test_purge_rejects_an_explicitly_empty_id_list():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        photo_api.purge_recycle_bin(
            payload=RecycleBinPurge(photo_ids=[]), db=MagicMock(), current_user=_api_user()
        )
    # An empty list is a client bug; `null` is the documented "everything" signal.
    assert exc.value.status_code == 400


def test_purge_status_is_scoped_to_its_owner():
    from fastapi import HTTPException
    from app.service import recycle_bin_purge

    owner = _api_user()
    job = recycle_bin_purge.PurgeJob(id="job-x", user_id=str(owner.id), total=5, processed=5)

    with patch.object(recycle_bin_purge, "get_job", return_value=job):
        result = photo_api.get_recycle_bin_purge_status(job_id="job-x", current_user=owner)
    assert result.data["progress"] == 100

    with patch.object(recycle_bin_purge, "get_job", return_value=None):
        with pytest.raises(HTTPException) as exc:
            photo_api.get_recycle_bin_purge_status(job_id="job-x", current_user=_api_user())
    assert exc.value.status_code == 404


def test_recycle_bin_stats_reports_total_and_retention():
    db = MagicMock()
    user = _api_user()
    with patch.object(
        photo_api.app.crud.photo, "count_recycle_bin_photos", return_value=1234
    ):
        result = photo_api.get_recycle_bin_stats(db=db, current_user=user)

    assert result.data["total"] == 1234
    assert result.data["retention_days"] >= 1


# ------------------------------- purge job registry -------------------------------


def test_purge_job_registry_tracks_and_scopes_jobs():
    from app.service import recycle_bin_purge

    user_id = uuid4()
    photo_ids = [uuid4(), uuid4()]

    # Patch the worker body so no thread touches a real database.
    with patch.object(recycle_bin_purge, "_run_job") as run:
        job = recycle_bin_purge.start_purge_job(user_id, photo_ids)
        run_called = run.call_count

    assert run_called == 1
    assert job.total == 2
    assert recycle_bin_purge.get_job(job.id, user_id) is job
    # Another user must not be able to read the job by guessing its id.
    assert recycle_bin_purge.get_job(job.id, uuid4()) is None


def test_purge_job_progress_dict_is_bounded():
    from app.service import recycle_bin_purge

    job = recycle_bin_purge.PurgeJob(id="j", user_id="u", total=200, processed=50)
    assert job.to_dict()["progress"] == 25

    job.status = "completed"
    assert job.to_dict()["progress"] == 100

    empty = recycle_bin_purge.PurgeJob(id="j2", user_id="u", total=0)
    # No division by zero when the bin turned out to be empty.
    assert empty.to_dict()["progress"] == 0


def test_background_worker_actually_deletes_and_closes_its_session():
    """Drive the real worker body, not a mock.

    Everywhere else _run_job is patched out, so this is the only place that proves
    the background path works end to end: it opens its own session (the request
    session is long gone by then), reports progress, marks the job completed, and
    closes the session instead of leaking a pooled connection.
    """
    from app.service import recycle_bin_purge

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    seed = SessionLocal()

    owner = User(username="worker", email="worker@e.com", hashed_password="x")
    seed.add(owner)
    seed.commit()
    seed.refresh(owner)
    photo_ids = [_photo(seed, owner, f"w{i}.jpg").id for i in range(5)]
    owner_id = owner.id
    seed.close()

    closed = []

    def tracking_session_factory():
        s = SessionLocal()
        original_close = s.close

        def close_and_record():
            closed.append(True)
            original_close()

        s.close = close_and_record
        return s

    job = recycle_bin_purge.PurgeJob(
        id="real-job", user_id=str(owner_id), total=len(photo_ids)
    )
    with recycle_bin_purge._lock:
        recycle_bin_purge._jobs["real-job"] = job

    try:
        with patch("app.db.session.SessionLocal", tracking_session_factory), _no_storage(), patch(
            "app.crud.album.trigger_conditional_albums_update"
        ):
            recycle_bin_purge._run_job("real-job", owner_id, photo_ids)

        assert job.status == "completed"
        assert job.deleted == 5
        assert job.processed == job.total
        assert closed, "the worker must close its session"

        verify = SessionLocal()
        assert verify.query(Photo).count() == 0
        verify.close()
    finally:
        with recycle_bin_purge._lock:
            recycle_bin_purge._jobs.pop("real-job", None)
        Base.metadata.drop_all(engine)


def test_background_worker_records_failure_instead_of_crashing():
    """A failing purge must surface as a failed job, not kill the thread silently."""
    from app.service import recycle_bin_purge

    job = recycle_bin_purge.PurgeJob(id="boom-job", user_id="u", total=3)
    with recycle_bin_purge._lock:
        recycle_bin_purge._jobs["boom-job"] = job

    try:
        with patch(
            "app.crud.photo.batch_delete_photos_db",
            side_effect=RuntimeError("disk on fire"),
        ), patch("app.db.session.SessionLocal", MagicMock()):
            # Must not re-raise.
            recycle_bin_purge._run_job("boom-job", uuid4(), [uuid4()])

        assert job.status == "failed"
        assert "disk on fire" in job.error
        assert job.finished_at is not None
    finally:
        with recycle_bin_purge._lock:
            recycle_bin_purge._jobs.pop("boom-job", None)
