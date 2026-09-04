"""A/B benchmark for the recycle-bin bulk delete rewrite.

Builds an in-memory SQLite photo library (photos + metadata + faces +
descriptions + album membership + clusters), then permanently deletes all of it
twice: once with the previous per-photo implementation, once with the current
set-based one. Reports wall time and the number of SQL statements each issued.

Run with:  uv run python scripts/bench_recycle_bin_purge.py [n_photos]
"""

import sys
import time
import uuid
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.pool import StaticPool

from app.crud import face as crud_face
from app.crud import photo as photo_crud
from app.crud.album import _update_album_photo_count
from app.crud.cluster import remove_photo_from_clusters
from app.db.base import Base
from app.db.models.album import Album, AlbumPhoto
from app.db.models.cluster import ImageCluster, PhotoCluster
from app.db.models.face import Face
from app.db.models.image_description import ImageDescription
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


def seed(db, n):
    """Create `n` trashed photos, each with the child rows a real photo carries."""
    user = User(username="bench", email="bench@example.com", hashed_password="x")
    db.add(user)
    db.commit()

    album = Album(name="Bench", owner_id=user.id, type="user", num_photos=n)
    db.add(album)
    db.commit()

    photos = [
        Photo(
            filename=f"p{i}.jpg",
            file_path=f"/tmp/bench/p{i}.jpg",
            file_type=FileType.image,
            size=1,
            owner_id=user.id,
            is_deleted=True,
        )
        for i in range(n)
    ]
    db.add_all(photos)
    db.commit()

    children = []
    # One cluster per 10 photos, mirroring similar-photo grouping.
    cluster_ids = []
    for i in range(0, n, 10):
        cid = str(uuid.uuid4())
        cluster_ids.append(cid)
        children.append(ImageCluster(cluster_id=cid, cluster_type="similar", count=10))

    for idx, photo in enumerate(photos):
        children.append(PhotoMetadata(photo_id=photo.id))
        children.append(ImageDescription(photo_id=photo.id, description="d"))
        children.append(Face(photo_id=photo.id, face_rect=[0, 0, 1, 1]))
        children.append(AlbumPhoto(album_id=album.id, photo_id=photo.id))
        children.append(
            PhotoCluster(cluster_id=cluster_ids[idx // 10], photo_id=photo.id)
        )
    db.add_all(children)
    db.commit()

    return user, [p.id for p in photos]


def old_batch_delete(db, photo_ids, is_delete_file=False, user_id=None):
    """The pre-rewrite implementation, verbatim, for comparison."""
    query = (
        db.query(Photo)
        .options(joinedload(Photo.albums), joinedload(Photo.faces))
        .filter(Photo.id.in_(photo_ids))
    )
    if user_id is not None:
        query = query.filter(Photo.owner_id == user_id)

    photos = query.all()
    affected_album_ids = set()
    for photo in photos:
        for album in photo.albums:
            affected_album_ids.add(album.id)
        for face in photo.faces:
            crud_face.handle_face_deletion_dependency(db, face)

    count = len(photos)
    for photo in photos:
        remove_photo_from_clusters(db, photo.id)
        db.delete(photo)
    db.commit()

    for album_id in affected_album_ids:
        _update_album_photo_count(db, album_id)
    return count


def count_statements(engine):
    counter = {"n": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    return counter


def run(label, fn, n):
    engine, db = make_session()
    user, photo_ids = seed(db, n)
    user_id = user.id
    # Drop the seeded entities from the identity map: a real request session never
    # holds the whole library, and leaving them in makes every commit's expire pass
    # O(library size), which would distort both sides of the comparison.
    db.expunge_all()
    counter = count_statements(engine)

    # Storage + smart-album refresh are identical on both paths and would only
    # add filesystem noise, so stub them out.
    with patch.multiple(
        photo_crud.storage, delete_file=MagicMock(), delete_thumbnails=MagicMock()
    ), patch("app.crud.album.trigger_conditional_albums_update"):
        start = time.perf_counter()
        deleted = fn(db, photo_ids, is_delete_file=True, user_id=user_id)
        elapsed = time.perf_counter() - start

    remaining = db.query(Photo).count()
    db.close()
    print(
        f"{label:>10}: {elapsed:7.3f}s  {counter['n']:>7} SQL statements  "
        f"deleted={deleted} remaining={remaining}"
    )
    return elapsed, counter["n"]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    print(f"Permanently deleting {n} photos (each with metadata/face/description/album/cluster rows)\n")

    old_time, old_stmts = run("old", old_batch_delete, n)
    new_time, new_stmts = run("new", photo_crud.batch_delete_photos_db, n)

    print(
        f"\nspeedup: {old_time / new_time:.1f}x   "
        f"statements: {old_stmts} -> {new_stmts} ({old_stmts / max(new_stmts, 1):.1f}x fewer)"
    )


if __name__ == "__main__":
    main()
