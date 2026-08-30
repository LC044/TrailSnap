from datetime import datetime
from typing import Iterable, List, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.crud.album import _update_album_photo_count, trigger_conditional_albums_update
from app.db.models.album import Album
from app.db.models.photo import Photo
from app.db.models.photo_declutter_record import PhotoDeclutterRecord


def _available_query(db: Session, owner_id: UUID):
    handled_ids = db.query(PhotoDeclutterRecord.photo_id).filter(
        PhotoDeclutterRecord.owner_id == owner_id
    )
    return db.query(Photo).filter(
        Photo.owner_id == owner_id,
        Photo.is_deleted.is_(False),
        ~Photo.id.in_(handled_ids),
    )


def get_stats(db: Session, owner_id: UUID) -> dict:
    decisions = db.query(
        PhotoDeclutterRecord.decision,
        func.count(PhotoDeclutterRecord.id),
    ).filter(
        PhotoDeclutterRecord.owner_id == owner_id
    ).group_by(PhotoDeclutterRecord.decision).all()
    counts = {decision: count for decision, count in decisions}
    kept = counts.get("keep", 0)
    deleted = counts.get("delete", 0)
    processed = kept + deleted
    remaining = _available_query(db, owner_id).count()
    return {
        "processed": processed,
        "remaining": remaining,
        "total": processed + remaining,
        "kept": kept,
        "deleted": deleted,
    }


def get_batch(db: Session, owner_id: UUID, limit: int) -> Tuple[List[Photo], dict]:
    photos = _available_query(db, owner_id).options(
        joinedload(Photo.metadata_info),
        joinedload(Photo.image_description),
    ).order_by(func.random()).limit(limit).all()
    return photos, get_stats(db, owner_id)


def _refresh_albums(db: Session, owner_id: UUID, albums: Iterable[Album], photo_id: UUID) -> None:
    for album_id in {album.id for album in albums}:
        _update_album_photo_count(db, album_id)
    trigger_conditional_albums_update(db, owner_id, [photo_id])


def save_decisions(db: Session, owner_id: UUID, items) -> int:
    changed_albums = []
    changed_photo_ids = []

    try:
        for item in items:
            photo = db.query(Photo).options(joinedload(Photo.albums)).filter(
                Photo.id == item.photo_id,
                Photo.owner_id == owner_id,
            ).first()
            if not photo:
                raise LookupError(f"Photo {item.photo_id} not found")

            record = db.query(PhotoDeclutterRecord).filter(
                PhotoDeclutterRecord.owner_id == owner_id,
                PhotoDeclutterRecord.photo_id == item.photo_id,
            ).first()

            if item.decision == "keep" and photo.is_deleted:
                # Switching an existing swipe-delete decision to keep is a valid,
                # idempotent recovery path. Other deleted photos are not eligible.
                if not record or record.decision != "delete":
                    raise ValueError(f"Photo {item.photo_id} is in the recycle bin")
                photo.is_deleted = False
                photo.deleted_at = None
                changed_albums.append(list(photo.albums))
                changed_photo_ids.append(photo.id)
            elif item.decision == "delete" and not photo.is_deleted:
                photo.is_deleted = True
                photo.deleted_at = datetime.now()
                changed_albums.append(list(photo.albums))
                changed_photo_ids.append(photo.id)

            if record:
                record.decision = item.decision
                record.updated_at = datetime.now()
            else:
                db.add(PhotoDeclutterRecord(
                    owner_id=owner_id,
                    photo_id=item.photo_id,
                    decision=item.decision,
                ))

        db.commit()
    except Exception:
        db.rollback()
        raise

    for albums, photo_id in zip(changed_albums, changed_photo_ids):
        _refresh_albums(db, owner_id, albums, photo_id)
    return len(items)


def undo_decision(db: Session, owner_id: UUID, photo_id: UUID) -> bool:
    record = db.query(PhotoDeclutterRecord).filter(
        PhotoDeclutterRecord.owner_id == owner_id,
        PhotoDeclutterRecord.photo_id == photo_id,
    ).first()
    if not record:
        return False

    photo = db.query(Photo).options(joinedload(Photo.albums)).filter(
        Photo.id == photo_id,
        Photo.owner_id == owner_id,
    ).first()
    albums = []
    restored = False
    if record.decision == "delete" and photo and photo.is_deleted:
        photo.is_deleted = False
        photo.deleted_at = None
        albums = list(photo.albums)
        restored = True

    try:
        db.delete(record)
        db.commit()
    except Exception:
        db.rollback()
        raise

    if restored:
        _refresh_albums(db, owner_id, albums, photo_id)
    return True


def reset_decisions(db: Session, owner_id: UUID) -> int:
    count = db.query(PhotoDeclutterRecord).filter(
        PhotoDeclutterRecord.owner_id == owner_id
    ).delete(synchronize_session=False)
    db.commit()
    return count
