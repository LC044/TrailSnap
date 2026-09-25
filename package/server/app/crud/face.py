from operator import rshift
from typing import Dict, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import sqlalchemy as sa

from app.db.models.face import Face, FaceIdentity
from app.db.models.person_timeline import PersonTimelineHide
from app.db.models.photo import Photo
from app.schemas import face as schemas
from app.core.config_manager import config_manager
import logging

from app.schemas.face import FaceIdentitySchema

logger = logging.getLogger(__name__)

# Face Operations
def create_face(db: Session, obj_in: schemas.FaceCreate) -> Face:
    db_obj = Face(
        photo_id=obj_in.photo_id,
        face_identity_id=obj_in.face_identity_id,
        face_rect=obj_in.face_rect,
        face_confidence=obj_in.face_confidence,
        recognize_confidence=obj_in.recognize_confidence,
        face_feature=obj_in.face_feature
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_face(db: Session, face_id: int, owner_id: Optional[UUID] = None) -> Optional[Face]:
    query = db.query(Face).filter(Face.id == face_id, Face.is_deleted == False)
    if owner_id:
        query = query.join(Photo).filter(Photo.owner_id == owner_id)
    return query.first()

def get_faces(db: Session, skip: int = 0, limit: int = 100, owner_id: Optional[UUID] = None) -> List[Face]:
    query = db.query(Face).filter(Face.is_deleted == False)
    if owner_id:
        query = query.join(Photo).filter(Photo.owner_id == owner_id, Photo.is_deleted == False)
    return query.offset(skip).limit(limit).all()

def update_face(db: Session, face_id: int, obj_in: schemas.FaceUpdate, owner_id: Optional[UUID] = None) -> Optional[Face]:
    db_obj = get_face(db, face_id, owner_id)
    if not db_obj:
        return None

    update_data = obj_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)

    db.add(db_obj)
    identity = db.query(FaceIdentity).get(db_obj.face_identity_id)
    if identity and not identity.default_face_id:
        identity.default_face_id = db_obj.id
    db.commit()
    db.refresh(db_obj)
    return db_obj

def delete_face(db: Session, face_id: int, owner_id: Optional[UUID] = None) -> Optional[Face]:
    """
    Delete a face record.
    Fix: When deleting a face, check if it is the default face for its identity.
    If so, try to find another face to set as default.
    """
    face = get_face(db, face_id, owner_id)
    if not face:
        return None
    
    handle_face_deletion_dependency(db, face)
    
    db.delete(face)
    db.commit()
    return face

def delete_faces(db: Session, face_ids: List[int], owner_id: Optional[UUID] = None):
    """
    Delete multiple face records.
    """
    for face_id in face_ids:
        delete_face(db, face_id, owner_id)

def handle_face_deletion_dependency(db: Session, face: Face):
    """
    Check if the face is the default face for its identity.
    If so, update the identity's default_face_id to another face.
    """
    if face.face_identity_id:
        identity = db.query(FaceIdentity).get(face.face_identity_id)
        if identity and identity.default_face_id == face.id:
            # Find another face for this identity
            # Exclude the current face and deleted faces
            next_face = db.query(Face).filter(
                Face.face_identity_id == identity.id,
                Face.id != face.id,
                Face.is_deleted == False
            ).order_by(Face.create_time.desc()).first()
            
            if next_face:
                identity.default_face_id = next_face.id
                logger.info(f"Updated default_face_id for identity {identity.id} to {next_face.id} (was {face.id})")
            else:
                # No other faces, set to None
                identity.default_face_id = None
                logger.info(f"Set default_face_id for identity {identity.id} to None (was {face.id})")
            
            db.add(identity)
            # Commit is handled by caller or we can flush here
            db.flush()

# FaceIdentity Operations
def create_identity(db: Session, obj_in: schemas.FaceIdentityCreate, owner_id: UUID) -> FaceIdentity:
    db_obj = FaceIdentity(
        identity_name=obj_in.identity_name,
        owner_id=owner_id
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_identity(db: Session, identity_id: UUID, owner_id: Optional[UUID] = None) -> Optional[FaceIdentity]:
    query = db.query(FaceIdentity).filter(FaceIdentity.id == identity_id, FaceIdentity.is_deleted == False)
    if owner_id:
        query = query.filter(FaceIdentity.owner_id == owner_id)
    return query.first()

def get_identities(db: Session, skip: int = 0, limit: int = 100, owner_id: Optional[UUID] = None) -> List[FaceIdentity]:
    query = db.query(FaceIdentity).filter(FaceIdentity.is_deleted == False)
    if owner_id:
        query = query.filter(FaceIdentity.owner_id == owner_id)
    return query.offset(skip).limit(limit).all()

def update_identity(db: Session, identity_id: UUID, obj_in: schemas.FaceIdentityUpdate, owner_id: Optional[UUID] = None) -> Optional[FaceIdentity]:
    db_obj = get_identity(db, identity_id, owner_id)
    if not db_obj:
        return None

    update_data = obj_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    print(update_data)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def delete_identity(db: Session, identity_id: UUID, owner_id: Optional[UUID] = None) -> bool:
    identity = get_identity(db, identity_id, owner_id)
    if not identity:
        return False

    for model in (PersonTimelineHide,):
        db.query(model).filter(
            model.owner_id == identity.owner_id,
            sa.or_(model.person_a_id == identity_id, model.person_b_id == identity_id),
        ).delete(synchronize_session=False)
    db.delete(identity)
    db.commit()
    return True

def get_identities_with_details(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    min_photos: int = 0,
    photo_id: Optional[UUID] = None,
    visibility_types: Optional[List[str]] = None,
    owner_id: Optional[UUID] = None
) -> List[FaceIdentitySchema]:
    # 1. 子查询：统计每个人脸身份的人脸数（按photo_id筛选并去重）
    face_counts_subq = db.query(
        Face.face_identity_id,
        func.count(func.distinct(Face.photo_id)).label("count")
    ).filter(
        Face.face_identity_id.isnot(None)  # 修正：非空判断
    )
    # 仅当photo_id有值时，添加photo_id筛选
    if photo_id:
        face_counts_subq = face_counts_subq.filter(Face.photo_id == photo_id)
    
    # NEW: Filter by owner_id in subquery
    if owner_id:
        face_counts_subq = face_counts_subq.join(Photo).filter(Photo.owner_id == owner_id)

    face_counts_subq = face_counts_subq.group_by(Face.face_identity_id).subquery()

    # 2. 主查询：关联FaceIdentity + 统计数 + 默认人脸 + 照片
    query = db.query(
        FaceIdentity,
        func.coalesce(face_counts_subq.c.count, 0).label("count"),  # 空值转0
        Face,
        Photo
    ).outerjoin(
        face_counts_subq, FaceIdentity.id == face_counts_subq.c.face_identity_id
    ).outerjoin(
        Face, FaceIdentity.default_face_id == Face.id
    ).outerjoin(
        Photo, Face.photo_id == Photo.id
    ).filter(
        # 核心修正：筛选「统计数>= min_photos」（SQL层过滤，提升性能）
        func.coalesce(face_counts_subq.c.count, 0) >= min_photos  # min_photos=0 must include 0-photo identities
    )

    # NEW: Filter by owner_id in main query
    if owner_id:
        query = query.filter(FaceIdentity.owner_id == owner_id)
    query = query.filter(FaceIdentity.is_deleted == False)  # exclude soft-deleted (merged) identities

    # 2.1 筛选逻辑
    if visibility_types:
        conditions = []
        if 'named' in visibility_types:
            conditions.append(sa.and_(FaceIdentity.is_hidden == False, FaceIdentity.identity_name != '未命名'))
        if 'unnamed' in visibility_types:
            conditions.append(sa.and_(FaceIdentity.is_hidden == False, FaceIdentity.identity_name == '未命名'))
        if 'hidden' in visibility_types:
            conditions.append(FaceIdentity.is_hidden == True)

        if conditions:
            query = query.filter(sa.or_(*conditions))
        else:
            # 如果提供了空列表，则不返回任何结果
            query = query.filter(sa.false())

    # 3. 仅当photo_id有值时：筛选「该身份在该photo_id下有人脸」
    if photo_id:
        # 方式1：通过face_counts_subq的count>0筛选（推荐）
        query = query.filter(face_counts_subq.c.count.isnot(None))
        # 方式2（备选）：子查询筛选有该photo_id人脸的身份ID
        # photo_identity_ids = db.query(Face.face_identity_id).filter(
        #     Face.photo_id == photo_id, Face.is_deleted == False
        # ).subquery()
        # query = query.filter(FaceIdentity.id.in_(photo_identity_ids))

    # 4. 排序+分页
    query = query.order_by(FaceIdentity.is_hidden.asc(), face_counts_subq.c.count.desc().nullslast()).offset(skip).limit(limit)

    results = []

    for identity, count, default_face, photo in query.all():
        # 无需再过滤min_photos（已在SQL层处理）
        cover = None
        if default_face and photo:
            cover = schemas.CoverPhotoInfo(
                photo_id=default_face.photo_id,
                face_rect=default_face.face_rect,
                face_confidence=default_face.face_confidence,
                recognize_confidence=default_face.recognize_confidence
            )

        results.append(FaceIdentitySchema(
            id=identity.id,
            identity_name=identity.identity_name,
            default_face_id=identity.default_face_id,
            description=identity.description,
            tags=identity.tags,
            face_count=count,
            cover_photo=cover,
            cover=photo,
            is_hidden=identity.is_hidden,
            create_time=identity.create_time,
            update_time=identity.update_time
        ))
    return results

def get_identities_by_photo_id(db: Session, photo_id: UUID, owner_id: Optional[UUID] = None) -> List[FaceIdentitySchema]:
    # 1. 主查询：单次拿所有 Face + Identity + Photo
    query = db.query(Face, FaceIdentity, Photo).join(
        FaceIdentity, Face.face_identity_id == FaceIdentity.id
    ).join(
        Photo, Face.photo_id == Photo.id
    ).filter(
        Face.photo_id == photo_id,
        Face.is_deleted == False,
        FaceIdentity.is_deleted == False
    )
    if owner_id:
        query = query.filter(Photo.owner_id == owner_id)

    rows = query.all()
    if not rows:
        return []

    # 2. 单次聚合：取所有相关 identity 的总 face 数（替代原 N+1 循环 count）
    identity_ids = {identity.id for _, identity, _ in rows}
    count_rows = db.query(
        Face.face_identity_id, func.count(Face.id)
    ).filter(
        Face.face_identity_id.in_(identity_ids),
        Face.is_deleted == False
    ).group_by(Face.face_identity_id).all()
    face_counts = {fid: cnt for fid, cnt in count_rows}

    # 3. 构结果（O(N) 内存组装，无额外查询）
    results = []
    for face, identity, photo in rows:
        cover_photo_info = schemas.CoverPhotoInfo(
            photo_id=photo.id,
            face_rect=face.face_rect,
            face_confidence=face.face_confidence,
            recognize_confidence=face.recognize_confidence
        )
        results.append(FaceIdentitySchema(
            id=identity.id,
            identity_name=identity.identity_name,
            default_face_id=identity.default_face_id,
            description=identity.description,
            tags=identity.tags,
            face_count=face_counts.get(identity.id, 0),
            cover_photo=cover_photo_info,
            cover=None,
            is_hidden=identity.is_hidden,
            create_time=identity.create_time,
            update_time=identity.update_time
        ))
    return results

def get_identity_photos(db: Session, identity_id: UUID, skip: int = 0, limit: int = 50, owner_id: Optional[UUID] = None) -> List[Photo]:
    query = db.query(Photo).distinct(Photo.id).join(Face).filter(
        Face.face_identity_id == identity_id,
        Photo.id == Face.photo_id
    )
    if owner_id:
        query = query.filter(Photo.owner_id == owner_id, Photo.is_deleted == False)
    return query.order_by(desc(Photo.id)).offset(skip).limit(limit).all()

def get_group_albums(
    db: Session,
    min_photos: int = 0,
    owner_id: Optional[UUID] = None
) -> List[schemas.GroupAlbumItem]:
    """合影组合相册列表。

    语义：与“个人”栏同口径——只有照片数达到展示阈值（min_photos）的“可展示人物”
    才参与组合；每张照片里出现的可展示人物集合构成一个组合；组合的照片数 =
    同时包含该组全部成员的照片数。返回组合列表（成员 + 照片数 + 封面），
    按组合照片数倒序、成员 id 排序保证稳定输出。
    """
    # 1. 可展示人物（与 get_identities_with_details 的统计口径一致：
    #    distinct photo 数 >= min_photos，未隐藏、未软删）
    photo_counts_subq = db.query(
        Face.face_identity_id.label("identity_id"),
        func.count(func.distinct(Face.photo_id)).label("count")
    ).filter(
        Face.face_identity_id.isnot(None),
        Face.is_deleted == False
    )
    if owner_id:
        photo_counts_subq = photo_counts_subq.join(Photo).filter(
            Photo.owner_id == owner_id,
            Photo.is_deleted == False
        )
    photo_counts_subq = photo_counts_subq.group_by(Face.face_identity_id).subquery()

    displayable_rows = db.query(photo_counts_subq.c.identity_id).join(
        FaceIdentity, FaceIdentity.id == photo_counts_subq.c.identity_id
    ).filter(
        FaceIdentity.is_deleted == False,
        FaceIdentity.is_hidden == False,
        photo_counts_subq.c.count >= min_photos
    )
    if owner_id:
        displayable_rows = displayable_rows.filter(FaceIdentity.owner_id == owner_id)
    displayable_ids = {row.identity_id for row in displayable_rows.all()}
    if len(displayable_ids) < 2:
        return []

    # 2. 每张照片里的可展示人物集合（只统计活跃照片）
    face_rows = db.query(Face.photo_id, Face.face_identity_id).join(
        Photo, Face.photo_id == Photo.id
    ).filter(
        Face.face_identity_id.in_(displayable_ids),
        Face.is_deleted == False,
        Photo.is_deleted == False
    )
    if owner_id:
        face_rows = face_rows.filter(Photo.owner_id == owner_id)

    members_by_photo: Dict[UUID, set] = {}
    for photo_id, identity_id in face_rows.distinct().all():
        members_by_photo.setdefault(photo_id, set()).add(identity_id)

    # 3. 按“可展示人物组合”聚合照片。每张照片只贡献给它实际包含的组合，
    #    不做超集归并（“张三+李四”相册不含三人照；三人照属于“张三+李四+王五”）
    photos_by_group: Dict[frozenset, List[UUID]] = {}
    for photo_id, members in members_by_photo.items():
        if len(members) >= 2:
            photos_by_group.setdefault(frozenset(members), []).append(photo_id)

    if not photos_by_group:
        return []

    # 4. 封面取组合内 photo_time 最新的一张；一次取回涉及的 Photo + 名称
    all_photo_ids = {pid for pids in photos_by_group.values() for pid in pids}
    photos_by_id = {
        photo.id: photo
        for photo in db.query(Photo).filter(Photo.id.in_(all_photo_ids))
    }
    identity_names = {
        identity.id: identity.identity_name
        for identity in db.query(FaceIdentity).filter(FaceIdentity.id.in_(displayable_ids))
    }

    # 5. 组装：按成员 id 排序保证组合内顺序稳定，按 photo_count 倒序
    results = []
    for members, pids in photos_by_group.items():
        covers = [photos_by_id[pid] for pid in pids if pid in photos_by_id]
        if not covers:
            continue
        cover = max(covers, key=lambda p: (p.photo_time is not None, p.photo_time))
        results.append(schemas.GroupAlbumItem(
            identities=[
                schemas.GroupAlbumIdentity(identity_id=iid, identity_name=identity_names.get(iid))
                for iid in sorted(members)
            ],
            photo_count=len(pids),
            cover=cover
        ))
    results.sort(key=lambda item: (-item.photo_count, tuple(str(i.identity_id) for i in item.identities)))
    return results


def get_group_album_photos(
    db: Session,
    identity_ids: List[UUID],
    skip: int = 0,
    limit: int = 500,
    owner_id: Optional[UUID] = None
) -> List[Photo]:
    """指定人物组合的合影照片：同时包含全部成员的照片，按拍摄时间倒序。"""
    if not identity_ids:
        return []

    # 每张照片命中的成员数
    hits_subq = db.query(
        Face.photo_id.label("photo_id"),
        func.count(func.distinct(Face.face_identity_id)).label("hits")
    ).filter(
        Face.face_identity_id.in_(identity_ids),
        Face.is_deleted == False
    ).group_by(Face.photo_id).subquery()

    query = db.query(Photo).join(
        hits_subq, Photo.id == hits_subq.c.photo_id
    ).filter(
        hits_subq.c.hits == len(identity_ids),
        Photo.is_deleted == False
    )
    if owner_id:
        query = query.filter(Photo.owner_id == owner_id)

    return query.order_by(Photo.photo_time.desc().nullslast(), desc(Photo.id)).offset(skip).limit(limit).all()

def remove_photos_from_identity(db: Session, identity_id: UUID, photo_ids: List[UUID], owner_id: Optional[UUID] = None) -> int:
    identity = get_identity(db, identity_id, owner_id)
    if not identity:
        return 0
    
    query = db.query(Face).join(Photo).filter(
        Face.face_identity_id == identity_id,
        Face.photo_id.in_(photo_ids)
    )
    if owner_id:
        query = query.filter(Photo.owner_id == owner_id)
    faces = query.all()
    
    for face in faces:
        handle_face_deletion_dependency(db, face)
        face.face_identity_id = None
        db.add(face)
        
    db.commit()
    return len(faces)

def delete_faces_by_photo(db: Session, photo_id: UUID, confidence_threshold: float = 1.0) -> int:
    faces = db.query(Face).filter(
        Face.photo_id == photo_id,
        Face.face_confidence < confidence_threshold
    ).all()
    count = len(faces)
    for face in faces:
        handle_face_deletion_dependency(db, face)
        db.delete(face)
    db.commit()
    return count

def set_identity_cover(db: Session, identity_id: UUID, photo_id: UUID, owner_id: Optional[UUID] = None) -> bool:
    identity = get_identity(db, identity_id, owner_id)
    if not identity:
        return False
        
    query = db.query(Face).join(Photo).filter(
        Face.face_identity_id == identity_id,
        Face.photo_id == photo_id
    )
    if owner_id:
        query = query.filter(Photo.owner_id == owner_id)
    face = query.first()
    
    if not face:
        return False
        
    identity.default_face_id = face.id
    db.add(identity)
    db.commit()
    return True

def merge_identities(db: Session, target_id: UUID, source_ids: List[UUID], owner_id: Optional[UUID] = None) -> bool:
    target = get_identity(db, target_id, owner_id)
    if not target:
        return False

    for source_id in source_ids:
        if source_id == target_id:
            continue

        source = get_identity(db, source_id, owner_id)
        if not source:
            continue

        # Move faces
        faces = db.query(Face).filter(Face.face_identity_id == source_id).all()
        for face in faces:
            face.face_identity_id = target_id
            db.add(face)

        # Keep user-authored story exclusions when a source identity is merged.
        for rule in db.query(PersonTimelineHide).filter(
            PersonTimelineHide.owner_id == target.owner_id,
            sa.or_(PersonTimelineHide.person_a_id == source_id, PersonTimelineHide.person_b_id == source_id),
        ).all():
            members = [target_id if value == source_id else value for value in (rule.person_a_id, rule.person_b_id)]
            if members[0] == members[1]:
                db.delete(rule)
            elif members[1] == UUID(int=0):
                rule.person_a_id, rule.person_b_id = members
            else:
                rule.person_a_id, rule.person_b_id = sorted(members, key=str)

        # Soft delete source
        source.is_deleted = True
        db.add(source)

    db.commit()
    return True
