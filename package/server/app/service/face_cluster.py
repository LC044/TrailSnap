import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sklearn.cluster import DBSCAN
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import Photo
from app.service.face_vector_cache import face_vector_cache, normalise_matrix
from app.crud import face as crud_face
from app.schemas import face as schemas
import logging
import os
import uuid
from datetime import datetime
from sqlalchemy.exc import PendingRollbackError, SQLAlchemyError

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _int_env(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


# Rows per round trip when streaming the unassigned pool out of the database.
# Bounds what the driver buffers so peak memory tracks the embedding matrix
# rather than the raw result set.
_FETCH_BATCH = _int_env("TS_FACE_CLUSTER_FETCH_BATCH", 1000, 100)


class FaceRescanError(RuntimeError):
    """Raised when an identity rescan fails and its transaction is rolled back."""


class FaceRescanConflictError(FaceRescanError):
    """Raised when a reviewed rescan selection is no longer valid."""


# Number of top-similarity faces verified against the database per round when
# resolving a nearest neighbour on SQLite.
_NEAREST_WINDOW = 64


from app.core.config_manager import config_manager

class FaceClusterService:
    MAX_RESCAN_PROTOTYPES = 12
    MAX_RESCAN_REFERENCE_SAMPLE = 200
    MANUAL_ASSIGNMENT_CONFIDENCE = 0.999

    def __init__(self, db: Session, user_id: uuid.UUID = None):
        self.db = db
        self.owner_id = user_id
        # Initialize from config
        if user_id:
            config = config_manager.get_user_config(user_id, db)
            self.SIMILARITY_THRESHOLD = config.ai.face_recognition_threshold
            self.DISTANCE_THRESHOLD = config.ai.face_cluster_threshold
            self.RESCAN_AUTO_MATCH_THRESHOLD = config.ai.face_rescan_auto_match_threshold
            self.RESCAN_CANDIDATE_THRESHOLD = max(
                self.RESCAN_AUTO_MATCH_THRESHOLD,
                config.ai.face_rescan_candidate_threshold,
            )
            self.RESCAN_REMOVAL_THRESHOLD = max(
                self.RESCAN_CANDIDATE_THRESHOLD,
                config.ai.face_rescan_removal_threshold,
            )
            self.MIN_CLUSTER_SIZE_FOR_IDENTITY = config.ai.face_recognition_min_photos
        else:
            # Fallback (should be avoided)
            self.SIMILARITY_THRESHOLD = 0.7
            self.DISTANCE_THRESHOLD = 0.4
            self.RESCAN_AUTO_MATCH_THRESHOLD = 0.35
            self.RESCAN_CANDIDATE_THRESHOLD = 0.45
            self.RESCAN_REMOVAL_THRESHOLD = 0.52
            self.MIN_CLUSTER_SIZE_FOR_IDENTITY = 5
            
        self.DBSCAN_EPS = self.DISTANCE_THRESHOLD
        self.DBSCAN_MIN_SAMPLES = 5
        self.CLUSTER_MERGE_THRESHOLD = self.DISTANCE_THRESHOLD + 0.08

    @staticmethod
    def normalize_embedding(embedding: list | np.ndarray) -> np.ndarray:
        """
        向量L2归一化（全链路统一，避免距离计算失真）
        :param embedding: 人脸特征向量（列表/数组）
        :return: 归一化后的向量
        """
        if isinstance(embedding, list):
            emb = np.array(embedding)
        else:
            emb = embedding.copy()

        # 避免除以0
        norm = np.linalg.norm(emb)
        if norm == 0:
            logger.warning("空向量（范数为0），返回原向量")
            return emb
        return emb / norm

    def assign_face_to_identity(self, face_id: int, embedding: list, owner_id: uuid.UUID = None, *, commit: bool = True) -> uuid.UUID | None:
        """Compatibility entry point: defer recognition output to batch clustering."""
        # The CPU clustering task processes committed faces as a batch.
        return None

    def _assigned_face_query(self, owner_id: uuid.UUID | None):
        query = self.db.query(Face.id, Face.face_identity_id).filter(
            Face.face_identity_id.isnot(None),
            Face.is_deleted.is_(False),
        )
        if owner_id:
            # Drive candidate verification from faces, not all of the owner's
            # photos. SQLite can otherwise nest every candidate id lookup
            # inside a scan of the entire photo library.
            query = query.filter(select(Photo.id).where(
                Photo.id == Face.photo_id,
                Photo.owner_id == owner_id,
            ).exists())
        return query

    def _resolve_assigned_candidates(
        self,
        candidate_ids: np.ndarray,
        owner_id: uuid.UUID | None,
    ) -> dict:
        """Map a small id window to its identity, keeping only eligible faces."""
        if candidate_ids.size == 0:
            return {}
        query = self._assigned_face_query(owner_id).filter(
            Face.id.in_([int(value) for value in candidate_ids]),
        )
        return {int(row[0]): row[1] for row in query.all()}

    def _sqlite_nearest_assigned_face(
        self,
        target_emb: np.ndarray,
        face_id: int,
        owner_id: uuid.UUID | None,
    ) -> tuple[int, uuid.UUID, float] | None:
        """Vectorised nearest-neighbour lookup over the cached embedding matrix.

        Only the most similar candidates are checked against the database.
        Listing every assigned face up front would rebuild an ORM row per
        library face on every call, which dominated the runtime and defeated
        the point of the matmul.
        """
        # No assigned reference means every widening window would be empty.
        # Check live database state on each lookup rather than caching a negative
        # result: an identity may be assigned later in this session or elsewhere.
        if self._assigned_face_query(owner_id).filter(Face.id != face_id).first() is None:
            return None

        queries = np.ascontiguousarray(target_emb, dtype=np.float32).reshape(1, -1)
        id_blocks = []
        score_blocks = []
        for ids, scores in face_vector_cache.similarities(self.db, owner_id, queries):
            keep = ids != face_id
            if not keep.any():
                continue
            id_blocks.append(ids[keep])
            score_blocks.append(scores[:, 0][keep])

        if not id_blocks:
            return None
        ids = np.concatenate(id_blocks)
        scores = np.concatenate(score_blocks)
        total = int(ids.size)
        if total == 0:
            return None

        # Widen the verification window geometrically. In practice the true
        # neighbour is in the first window; the loop only grows when most of
        # the library is still unassigned.
        scanned = 0
        while scanned < total:
            limit = min(max(_NEAREST_WINDOW, scanned * 8), total)
            if limit < total:
                window = np.argpartition(-scores, limit - 1)[:limit]
            else:
                window = np.arange(total)
            window = window[np.argsort(-scores[window])][scanned:limit]
            if window.size:
                resolved = self._resolve_assigned_candidates(ids[window], owner_id)
                if resolved:
                    # ``window`` is sorted by descending similarity, so the
                    # first eligible hit is the nearest neighbour.
                    for offset in window:
                        identity_id = resolved.get(int(ids[offset]))
                        if identity_id is not None:
                            distance = float(np.clip(1.0 - float(scores[offset]), 0.0, 2.0))
                            return int(ids[offset]), identity_id, distance
            scanned = limit
        return None

    def preview_identity_rescan(self, identity_id: uuid.UUID, owner_id: uuid.UUID = None,
                                *, threshold: float | None = None,
                                removal_threshold: float | None = None) -> dict:
        """Return add/remove candidates without changing any face assignment."""
        try:
            analysis = self._analyze_identity_rescan(identity_id, owner_id, lock=False,
                **({"threshold": threshold} if threshold is not None else {}),
                **({"removal_threshold": removal_threshold} if removal_threshold is not None else {}))
            return self._serialize_rescan_preview(analysis)
        except Exception as exc:
            self.db.rollback()
            logger.error("预览人物 %s 重新扫描失败：%s", identity_id, exc, exc_info=True)
            raise FaceRescanError(f"Failed to preview identity rescan {identity_id}") from exc

    def apply_identity_rescan(
        self,
        identity_id: uuid.UUID,
        owner_id: uuid.UUID,
        add_face_ids: list[int],
        remove_face_ids: list[int],
        *, threshold: float | None = None,
        removal_threshold: float | None = None,
    ) -> dict:
        """Recompute and atomically apply only the candidates confirmed by the user."""
        try:
            from app.service.face_appearance_clusters import lock_owner
            lock_owner(self.db, owner_id)
            self.owner_id = owner_id
            analysis = self._analyze_identity_rescan(identity_id, owner_id, lock=True,
                **({"threshold": threshold} if threshold is not None else {}),
                **({"removal_threshold": removal_threshold} if removal_threshold is not None else {}))
            valid_add_ids = {item["face"].id for item in analysis["add_candidates"]}
            valid_remove_ids = {item["face"].id for item in analysis["remove_candidates"]}
            selected_add_ids = set(add_face_ids)
            selected_remove_ids = set(remove_face_ids)
            if not selected_add_ids.issubset(valid_add_ids) or not selected_remove_ids.issubset(valid_remove_ids):
                raise FaceRescanConflictError("Rescan candidates changed; preview again")
            return self._apply_rescan_analysis(analysis, selected_add_ids, selected_remove_ids)
        except FaceRescanConflictError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.error("应用人物 %s 重新扫描失败：%s", identity_id, exc, exc_info=True)
            raise FaceRescanError(f"Failed to apply identity rescan {identity_id}") from exc

    def rescan_identity(self, identity_id: uuid.UUID, owner_id: uuid.UUID = None) -> dict:
        """Apply high-confidence additions and all removal candidates for API compatibility."""
        try:
            from app.service.face_appearance_clusters import lock_owner
            lock_owner(self.db, owner_id)
            self.owner_id = owner_id
            analysis = self._analyze_identity_rescan(identity_id, owner_id, lock=True)
            return self._apply_rescan_analysis(
                analysis,
                {
                    item["face"].id
                    for item in analysis["add_candidates"]
                    if item["distance"] <= self.RESCAN_AUTO_MATCH_THRESHOLD
                },
                {item["face"].id for item in analysis["remove_candidates"]},
            )
        except Exception as exc:
            self.db.rollback()
            logger.error("重新扫描人物 %s 失败：%s", identity_id, exc, exc_info=True)
            if isinstance(exc, FaceRescanError):
                raise
            raise FaceRescanError(f"Failed to rescan identity {identity_id}") from exc

    def _analyze_identity_rescan(
        self,
        identity_id: uuid.UUID,
        owner_id: uuid.UUID | None,
        lock: bool,
        threshold: float | None = None,
        removal_threshold: float | None = None,
    ) -> dict:
        assigned_query = self.db.query(Face).join(Photo).filter(
            Face.face_identity_id == identity_id,
            Face.is_deleted.is_(False),
            Face.face_feature.isnot(None),
            Photo.is_deleted.is_(False),
        )
        if owner_id:
            assigned_query = assigned_query.filter(Photo.owner_id == owner_id)
        assigned_query = assigned_query.order_by(Face.id)
        if lock:
            assigned_query = assigned_query.with_for_update(of=Face)
        assigned_faces = assigned_query.all()

        candidate_threshold = self.RESCAN_CANDIDATE_THRESHOLD if threshold is None else threshold
        removal_threshold = self.RESCAN_REMOVAL_THRESHOLD if removal_threshold is None else removal_threshold
        if not assigned_faces:
            return {
                "identity_id": identity_id,
                "owner_id": owner_id,
                "reason": "no_reference_faces",
                "prototypes": [],
                "add_candidates": [],
                "remove_candidates": [],
                "removal_threshold": removal_threshold,
                "candidate_threshold": candidate_threshold,
            }

        embeddings = [self.normalize_embedding(face.face_feature) for face in assigned_faces]
        identity = crud_face.get_identity(self.db, identity_id, owner_id=owner_id)
        default_face_id = identity.default_face_id if identity else None
        trusted_indices, prototypes = self._select_rescan_references(assigned_faces, embeddings, default_face_id)
        manually_confirmed_indices = {
            index for index, face in enumerate(assigned_faces) if self._is_manually_confirmed(face)
        }

        remove_candidates = []
        if len(assigned_faces) >= 3:
            trusted_index_set = set(trusted_indices)
            for index, face in enumerate(assigned_faces):
                if index in trusted_index_set or index in manually_confirmed_indices:
                    continue
                min_distance = min(self._cosine_distance(embeddings[index], ref) for ref in prototypes)
                if min_distance > removal_threshold:
                    remove_candidates.append({"face": face, "distance": min_distance})

        matching_face_ids = self._find_matching_face_ids(
            prototypes,
            owner_id,
            threshold=candidate_threshold,
        )
        candidate_faces = []
        if matching_face_ids:
            candidate_query = self.db.query(Face).join(Photo).filter(
                Face.id.in_(matching_face_ids),
                Face.is_deleted.is_(False),
                Face.face_feature.isnot(None),
                Photo.is_deleted.is_(False),
            )
            if owner_id:
                candidate_query = candidate_query.filter(Photo.owner_id == owner_id)
            if lock:
                candidate_query = candidate_query.with_for_update(of=Face)
            candidate_faces = candidate_query.all()

        removal_ids = {item["face"].id for item in remove_candidates}
        currently_kept_ids = {face.id for face in assigned_faces} - removal_ids
        add_candidates = []
        for face in candidate_faces:
            if face.face_identity_id == identity_id or face.id in currently_kept_ids:
                continue
            min_distance = min(
                self._cosine_distance(self.normalize_embedding(face.face_feature), prototype)
                for prototype in prototypes
            )
            if min_distance > candidate_threshold:
                continue
            if face.face_identity_id and face.face_identity_id != identity_id and self._is_manually_confirmed(face):
                continue
            add_candidates.append({"face": face, "distance": min_distance})

        # ``candidate_faces`` comes back in database order; sort by similarity
        # (distance ascending) so the preview grid shows the best matches first.
        add_candidates.sort(key=lambda item: (item["distance"], item["face"].id))
        # Removals rank least-similar first (distance descending): the further
        # a face is from the trusted prototypes, the more suspect it is.
        remove_candidates.sort(key=lambda item: (-item["distance"], item["face"].id))

        return {
            "identity_id": identity_id,
            "owner_id": owner_id,
            "reason": None,
            "prototypes": prototypes,
            "add_candidates": add_candidates,
            "remove_candidates": remove_candidates,
            "removal_threshold": removal_threshold,
            "candidate_threshold": candidate_threshold,
        }

    def _serialize_rescan_preview(self, analysis: dict) -> dict:
        identity_ids = {
            item["face"].face_identity_id
            for item in analysis["add_candidates"]
            if item["face"].face_identity_id
        }
        identity_names = {}
        if identity_ids:
            identity_query = self.db.query(FaceIdentity.id, FaceIdentity.identity_name).filter(
                FaceIdentity.id.in_(identity_ids)
            )
            if analysis.get("owner_id"):
                identity_query = identity_query.filter(FaceIdentity.owner_id == analysis["owner_id"])
            identity_names = dict(identity_query.all())

        def serialize(item: dict, action: str) -> dict:
            face = item["face"]
            distance = float(item["distance"])
            current_identity_id = face.face_identity_id
            return {
                "face_id": face.id,
                "photo_id": str(face.photo_id),
                "face_rect": face.face_rect,
                "distance": distance,
                "confidence": max(0.0, min(1.0, 1.0 - distance)),
                "recommended": action == "add" and distance <= self.RESCAN_AUTO_MATCH_THRESHOLD,
                "current_identity_id": str(current_identity_id) if current_identity_id else None,
                "current_identity_name": identity_names.get(current_identity_id),
                "assignment_type": (
                    "remove" if action == "remove"
                    else "reassign" if current_identity_id and current_identity_id != analysis["identity_id"]
                    else "unassigned"
                ),
            }

        add_candidates = [serialize(item, "add") for item in analysis["add_candidates"]]
        remove_candidates = [serialize(item, "remove") for item in analysis["remove_candidates"]]
        return {
            "status": "success",
            "reason": analysis["reason"],
            "reference_count": len(analysis["prototypes"]),
            "threshold": self.RESCAN_AUTO_MATCH_THRESHOLD,
            "candidate_threshold": analysis.get("candidate_threshold", self.RESCAN_CANDIDATE_THRESHOLD),
            "removal_threshold": analysis["removal_threshold"],
            "add_candidates": add_candidates,
            "remove_candidates": remove_candidates,
            "summary": {
                "add_count": len(add_candidates),
                "remove_count": len(remove_candidates),
                "reassign_count": sum(item["assignment_type"] == "reassign" for item in add_candidates),
            },
        }

    def _apply_rescan_analysis(
        self,
        analysis: dict,
        selected_add_ids: set[int],
        selected_remove_ids: set[int],
    ) -> dict:
        affected_identity_ids = {analysis["identity_id"]}
        affected_photo_ids = set()
        reassigned_count = 0

        for item in analysis["remove_candidates"]:
            face = item["face"]
            if face.id not in selected_remove_ids:
                continue
            from app.service.face_appearance_clusters import set_identity
            set_identity(self.db, face, None, self.owner_id)
            face.recognize_confidence = None
            affected_photo_ids.add(face.photo_id)

        for item in analysis["add_candidates"]:
            face = item["face"]
            if face.id not in selected_add_ids:
                continue
            previous_identity_id = face.face_identity_id
            if previous_identity_id and previous_identity_id != analysis["identity_id"]:
                affected_identity_ids.add(previous_identity_id)
                reassigned_count += 1
            from app.service.face_appearance_clusters import set_identity
            set_identity(self.db, face, analysis["identity_id"], self.owner_id)
            face.recognize_confidence = float(1.0 - item["distance"])
            affected_photo_ids.add(face.photo_id)

        self.db.flush()
        self._repair_default_faces(affected_identity_ids)
        self.db.commit()
        return {
            "status": "success",
            "added_count": len(selected_add_ids),
            "removed_count": len(selected_remove_ids),
            "reassigned_count": reassigned_count,
            "count": len(selected_add_ids),
            "reference_count": len(analysis["prototypes"]),
            "threshold": self.RESCAN_AUTO_MATCH_THRESHOLD,
            "candidate_threshold": analysis.get("candidate_threshold", self.RESCAN_CANDIDATE_THRESHOLD),
            "affected_photo_ids": [str(photo_id) for photo_id in affected_photo_ids],
            "removal_threshold": analysis["removal_threshold"],
        }

    @staticmethod
    def _cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
        return float(np.clip(1.0 - np.dot(left, right), 0.0, 2.0))

    def _is_manually_confirmed(self, face: Face) -> bool:
        confidence = getattr(face, "recognize_confidence", None)
        return (
            confidence is not None
            and float(confidence) >= self.MANUAL_ASSIGNMENT_CONFIDENCE
        )

    def _select_consistent_component(
        self,
        embeddings: list[np.ndarray],
        face_ids: list[int],
        default_face_id: int | None,
        confirmed_face_ids: set[int] | None = None,
    ) -> list[int]:
        """Prefer a manually supported component, then its size and cover."""
        if len(embeddings) <= 1:
            return list(range(len(embeddings)))

        remaining = set(range(len(embeddings)))
        components = []
        while remaining:
            start = remaining.pop()
            component = {start}
            frontier = [start]
            while frontier:
                current = frontier.pop()
                neighbours = {
                    index for index in remaining
                    if self._cosine_distance(embeddings[current], embeddings[index]) < self.DISTANCE_THRESHOLD
                }
                remaining.difference_update(neighbours)
                component.update(neighbours)
                frontier.extend(neighbours)
            components.append(sorted(component))

        def component_rank(component: list[int]):
            contains_default = default_face_id in {face_ids[index] for index in component}
            confirmed_count = sum(face_ids[index] in (confirmed_face_ids or set()) for index in component)
            return confirmed_count, len(component), contains_default

        return max(components, key=component_rank)

    def _select_rescan_references(self, faces, embeddings, default_face_id):
        """Choose a trusted component per appearance, with confirmed faces first.

        Legacy faces without a cluster share a fallback group. Each appearance
        receives a reference before the remaining budget is used for diversity.
        """
        groups = {}
        for index, face in enumerate(faces):
            groups.setdefault(getattr(face, "face_cluster_id", None), []).append(index)
        trusted = []
        reference_groups = []
        for indices in groups.values():
            group_faces = [faces[index] for index in indices]
            sampled = self._sample_reference_indices(len(indices), group_faces, default_face_id)
            sampled_indices = [indices[index] for index in sampled]
            confirmed_ids = {faces[index].id for index in sampled_indices if self._is_manually_confirmed(faces[index])}
            component = self._select_consistent_component(
                [embeddings[index] for index in sampled_indices],
                [faces[index].id for index in sampled_indices], default_face_id, confirmed_ids,
            )
            selected = [sampled_indices[index] for index in component]
            trusted.extend(selected)
            # A confirmed face seeds farthest-first selection instead of the
            # earliest automatically assigned face in the appearance.
            selected.sort(key=lambda index: (not self._is_manually_confirmed(faces[index]), faces[index].id))
            manual = [embeddings[index] for index in selected if self._is_manually_confirmed(faces[index])]
            automatic = [embeddings[index] for index in selected if not self._is_manually_confirmed(faces[index])]
            representatives = self._select_diverse_prototypes(manual)
            if len(representatives) < self.MAX_RESCAN_PROTOTYPES:
                expanded = self._select_diverse_prototypes(representatives + automatic)
                # Keep manual representatives even when diversity favors an
                # automatic outlier over a second confirmed face.
                for vector in expanded:
                    if len(representatives) >= self.MAX_RESCAN_PROTOTYPES:
                        break
                    if not any(np.array_equal(vector, item) for item in representatives):
                        representatives.append(vector)
            reference_groups.append((bool(manual), representatives))
        reference_groups.sort(key=lambda group: not group[0])
        budget = max(self.MAX_RESCAN_PROTOTYPES, len(reference_groups))
        prototypes = [group[1][0] for group in reference_groups]
        for position in range(1, self.MAX_RESCAN_PROTOTYPES):
            for _, representatives in reference_groups:
                if len(prototypes) >= budget:
                    return trusted, prototypes
                if position < len(representatives):
                    prototypes.append(representatives[position])
        return trusted, prototypes

    def _select_diverse_prototypes(self, embeddings: list[np.ndarray]) -> list[np.ndarray]:
        """Choose multiple representative embeddings with farthest-first sampling."""
        if len(embeddings) <= self.MAX_RESCAN_PROTOTYPES:
            return embeddings

        selected = [0]
        min_distances = np.array([
            self._cosine_distance(embedding, embeddings[0])
            for embedding in embeddings
        ])
        while len(selected) < self.MAX_RESCAN_PROTOTYPES:
            min_distances[selected] = -1
            next_index = int(np.argmax(min_distances))
            if min_distances[next_index] <= 0:
                break
            selected.append(next_index)
            min_distances = np.minimum(
                min_distances,
                np.array([
                    self._cosine_distance(embedding, embeddings[next_index])
                    for embedding in embeddings
                ]),
            )
        return [embeddings[index] for index in selected]

    def _sample_reference_indices(
        self,
        face_count: int,
        faces: list[Face],
        default_face_id: int | None,
    ) -> list[int]:
        if face_count <= self.MAX_RESCAN_REFERENCE_SAMPLE:
            return list(range(face_count))

        confirmed = [index for index, face in enumerate(faces) if self._is_manually_confirmed(face)]
        if len(confirmed) >= self.MAX_RESCAN_REFERENCE_SAMPLE:
            return [confirmed[int(index)] for index in np.linspace(0, len(confirmed) - 1, self.MAX_RESCAN_REFERENCE_SAMPLE)]
        sampled = set(confirmed)
        sampled.update({
            int(index)
            for index in np.linspace(0, face_count - 1, self.MAX_RESCAN_REFERENCE_SAMPLE - len(confirmed))
        })
        if default_face_id is not None:
            default_index = next(
                (index for index, face in enumerate(faces) if face.id == default_face_id),
                None,
            )
            if default_index is not None:
                sampled.add(default_index)
        return sorted(sampled)

    def _find_matching_face_ids(
        self,
        prototypes: list[np.ndarray],
        owner_id: uuid.UUID | None,
        threshold: float | None = None,
    ) -> set[int]:
        """Use pgvector distance predicates so non-matching library faces never leave PostgreSQL."""
        distance_threshold = self.DISTANCE_THRESHOLD if threshold is None else threshold
        if not prototypes:
            return set()
        if self.db.bind.dialect.name == "sqlite":
            return self._sqlite_find_matching_face_ids(prototypes, owner_id, distance_threshold)
        face_ids = set()
        for prototype in prototypes:
            distance = Face.face_feature.cosine_distance(prototype.tolist())
            query = self.db.query(Face.id).join(Photo).filter(
                Face.is_deleted.is_(False),
                Face.face_feature.isnot(None),
                Photo.is_deleted.is_(False),
                distance <= distance_threshold,
            )
            if owner_id:
                query = query.filter(Photo.owner_id == owner_id)
            face_ids.update(row[0] for row in query.all())
        return face_ids

    def _live_face_ids(self, owner_id: uuid.UUID | None) -> np.ndarray:
        """Ids of non-deleted faces on non-deleted photos (scalar-only query)."""
        query = self.db.query(Face.id).join(Photo).filter(
            Face.is_deleted.is_(False),
            Face.face_feature.isnot(None),
            Photo.is_deleted.is_(False),
        )
        if owner_id:
            query = query.filter(Photo.owner_id == owner_id)
        return np.fromiter((row[0] for row in query.all()), dtype=np.int64)

    def _sqlite_find_matching_face_ids(
        self,
        prototypes: list[np.ndarray],
        owner_id: uuid.UUID | None,
        distance_threshold: float,
    ) -> set[int]:
        """Score every prototype against the cached matrix in one matmul.

        The pre-8adff5d SQLite fallback compared raw ``face_feature`` values
        against normalised prototypes, so the cosine distance was scaled by the
        candidate's norm and matches were silently missed. Both sides are
        normalised here.
        """
        live = self._live_face_ids(owner_id)
        if live.size == 0:
            return set()

        queries = np.ascontiguousarray(np.vstack(prototypes), dtype=np.float32)
        queries = normalise_matrix(queries.copy())
        min_similarity = 1.0 - distance_threshold

        matched: set[int] = set()
        for ids, scores in face_vector_cache.similarities(self.db, owner_id, queries):
            best = scores.max(axis=1)
            hit = (best >= min_similarity) & np.isin(ids, live, assume_unique=False)
            matched.update(int(value) for value in ids[hit])
        return matched

    def _repair_default_faces(self, identity_ids: set[uuid.UUID]) -> None:
        for identity in self.db.query(FaceIdentity).filter(FaceIdentity.id.in_(identity_ids)).all():
            valid_default = None
            if identity.default_face_id:
                valid_default = self.db.query(Face.id).join(Photo).filter(
                    Face.id == identity.default_face_id,
                    Face.face_identity_id == identity.id,
                    Face.is_deleted.is_(False),
                    Photo.is_deleted.is_(False),
                ).first()
            if valid_default:
                continue
            replacement = self.db.query(Face.id).join(Photo).filter(
                Face.face_identity_id == identity.id,
                Face.is_deleted.is_(False),
                Photo.is_deleted.is_(False),
            ).order_by(Face.recognize_confidence.desc().nullslast(), Face.id).first()
            identity.default_face_id = replacement[0] if replacement else None

    def process_unassigned_faces(self, owner_id: uuid.UUID = None):
        """Process committed faces and initialize legacy appearance clusters."""
        self._cluster_unassigned_faces(owner_id)

    def _cluster_unassigned_faces(self, owner_id: uuid.UUID = None):
        from app.service.face_appearance_clusters import process_faces
        if owner_id is None:
            raise ValueError("Face clustering requires an owner")
        process_faces(self.db, owner_id)
