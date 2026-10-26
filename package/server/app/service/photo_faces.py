"""Photo-local face labeling. Never infer which face the user selected."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import Photo
from app.schemas.face import PhotoFace


def owned_photo(db: Session, photo_id: UUID, owner_id: UUID) -> Photo:
    photo = db.query(Photo).filter(
        Photo.id == photo_id, Photo.owner_id == owner_id, Photo.is_deleted.is_(False)
    ).first()
    if not photo:
        raise HTTPException(404, "照片不存在")
    return photo


def list_photo_faces(db: Session, photo_id: UUID, owner_id: UUID) -> list[PhotoFace]:
    owned_photo(db, photo_id, owner_id)
    rows = db.query(Face.id, Face.photo_id, Face.face_rect,
                    FaceIdentity.id.label("identity_id"), FaceIdentity.identity_name).outerjoin(FaceIdentity, (
        (Face.face_identity_id == FaceIdentity.id)
        & (FaceIdentity.owner_id == owner_id)
        & FaceIdentity.is_deleted.is_(False)
        & FaceIdentity.is_hidden.is_(False)
    )).filter(Face.photo_id == photo_id, Face.is_deleted.is_(False)).order_by(Face.id).all()
    return [PhotoFace(id=row.id, photo_id=row.photo_id, face_rect=row.face_rect,
                      identity_id=row.identity_id, identity_name=row.identity_name) for row in rows]


def assign_photo_face(db: Session, photo_id: UUID, face_id: int,
                      identity_id: UUID | None, owner_id: UUID) -> None:
    owned_photo(db, photo_id, owner_id)
    face = db.query(Face).filter(Face.id == face_id, Face.photo_id == photo_id,
                                 Face.is_deleted.is_(False)).with_for_update().first()
    if not face:
        raise HTTPException(404, "人脸不存在，请刷新后重试")
    identity = None
    if identity_id is not None:
        identity = db.query(FaceIdentity).filter(
            FaceIdentity.id == identity_id, FaceIdentity.owner_id == owner_id,
            FaceIdentity.is_deleted.is_(False), FaceIdentity.is_hidden.is_(False)
        ).first()
        if not identity:
            raise HTTPException(404, "人物不存在")
    previous_id = face.face_identity_id
    face.face_identity_id = identity_id
    face.recognize_confidence = 1.0 if identity_id else None
    db.flush()
    # Repair both covers inside the same transaction, without loading AI models.
    for affected_id in {previous_id, identity_id} - {None}:
        person = db.query(FaceIdentity).filter(
            FaceIdentity.id == affected_id, FaceIdentity.owner_id == owner_id
        ).first()
        if not person:
            continue
        candidates = db.query(Face.id).join(Photo).filter(
            Face.face_identity_id == affected_id, Face.is_deleted.is_(False),
            Photo.owner_id == owner_id, Photo.is_deleted.is_(False)
        )
        if not person.default_face_id or not candidates.filter(Face.id == person.default_face_id).first():
            replacement = candidates.order_by(Face.recognize_confidence.desc().nullslast(), Face.id).first()
            person.default_face_id = replacement[0] if replacement else None
    db.commit()
    from app.crud.album import trigger_conditional_albums_update
    trigger_conditional_albums_update(db, owner_id, [photo_id])
