from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.schemas import tag as schemas
import uuid

def get_tag_by_name(db: Session, tag_name: str, owner_id: Optional[UUID] = None):
    query = db.query(PhotoTag).filter(PhotoTag.tag_name == tag_name)
    if owner_id:
        query = query.filter(PhotoTag.owner_id == owner_id)
    else:
        query = query.filter(PhotoTag.owner_id == None)
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
    tag = get_tag_by_name(db, tag_name, owner_id)
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
    
    return schemas.PhotoTagResponse(id=tag.id, tag_name=tag.tag_name, confidence=relation.confidence)

def remove_tag_from_photo(db: Session, photo_id: UUID, tag_id: UUID):
    relation = db.query(PhotoTagRelation).filter(
        PhotoTagRelation.photo_id == photo_id,
        PhotoTagRelation.tag_id == tag_id,
    ).first()

    if relation:
        db.delete(relation)
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
        .filter(PhotoTag.owner_id == owner_id)\
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
            count=count,
            cover=cover_photo
        ))

    # Commit only once if there are tags that need their cover_id updated
    if tags_to_update:
        db.commit()

    return result

def get_photos_by_tag_name(db: Session, owner_id: UUID, tag_name: str, skip: int = 0, limit: int = 50):
    tag = get_tag_by_name(db, tag_name, owner_id)
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

def remove_photos_from_tag(db: Session, owner_id: UUID, tag_name: str, photo_ids: List[UUID]) -> int:
    tag = get_tag_by_name(db, tag_name, owner_id)
    if not tag:
        return 0

    count = db.query(PhotoTagRelation).filter(
        PhotoTagRelation.tag_id == tag.id,
        PhotoTagRelation.photo_id.in_(photo_ids)
    ).delete(synchronize_session=False)
    
    db.commit()
    return count

def set_tag_cover(db: Session, owner_id: UUID, tag_name: str, photo_id: UUID) -> bool:
    tag = get_tag_by_name(db, tag_name, owner_id)
    if not tag:
        return False
        
    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.owner_id == owner_id, Photo.is_deleted == False).first()
    if not photo:
        return False
        
    tag.cover_id = photo_id
    db.commit()
    return True

def delete_tag(db: Session, owner_id: UUID, tag_name: str) -> bool:
    tag = get_tag_by_name(db, tag_name, owner_id)
    if not tag:
        return False

    db.query(PhotoTagRelation).filter(PhotoTagRelation.tag_id == tag.id).delete(synchronize_session=False)
    db.delete(tag)
    db.commit()
    return True

def rename_tag(db: Session, owner_id: UUID, old_name: str, new_name: str) -> Tuple[bool, str]:
    new_name = new_name.strip()
    if not new_name:
        return False, "New tag name is empty"

    tag = get_tag_by_name(db, old_name, owner_id)
    if not tag:
        return False, "Tag not found"

    existing = get_tag_by_name(db, new_name, owner_id)
    if existing and existing.id != tag.id:
        return False, "Target tag already exists"

    tag.tag_name = new_name
    db.commit()
    return True, "success"

def merge_tags(db: Session, owner_id: UUID, target_name: str, source_names: List[str]) -> Tuple[bool, int, str]:
    target_name = target_name.strip()
    source_names = [name.strip() for name in source_names if name and name.strip()]
    if not target_name:
        return False, 0, "Target tag name is empty"
    if not source_names:
        return False, 0, "Source tags are empty"

    target = get_tag_by_name(db, target_name, owner_id)
    if not target:
        target = create_tag(db, target_name, "classification", owner_id)

    merged_count = 0
    for source_name in source_names:
        if source_name == target_name:
            continue

        source = get_tag_by_name(db, source_name, owner_id)
        if not source:
            continue

        if not target.cover_id and source.cover_id:
            target.cover_id = source.cover_id

        source_relations = db.query(PhotoTagRelation).filter(
            PhotoTagRelation.tag_id == source.id
        ).all()

        for relation in source_relations:
            target_relation = db.query(PhotoTagRelation).filter(
                PhotoTagRelation.photo_id == relation.photo_id,
                PhotoTagRelation.tag_id == target.id
            ).first()

            if target_relation:
                target_relation.confidence = max(target_relation.confidence or 0, relation.confidence or 0)
                db.delete(relation)
            else:
                relation.tag_id = target.id
            merged_count += 1

        db.delete(source)

    db.commit()
    return True, merged_count, "success"
