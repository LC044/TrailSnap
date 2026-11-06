"""Owner-scoped appearance clusters, transactional edits and resumable rebuilds."""
from datetime import datetime
import json
import uuid

import numpy as np
from fastapi import HTTPException
from sqlalchemy import func, text, select, update, values, column, Integer
from app.db.types import UUID as UUIDType
from sqlalchemy.orm import load_only
from sqlalchemy.orm.attributes import set_committed_value

from app.core.config_manager import config_manager
from app.db.models.face import Face, FaceCluster, FaceIdentity
from app.db.models.photo import Photo
from app.db.models.system import SystemState

_BATCH = 512
_MARGIN = 0.05
_COMPACT_DISTANCE_FACTOR = 0.5


def unit(feature):
    if feature is None:
        return None
    try:
        value = np.asarray(feature, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if value.shape != (512,) or not np.isfinite(value).all():
        return None
    norm = np.linalg.norm(value)
    return value / norm if np.isfinite(norm) and norm > 0 else None


def state_key(owner_id):
    return f"face_cluster_state:{owner_id}"


def get_state(db, owner_id):
    value = db.query(SystemState.value).filter(SystemState.key == state_key(owner_id)).scalar()
    return json.loads(value) if value else {"phase": "initializing", "generation": 0, "revision": 0}


def lock_owner(db, owner_id, *, allow_reset=False):
    """Serialize writes across workers. The caller commits or rolls back."""
    key = state_key(owner_id)
    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        lock_id = int.from_bytes(uuid.UUID(str(owner_id)).bytes[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    else:
        # Reserving the writer before reading avoids upgrading a stale WAL snapshot.
        db.execute(text("INSERT INTO system_state (key, value) VALUES (:key, :value) ON CONFLICT (key) DO NOTHING"),
                   {"key": key, "value": json.dumps({"phase": "initializing", "generation": 0, "revision": 0})})
        db.execute(text("UPDATE system_state SET value=value WHERE key=:key"), {"key": key})
    state = get_state(db, owner_id)
    if not allow_reset and state["phase"] in ("resetting", "failed"):
        raise HTTPException(409, "人物正在重新整理，请稍后重试")
    return state


def save_state(db, owner_id, state):
    row = db.get(SystemState, state_key(owner_id))
    if row is None:
        row = SystemState(key=state_key(owner_id))
        db.add(row)
    row.value = json.dumps(state)


def changed(db, owner_id):
    state = get_state(db, owner_id)
    state["revision"] = state.get("revision", 0) + 1
    save_state(db, owner_id, state)


def _visible_photo(owner_id):
    return select(Photo.id).where(Photo.id == Face.photo_id, Photo.owner_id == owner_id,
                                   Photo.is_deleted.is_(False)).exists()


def rebuild_cluster(db, cluster_id):
    cluster = db.get(FaceCluster, cluster_id)
    if cluster is None:
        return
    rows = db.query(Face.id, Face.face_feature).filter(
        Face.face_cluster_id == cluster_id, Face.is_deleted.is_(False),
        _visible_photo(cluster.owner_id),
    ).order_by(Face.id).all()
    valid = [(face_id, vector) for face_id, feature in rows if (vector := unit(feature)) is not None]
    if not valid:
        db.query(Face).filter(Face.face_cluster_id == cluster_id).update(
            {Face.face_cluster_id: None}, synchronize_session="fetch")
        cluster.anchor_face_id = None
        db.flush()
        db.delete(cluster)
        return
    total = np.sum([vector for _, vector in valid], axis=0)
    center = unit(total)
    if center is None:
        center = valid[0][1]
    cluster.vector_sum = total.tolist()
    cluster.center = center.tolist()
    cluster.face_count = len(valid)
    if cluster.anchor_face_id not in {face_id for face_id, _ in valid}:
        cluster.anchor_face_id = max(valid, key=lambda item: float(item[1] @ center))[0]
    cluster.revision += 1
    cluster.updated_at = datetime.now()


def detach(db, face):
    previous = face.face_cluster_id
    if previous is None:
        return
    cluster = db.get(FaceCluster, previous)
    face.face_cluster_id = None
    vector = unit(face.face_feature)
    if cluster is None:
        return
    if cluster.face_count <= 1 or cluster.anchor_face_id == face.id or vector is None:
        db.flush()
        rebuild_cluster(db, previous)
    else:
        total = np.asarray(cluster.vector_sum, dtype=np.float64) - vector
        center = unit(total)
        if center is None:
            db.flush()
            rebuild_cluster(db, previous)
        else:
            cluster.vector_sum = total.tolist()
            cluster.center = center.tolist()
            cluster.face_count -= 1
            cluster.revision += 1
            cluster.updated_at = datetime.now()


def attach(db, face, cluster, vector, owner_id, identity_id=None, cluster_id=None, *, defer_membership=False):
    if cluster is None:
        cluster = FaceCluster(
            id=cluster_id or uuid.uuid4(), owner_id=owner_id, identity_id=identity_id,
            center=vector.tolist(), vector_sum=vector.tolist(),
            anchor_face_id=face.id, face_count=1,
            status="active" if identity_id else "pending", revision=1,
        )
        db.add(cluster)
        # Establish the referenced row before assigning the face's FK.
        if not defer_membership:
            db.flush([cluster])
    else:
        total = np.asarray(cluster.vector_sum, dtype=np.float64) + vector
        center = unit(total)
        cluster.vector_sum = total.tolist()
        cluster.center = (center if center is not None else vector).tolist()
        cluster.face_count += 1
        cluster.revision += 1
        cluster.updated_at = datetime.now()
    if defer_membership:
        set_committed_value(face, "face_cluster_id", cluster.id)
        set_committed_value(face, "face_identity_id", cluster.identity_id)
    else:
        face.face_cluster_id = cluster.id
        face.face_identity_id = cluster.identity_id
    return cluster


class ClusterIndex:
    """Task-local mutable index. Database state is rechecked before committing."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.capacity = max(1024, len(rows) * 2)
        self.centers = np.empty((self.capacity, 512), dtype=np.float32)
        self.anchors = np.empty((self.capacity, 512), dtype=np.float32)
        self.ann = None
        self.identities = {row["identity"] for row in rows if row["identity"] is not None}
        for index, row in enumerate(rows):
            row["index"] = index
            self.centers[index] = row.pop("center")
            self.anchors[index] = row.pop("anchor")
        self._enable_ann()

    def _enable_ann(self):
        if self.ann is None and len(self.rows) >= 256:
            import hnswlib
            self.ann = hnswlib.Index(space="cosine", dim=512)
            self.ann.init_index(max_elements=self.capacity, ef_construction=100, M=16, random_seed=42)
            self.ann.set_ef(128)
            self.ann.set_num_threads(1)
            self.ann.add_items(self.anchors[:len(self.rows)], np.arange(len(self.rows)))

    def upsert(self, row):
        index = row.get("index")
        is_new = index is None
        anchor_changed = "anchor" in row
        if index is None:
            index = len(self.rows)
            row["index"] = index
            self.rows.append(row)
        if index >= self.capacity:
            self.capacity *= 2
            self.centers = np.resize(self.centers, (self.capacity, 512))
            self.anchors = np.resize(self.anchors, (self.capacity, 512))
            if self.ann is not None:
                self.ann.resize_index(self.capacity)
        self.centers[index] = row.pop("center")
        if "anchor" in row:
            self.anchors[index] = row.pop("anchor")
        if row["identity"] is not None:
            self.identities.add(row["identity"])
        if self.ann is not None:
            if is_new or anchor_changed:
                self.ann.add_items(self.anchors[index:index + 1], np.array([index]))
        else:
            self._enable_ann()

    def batch_candidates(self, vectors, threshold):
        size = len(self.rows)
        if not size:
            return [np.empty(0, dtype=int) for _ in vectors]
        if size > 8192:
            return self.ann.knn_query(vectors, k=min(64, size), num_threads=1)[0]
        # Matrix multiplication shares the library read across the whole batch.
        similarities = vectors @ self.centers[:size].T
        anchor_similarities = vectors @ self.anchors[:size].T
        candidates = []
        for scores, anchor_scores in zip(similarities, anchor_similarities):
            eligible = np.flatnonzero((scores > 1.0 - threshold) & (anchor_scores > 1.0 - threshold))
            if len(eligible) > 64:
                eligible = eligible[np.argpartition(-scores[eligible], 63)[:64]]
            if len(eligible):
                best = self.rows[int(eligible[np.argmax(scores[eligible])])]["identity"]
                if best is not None and len(self.identities) > 1:
                    others = np.array([i for i, row in enumerate(self.rows)
                                       if row["identity"] is not None and row["identity"] != best], dtype=int)
                    if len(others):
                        competitor = others[int(np.argmax(scores[others]))]
                        eligible = np.unique(np.append(eligible, competitor))
            candidates.append(eligible)
        return candidates

    def select(self, vector, threshold, identity_id=None, *, assigned_only=False, candidates=None,
               require_anchor=True, check_margin=True):
        size = len(self.rows)
        if not size:
            return None
        if identity_id is not None:
            indices = np.array([i for i, row in enumerate(self.rows) if row["identity"] == identity_id], dtype=int)
        elif candidates is not None:
            indices = candidates
        elif self.ann is not None:
            indices = self.ann.knn_query(vector.astype(np.float32), k=min(64, size))[0][0]
        else:
            indices = np.arange(size)
        if assigned_only:
            indices = np.array([i for i in indices if self.rows[int(i)]["identity"] is not None], dtype=int)
        if not len(indices):
            return None
        query = np.asarray(vector, dtype=np.float32)
        distances = np.clip(1.0 - np.einsum("ij,j->i", self.centers[indices], query), 0.0, 2.0)
        anchor_distances = np.clip(1.0 - np.einsum("ij,j->i", self.anchors[indices], query), 0.0, 2.0)
        valid = distances < threshold
        if require_anchor:
            valid &= anchor_distances < threshold
        eligible = np.flatnonzero(valid)
        if not len(eligible):
            return None
        ordered = eligible[np.argsort(distances[eligible], kind="stable")]
        best = self.rows[int(indices[ordered[0]])]
        if check_margin and identity_id is None and best["identity"] is not None:
            # Compare the nearest center of every other identity as well. This
            # prevents many clusters of one child hiding the sibling in ANN top-k.
            others = np.array([i for i in indices if self.rows[int(i)]["identity"] is not None
                               and self.rows[int(i)]["identity"] != best["identity"]], dtype=int)
            if not len(others) and self.ann is not None and len(self.identities) > 1:
                others = np.array([i for i, row in enumerate(self.rows)
                                   if row["identity"] is not None and row["identity"] != best["identity"]], dtype=int)
            if len(others):
                competitor = float(np.min(1.0 - np.einsum("ij,j->i", self.centers[others], query)))
                if competitor - float(distances[ordered[0]]) < _MARGIN:
                    return None
        return best


def load_index(db, owner_id, identity_id=None):
    query = db.query(FaceCluster.id, FaceCluster.identity_id, FaceCluster.center,
                     Face.face_feature, FaceCluster.revision).join(
        Face, Face.id == FaceCluster.anchor_face_id,
    ).outerjoin(
        FaceIdentity, FaceIdentity.id == FaceCluster.identity_id,
    ).filter(
        FaceCluster.owner_id == owner_id, _visible_photo(owner_id),
        (FaceCluster.identity_id.is_(None) | FaceIdentity.is_deleted.is_(False)),
        Face.is_deleted.is_(False),
    )
    if identity_id is not None:
        query = query.filter(FaceCluster.identity_id == identity_id)
    index = ClusterIndex([])
    for row in query.order_by(FaceCluster.id).yield_per(_BATCH):
        anchor = unit(row.face_feature)
        if anchor is not None:
            index.upsert({"id":row.id, "identity":row.identity_id, "center":row.center,
                          "anchor":anchor, "revision":row.revision})
    return index


def set_identity(db, face, identity_id, owner_id):
    """Assign one selected face, preserving the other members of its old cluster."""
    if face.face_identity_id == identity_id and face.face_cluster_id is not None:
        return
    detach(db, face)
    face.face_identity_id = identity_id
    vector = unit(face.face_feature)
    if identity_id is not None and vector is not None:
        index = load_index(db, owner_id, identity_id)
        threshold = config_manager.get_user_config(owner_id, db).ai.face_cluster_threshold
        selected = index.select(vector, threshold, identity_id)
        cluster = db.get(FaceCluster, selected["id"]) if selected else None
        attach(db, face, cluster, vector, owner_id, identity_id)
    changed(db, owner_id)


def _merge_compact_pair(db, owner_id, source, target, index, records, threshold, strict_threshold):
    source_record = records[source.id]
    target_record = records[target.id]
    source_anchor = index.anchors[source_record["index"]]
    target_anchor = index.anchors[target_record["index"]]
    core_distances = [1.0 - source_anchor @ target_anchor,
                      1.0 - np.asarray(target.center) @ source_anchor]
    if max(core_distances) >= strict_threshold:
        return False
    # Verify every member against both fixed cores and the resulting center.
    # This also protects clusters initialized from legacy, less compact data.
    center = unit(np.asarray(source.vector_sum) + np.asarray(target.vector_sum))
    if center is None:
        return False
    references = np.asarray([source_anchor, target_anchor, center])
    total = np.zeros(512, dtype=np.float64)
    count = 0
    members = db.query(Face.face_feature).filter(
        Face.face_cluster_id.in_([source.id, target.id]),
        Face.is_deleted.is_(False), _visible_photo(owner_id),
    ).yield_per(_BATCH)
    for (feature,) in members:
        vector = unit(feature)
        if vector is None or np.any(1.0 - references @ vector >= threshold):
            return False
        total += vector
        count += 1
    if count != source.face_count + target.face_count:
        return False
    target.vector_sum = total.tolist()
    target.center = unit(total).tolist()
    target.face_count = count
    target.status = "active" if target.identity_id else "pending"
    target.revision += 1
    target.updated_at = datetime.now()
    db.query(Face).filter(Face.face_cluster_id == source.id).update(
        {Face.face_cluster_id: target.id, Face.face_identity_id: target.identity_id},
        synchronize_session="fetch",
    )
    source.anchor_face_id = None
    db.flush()
    db.delete(source)
    db.flush()
    target_record.update(center=target.center, revision=target.revision)
    index.upsert(target_record)
    return True


def _compact_clusters(db, owner_id, threshold, index, merge_threshold=None):
    """Physically consolidate compatible appearances under the owner's lock."""
    groups = db.query(FaceCluster.id, FaceCluster.identity_id, FaceCluster.face_count).filter(
        FaceCluster.owner_id == owner_id,
    ).order_by(FaceCluster.face_count, FaceCluster.id).all()
    counts = {group.id: group.face_count for group in groups}
    records = {record["id"]: record for record in index.rows}
    merged = 0
    strict_threshold = min(threshold, merge_threshold if merge_threshold is not None
                           else threshold * _COMPACT_DISTANCE_FACTOR)
    for group in groups:
        if group.id not in counts or group.id not in records:
            continue
        source_record = records[group.id]
        vector = index.centers[source_record["index"]]
        if index.ann is None:
            neighbors = np.arange(len(index.rows))
        else:
            neighbors = index.ann.knn_query(vector, k=min(64, len(index.rows)))[0][0]
        eligible = []
        for label in neighbors:
            candidate = index.rows[int(label)]
            candidate_id = candidate["id"]
            if candidate_id == group.id or candidate_id not in counts:
                continue
            if source_record["identity"] is not None and candidate["identity"] != source_record["identity"]:
                continue
            # Preserve an established identity. Otherwise move the smaller
            # group, with a stable tie-break, to limit membership writes.
            inherits_identity = source_record["identity"] is None and candidate["identity"] is not None
            if not inherits_identity and (counts[candidate_id], str(candidate_id)) <= (counts[group.id], str(group.id)):
                continue
            eligible.append(int(label))
        matched = index.select(vector, strict_threshold, candidates=np.asarray(eligible, dtype=int), check_margin=False)
        if matched is None:
            continue
        source = db.get(FaceCluster, group.id)
        target = db.get(FaceCluster, matched["id"])
        if _merge_compact_pair(db, owner_id, source, target, index, records, threshold, strict_threshold):
            counts[target.id] += counts.pop(source.id)
            merged += 1
    return merged


def _representative_samples(db, owner_id, cluster_id, center, cache):
    if cluster_id in cache:
        return cache[cluster_id]
    # Keep only three closest representatives from distinct photos in memory.
    samples = {}
    center = np.asarray(center)
    rows = db.query(Face.photo_id, Face.face_feature).filter(
        Face.face_cluster_id == cluster_id, Face.is_deleted.is_(False), _visible_photo(owner_id),
    ).yield_per(_BATCH)
    for photo_id, feature in rows:
        vector = unit(feature)
        if vector is None:
            continue
        distance = float(1.0 - center @ vector)
        previous = samples.get(photo_id)
        if previous is not None and previous[0] <= distance:
            continue
        samples[photo_id] = (distance, vector)
        if len(samples) > 3:
            samples.pop(max(samples, key=lambda photo: samples[photo][0]))
    result = np.asarray([item[1] for item in sorted(samples.values(), key=lambda item: item[0])])
    cache[cluster_id] = result
    return result


def _samples_support(db, owner_id, first_id, first_center, second_id, second_center, threshold, cache):
    first = _representative_samples(db, owner_id, first_id, first_center, cache)
    second = _representative_samples(db, owner_id, second_id, second_center, cache)
    if len(first) < 2 or len(second) < 2:
        return False
    distances = np.clip(1.0 - first @ second.T, 0.0, 2.0)
    return bool(np.all(np.min(distances, axis=0) < threshold)
                and np.all(np.min(distances, axis=1) < threshold))


def _merge_unnamed_identities(db, owner_id, config):
    """Reconcile automatic unnamed groups under the existing owner lock."""
    groups = db.query(FaceCluster.id, FaceCluster.identity_id, FaceCluster.center,
                      FaceCluster.face_count).join(FaceIdentity, FaceIdentity.id == FaceCluster.identity_id).filter(
        FaceCluster.owner_id == owner_id, FaceIdentity.owner_id == owner_id,
        FaceIdentity.is_deleted.is_(False), FaceIdentity.identity_name == "未命名",
    ).order_by(FaceCluster.face_count, FaceCluster.id).all()
    counts = {}
    for group in groups:
        counts[group.identity_id] = counts.get(group.identity_id, 0) + group.face_count
    if len(counts) < 2:
        return 0
    # Fixed-center recall also handles broad legacy clusters with atypical anchors.
    index = ClusterIndex([{"id":group.id, "identity":group.identity_id,
                           "center":group.center, "anchor":group.center, "revision":0} for group in groups])
    center_threshold = getattr(config, "face_identity_merge_threshold", config.face_cluster_threshold * .4)
    sample_threshold = getattr(config, "face_identity_match_threshold", config.face_cluster_threshold * .85)
    cache = {}
    merged = 0
    from app.crud.face import merge_identities
    for source in index.rows:
        source_identity = source["identity"]
        vector = index.centers[source["index"]]
        if index.ann is None:
            neighbors = np.arange(len(index.rows))
        else:
            neighbors = index.ann.knn_query(vector, k=min(64, len(index.rows)))[0][0]
        distances = np.clip(1.0 - np.einsum("ij,j->i", index.centers[neighbors], vector), 0.0, 2.0)
        for offset in np.argsort(distances, kind="stable"):
            if distances[offset] >= center_threshold:
                break
            target = index.rows[int(neighbors[offset])]
            target_identity = target["identity"]
            if target_identity == source_identity:
                continue
            if (counts[target_identity], str(target_identity)) <= (counts[source_identity], str(source_identity)):
                continue
            if not _samples_support(db, owner_id, source["id"], vector, target["id"],
                                    index.centers[target["index"]], sample_threshold, cache):
                continue
            # Both IDs come from this owner's query. The transaction lock is
            # already held, including while publishing a reset result.
            merge_identities(db, target_identity, [source_identity], commit=False)
            counts[target_identity] += counts.pop(source_identity)
            for record in index.rows:
                if record["identity"] == source_identity:
                    record["identity"] = target_identity
            merged += 1
            break
    return merged


def _promote_clusters(db, owner_id, minimum, assigned=None, threshold=None):
    candidates = db.query(FaceCluster).filter(
        FaceCluster.owner_id == owner_id, FaceCluster.identity_id.is_(None),
        FaceCluster.face_count >= minimum,
    ).order_by(FaceCluster.anchor_face_id, FaceCluster.id).all()
    if not candidates:
        return
    if assigned is None:
        assigned = load_index(db, owner_id)
    if threshold is None:
        config = config_manager.get_user_config(owner_id, db).ai
        threshold = getattr(config, "face_identity_match_threshold", config.face_cluster_threshold * .95)
    counts = dict(db.query(Face.face_cluster_id, func.count(func.distinct(Face.photo_id))).filter(
        Face.face_cluster_id.in_([c.id for c in candidates]), Face.is_deleted.is_(False),
        _visible_photo(owner_id),
    ).group_by(Face.face_cluster_id).all())
    cache = {}
    for cluster in candidates:
        if counts.get(cluster.id, 0) < minimum:
            continue
        matched = assigned.select(np.asarray(cluster.center), threshold, assigned_only=True,
                                  require_anchor=False, check_margin=False)
        identity = None
        if matched:
            if _samples_support(db, owner_id, cluster.id, cluster.center, matched["id"],
                                assigned.centers[matched["index"]], threshold, cache):
                identity = db.get(FaceIdentity, matched["identity"])
        if identity is None:
            identity = FaceIdentity(id=uuid.uuid4(), owner_id=owner_id, identity_name="未命名",
                                    default_face_id=cluster.anchor_face_id)
            db.add(identity)
            db.flush([identity])
        cluster.identity_id = identity.id
        cluster.status = "active"
        cluster.revision += 1
        record = next(row for row in assigned.rows if row["id"] == cluster.id)
        record["identity"] = identity.id
        record["revision"] = cluster.revision
        assigned.identities.add(identity.id)
        db.query(Face).filter(Face.face_cluster_id == cluster.id).update(
            {Face.face_identity_id: identity.id}, synchronize_session=False)


def _promote_batch(db, owner_id, current_clusters, current_faces, minimum, index):
    pending = [cluster for cluster in current_clusters.values()
               if cluster.identity_id is None and cluster.face_count >= minimum]
    if not pending:
        return
    photos = {cluster.id: set() for cluster in pending}
    for cluster_id, photo_id in db.query(Face.face_cluster_id, Face.photo_id).filter(
        Face.face_cluster_id.in_(photos), Face.is_deleted.is_(False),
        _visible_photo(owner_id),
    ).all():
        photos[cluster_id].add(photo_id)
    for face in current_faces.values():
        if face.face_cluster_id in photos:
            photos[face.face_cluster_id].add(face.photo_id)
    config = config_manager.get_user_config(owner_id, db).ai
    threshold = getattr(config, "face_identity_match_threshold", config.face_cluster_threshold * .85)
    promoted = []
    for cluster in pending:
        if len(photos[cluster.id]) < minimum:
            continue
        # Cross-appearance links need actual stored members and are checked
        # after the pass. Clearly separate groups can be published with their
        # first membership write, saving a second rewrite of wide SQLite rows.
        if index.select(np.asarray(cluster.center), threshold, assigned_only=True,
                        require_anchor=False, check_margin=False) is not None:
            continue
        identity = FaceIdentity(id=uuid.uuid4(), owner_id=owner_id, identity_name="未命名",
                                default_face_id=cluster.anchor_face_id)
        db.add(identity)
        promoted.append((cluster, identity))
        cluster.identity_id = identity.id
        cluster.status = "active"
        cluster.revision += 1
        record = next(row for row in index.rows if row["id"] == cluster.id)
        record["identity"] = identity.id
        record["revision"] = cluster.revision
        index.identities.add(identity.id)
        for face in current_faces.values():
            if face.face_cluster_id == cluster.id:
                set_committed_value(face, "face_identity_id", identity.id)
    if promoted:
        db.flush([identity for _, identity in promoted])
    for cluster, identity in promoted:
        if cluster not in db.new:
            db.query(Face).filter(Face.face_cluster_id == cluster.id).update(
                {Face.face_identity_id: identity.id}, synchronize_session=False)


def _unclustered_batch(db, owner_id, last_id):
    if db.bind.dialect.name == "sqlite":
        # Keep the keyset scan on the narrow partial index. SQLite otherwise
        # drives this from all owner photos and sorts wide embedding rows.
        rows = db.execute(text("""
            SELECT f.id, f.face_feature, f.face_identity_id
            FROM faces AS f INDEXED BY ix_faces_unclustered
            WHERE f.face_cluster_id IS NULL AND f.is_deleted = false
              AND f.face_feature IS NOT NULL AND f.id > :cursor
              AND EXISTS (SELECT 1 FROM photos AS p WHERE p.id=f.photo_id
                          AND p.owner_id=:owner AND p.is_deleted=false)
            ORDER BY f.id LIMIT :limit
        """), {"cursor": last_id, "owner": str(owner_id), "limit": _BATCH}).all()
        from types import SimpleNamespace
        return [SimpleNamespace(id=row.id, face_feature=json.loads(row.face_feature),
                                face_identity_id=uuid.UUID(row.face_identity_id) if row.face_identity_id else None)
                for row in rows]
    pending = db.query(Face.id).filter(
        _visible_photo(owner_id), Face.is_deleted == text("false"),
        Face.face_cluster_id.is_(None), Face.face_feature.isnot(None), Face.id > last_id,
    ).order_by(Face.id).limit(_BATCH).cte("pending_face_ids").prefix_with("MATERIALIZED")
    return db.query(Face.id, Face.face_feature, Face.face_identity_id).join(
        pending, pending.c.id == Face.id,
    ).order_by(Face.id).all()


def _write_members(db, members_by_cluster, current_clusters):
    if not members_by_cluster:
        return
    if db.bind.dialect.name == "postgresql":
        assignments = [(face_id, cluster_id, current_clusters[cluster_id].identity_id)
                       for cluster_id, member_ids in members_by_cluster.items() for face_id in member_ids]
        rows = values(column("face_id", Integer), column("cluster_id", UUIDType()),
                      column("identity_id", UUIDType()), name="assigned_faces").data(assignments)
        db.execute(update(Face).where(Face.id == rows.c.face_id).values(
            face_cluster_id=rows.c.cluster_id.cast(UUIDType()),
            face_identity_id=rows.c.identity_id.cast(UUIDType()),
        ).execution_options(synchronize_session=False))
    else:
        for cluster_id, member_ids in members_by_cluster.items():
            db.query(Face).filter(Face.id.in_(member_ids)).update(
                {Face.face_cluster_id:cluster_id,
                 Face.face_identity_id:current_clusters[cluster_id].identity_id}, synchronize_session=False)


def process_faces(db, owner_id):
    """Initialize legacy members and consume unclustered faces in bounded batches."""
    config = config_manager.get_user_config(owner_id, db).ai
    last_id = 0
    index = None
    index_revision = None
    while True:
        state = lock_owner(db, owner_id, allow_reset=True)
        generation = state.get("generation", 0)
        if state.get("phase") == "failed":
            db.rollback()
            return
        resetting = state.get("phase") == "resetting"
        if resetting and not state.get("cleared"):
            _clear_results(db, owner_id)
            last_id = 0
            index = None
            index_revision = None
            state["cleared"] = True
            state["revision"] = state.get("revision", 0) + 1
            save_state(db, owner_id, state)
            db.commit()
            continue
        if state.get("params"):
            from types import SimpleNamespace
            config = SimpleNamespace(**state["params"])
        revision = state.get("revision", 0)
        db.commit()
        if index is None or index_revision != revision:
            index = load_index(db, owner_id)
        # Read scalars to avoid carrying stale ORM faces across the computation.
        rows = _unclustered_batch(db, owner_id, last_id)
        db.commit()
        if not rows:
            state = lock_owner(db, owner_id, allow_reset=True)
            if state.get("generation", 0) != generation:
                db.rollback()
                last_id = 0
                continue
            if state.get("revision", 0) != revision:
                db.rollback()
                index = None
                last_id = 0
                continue
            if _compact_clusters(db, owner_id, config.face_cluster_threshold, index,
                                 getattr(config, "face_cluster_merge_threshold", None)):
                index = load_index(db, owner_id)
            _promote_clusters(db, owner_id, config.face_recognition_min_photos, index,
                              getattr(config, "face_identity_match_threshold", config.face_cluster_threshold * .85))
            db.flush()
            _merge_unnamed_identities(db, owner_id, config)
            state["phase"] = "ready"
            state["revision"] = state.get("revision", 0) + 1
            state.pop("error", None)
            state.pop("params", None)
            save_state(db, owner_id, state)
            db.commit()
            return
        # Compute matching outside a write transaction. Include the newly
        # proposed centers so faces in the same batch can create compact groups.
        plans = []
        prepared = [(row, vector) for row in rows if (vector := unit(row.face_feature)) is not None]
        base_size = len(index.rows)
        candidate_batches = index.batch_candidates(
            np.asarray([vector for _, vector in prepared], dtype=np.float32), config.face_cluster_threshold,
        ) if prepared else []
        for (row, vector), initial_candidates in zip(prepared, candidate_batches):
            candidates = np.concatenate((np.asarray(initial_candidates, dtype=np.int64),
                                         np.arange(base_size, len(index.rows))))
            selected = index.select(vector, config.face_cluster_threshold, row.face_identity_id,
                                    candidates=candidates)
            if selected is None:
                selected = {"id": uuid.uuid4(), "identity": row.face_identity_id,
                            "center": vector, "anchor": vector, "revision": None}
                index.upsert(selected)
            plans.append((row, vector, selected["id"]))
        state = lock_owner(db, owner_id, allow_reset=True)
        if state.get("generation", 0) != generation or state.get("revision", 0) != revision:
            last_id = 0
            db.rollback()
            index = None
            continue
        index_rows = {item["id"]: item for item in index.rows}
        face_ids = [row.id for row, _, _ in plans]
        current_faces = {face.id: face for face in db.query(Face).options(load_only(
            Face.id, Face.photo_id, Face.face_identity_id, Face.face_cluster_id, Face.is_deleted,
        )).filter(
            Face.id.in_(face_ids), _visible_photo(owner_id),
            Face.is_deleted.is_(False),
        ).populate_existing().all()}
        cluster_ids = {cluster_id for _, _, cluster_id in plans}
        current_clusters = {cluster.id: cluster for cluster in db.query(FaceCluster).filter(
            FaceCluster.id.in_(cluster_ids), FaceCluster.owner_id == owner_id,
        ).all()}
        touched = set()
        members_by_cluster = {}
        for row, vector, cluster_id in plans:
            face = current_faces.get(row.id)
            if face is None or face.face_cluster_id is not None or face.face_identity_id != row.face_identity_id:
                continue
            cluster = attach(db, face, current_clusters.get(cluster_id), vector,
                             owner_id, row.face_identity_id, cluster_id, defer_membership=True)
            members_by_cluster.setdefault(cluster_id, []).append(face.id)
            current_clusters[cluster_id] = cluster
            touched.add(cluster_id)
        for cluster_id in touched:
            cluster = current_clusters[cluster_id]
            item = index_rows[cluster_id]
            item["center"] = cluster.center
            item["identity"] = cluster.identity_id
            item["revision"] = cluster.revision
            index.upsert(item)
        if not resetting:
            _promote_batch(db, owner_id, current_clusters, current_faces,
                           config.face_recognition_min_photos, index)
        new_clusters = [cluster for cluster in current_clusters.values() if cluster in db.new]
        if new_clusters:
            db.flush(new_clusters)
        _write_members(db, members_by_cluster, current_clusters)
        db.flush()
        state["revision"] = revision + 1
        state["checkpoint"] = rows[-1].id
        save_state(db, owner_id, state)
        db.commit()
        last_id = rows[-1].id
        index_revision = revision + 1


def _clear_results(db, owner_id):
    photos = db.query(Photo.id).filter(Photo.owner_id == owner_id)
    db.query(Face).filter(Face.photo_id.in_(photos)).update(
        {Face.face_cluster_id: None, Face.face_identity_id: None, Face.recognize_confidence: None},
        synchronize_session=False)
    db.query(FaceCluster).filter(FaceCluster.owner_id == owner_id).update(
        {FaceCluster.anchor_face_id: None}, synchronize_session=False)
    db.query(FaceCluster).filter(FaceCluster.owner_id == owner_id).delete(synchronize_session=False)
    db.query(FaceIdentity).filter(FaceIdentity.owner_id == owner_id).update(
        {FaceIdentity.is_deleted: True, FaceIdentity.default_face_id: None}, synchronize_session=False)
    from app.db.models.person_timeline import PersonTimelineHide
    db.query(PersonTimelineHide).filter(PersonTimelineHide.owner_id == owner_id).delete(synchronize_session=False)


def request_reset(db, owner_id, request_id=None):
    state = lock_owner(db, owner_id, allow_reset=True)
    from app.service.tasks.face_cluster import enqueue_cluster_faces
    if request_id and state.get("request_id") == str(request_id):
        db.commit()
        return state
    if state.get("phase") != "resetting":
        config = config_manager.get_user_config(owner_id, db).ai
        state = {"phase": "resetting", "generation": state.get("generation", 0) + 1,
                 "revision": state.get("revision", 0) + 1, "cleared": False,
                 "request_id": str(request_id) if request_id else None,
                 "params": {"face_cluster_threshold": config.face_cluster_threshold,
                            "face_recognition_min_photos": config.face_recognition_min_photos}}
        for key in ("face_cluster_merge_threshold", "face_identity_match_threshold", "face_identity_merge_threshold"):
            if hasattr(config, key):
                state["params"][key] = getattr(config, key)
        save_state(db, owner_id, state)
    task = enqueue_cluster_faces(db, owner_id, commit=False)
    task.payload = {**(task.payload or {}), "owner_id": str(owner_id), "reset": True, "auto": False}
    db.commit()
    return get_state(db, owner_id)


def detach_photo_clusters(db, photo_ids):
    """Remove deleted photos from cluster statistics before their rows disappear."""
    if not photo_ids:
        return
    for offset in range(0, len(photo_ids), 200):
        ids = photo_ids[offset:offset + 200]
        rows = db.query(Face.face_cluster_id, Photo.owner_id).join(Photo).filter(
            Face.photo_id.in_(ids), Face.face_cluster_id.isnot(None),
        ).distinct().all()
        for owner_id in sorted({owner for _, owner in rows}, key=str):
            lock_owner(db, owner_id, allow_reset=True)
        db.query(Face).filter(Face.photo_id.in_(ids)).update(
            {Face.face_cluster_id: None}, synchronize_session="fetch")
        for cluster_id, _ in rows:
            rebuild_cluster(db, cluster_id)
        for owner_id in {owner for _, owner in rows}:
            changed(db, owner_id)



def retry_clustering(db, owner_id):
    state = lock_owner(db, owner_id, allow_reset=True)
    if state.get("phase") == "failed":
        state["phase"] = "resetting" if "cleared" in state else "initializing"
        state.pop("error", None)
        save_state(db, owner_id, state)
        from app.service.tasks.face_cluster import enqueue_cluster_faces
        task = enqueue_cluster_faces(db, owner_id, commit=False)
        task.payload = {"owner_id":str(owner_id), "auto":False, "reset":"cleared" in state}
    db.commit()
    return state
