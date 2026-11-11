"""Metadata search predicates shared by photo browsing and timeline statistics."""
from uuid import UUID
from sqlalchemy import or_, and_, false

from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.face import Face, FaceIdentity
from app.db.models.album import Album
from app.db.models.tag import PhotoTag
from app.db.models.scene import Scene
from app.db.models.ocr import OCR
from app.crud.photo_paths import escape_like, normalized_file_path


def apply_metadata_search(query, search_type, search_text, cities=None, people=None, categories=None):
    value = (search_text or '').strip()
    # One predicate per group: alternatives within a group use OR; independent
    # group predicates are applied with AND. EXISTS prevents duplicate photos.
    if search_type == 'location':
        places = list(set((cities or []) + ([value] if value else [])))
        if places:
            query = query.filter(Photo.metadata_info.has(or_(*[
                field.in_(places) for field in (PhotoMetadata.city, PhotoMetadata.province,
                                               PhotoMetadata.country, PhotoMetadata.district,
                                               PhotoMetadata.address)
            ])))
    identity_ids, names = [], []
    for person in people or []:
        try:
            identity_ids.append(UUID(person))
        except ValueError:
            names.append(person)  # Keep existing saved name-based filters usable.
    if search_type == 'person' and value:
        names.append(value)
    if identity_ids or names:
        query = query.filter(Photo.faces.any(and_(
            Face.is_deleted.is_(False),
            Face.identity.has(and_(FaceIdentity.is_deleted.is_(False), or_(
                FaceIdentity.id.in_(identity_ids), FaceIdentity.identity_name.in_(names)
            )))
        )))
    tags = list(set((categories or []) + ([value] if search_type == 'tag' and value else [])))
    if tags:
        query = query.filter(Photo.tags.any(PhotoTag.tag_name.in_(tags)))
    if not search_type or search_type in ('location', 'person', 'tag', 'date'):
        return query
    if not value:
        return query.filter(false())
    term = f"%{escape_like(value)}%"
    if search_type == "album":
        condition = Photo.albums.any(Album.name == value)
    elif search_type == "scene":
        condition = Photo.metadata_info.has(PhotoMetadata.scene.has(Scene.name == value))
    elif search_type == "ocr":
        condition = query.session.query(OCR.photo_id).filter(
            OCR.photo_id == Photo.id, OCR.text.ilike(term, escape="\\")
        ).exists()
    elif search_type == "filename":
        condition = Photo.filename == value
    elif search_type == "folder":
        folder = value.replace("\\", "/").rstrip("/")
        condition = normalized_file_path().like(escape_like(folder) + "/%", escape="\\")
    else:
        condition = false()
    # EXISTS keeps a photo unique even when several faces/OCR rows match.
    return query.filter(condition)
