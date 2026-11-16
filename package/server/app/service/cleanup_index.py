"""Disposable, database/user/model isolated disk cache with bounded HNSW shards.

The DB remains authoritative. Every pass verifies vector content, removes stale
entries and rebuilds only changed shards. A process lock covers sync and queries;
partial files are never published. No pickle or whole-library Python matrices.
"""
import contextlib
import hashlib
import os
from pathlib import Path
import sqlite3
from uuid import UUID
from collections import OrderedDict

import numpy as np
from sqlalchemy import select

from app.core.paths import DATA_DIR
from app.db.models.image_vector import ImageVector
from app.db.models.photo import Photo, FileType

SHARD_SIZE = 20000
BLOCK_SIZE = 512


@contextlib.contextmanager
def file_lock(path):
    with open(path, "a+b") as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            # Blocking lock is retried by the caller as a transient task failure.
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class CleanupIndex:
    def __init__(self, db, owner, model, root=None):
        identity = str(db.get_bind().url.render_as_string(hide_password=False))
        identity += "|" + str(owner) + "|" + model + "|v1"
        key = hashlib.sha256(identity.encode()).hexdigest()
        self.root = Path(root or os.environ.get("TS_CLEANUP_CACHE_DIR") or Path(DATA_DIR) / "cleanup-cache") / key
        self.root.mkdir(parents=True, exist_ok=True)
        self.db, self.owner, self.model = db, owner, model
        self.loaded = OrderedDict()
        self._shards = None
        self.max_resident_rows = max(SHARD_SIZE, int(os.environ.get("TS_CLEANUP_INDEX_MEMORY_MB", "256")) * 1024 * 1024 // 2400)
        self.rebuilt = self.changed = self.invalid = self.decoded = 0

    def __enter__(self):
        self.resources = contextlib.ExitStack()
        try:
            self.resources.enter_context(file_lock(self.root / "lock"))
            self.cache = self.resources.enter_context(contextlib.closing(sqlite3.connect(self.root / "manifest.sqlite")))
            self._initialize_cache()
        except BaseException:
            self.resources.close()
            raise
        return self

    def _initialize_cache(self):
        self.cache.execute("PRAGMA temp_store=MEMORY")
        self.cache.execute("PRAGMA cache_size=-4096")
        self.cache.execute("CREATE TABLE IF NOT EXISTS vectors (label INTEGER PRIMARY KEY AUTOINCREMENT, photo TEXT UNIQUE, digest TEXT, vector BLOB, generation INTEGER)")
        self.cache.execute("CREATE TABLE IF NOT EXISTS dirty (shard INTEGER PRIMARY KEY)")
        if "revision" not in {r[1] for r in self.cache.execute("PRAGMA table_info(vectors)")}:
            self.cache.execute("ALTER TABLE vectors ADD COLUMN revision TEXT")
        self.cache.execute("CREATE INDEX IF NOT EXISTS vectors_photo_revision ON vectors(photo,revision)")

    def __exit__(self, *args):
        self.loaded.clear()
        self.resources.__exit__(*args)

    def sync(self, checkpoint=lambda: None):
        self._shards = None
        self.cache.execute("CREATE TEMP TABLE seen (photo TEXT PRIMARY KEY)")
        generation = self.cache.execute("SELECT coalesce(max(generation),0)+1 FROM vectors").fetchone()[0]
        query = select(ImageVector.photo_id, ImageVector.content_revision).join(Photo).where(
            Photo.owner_id == self.owner, Photo.is_deleted.is_(False),
            Photo.file_type == FileType.image, ImageVector.model_name == self.model).order_by(ImageVector.photo_id)
        cursor = None
        while True:
            page = query.where(ImageVector.photo_id > UUID(cursor)) if cursor else query
            rows = self.db.execute(page.limit(BLOCK_SIZE)).all()
            if not rows:
                break
            changed_ids = []
            for pid, revision in rows:
                old = self.cache.execute("SELECT revision FROM vectors WHERE photo=?", (str(pid),)).fetchone()
                if old is not None and old[0] == revision:
                    self.cache.execute("INSERT INTO seen VALUES(?)", (str(pid),))
                else:
                    changed_ids.append(pid)
            changed_rows = self.db.execute(select(ImageVector.photo_id, ImageVector.embedding, ImageVector.content_revision).where(
                ImageVector.photo_id.in_(changed_ids))).all() if changed_ids else []
            for pid, raw, revision in changed_rows:
                self.decoded += 1
                try:
                    vector = np.asarray(raw, dtype=np.float32)
                except (TypeError, ValueError):
                    self.invalid += 1
                    continue
                norm = np.linalg.norm(vector)
                if vector.shape != (512,) or not np.isfinite(vector).all() or not np.isfinite(norm) or norm <= 0:
                    self.invalid += 1
                    continue
                vector = (vector / norm).astype(np.float32).tobytes()
                self.cache.execute("INSERT INTO seen VALUES(?)", (str(pid),))
                digest = hashlib.sha256(vector).hexdigest()
                old = self.cache.execute("SELECT label,digest FROM vectors WHERE photo=?", (str(pid),)).fetchone()
                if old is None:
                    label = self.cache.execute("INSERT INTO vectors(photo,digest,vector,generation,revision) VALUES(?,?,?,?,?)", (str(pid), digest, vector, generation, revision)).lastrowid
                elif old[1] != digest:
                    label = old[0]
                    self.cache.execute("UPDATE vectors SET digest=?,vector=?,generation=?,revision=? WHERE label=?", (digest, vector, generation, revision, label))
                else:
                    self.cache.execute("UPDATE vectors SET generation=?,revision=? WHERE label=?", (generation, revision, old[0]))
                    continue
                self.changed += 1
                self.cache.execute("INSERT OR IGNORE INTO dirty VALUES(?)", ((label - 1) // SHARD_SIZE,))
            self.cache.commit()
            cursor = str(rows[-1][0])
            checkpoint()
        self.cache.execute("INSERT OR IGNORE INTO dirty SELECT (label-1)/? FROM vectors WHERE photo NOT IN (SELECT photo FROM seen)", (SHARD_SIZE,))
        self.cache.execute("DELETE FROM vectors WHERE photo NOT IN (SELECT photo FROM seen)")
        self.cache.execute("DROP TABLE seen")
        self.cache.commit()
        for (shard,) in self.cache.execute("SELECT shard FROM dirty").fetchall():
            if not self.cache.execute("SELECT 1 FROM vectors WHERE label BETWEEN ? AND ? LIMIT 1", (shard * SHARD_SIZE + 1, (shard + 1) * SHARD_SIZE)).fetchone():
                (self.root / f"{shard}.hnsw").unlink(missing_ok=True)
                self.cache.execute("DELETE FROM dirty WHERE shard=?", (shard,))
        self.cache.commit()

    def vector(self, pid):
        row = self.cache.execute("SELECT vector FROM vectors WHERE photo=?", (str(pid),)).fetchone()
        return np.frombuffer(row[0], dtype=np.float32) if row else None

    def shards(self):
        if self._shards is None:
            self._shards = [r[0] for r in self.cache.execute("SELECT DISTINCT (label-1)/? FROM vectors ORDER BY 1", (SHARD_SIZE,))]
        return self._shards

    def shard_rows(self, shard):
        return self.cache.execute("SELECT label,photo,vector FROM vectors WHERE label BETWEEN ? AND ? ORDER BY label", (shard * SHARD_SIZE + 1, (shard + 1) * SHARD_SIZE)).fetchall()

    def prepare(self, checkpoint=lambda: None):
        import hnswlib
        for shard in self.shards():
            path = self.root / f"{shard}.hnsw"
            dirty = self.cache.execute("SELECT 1 FROM dirty WHERE shard=?", (shard,)).fetchone()
            if dirty or not path.exists():
                rows = self.shard_rows(shard)
                index = hnswlib.Index(space="cosine", dim=512)
                index.init_index(max_elements=len(rows), ef_construction=100, M=16, random_seed=42)
                index.add_items(np.stack([np.frombuffer(r[2], dtype=np.float32) for r in rows]), np.array([r[0] for r in rows]), num_threads=1)
                temporary = str(path) + ".tmp"
                index.save_index(temporary)
                os.replace(temporary, path)
                self.cache.execute("DELETE FROM dirty WHERE shard=?", (shard,))
                self.cache.commit()
                self.rebuilt += 1
            checkpoint()

    def matches(self, pid, threshold, complete=False):
        vector = self.vector(pid)
        if vector is None:
            return
        if complete:
            cursor = self.cache.execute("SELECT photo,vector FROM vectors ORDER BY label")
            while rows := cursor.fetchmany(BLOCK_SIZE):
                matrix = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
                for i in np.flatnonzero(matrix @ vector >= threshold - 1e-6):
                    yield rows[i][0]
            return
        import hnswlib
        for shard in self.shards():
            # Resident shards share the configured budget. Search every shard,
            # cross-date/folder matches; scopes are filtered by the caller.
            if shard not in self.loaded:
                rows = self.shard_rows(shard)
                while self.loaded and sum(len(entry[1]) for entry in self.loaded.values()) + len(rows) > self.max_resident_rows:
                    self.loaded.popitem(last=False)
                index = hnswlib.Index(space="cosine", dim=512)
                try:
                    index.load_index(str(self.root / f"{shard}.hnsw"))
                except RuntimeError:
                    self.cache.execute("INSERT OR IGNORE INTO dirty VALUES(?)", (shard,))
                    self.cache.commit()
                    self.prepare()
                    index.load_index(str(self.root / f"{shard}.hnsw"))
                self.loaded[shard] = (index, {r[0]: r[1] for r in rows})
                del rows
            self.loaded.move_to_end(shard)
            index, mapping = self.loaded[shard]
            count, k = len(mapping), min(32, len(mapping))
            fallback = False
            while k:
                if k == count:
                    fallback = True
                    break
                index.set_ef(min(count, max(100, k * 2)))
                try:
                    labels, distances = index.knn_query(vector, k=k, num_threads=1)
                except RuntimeError:
                    # Dense identical-vector components can return fewer than
                    # k reachable vertices even at ef=count. Exact shard scan
                    # prevents truncation and avoids repeated failing queries.
                    fallback = True
                    break
                if distances[0][-1] > 1 - threshold + 1e-6:
                    break
                k = min(count, k * 2)
            if fallback:
                cursor = self.cache.execute("SELECT photo,vector FROM vectors WHERE label BETWEEN ? AND ? ORDER BY label", (shard * SHARD_SIZE + 1, (shard + 1) * SHARD_SIZE))
                while rows := cursor.fetchmany(BLOCK_SIZE):
                    matrix = np.stack([np.frombuffer(row[1], dtype=np.float32) for row in rows])
                    for i in np.flatnonzero(matrix @ vector >= threshold - 1e-6):
                        yield rows[i][0]
                continue
            near_labels = labels[0][distances[0] <= 1 - threshold + 1e-6]
            if not len(near_labels):
                continue
            vectors = index.get_items(near_labels)
            scores = np.einsum("ij,j->i", vectors, vector)
            for i in np.flatnonzero(scores >= threshold - 1e-6):
                yield mapping[int(near_labels[i])]
