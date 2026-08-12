import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sklearn.cluster import DBSCAN
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import Photo
from app.crud import face as crud_face
from app.schemas import face as schemas
import logging
import uuid
from datetime import datetime
from sqlalchemy.exc import PendingRollbackError, SQLAlchemyError

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FaceRescanError(RuntimeError):
    """Raised when an identity rescan fails and its transaction is rolled back."""


class FaceRescanConflictError(FaceRescanError):
    """Raised when a reviewed rescan selection is no longer valid."""


from app.core.config_manager import config_manager

class FaceClusterService:
    MAX_RESCAN_PROTOTYPES = 12
    MAX_RESCAN_REFERENCE_SAMPLE = 200
    MANUAL_ASSIGNMENT_CONFIDENCE = 0.999

    def __init__(self, db: Session, user_id: uuid.UUID = None):
        self.db = db
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

    def assign_face_to_identity(self, face_id: int, embedding: list, owner_id: uuid.UUID = None) -> uuid.UUID | None:
        """
        优化版：利用pgvector索引查找最近邻人脸，快速分配Identity
        :param face_id: 人脸ID
        :param embedding: 人脸特征向量
        :return: 匹配的Identity ID / None（无匹配）
        """
        target_emb = self.normalize_embedding(embedding)
        
        try:
            # 1. 利用pgvector <=> 操作符查找最近邻人脸（排除当前人脸，且必须有Identity）
            # <=> 是 cosine distance
            query = self.db.query(Face).join(Photo).filter(
                Face.id != face_id,
                Face.face_identity_id.isnot(None),
                Face.is_deleted == False
            )
            
            if owner_id:
                query = query.filter(Photo.owner_id == owner_id)
                
            if self.db.bind.dialect.name == "sqlite":
                # SQLite stores vectors as JSON and has no pgvector <=> operator.
                # Desktop libraries are expected to be smaller, so evaluate the
                # filtered candidate set in memory.
                candidates = query.all()
                nearest_face = min(
                    candidates,
                    key=lambda item: 1.0 - float(np.dot(
                        target_emb,
                        self.normalize_embedding(item.face_feature),
                    )),
                    default=None,
                )
            else:
                nearest_face = query.order_by(
                    Face.face_feature.cosine_distance(target_emb)
                ).limit(1).first()

            if not nearest_face:
                # 无参考人脸，返回None由外部决定是否触发聚类
                return None

            # 2. 计算距离
            # 注意：数据库中的向量通常应该是归一化的，但为了保险起见，再次归一化
            nearest_emb = self.normalize_embedding(nearest_face.face_feature)
            dist = 1.0 - np.dot(target_emb, nearest_emb)

            # 3. 判断是否匹配成功
            if dist < config_manager.get_user_config(owner_id, self.db).ai.face_cluster_threshold:
                # 分配到已有Identity
                best_match_id = nearest_face.face_identity_id

                # 使用 update_face 更新
                update_data = schemas.FaceUpdate(
                    face_identity_id=best_match_id,
                    recognize_confidence=float(1.0 - dist)
                )
                crud_face.update_face(self.db, face_id, update_data, owner_id=owner_id)

                return best_match_id
            else:
                return None

        except PendingRollbackError:
            # 事务已回滚，重置Session
            self.db.rollback()
            logger.error("事务回滚，重置Session后重试")
            raise
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"分配Identity失败：{str(e)}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"分配Identity异常：{str(e)}", exc_info=True)
            raise

    def preview_identity_rescan(self, identity_id: uuid.UUID, owner_id: uuid.UUID = None) -> dict:
        """Return add/remove candidates without changing any face assignment."""
        try:
            analysis = self._analyze_identity_rescan(identity_id, owner_id, lock=False)
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
    ) -> dict:
        """Recompute and atomically apply only the candidates confirmed by the user."""
        try:
            analysis = self._analyze_identity_rescan(identity_id, owner_id, lock=True)
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

        removal_threshold = self.RESCAN_REMOVAL_THRESHOLD
        if not assigned_faces:
            return {
                "identity_id": identity_id,
                "owner_id": owner_id,
                "reason": "no_reference_faces",
                "prototypes": [],
                "add_candidates": [],
                "remove_candidates": [],
                "removal_threshold": removal_threshold,
            }

        embeddings = [self.normalize_embedding(face.face_feature) for face in assigned_faces]
        identity = crud_face.get_identity(self.db, identity_id, owner_id=owner_id)
        default_face_id = identity.default_face_id if identity else None
        sample_indices = self._sample_reference_indices(len(assigned_faces), assigned_faces, default_face_id)
        trusted_sample_indices = self._select_consistent_component(
            [embeddings[index] for index in sample_indices],
            [assigned_faces[index].id for index in sample_indices],
            default_face_id,
        )
        trusted_indices = [sample_indices[index] for index in trusted_sample_indices]
        manually_confirmed_indices = {
            index for index, face in enumerate(assigned_faces) if self._is_manually_confirmed(face)
        }
        trusted_indices = sorted(set(trusted_indices) | manually_confirmed_indices)
        prototypes = self._select_diverse_prototypes([embeddings[index] for index in trusted_indices])

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
            threshold=self.RESCAN_CANDIDATE_THRESHOLD,
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
            if face.id in currently_kept_ids:
                continue
            min_distance = min(
                self._cosine_distance(self.normalize_embedding(face.face_feature), prototype)
                for prototype in prototypes
            )
            if min_distance > self.RESCAN_CANDIDATE_THRESHOLD:
                continue
            if face.face_identity_id and face.face_identity_id != identity_id and self._is_manually_confirmed(face):
                continue
            add_candidates.append({"face": face, "distance": min_distance})

        return {
            "identity_id": identity_id,
            "owner_id": owner_id,
            "reason": None,
            "prototypes": prototypes,
            "add_candidates": add_candidates,
            "remove_candidates": remove_candidates,
            "removal_threshold": removal_threshold,
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
            "candidate_threshold": self.RESCAN_CANDIDATE_THRESHOLD,
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
            face.face_identity_id = None
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
            face.face_identity_id = analysis["identity_id"]
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
            "candidate_threshold": self.RESCAN_CANDIDATE_THRESHOLD,
            "affected_photo_ids": [str(photo_id) for photo_id in affected_photo_ids],
        }

    @staticmethod
    def _cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
        return float(np.clip(1.0 - np.dot(left, right), 0.0, 2.0))

    def _is_manually_confirmed(self, face: Face) -> bool:
        return (
            face.recognize_confidence is not None
            and float(face.recognize_confidence) >= self.MANUAL_ASSIGNMENT_CONFIDENCE
        )

    def _select_consistent_component(
        self,
        embeddings: list[np.ndarray],
        face_ids: list[int],
        default_face_id: int | None,
    ) -> list[int]:
        """Select the largest connected face component; use the cover only as a tie-breaker."""
        if len(embeddings) <= 2:
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
            return len(component), contains_default

        return max(components, key=component_rank)

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

        sampled = {
            int(index)
            for index in np.linspace(0, face_count - 1, self.MAX_RESCAN_REFERENCE_SAMPLE)
        }
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
        if self.db.bind.dialect.name == "sqlite":
            query = self.db.query(Face).join(Photo).filter(
                Face.is_deleted.is_(False),
                Face.face_feature.isnot(None),
                Photo.is_deleted.is_(False),
            )
            if owner_id:
                query = query.filter(Photo.owner_id == owner_id)
            candidates = query.all()
            return {
                face.id for face in candidates
                if any(self._cosine_distance(face.face_feature, prototype) <= distance_threshold for prototype in prototypes)
            }
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
        """
        批量处理未分配的人脸（DBSCAN聚类）
        """
        # 只要有未分配的人脸，就尝试聚类
        # 为了避免过多无效调用，可以先count一下? 
        # _try_create_new_cluster 内部有查询逻辑，可以直接调用，但我们需要稍微修改一下 _try_create_new_cluster
        # 让它不依赖 current_face_id
        self._cluster_unassigned_faces(owner_id)

    def _cluster_unassigned_faces(self, owner_id: uuid.UUID = None):
        """
        优化版：调整DBSCAN参数 + 簇合并逻辑，解决聚类分散问题
        对未分配的人脸做DBSCAN聚类，合并相似簇后创建新Identity
        """
        try:
            # 1. 查询未分配的人脸
            unassigned_faces = self.db.query(Face).filter(
                Face.face_identity_id == None,
                Face.is_deleted == False,
                Face.face_feature.isnot(None)
            ).all()

            face_count = len(unassigned_faces)
            if face_count < self.DBSCAN_MIN_SAMPLES:
                return

            # 2. 提取并归一化向量
            embeddings = []
            face_ids = []
            for face in unassigned_faces:
                emb = self.normalize_embedding(face.face_feature)
                embeddings.append(emb)
                face_ids.append(face.id)

            X = np.array(embeddings)

            # 3. DBSCAN聚类（宽松参数，避免拆分）
            clustering = DBSCAN(
                eps=config_manager.config.ai.face_cluster_threshold,
                min_samples=self.DBSCAN_MIN_SAMPLES,
                metric='cosine'
            ).fit(X)

            labels = clustering.labels_
            
            # 4. 计算簇中心，合并相似簇（核心：解决同一人拆分为多个簇）
            cluster_centers = {}  # label -> 簇中心向量
            cluster_members = {}  # label -> 成员face ID列表

            # 4.1 计算每个簇的中心（均值向量）
            unique_labels = set(labels)
            for label in unique_labels:
                if label == -1:  # 噪声点，跳过
                    continue

                cluster_indices = np.where(labels == label)[0]
                if len(cluster_indices) < 1:
                    continue

                # 簇内向量的均值作为中心
                cluster_emb = X[cluster_indices]
                center = np.mean(cluster_emb, axis=0)
                center = self.normalize_embedding(center)

                cluster_centers[label] = center
                cluster_members[label] = [face_ids[idx] for idx in cluster_indices]

            # 4.2 合并相似簇（中心距离 < 阈值）
            merged_clusters = []
            used_labels = set()

            for label1 in cluster_centers:
                if label1 in used_labels:
                    continue

                # 初始合并当前簇
                merged_members = cluster_members[label1].copy()
                used_labels.add(label1)

                # 遍历其他簇，判断是否合并
                for label2 in cluster_centers:
                    if label1 == label2 or label2 in used_labels:
                        continue

                    # 计算簇中心的余弦距离
                    dist = 1.0 - np.dot(cluster_centers[label1], cluster_centers[label2])
                    if dist < self.DISTANCE_THRESHOLD + 0.08:
                        merged_members += cluster_members[label2]
                        used_labels.add(label2)
                        logger.info(f"合并簇 {label1} 和 {label2}（中心距离={dist:.4f}）")

                merged_clusters.append(merged_members)

            # 5. 为合并后的簇创建新Identity
            for cluster in merged_clusters:
                cluster_size = len(cluster)
                if cluster_size < self.MIN_CLUSTER_SIZE_FOR_IDENTITY:
                    continue

                # 创建新Identity
                create_identity_data = schemas.FaceIdentityCreate(identity_name="未命名")
                new_identity = crud_face.create_identity(self.db, create_identity_data, owner_id)

                # 分配人脸到新Identity
                first_face_id = None
                for f_id in cluster:
                    face = crud_face.get_face(self.db, f_id)
                    if not face:
                        continue

                    update_data = schemas.FaceUpdate(
                        face_identity_id=new_identity.id,
                        recognize_confidence=0.9
                    )
                    crud_face.update_face(self.db, f_id, update_data)

                    if not first_face_id:
                        first_face_id = face.id

                # 设置默认人脸
                if first_face_id:
                    update_identity_data = schemas.FaceIdentityUpdate(default_face_id=first_face_id)
                    crud_face.update_identity(self.db, new_identity.id, update_identity_data)

                logger.info(
                    f"创建新Identity {new_identity.id}，包含 {cluster_size} 个人脸（合并后）"
                )

        except PendingRollbackError:
            self.db.rollback()
            logger.error("聚类时事务回滚，重置Session", exc_info=True)
            raise
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"聚类数据库错误：{str(e)}", exc_info=True)
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"聚类异常：{str(e)}", exc_info=True)
            raise
