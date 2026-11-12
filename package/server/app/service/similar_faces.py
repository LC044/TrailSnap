"""Sample-face search and explicit, atomic reassignment of reviewed faces."""
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

import numpy as np
from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.system_config import system_config
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import Photo
from app.schemas.face import (
    AssignSimilarFaces, BatchFaceAssignmentResult, SimilarFaceCandidate,
    SimilarFaceMatch, SimilarFacesResult, SimilarFaceScope,
)
from app.service.face_vector_cache import face_vector_cache
from app.service.photo_faces import owned_photo, repair_face_covers

DISTANCES = {"strict": 0.35, "balanced": 0.45, "broad": 0.55}
LOW_DISTANCES = {"strict": 0.55, "balanced": 0.45, "broad": 0.35}
MANUAL_CONFIDENCE = 0.999


def _sign(payload: dict, owner_id: UUID, purpose: str, minutes: int) -> str:
    security = system_config.config.security
    return jwt.encode({
        **payload, "owner": str(owner_id), "purpose": purpose,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
    }, security.secret_key, algorithm=security.algorithm)


def _verify(token: str, owner_id: UUID, purpose: str) -> dict:
    security = system_config.config.security
    try:
        payload = jwt.decode(token, security.secret_key, algorithms=[security.algorithm])
        if payload.get("owner") != str(owner_id) or payload.get("purpose") != purpose:
            raise ValueError("Wrong token scope")
        return payload
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(409, "确认结果已过期或无效，请重新查找并确认") from exc


def _fingerprint(identity_id, confidence, rect) -> str:
    value = [str(identity_id) if identity_id else None,
             float(confidence) if confidence is not None else None, rect]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def _valid_rect(rect) -> bool:
    return (isinstance(rect, list) and len(rect) == 4
            and all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in rect)
            and rect[2] > rect[0] and rect[3] > rect[1])


def _reference(db: Session, photo_id: UUID, face_id: int, owner_id: UUID) -> Face:
    owned_photo(db, photo_id, owner_id)
    face = db.query(Face).filter(
        Face.id == face_id, Face.photo_id == photo_id, Face.is_deleted.is_(False),
    ).first()
    if not face:
        raise HTTPException(404, "人脸不存在")
    if not _valid_rect(face.face_rect) or face.face_feature is None:
        raise HTTPException(422, "这张人脸缺少有效特征，请先重新识别当前照片的人脸")
    return face


def _normalised_feature(face: Face) -> np.ndarray:
    vector = np.asarray(face.face_feature, dtype=np.float32)
    norm = np.linalg.norm(vector)
    if vector.shape != (512,) or not np.isfinite(vector).all() or not np.isfinite(norm) or norm <= 0:
        raise HTTPException(422, "这张人脸的特征无效，请重新识别当前照片的人脸")
    return vector / norm


def _feature_signature(vector: np.ndarray) -> str:
    return hashlib.sha256(vector.tobytes()).hexdigest()


def _candidate_query(db: Session, owner_id: UUID):
    # Read mutable state fresh even when SQLite embeddings come from the cache.
    return db.query(
        Face.id, Face.photo_id, Face.face_rect, Face.face_identity_id,
        Face.recognize_confidence, Photo.photo_time,
        FaceIdentity.identity_name,
    ).join(Photo).outerjoin(FaceIdentity, Face.face_identity_id == FaceIdentity.id).filter(
        Photo.owner_id == owner_id, Photo.is_deleted.is_(False),
        Face.is_deleted.is_(False), Face.face_feature.isnot(None), Face.face_rect.isnot(None),
        or_(Face.face_identity_id.is_(None), (
            (FaceIdentity.owner_id == owner_id)
            & FaceIdentity.is_deleted.is_(False) & FaceIdentity.is_hidden.is_(False)
        )),
    )


def _sqlite_scores(db: Session, owner_id: UUID, vector: np.ndarray, threshold: float,
                   low_similarity: bool = False) -> dict[int, float]:
    matches = {}
    for ids, scores in face_vector_cache.similarities(db, owner_id, vector.reshape(1, -1), valid_only=True):
        values = scores[:, 0]
        distances = np.clip(1 - values, 0, 2)
        hits = np.isfinite(values) & (distances >= threshold if low_similarity else distances <= threshold)
        matches.update((int(i), float(distance)) for i, distance in zip(ids[hits], distances[hits]))
    return matches


def _serialize(row, distance: float, owner_id: UUID, reference_id: int, feature_signature: str):
    token = _sign({
        "face": row.id, "reference": reference_id, "feature": feature_signature,
        "state": _fingerprint(row.face_identity_id, row.recognize_confidence, row.face_rect),
    }, owner_id, "face-review", 30)
    return SimilarFaceCandidate(
        id=row.id, photo_id=row.photo_id, face_rect=row.face_rect,
        identity_id=row.face_identity_id, identity_name=row.identity_name,
        photo_time=row.photo_time, similarity=max(0.0, min(1.0, 1 - distance)),
        manually_confirmed=(row.recognize_confidence is not None
                            and float(row.recognize_confidence) >= MANUAL_CONFIDENCE),
        review_token=token,
    )


def search_similar_faces(db: Session, photo_id: UUID, face_id: int, owner_id: UUID,
                         scope: SimilarFaceScope = "other", match: SimilarFaceMatch = "balanced",
                         exclude_identity_id: UUID | None = None, skip: int = 0, limit: int = 60,
                         threshold: float | None = None, include_confirmed: bool = False):
    reference = _reference(db, photo_id, face_id, owner_id)
    vector = _normalised_feature(reference)
    signature = _feature_signature(vector)
    query = _candidate_query(db, owner_id)
    reference_row = query.filter(Face.id == face_id).first()
    if not reference_row:
        raise HTTPException(404, "该人脸当前所属人物不可见，无法查找")
    low_similarity = scope == "current_low"
    if low_similarity and reference.face_identity_id is None:
        raise HTTPException(422, "样本人脸尚未归属人物，无法排查当前人物")
    query = query.filter(Face.id != face_id)
    if not include_confirmed:
        query = query.filter(or_(Face.recognize_confidence.is_(None),
                                 Face.recognize_confidence < MANUAL_CONFIDENCE))
    if scope in {"current", "current_low"}:
        query = query.filter(Face.face_identity_id == reference.face_identity_id)
    elif scope == "other":
        if reference.face_identity_id is None:
            query = query.filter(Face.face_identity_id.isnot(None))
        else:
            query = query.filter(or_(
                Face.face_identity_id.is_(None),
                Face.face_identity_id != reference.face_identity_id,
            ))
    elif scope == "unassigned":
        query = query.filter(Face.face_identity_id.is_(None))
    if exclude_identity_id:
        query = query.filter(or_(Face.face_identity_id.is_(None), Face.face_identity_id != exclude_identity_id))
    if threshold is None:
        threshold = (LOW_DISTANCES if low_similarity else DISTANCES)[match]
    if db.get_bind().dialect.name == "sqlite":
        scores = _sqlite_scores(db, owner_id, vector, threshold, low_similarity)
        rows = [(row, scores[row.id]) for row in query.all() if row.id in scores and _valid_rect(row.face_rect)]
    else:
        distance = Face.face_feature.cosine_distance(vector.tolist())
        distance_filter = distance >= threshold if low_similarity else distance <= threshold
        rows = [(row, float(row.distance)) for row in query.add_columns(distance.label("distance"))
                .filter(distance_filter, distance <= 2).all() if _valid_rect(row.face_rect)]
    rows.sort(key=lambda item: (-item[1] if low_similarity else item[1], item[0].id))
    page = rows[skip:skip + limit]
    return SimilarFacesResult(
        reference=_serialize(reference_row, 0, owner_id, face_id, signature),
        items=[_serialize(row, distance, owner_id, face_id, signature) for row, distance in page],
        face_count=len(rows), photo_count=len({row.photo_id for row, _ in rows}),
        has_more=skip + limit < len(rows),
    )


def _owned_identity(db: Session, identity_id: UUID, owner_id: UUID) -> FaceIdentity:
    identity = db.query(FaceIdentity).filter(
        FaceIdentity.id == identity_id, FaceIdentity.owner_id == owner_id,
        FaceIdentity.is_deleted.is_(False), FaceIdentity.is_hidden.is_(False),
    ).first()
    if not identity:
        raise HTTPException(404, "人物不存在或不可见")
    return identity


def _lock_faces(db: Session, ids: set[int], owner_id: UUID) -> dict[int, Face]:
    rows = db.query(Face).join(Photo).filter(
        Face.id.in_(ids), Face.is_deleted.is_(False),
        Photo.owner_id == owner_id, Photo.is_deleted.is_(False),
    ).order_by(Face.id).with_for_update(of=Face).populate_existing().all()
    if len(rows) != len(ids):
        raise HTTPException(409, "选中的人脸已变化，请重新查找")
    return {face.id: face for face in rows}


def _finish(db: Session, owner_id: UUID, faces: list[Face], identity_ids: set[UUID]):
    db.flush()
    repair_face_covers(db, identity_ids, owner_id)
    photo_ids = sorted({face.photo_id for face in faces}, key=str)
    from app.crud.album import trigger_conditional_albums_update
    trigger_conditional_albums_update(db, owner_id, photo_ids, commit=False)
    db.commit()
    return photo_ids


def assign_similar_faces(db: Session, photo_id: UUID, face_id: int, owner_id: UUID,
                         payload: AssignSimilarFaces) -> BatchFaceAssignmentResult:
    try:
        from app.service.face_appearance_clusters import lock_owner, set_identity
        lock_owner(db, owner_id)
        reference = _reference(db, photo_id, face_id, owner_id)
        signature = _feature_signature(_normalised_feature(reference))
        if payload.identity_id is not None:
            _owned_identity(db, payload.identity_id, owner_id)
        ids = {item.face_id for item in payload.selections}
        if len(ids) != len(payload.selections):
            raise HTTPException(422, "不能重复提交同一张人脸")
        faces = _lock_faces(db, ids, owner_id)
        # Validate the entire selection before modifying even a single face.
        for item in payload.selections:
            reviewed = _verify(item.review_token, owner_id, "face-review")
            face = faces[item.face_id]
            if (reviewed.get("face") != face.id or reviewed.get("reference") != face_id
                    or reviewed.get("feature") != signature
                    or reviewed.get("state") != _fingerprint(
                        face.face_identity_id, face.recognize_confidence, face.face_rect)):
                raise HTTPException(409, "人脸归属或样本已变化，请重新查找并确认")
            if face.face_identity_id:
                _owned_identity(db, face.face_identity_id, owner_id)
        affected = {payload.identity_id} if payload.identity_id else set()
        confidence = 1.0 if payload.identity_id else None
        previous = []
        changed = [face for face in faces.values() if face.face_identity_id != payload.identity_id]
        for face in changed:
            previous.append({
                "id": face.id, "identity": str(face.face_identity_id) if face.face_identity_id else None,
                "confidence": float(face.recognize_confidence) if face.recognize_confidence is not None else None,
                "expected": _fingerprint(payload.identity_id, confidence, face.face_rect),
            })
            if face.face_identity_id:
                affected.add(face.face_identity_id)
            set_identity(db, face, payload.identity_id, owner_id)
            face.recognize_confidence = confidence
        undo_token = _sign({"items": previous}, owner_id, "face-undo", 15) if previous else None
        photo_ids = _finish(db, owner_id, changed, affected) if changed else []
        return BatchFaceAssignmentResult(face_count=len(changed), photo_ids=photo_ids, undo_token=undo_token)
    except Exception:
        db.rollback()
        raise


def undo_face_assignment(db: Session, owner_id: UUID, token: str) -> BatchFaceAssignmentResult:
    try:
        from app.service.face_appearance_clusters import lock_owner, set_identity
        lock_owner(db, owner_id)
        payload = _verify(token, owner_id, "face-undo")
        items = payload.get("items", [])
        if not items or len(items) > 500:
            raise HTTPException(409, "撤销记录无效")
        faces = _lock_faces(db, {item["id"] for item in items}, owner_id)
        affected = set()
        for item in items:
            face = faces[item["id"]]
            if item["expected"] != _fingerprint(face.face_identity_id, face.recognize_confidence, face.face_rect):
                raise HTTPException(409, "这些人脸已再次修改，不能覆盖后续更正")
            if item["identity"]:
                _owned_identity(db, UUID(item["identity"]), owner_id)
        for item in items:
            face = faces[item["id"]]
            if face.face_identity_id:
                affected.add(face.face_identity_id)
            set_identity(db, face, UUID(item["identity"]) if item["identity"] else None, owner_id)
            face.recognize_confidence = item["confidence"]
            if face.face_identity_id:
                affected.add(face.face_identity_id)
        photo_ids = _finish(db, owner_id, list(faces.values()), affected)
        return BatchFaceAssignmentResult(face_count=len(faces), photo_ids=photo_ids)
    except Exception:
        db.rollback()
        raise
