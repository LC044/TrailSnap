from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract, select
from app.db.models.scene import Scene
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.photo import Photo
from app.schemas.scene import SceneCreate, SceneUpdate
from uuid import uuid4, UUID
from typing import List, Optional

def point_in_polygon(x, y, polygon):
    """
    Check if point (x, y) is inside the polygon.
    polygon: list of [x, y] points.
    """
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def update_scene_photos(db: Session, scene: Scene):
    """
    Update photos that fall within the scene's polygon.
    """
    if not scene.polygon:
        return

    # polygon is stored as [[lat, lng], ...] (list of lists)
    # Convert to [[lng, lat], ...] for point_in_polygon (x=lng, y=lat)
    poly_points = [[float(p[1]), float(p[0])] for p in scene.polygon]
    
    # Fetch all photos with location
    # Optimization: Filter by bounding box first if possible, but for now fetch all is safer/easier
    # given we don't have PostGIS. 
    # If dataset is huge, we should calculate bbox of polygon and filter by that first.
    
    min_lng = min(p[0] for p in poly_points)
    max_lng = max(p[0] for p in poly_points)
    min_lat = min(p[1] for p in poly_points)
    max_lat = max(p[1] for p in poly_points)

    query = db.query(PhotoMetadata).filter(
        PhotoMetadata.latitude >= min_lat,
        PhotoMetadata.latitude <= max_lat,
        PhotoMetadata.longitude >= min_lng,
        PhotoMetadata.longitude <= max_lng
    )

    # If scene is private, only include owner's photos
    if scene.owner_id:
        query = query.join(Photo, Photo.id == PhotoMetadata.photo_id).filter(Photo.owner_id == scene.owner_id)
    
    photos = query.all()
    
    updated_count = 0
    for photo in photos:
        if point_in_polygon(float(photo.longitude), float(photo.latitude), poly_points):
            photo.scene_id = scene.id
            updated_count += 1
            
    if updated_count > 0:
        db.commit()

def create_scene(db: Session, scene: SceneCreate, owner_id: Optional[UUID] = None):
    db_scene = Scene(
        id=uuid4(),
        owner_id=owner_id,
        **scene.model_dump()
    )
    db.add(db_scene)
    db.commit()
    db.refresh(db_scene)
    
    update_scene_photos(db, db_scene)
    
    return db_scene

def get_scenes(db: Session, skip: int = 0, limit: int = 100, start_date: str = None, end_date: str = None, owner_id: Optional[UUID] = None):
    # Join Photo to filter by owner
    photo_join_cond = PhotoMetadata.photo_id == Photo.id
    if owner_id:
        photo_join_cond = (PhotoMetadata.photo_id == Photo.id) & (Photo.owner_id == owner_id)

    query = db.query(
        Scene,
        func.count(Photo.id).label("photo_count")
    ).outerjoin(
        PhotoMetadata, Scene.id == PhotoMetadata.scene_id
    ).outerjoin(
        Photo, photo_join_cond
    )

    query = query.filter((Scene.owner_id == owner_id) | (Scene.owner_id == None))

    if start_date:
        query = query.filter(Photo.photo_time >= start_date)
    if end_date:
        query = query.filter(Photo.photo_time <= f"{end_date} 23:59:59")

    results = query.group_by(
        Scene.id
    ).order_by(
        desc("photo_count")
    ).offset(skip).limit(limit).all()
    
    # Batch fetch cover photos
    scene_ids = [s[0].id for s in results]
    if not scene_ids:
        return []
    
    # Get covers for these scenes
    # Rank narrow rows before loading full photos; DISTINCT ON otherwise loads
    # every matching photo on SQLite instead of one cover per scene.
    ranked_query = select(
        Photo.id.label('photo_id'),
        PhotoMetadata.scene_id,
        func.row_number().over(
            partition_by=PhotoMetadata.scene_id,
            order_by=(Photo.photo_time.desc().nullslast(), Photo.id.desc()),
        ).label('rank'),
    ).select_from(Photo).join(
        PhotoMetadata, Photo.id == PhotoMetadata.photo_id
    ).filter(
        Photo.owner_id == owner_id,
        PhotoMetadata.scene_id.in_(scene_ids)
    )

    if start_date:
        ranked_query = ranked_query.filter(Photo.photo_time >= start_date)
    if end_date:
        ranked_query = ranked_query.filter(Photo.photo_time <= f"{end_date} 23:59:59")

    ranked_covers = ranked_query.subquery()
    covers = db.query(Photo, ranked_covers.c.scene_id).join(
        ranked_covers, Photo.id == ranked_covers.c.photo_id
    ).filter(ranked_covers.c.rank == 1).all()
    cover_map = {sid: photo for photo, sid in covers}
    
    scenes = []
    for scene, count in results:
        scene.photo_count = count
        scene.cover = cover_map.get(scene.id)
        scenes.append(scene)
    return scenes

def get_scene(db: Session, scene_id: UUID, owner_id: Optional[UUID] = None):
    query = db.query(Scene).filter(Scene.id == scene_id)
    if owner_id:
        query = query.filter((Scene.owner_id == owner_id) | (Scene.owner_id == None))
    else:
        query = query.filter(Scene.owner_id == None)
    return query.first()

def delete_scene(db: Session, scene_id: UUID, owner_id: Optional[UUID] = None):
    db_scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if db_scene:
        if db_scene.owner_id and db_scene.owner_id != owner_id:
             raise ValueError("Permission denied")
        if not db_scene.is_custom:
            raise ValueError("Cannot delete system default scene")
            
        # Clear scene_id from photos?
        # ForeignKey has ondelete set? 
        # Check PhotoMetadata model: scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id"), nullable=True)
        # It doesn't specify ondelete="SET NULL" explicitly in the Column definition, 
        # but usually SQLAlchemy handles this if relationship is configured.
        # Actually, let's just let DB handle it or manually set null.
        # Ideally we want to set null.
        
        photos = db.query(PhotoMetadata).filter(PhotoMetadata.scene_id == scene_id).all()
        for p in photos:
            p.scene_id = None
            
        db.delete(db_scene)
        db.commit()
    return db_scene

def update_scene(db: Session, scene_id: UUID, scene: SceneUpdate, owner_id: Optional[UUID] = None):
    db_scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not db_scene:
        return None
    
    if db_scene.owner_id and db_scene.owner_id != owner_id:
         raise ValueError("Permission denied")
    
    update_data = scene.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_scene, key, value)
        
    db.add(db_scene)
    db.commit()
    db.refresh(db_scene)
    
    # If polygon or location changed, we might need to re-evaluate photos?
    # For now, let's re-run update_scene_photos if polygon changed.
    if 'polygon' in update_data:
        update_scene_photos(db, db_scene)
        
    return db_scene
