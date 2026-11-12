from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.schemas import tag as schemas
import uuid

def get_tag_by_name(db: Session, tag_name: str, owner_id: Optional[UUID] = None, tag_type: Optional[str] = None):
    query = db.query(PhotoTag).filter(PhotoTag.tag_name == tag_name)
    if owner_id:
        query = query.filter(PhotoTag.owner_id == owner_id)
    else:
        query = query.filter(PhotoTag.owner_id == None)
    if tag_type is not None:
        query = query.filter(PhotoTag.type == tag_type)
    return query.first()

def create_tag(db: Session, tag_name: str, tag_type: str = None, owner_id: Optional[UUID] = None):
    db_tag = PhotoTag(tag_name=tag_name, type = tag_type, owner_id=owner_id)
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

def get_photo_tags(db: Session, photo_id: UUID, owner_id: Optional[UUID] = None) -> List[schemas.PhotoTagResponse]:
    # Join PhotoTagRelation and PhotoTag
    query = db.query(PhotoTag, PhotoTagRelation.confidence)\
        .join(PhotoTagRelation, PhotoTag.id == PhotoTagRelation.tag_id)\
        .filter(PhotoTagRelation.photo_id == photo_id, PhotoTagRelation.is_deleted == False)

    results = query.all()

    tags = []
    for tag, confidence in results:
        tags.append(schemas.PhotoTagResponse(
            id=tag.id,
            tag_name=tag.tag_name,
            confidence=confidence
        ))
    return tags

def add_tag_to_photo(db: Session, photo_id: UUID, tag_name: str, confidence: float = 1.0, owner_id: Optional[UUID] = None) -> schemas.PhotoTagResponse:
    # Check if tag exists
    tag = get_tag_by_name(db, tag_name, owner_id, tag_type="custom")
    if not tag:
        tag = create_tag(db, tag_name, 'custom', owner_id)

    # Check if relation exists
    relation = db.query(PhotoTagRelation).filter(
        PhotoTagRelation.photo_id == photo_id,
        PhotoTagRelation.tag_id == tag.id
    ).first()

    if relation:
        if relation.is_deleted:
            relation.is_deleted = False
            relation.confidence = confidence
            db.commit()
        else:
            # If manually added (confidence=1.0), overwrite existing confidence
            # Or if new confidence > old confidence (optional logic, but let's stick to simple override if manual)
            if confidence == 1.0:
                relation.confidence = 1.0
                db.commit()
        db.refresh(relation)
    else:
        relation = PhotoTagRelation(photo_id=photo_id, tag_id=tag.id, confidence=confidence)
        db.add(relation)
        db.commit()
        db.refresh(relation)
    
    from app.service.clip_classification import decide_tag
    decide_tag(db, photo_id, tag.id, True)
    db.commit()
    return schemas.PhotoTagResponse(id=tag.id, tag_name=tag.tag_name, confidence=relation.confidence)

def remove_tag_from_photo(db: Session, photo_id: UUID, tag_id: UUID):
    relation = db.query(PhotoTagRelation).filter(
        PhotoTagRelation.photo_id == photo_id,
        PhotoTagRelation.tag_id == tag_id,
    ).first()

    if relation:
        from app.service.clip_classification import decide_tag
        decide_tag(db, photo_id, tag_id, False)
        db.commit()
    return True

def remove_tags_from_photo(db: Session, photo_id: UUID | str | List[UUID] | List[str], ai_generated: bool = False):
    if ai_generated:
        db.query(PhotoTagRelation).filter(
            (PhotoTagRelation.photo_id.in_(photo_id) if isinstance(photo_id, list) else PhotoTagRelation.photo_id == photo_id)
        ).delete()
    else:
        db.query(PhotoTagRelation).filter(
            (PhotoTagRelation.photo_id.in_(photo_id) if isinstance(photo_id, list) else PhotoTagRelation.photo_id == photo_id)
        ).delete()
    db.commit()
    return True

from sqlalchemy import func, desc
from app.db.models.photo import Photo

def get_tags_with_stats(db: Session, owner_id: UUID, skip: int = 0, limit: int = 100):
    # Subquery to count photos per tag
    subquery = db.query(
        PhotoTagRelation.tag_id,
        func.count(PhotoTagRelation.photo_id).label('count')
    ).join(Photo).filter(
        Photo.owner_id == owner_id,
        Photo.is_deleted == False
    ).group_by(PhotoTagRelation.tag_id).subquery()

    # Query tags joined with count and cover photo
    tags_with_data = db.query(PhotoTag, subquery.c.count, Photo)\
        .join(subquery, PhotoTag.id == subquery.c.tag_id)\
        .outerjoin(Photo, (PhotoTag.cover_id == Photo.id) & (Photo.is_deleted == False))\
        .filter(PhotoTag.owner_id == owner_id, PhotoTag.is_deleted.is_(False))\
        .order_by(desc(subquery.c.count))\
        .offset(skip).limit(limit).all()

    result = []
    tags_to_update = []
    for tag, count, cover_photo in tags_with_data:
        # If no valid cover is found from cover_id, fetch the first available photo
        if not cover_photo:
            cover_photo = db.query(Photo)\
                .join(PhotoTagRelation, Photo.id == PhotoTagRelation.photo_id)\
                .filter(
                    Photo.owner_id == owner_id,
                    Photo.is_deleted == False,
                    PhotoTagRelation.tag_id == tag.id
                ).first()
            
            if cover_photo:
                tag.cover_id = cover_photo.id
                tags_to_update.append(tag)

        result.append(schemas.TagStats(
            id=tag.id,
            tag_name=tag.tag_name,
            type=tag.type,
            count=count,
            cover=cover_photo
        ))

    # Commit only once if there are tags that need their cover_id updated
    if tags_to_update:
        db.commit()

    return result

def resolve_tag(db, owner_id, tag_name, tag_id=None):
    if tag_id is None:
        return get_tag_by_name(db, tag_name, owner_id)
    return db.query(PhotoTag).filter_by(id=tag_id, owner_id=owner_id, is_deleted=False).first()


def get_photos_by_tag_name(db: Session, owner_id: UUID, tag_name: str, skip: int = 0, limit: int = 50, tag_id: Optional[UUID] = None):
    tag = resolve_tag(db, owner_id, tag_name, tag_id)
    if not tag:
        return []

    photos = db.query(Photo)\
        .join(PhotoTagRelation, Photo.id == PhotoTagRelation.photo_id)\
        .filter(
            Photo.owner_id == owner_id,
            Photo.is_deleted == False,
            PhotoTagRelation.tag_id == tag.id
        ).order_by(desc(Photo.photo_time))\
        .offset(skip).limit(limit).all()

    return photos

def remove_photos_from_tag(db: Session, owner_id: UUID, tag_name: str, photo_ids: List[UUID], tag_id: Optional[UUID] = None) -> int:
    tag = resolve_tag(db, owner_id, tag_name, tag_id)
    if not tag:
        return 0

    owned_ids = [p.id for p in db.query(Photo).filter(Photo.owner_id == owner_id, Photo.id.in_(photo_ids))]
    relations = db.query(PhotoTagRelation).filter(
        PhotoTagRelation.tag_id == tag.id,
        PhotoTagRelation.photo_id.in_(owned_ids)
    ).all()
    from app.service.clip_classification import decide_tag
    for photo_id in owned_ids:
        decide_tag(db, photo_id, tag.id, False)
    count = len(relations)
    
    db.commit()
    return count

def set_tag_cover(db: Session, owner_id: UUID, tag_name: str, photo_id: UUID, tag_id: Optional[UUID] = None) -> bool:
    tag = resolve_tag(db, owner_id, tag_name, tag_id)
    if not tag:
        return False
        
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.owner_id == owner_id, Photo.is_deleted == False).first()
    if not photo:
        return False
        
    tag.cover_id = photo_id
    db.commit()
    return True
