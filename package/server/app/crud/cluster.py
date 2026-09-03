from collections import Counter
from typing import Iterable, List
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.cluster import PhotoCluster, ImageCluster

def remove_photo_from_clusters(db: Session, photo_id: UUID):
    """
    Remove a photo from all its associated clusters.
    If a cluster's photo count becomes 0 (or was already <= 1), the cluster is deleted.
    """
    photo_clusters = db.query(PhotoCluster).filter(PhotoCluster.photo_id == photo_id).all()
    
    if not photo_clusters:
        return
        
    for pc in photo_clusters:
        cluster_id = pc.cluster_id
        
        # Get the associated ImageCluster before deleting PhotoCluster
        image_cluster = db.query(ImageCluster).filter(ImageCluster.cluster_id == cluster_id).first()
        
        # Delete the PhotoCluster record
        db.delete(pc)
        
        if image_cluster:
            if image_cluster.count <= 1:
                db.delete(image_cluster)
            else:
                image_cluster.count -= 1


def remove_photos_from_clusters(db: Session, photo_ids: Iterable[UUID]):
    """Set-based variant of :func:`remove_photo_from_clusters` for bulk deletes.

    ``remove_photo_from_clusters`` issues two queries **per photo**, which turns a
    10k-photo purge into 20k round trips and keeps a write transaction open long
    enough to stall every other request (on SQLite it holds the single writer
    lock the whole time). This version resolves the whole batch with three
    statements: collect the affected cluster ids, drop all ``photo_clusters``
    rows in one DELETE, then decrement / delete the parent ``image_clusters``.
    """
    photo_id_list: List[UUID] = list(photo_ids)
    if not photo_id_list:
        return

    rows = (
        db.query(PhotoCluster.cluster_id)
        .filter(PhotoCluster.photo_id.in_(photo_id_list))
        .all()
    )
    if not rows:
        return

    # How many photos of this batch belong to each cluster, so the parent counter
    # is decremented by the real amount instead of once per call.
    removed_per_cluster = Counter(row[0] for row in rows)

    db.query(PhotoCluster).filter(
        PhotoCluster.photo_id.in_(photo_id_list)
    ).delete(synchronize_session=False)

    image_clusters = (
        db.query(ImageCluster)
        .filter(ImageCluster.cluster_id.in_(list(removed_per_cluster.keys())))
        .all()
    )
    for image_cluster in image_clusters:
        remaining = (image_cluster.count or 0) - removed_per_cluster[image_cluster.cluster_id]
        if remaining <= 0:
            db.delete(image_cluster)
        else:
            image_cluster.count = remaining
