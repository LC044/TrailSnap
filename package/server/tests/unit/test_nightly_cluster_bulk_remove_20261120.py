"""Set-based bulk removal of photos from similarity clusters."""
from uuid import uuid4

import pytest

from app.crud.cluster import remove_photos_from_clusters
from app.db.models.cluster import ImageCluster, PhotoCluster
from app.db.models.photo import Photo
from app.db.models.photo import FileType

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def _photo(db, owner_id):
    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename="photo.jpg",
        photo_time=None,
        file_path="/tmp/photo.jpg",
        file_type=FileType.image,
    )
    db.add(photo)
    db.flush()
    return photo


def _cluster(db, count):
    cluster = ImageCluster(cluster_id=uuid4(), cluster_type="similar", count=count)
    db.add(cluster)
    db.flush()
    return cluster


def test_empty_batch_is_a_no_op(face_sqlite_session):
    remove_photos_from_clusters(face_sqlite_session, [])
    assert face_sqlite_session.query(PhotoCluster).count() == 0


def test_removes_the_membership_rows(face_sqlite_session):
    owner_id = uuid4()
    photo = _photo(face_sqlite_session, owner_id)
    cluster = _cluster(face_sqlite_session, 1)
    face_sqlite_session.add(PhotoCluster(photo_id=photo.id, cluster_id=cluster.cluster_id))
    face_sqlite_session.flush()

    remove_photos_from_clusters(face_sqlite_session, [photo.id])
    face_sqlite_session.flush()
    assert face_sqlite_session.query(PhotoCluster).count() == 0


def test_deletes_the_parent_cluster_when_no_photo_remains(face_sqlite_session):
    owner_id = uuid4()
    photo = _photo(face_sqlite_session, owner_id)
    cluster = _cluster(face_sqlite_session, 1)
    face_sqlite_session.add(PhotoCluster(photo_id=photo.id, cluster_id=cluster.cluster_id))
    face_sqlite_session.flush()

    remove_photos_from_clusters(face_sqlite_session, [photo.id])
    face_sqlite_session.flush()
    assert face_sqlite_session.query(ImageCluster).filter_by(cluster_id=cluster.cluster_id).first() is None


def test_decrements_the_counter_when_other_photos_remain(face_sqlite_session):
    owner_id = uuid4()
    first = _photo(face_sqlite_session, owner_id)
    second = _photo(face_sqlite_session, owner_id)
    cluster = _cluster(face_sqlite_session, 2)
    face_sqlite_session.add(PhotoCluster(photo_id=first.id, cluster_id=cluster.cluster_id))
    face_sqlite_session.add(PhotoCluster(photo_id=second.id, cluster_id=cluster.cluster_id))
    face_sqlite_session.flush()

    remove_photos_from_clusters(face_sqlite_session, [first.id])
    face_sqlite_session.flush()
    remaining = face_sqlite_session.query(ImageCluster).filter_by(cluster_id=cluster.cluster_id).first()
    assert remaining is not None
    assert remaining.count == 1


def test_decrements_by_the_number_of_removed_photos_not_by_one(face_sqlite_session):
    owner_id = uuid4()
    photos = [_photo(face_sqlite_session, owner_id) for _ in range(3)]
    cluster = _cluster(face_sqlite_session, 5)
    for photo in photos:
        face_sqlite_session.add(PhotoCluster(photo_id=photo.id, cluster_id=cluster.cluster_id))
    face_sqlite_session.flush()

    remove_photos_from_clusters(face_sqlite_session, [photo.id for photo in photos])
    face_sqlite_session.flush()
    remaining = face_sqlite_session.query(ImageCluster).filter_by(cluster_id=cluster.cluster_id).first()
    assert remaining is not None
    assert remaining.count == 2
