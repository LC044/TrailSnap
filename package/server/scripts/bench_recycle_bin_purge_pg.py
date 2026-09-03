"""Real-PostgreSQL benchmark for the recycle-bin purge rewrite.

The SQLite benchmark proves the statement-count reduction, but SQLite has a single
writer and no MVCC, so it cannot show what actually matters in production:

* whether the purge still holds a long write transaction that blocks other queries
* whether ON DELETE CASCADE on real FK constraints behaves the same
* whether the chunked commits let concurrent readers make progress

This drives the real engine. It needs a throwaway database — never point it at a
library you care about.

Usage:
    TS_BENCH_PG_URL=postgresql://user:pass@localhost:5432/throwaway \
        PYTHONPATH=. uv run python scripts/bench_recycle_bin_purge_pg.py [n]
"""

import os
import sys
import threading
import time
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock, patch

from app.crud import photo as photo_crud
from app.db.models.album import Album, AlbumPhoto
from app.db.models.cluster import ImageCluster, PhotoCluster
from app.db.models.face import Face
from app.db.models.image_description import ImageDescription
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User

URL = os.environ.get("TS_BENCH_PG_URL")
if not URL:
    sys.exit("refusing to run without an explicit TS_BENCH_PG_URL (use a throwaway DB)")

engine = sa.create_engine(URL)
Session = sessionmaker(bind=engine)


def reset(db):
    """Clear only the tables this benchmark writes, in FK-safe order."""
    db.rollback()
    db.execute(
        sa.text(
            "TRUNCATE photo_clusters, image_clusters, album_photos, faces, "
            "photo_metadata, image_descriptions, albums, photos, users CASCADE"
        )
    )
    db.commit()


def seed(db, n):
    user = User(username=f"bench-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@e.com", hashed_password="x")
    db.add(user)
    db.commit()

    album = Album(name="Bench", owner_id=user.id, type="user", num_photos=n)
    db.add(album)
    db.commit()

    photos = [
        Photo(
            filename=f"p{i}.jpg",
            file_path=f"/tmp/bench/{uuid.uuid4().hex}.jpg",
            file_type=FileType.image,
            size=1,
            owner_id=user.id,
            is_deleted=True,
        )
        for i in range(n)
    ]
    db.add_all(photos)
    db.commit()

    cluster_ids = []
    children = []
    for i in range(0, n, 10):
        cid = uuid.uuid4()
        cluster_ids.append(cid)
        children.append(ImageCluster(cluster_id=cid, cluster_type="similar", count=10))
    for idx, p in enumerate(photos):
        children.append(PhotoMetadata(photo_id=p.id))
        children.append(ImageDescription(photo_id=p.id, description="d"))
        children.append(Face(photo_id=p.id, face_rect=[0, 0, 1, 1]))
        children.append(AlbumPhoto(album_id=album.id, photo_id=p.id))
        children.append(PhotoCluster(cluster_id=cluster_ids[idx // 10], photo_id=p.id))
    db.add_all(children)
    db.commit()

    ids = [p.id for p in photos]
    uid = user.id
    db.expunge_all()
    return uid, ids


def probe_reader(stop, latencies):
    """Hammer a trivial read the whole time the purge runs.

    This is the part SQLite cannot show: if the purge holds one giant transaction,
    these reads stall. With chunked commits they should stay fast throughout.
    """
    probe_engine = sa.create_engine(URL, pool_pre_ping=True)
    while not stop.is_set():
        t = time.perf_counter()
        try:
            with probe_engine.connect() as c:
                c.execute(sa.text("SELECT COUNT(*) FROM photos WHERE is_deleted"))
            latencies.append(time.perf_counter() - t)
        except Exception:
            latencies.append(float("inf"))
        time.sleep(0.02)
    probe_engine.dispose()


def old_batch_delete(db, photo_ids, is_delete_file=False, user_id=None):
    """The pre-rewrite implementation, for an apples-to-apples comparison."""
    from sqlalchemy.orm import joinedload
    from app.crud import face as crud_face
    from app.crud.album import _update_album_photo_count
    from app.crud.cluster import remove_photo_from_clusters

    query = (
        db.query(Photo)
        .options(joinedload(Photo.albums), joinedload(Photo.faces))
        .filter(Photo.id.in_(photo_ids))
    )
    if user_id is not None:
        query = query.filter(Photo.owner_id == user_id)
    photos = query.all()

    affected = set()
    for photo in photos:
        for album in photo.albums:
            affected.add(album.id)
        for face in photo.faces:
            crud_face.handle_face_deletion_dependency(db, face)

    count = len(photos)
    for photo in photos:
        remove_photo_from_clusters(db, photo.id)
        db.delete(photo)
    db.commit()
    for album_id in affected:
        _update_album_photo_count(db, album_id)
    return count


def run_one(label, fn, n):
    db = Session()
    reset(db)
    uid, ids = seed(db, n)

    stop = threading.Event()
    latencies = []
    reader = threading.Thread(target=probe_reader, args=(stop, latencies), daemon=True)
    reader.start()

    with patch.multiple(
        photo_crud.storage, delete_file=MagicMock(), delete_thumbnails=MagicMock()
    ), patch("app.crud.album.trigger_conditional_albums_update"):
        t0 = time.perf_counter()
        deleted = fn(db, ids, is_delete_file=True, user_id=uid)
        elapsed = time.perf_counter() - t0

    stop.set()
    reader.join(timeout=2)

    remaining = db.query(Photo).count()
    orphans = {
        t: db.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar()
        for t in ("photo_metadata", "image_descriptions", "faces", "album_photos", "photo_clusters")
    }
    clusters = db.execute(sa.text("SELECT COUNT(*) FROM image_clusters")).scalar()
    db.close()

    ok = sorted(l for l in latencies if l != float("inf"))
    print(f"[{label}] {elapsed:7.3f}s  {deleted/elapsed:>8,.0f} photos/s  left={remaining} clusters={clusters}")
    print(f"          orphans={orphans}")
    if ok:
        print(
            f"          concurrent reads: n={len(ok)} p50={ok[len(ok)//2]*1000:.1f}ms "
            f"p99={ok[int(len(ok)*0.99)]*1000:.1f}ms max={ok[-1]*1000:.1f}ms "
            f"failed={len(latencies)-len(ok)}"
        )
    return elapsed, (ok[-1] if ok else 0)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    print(f"Real PostgreSQL, {n} trashed photos each with metadata/face/description/album/cluster\n")

    old_t, old_max = run_one("old", old_batch_delete, n)
    print()
    new_t, new_max = run_one("new", photo_crud.batch_delete_photos_db, n)
    print(
        f"\nspeedup {old_t/new_t:.1f}x   "
        f"worst concurrent read {old_max*1000:.0f}ms -> {new_max*1000:.0f}ms"
    )


if __name__ == "__main__":
    main()
