import logging
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.models.album import Album
from app.db.models.face import FaceIdentity, Face
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.dependencies import get_db, BaseResponse
from app.core.config_manager import config_manager
from app.schemas.nav import NavItemRef, ResolvedNavItem, NavItemsUpdate, NavItemsResponse

logger = logging.getLogger("app.nav")
router = APIRouter()


def resolve_nav_items(user_id: UUID, db: Session) -> List[ResolvedNavItem]:
    """Resolve nav item references to full items with cover/name, auto-pruning deleted entities."""
    config = config_manager.get_user_config(user_id, db)
    refs = config.nav.items
    resolved = []
    valid_refs = []
    needs_prune = False

    for ref in refs:
        try:
            item = resolve_single_entity(ref, user_id, db)
            if item is not None:
                resolved.append(item)
                valid_refs.append(ref)
            else:
                needs_prune = True
        except Exception as e:
            logger.warning(f"Failed to resolve nav item {ref.entity_type}/{ref.entity_id}: {e}")
            db.rollback()
            needs_prune = True

    # If some refs were pruned, persist the updated list
    if needs_prune and len(valid_refs) != len(refs):
        config_manager.update_user_config(
            user_id,
            {"nav": {"items": [r.model_dump() for r in valid_refs]}},
            db
        )

    return resolved


def resolve_single_entity(ref: NavItemRef, user_id: UUID, db: Session) -> ResolvedNavItem | None:
    """Resolve a single nav item reference. Returns None if entity doesn't exist."""
    try:
        if ref.entity_type == "album":
            return resolve_album(ref.entity_id, user_id, db)
        elif ref.entity_type == "person":
            return resolve_person(ref.entity_id, user_id, db)
        elif ref.entity_type == "location":
            return resolve_location(ref.entity_id, user_id, db)
        elif ref.entity_type == "classification":
            return resolve_classification(ref.entity_id, user_id, db)
        else:
            logger.warning(f"Unknown nav entity type: {ref.entity_type}")
            return None
    except Exception as e:
        logger.warning(f"Failed to resolve nav item {ref.entity_type}/{ref.entity_id}: {e}")
        return None


def resolve_album(entity_id: str, user_id: UUID, db: Session) -> ResolvedNavItem | None:
    album = db.query(Album).filter(
        Album.id == UUID(entity_id),
        Album.owner_id == user_id
    ).first()
    if not album:
        return None
    return ResolvedNavItem(
        entity_type="album",
        entity_id=entity_id,
        name=album.name,
        cover_photo_id=str(album.cover_id) if album.cover_id else None,
        route_path=f"/album/{entity_id}",
        photo_count=album.num_photos or 0
    )


def resolve_person(entity_id: str, user_id: UUID, db: Session) -> ResolvedNavItem | None:
    identity = db.query(FaceIdentity).filter(
        FaceIdentity.id == UUID(entity_id),
        FaceIdentity.owner_id == user_id,
        FaceIdentity.is_deleted == False
    ).first()
    if not identity:
        return None

    cover_photo_id = None
    face_rect = None
    photo_count = 0

    if identity.default_face_id:
        face = db.query(Face).filter(Face.id == identity.default_face_id).first()
        if face and not face.is_deleted:
            cover_photo_id = str(face.photo_id)
            face_rect = face.face_rect
            photo_count = db.query(func.count(func.distinct(Face.photo_id))).filter(
                Face.face_identity_id == identity.id,
                Face.is_deleted == False
            ).scalar() or 0

    if not cover_photo_id:
        # Fallback: find any face for this identity
        face = db.query(Face).filter(
            Face.face_identity_id == identity.id,
            Face.is_deleted == False
        ).first()
        if face:
            cover_photo_id = str(face.photo_id)
            face_rect = face.face_rect
        photo_count = db.query(func.count(func.distinct(Face.photo_id))).filter(
            Face.face_identity_id == identity.id,
            Face.is_deleted == False
        ).scalar() or 0

    return ResolvedNavItem(
        entity_type="person",
        entity_id=entity_id,
        name=identity.identity_name or "未命名",
        cover_photo_id=cover_photo_id,
        cover_photo_face_rect=face_rect,
        route_path=f"/album/people/{entity_id}",
        photo_count=photo_count
    )


def resolve_location(entity_id: str, user_id: UUID, db: Session) -> ResolvedNavItem | None:
    """Resolve a location by city name. Find the most recent photo as cover."""
    # Count photos with this city name
    photo_count = db.query(func.count(Photo.id)).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    ).filter(
        Photo.owner_id == user_id,
        Photo.is_deleted == False,
        PhotoMetadata.city == entity_id
    ).scalar() or 0

    if photo_count == 0:
        return None

    # Get the most recent photo as cover
    cover_photo = db.query(Photo).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    ).filter(
        Photo.owner_id == user_id,
        Photo.is_deleted == False,
        PhotoMetadata.city == entity_id,
        Photo.photo_time.isnot(None)
    ).order_by(Photo.photo_time.desc()).first()

    return ResolvedNavItem(
        entity_type="location",
        entity_id=entity_id,
        name=entity_id,
        cover_photo_id=str(cover_photo.id) if cover_photo else None,
        route_path=f"/album/location/{entity_id}",
        photo_count=photo_count
    )


def resolve_classification(entity_id: str, user_id: UUID, db: Session) -> ResolvedNavItem | None:
    """Resolve a classification/tag by tag UUID."""
    tag = db.query(PhotoTag).filter(
        PhotoTag.id == UUID(entity_id),
        PhotoTag.owner_id == user_id,
        PhotoTag.is_deleted == False
    ).first()
    if not tag:
        return None

    cover_photo_id = str(tag.cover_id) if tag.cover_id else None
    photo_count = db.query(func.count(PhotoTagRelation.id)).filter(
        PhotoTagRelation.tag_id == tag.id,
        PhotoTagRelation.is_deleted == False
    ).scalar() or 0

    # If no cover, try to find a photo with this tag
    if not cover_photo_id:
        relation = db.query(PhotoTagRelation).filter(
            PhotoTagRelation.tag_id == tag.id,
            PhotoTagRelation.is_deleted == False
        ).first()
        if relation:
            cover_photo_id = str(relation.photo_id)

    return ResolvedNavItem(
        entity_type="classification",
        entity_id=entity_id,
        name=tag.tag_name,
        cover_photo_id=cover_photo_id,
        route_path=f"/album/classification/{tag.tag_name}",
        photo_count=photo_count
    )


@router.get("/items", response_model=BaseResponse[NavItemsResponse])
def get_nav_items(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get resolved nav items for the current user."""
    items = resolve_nav_items(current_user.id, db)
    return BaseResponse(data=NavItemsResponse(items=items))


@router.put("/items", response_model=BaseResponse[NavItemsResponse])
def update_nav_items(
    body: NavItemsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Replace the entire ordered list of nav items."""
    # Validate that entity_ids are well-formed for UUID types
    for ref in body.items:
        if ref.entity_type in ("album", "person", "classification"):
            try:
                UUID(ref.entity_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid UUID for {ref.entity_type}: {ref.entity_id}")

    config_manager.update_user_config(
        current_user.id,
        {"nav": {"items": [r.model_dump() for r in body.items]}},
        db
    )
    items = resolve_nav_items(current_user.id, db)
    return BaseResponse(data=NavItemsResponse(items=items))


@router.delete("/items/{entity_type}/{entity_id}", response_model=BaseResponse[NavItemsResponse])
def delete_nav_item(
    entity_type: str,
    entity_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a single nav item."""
    config = config_manager.get_user_config(current_user.id, db)
    new_items = [
        ref for ref in config.nav.items
        if not (ref.entity_type == entity_type and ref.entity_id == entity_id)
    ]
    config_manager.update_user_config(
        current_user.id,
        {"nav": {"items": [r.model_dump() for r in new_items]}},
        db
    )
    items = resolve_nav_items(current_user.id, db)
    return BaseResponse(data=NavItemsResponse(items=items))
