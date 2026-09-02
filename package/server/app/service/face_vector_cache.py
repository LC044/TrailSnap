"""Process-wide cache of normalised face embeddings for the SQLite backend.

Background
----------
PostgreSQL answers nearest-neighbour queries with pgvector's HNSW index, so
the service never materialises embeddings in Python.  SQLite has no such
index: commit 8adff5d added a fallback that loaded every candidate ``Face``
ORM entity and scored it in a Python loop, which is O(N) per face and
therefore O(N^2) per library scan.  On a 50k-face library that measured
~4.1 s per face.

This module replaces that fallback with a vectorised one:

* embeddings are read once via a streaming cursor (never ``fetchall()``, so
  peak RSS stays flat) and packed into a contiguous ``float32`` matrix;
* scoring is a single BLAS matmul instead of a Python loop;
* the matrix is cached for the lifetime of the worker process.

Why caching the matrix is safe
------------------------------
A face embedding is immutable: it is written once when the AI service
detects the face and is never updated afterwards.  Everything the product
mutates (assigning a person, rescanning, hiding, deleting) only touches
``faces.face_identity_id`` / ``faces.is_deleted`` -- scalar columns, never
``face_feature``.

So the cache is append-only and needs no invalidation.  Mutable state is
read fresh from the database on every query and applied as a boolean mask
over the cached rows.  A face row is never removed from the matrix; it is
simply masked out, which also makes un-deleting free.

Memory
------
One row costs ``dim * 4`` bytes (~2 KB at 512 dimensions).  ``MAX_CACHED_ROWS``
caps total residency; libraries beyond the cap fall back to a chunked
streaming scan that is still vectorised but keeps only one chunk in memory.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from typing import Iterator, Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.face import Face
from app.db.models.photo import Photo

logger = logging.getLogger(__name__)

# Sentinel shard key used when a caller does not scope the query to an owner.
_GLOBAL_KEY = "__all__"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring non-integer %s=%r; using %d", name, raw, default)
        return default
    if value <= 0:
        logger.warning("Ignoring non-positive %s=%r; using %d", name, raw, default)
        return default
    return value


# ~300 MB of float32 at 512 dimensions. Beyond this the chunked scan kicks in.
MAX_CACHED_ROWS = _env_int("TS_FACE_CACHE_MAX_ROWS", 150_000)
# Rows pulled per streaming step, both for cache fill and for the uncached scan.
STREAM_CHUNK_ROWS = _env_int("TS_FACE_STREAM_CHUNK", 8192)
# Smallest buffer a shard reserves. Kept low so that many small owners (or a
# long test session) cannot pin a large multiple of their actual row count.
_MIN_SHARD_CAPACITY = 128


def normalise_matrix(rows: np.ndarray) -> np.ndarray:
    """L2-normalise each row; zero rows are left as zeros (never NaN)."""
    norms = np.linalg.norm(rows, axis=1, keepdims=True)
    np.divide(rows, norms, out=rows, where=norms > 0)
    return rows


def _pack(raw_vectors: Sequence[Sequence[float]], dim: int) -> np.ndarray:
    block = np.zeros((len(raw_vectors), dim), dtype=np.float32)
    for offset, vector in enumerate(raw_vectors):
        if vector is None:
            continue
        if len(vector) != dim:
            # Mixed-dimension libraries (model switch) would corrupt the matmul.
            # Leave the row zeroed; a zero row scores distance 1.0 and is thus
            # never selected as a neighbour.
            continue
        block[offset] = vector
    return normalise_matrix(block)


class _Shard:
    """Append-only ``face_id -> normalised embedding`` matrix for one owner."""

    def __init__(self) -> None:
        self._ids = np.empty(0, dtype=np.int64)
        self._buffer = np.empty((0, 0), dtype=np.float32)
        self._size = 0
        self._dim: int | None = None
        # Embeddings are immutable and ids autoincrement, so the highest id
        # already packed is a valid incremental-load watermark.
        self.max_face_id = 0

    @property
    def size(self) -> int:
        return self._size

    @property
    def capacity(self) -> int:
        """Rows backed by allocated memory (>= ``size``)."""
        return self._buffer.shape[0]

    @property
    def ids(self) -> np.ndarray:
        return self._ids[: self._size]

    @property
    def matrix(self) -> np.ndarray:
        return self._buffer[: self._size]

    def _reserve(self, extra: int, dim: int) -> None:
        if self._dim is None:
            self._dim = dim
            initial = max(extra, _MIN_SHARD_CAPACITY)
            self._buffer = np.empty((initial, dim), dtype=np.float32)
            self._ids = np.empty(initial, dtype=np.int64)
            return
        needed = self._size + extra
        capacity = self._buffer.shape[0]
        if needed <= capacity:
            return
        # Geometric growth keeps repeated incremental appends amortised O(1).
        new_capacity = max(needed, capacity * 2)
        grown = np.empty((new_capacity, self._dim), dtype=np.float32)
        grown[: self._size] = self._buffer[: self._size]
        self._buffer = grown
        grown_ids = np.empty(new_capacity, dtype=np.int64)
        grown_ids[: self._size] = self._ids[: self._size]
        self._ids = grown_ids

    def append(self, face_ids: Sequence[int], vectors: Sequence[Sequence[float]]) -> None:
        if not face_ids:
            return
        dim = self._dim
        if dim is None:
            dim = next((len(v) for v in vectors if v is not None), None)
            if dim is None:
                return
        self._reserve(len(face_ids), dim)
        block = _pack(vectors, self._dim or dim)
        self._buffer[self._size : self._size + len(face_ids)] = block
        self._ids[self._size : self._size + len(face_ids)] = face_ids
        self._size += len(face_ids)
        self.max_face_id = max(self.max_face_id, int(max(face_ids)))


def _vector_stmt(owner_id, after_id: int):
    stmt = select(Face.id, Face.face_feature).where(
        Face.face_feature.isnot(None),
        Face.id > after_id,
    )
    if owner_id is not None:
        # Scope by owner without a JOIN so the streaming cursor stays on the
        # faces table's primary-key order.
        stmt = stmt.where(Face.photo_id.in_(select(Photo.id).where(Photo.owner_id == owner_id)))
    return stmt.order_by(Face.id)


def _stream_rows(db: Session, owner_id, after_id: int) -> Iterator[tuple[list[int], list]]:
    """Yield ``(ids, vectors)`` chunks without ever materialising the full set."""
    stmt = _vector_stmt(owner_id, after_id).execution_options(yield_per=STREAM_CHUNK_ROWS)
    ids: list[int] = []
    vectors: list = []
    for face_id, feature in db.execute(stmt):
        ids.append(int(face_id))
        vectors.append(feature)
        if len(ids) >= STREAM_CHUNK_ROWS:
            yield ids, vectors
            ids, vectors = [], []
    if ids:
        yield ids, vectors


class FaceVectorCache:
    """Thread-safe, append-only embedding cache shared by the worker process."""

    def __init__(self, max_rows: int = MAX_CACHED_ROWS) -> None:
        self._lock = threading.RLock()
        self._shards: "OrderedDict[object, _Shard]" = OrderedDict()
        self._max_rows = max_rows
        self._oversized: set = set()

    # -- internals ---------------------------------------------------------

    def _allocated_rows(self) -> int:
        """Rows actually backed by memory, not just the ones in use.

        Eviction has to account for capacity rather than ``size``: every shard
        reserves at least ``_MIN_SHARD_CAPACITY`` rows up front, so a workload
        with many small owners can pin far more memory than the logical row
        count suggests.
        """
        return sum(shard.capacity for shard in self._shards.values())

    def _evict_until_fits(self, incoming: int, keep_key) -> None:
        while self._shards and self._allocated_rows() + incoming > self._max_rows:
            victim_key, victim = next(iter(self._shards.items()))
            if victim_key == keep_key:
                if len(self._shards) == 1:
                    return
                self._shards.move_to_end(victim_key)
                continue
            self._shards.pop(victim_key)
            logger.info(
                "Evicted face vector shard %s (%d rows) to stay under %d cached rows",
                victim_key, victim.size, self._max_rows,
            )

    def _shard_key(self, owner_id):
        return _GLOBAL_KEY if owner_id is None else str(owner_id)

    def _refresh(self, db: Session, owner_id) -> _Shard | None:
        """Return an up-to-date shard, or None when the owner is too large."""
        key = self._shard_key(owner_id)
        if key in self._oversized:
            return None
        shard = self._shards.get(key)
        if shard is None:
            # Reserving before the shard is registered keeps the new shard's own
            # capacity out of the eviction budget it is being measured against.
            self._evict_until_fits(_MIN_SHARD_CAPACITY, key)
            shard = _Shard()
            self._shards[key] = shard
        self._shards.move_to_end(key)

        for ids, vectors in _stream_rows(db, owner_id, shard.max_face_id):
            if shard.size + len(ids) > self._max_rows:
                # A single owner exceeding the cap would thrash the cache; drop
                # it and let callers fall back to the chunked scan.
                logger.warning(
                    "Face library for %s exceeds %d cached rows; using streaming scan",
                    key, self._max_rows,
                )
                self._shards.pop(key, None)
                self._oversized.add(key)
                return None
            self._evict_until_fits(len(ids), key)
            shard.append(ids, vectors)
        return shard

    # -- public API --------------------------------------------------------

    def similarities(self, db: Session, owner_id, queries: np.ndarray):
        """Yield ``(ids, scores)`` blocks of cosine similarity for ``queries``.

        ``queries`` is ``(q, dim)`` and each yielded ``scores`` is ``(rows, q)``.
        Cached libraries yield exactly one block; oversized ones yield a block
        per streamed chunk so memory stays bounded.
        """
        # The matmul is computed while the lock is held, but the result is
        # yielded after releasing it. Yielding inside the critical section would
        # keep the lock for as long as the consumer takes to iterate -- and
        # indefinitely if it abandons the generator early -- which would stall
        # every other worker thread sharing this cache.
        with self._lock:
            shard = self._refresh(db, owner_id)
            cached = shard is not None
            block = None
            if shard is not None:
                matrix = shard.matrix
                if matrix.shape[0] and matrix.shape[1] == queries.shape[1]:
                    # Copy the ids: the shard's buffer may be reallocated by a
                    # later append while the consumer still holds this view.
                    block = (shard.ids.copy(), matrix @ queries.T)

        if cached:
            if block is not None:
                yield block[0], block[1]
            return

        # Oversized library: stream and score chunk by chunk.
        for chunk_ids, vectors in _stream_rows(db, owner_id, 0):
            packed = _pack(vectors, queries.shape[1])
            yield np.asarray(chunk_ids, dtype=np.int64), packed @ queries.T

    def invalidate(self, owner_id=None) -> None:
        """Drop cached rows. Only needed if embeddings are ever backfilled."""
        with self._lock:
            if owner_id is None:
                self._shards.clear()
                self._oversized.clear()
            else:
                key = self._shard_key(owner_id)
                self._shards.pop(key, None)
                self._oversized.discard(key)

    def stats(self) -> dict:
        with self._lock:
            return {
                "shards": len(self._shards),
                "rows": sum(shard.size for shard in self._shards.values()),
                "allocated_rows": self._allocated_rows(),
                "max_rows": self._max_rows,
                "oversized": sorted(self._oversized),
            }


face_vector_cache = FaceVectorCache()
