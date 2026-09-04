
import numpy as np
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import List, Dict, Any
from sklearn.cluster import AgglomerativeClustering
from app.db.models.image_vector import ImageVector
from app.db.models.photo import Photo
from app.db.models.image_description import ImageDescription
from app.service.media_urls import thumbnail_url

class SimilarPhotoService:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    def get_similar_groups(self, threshold: float = 0.9) -> List[List[Dict[str, Any]]]:
        # 1. Fetch all vectors for the user
        # Join with Photo to ensure ownership and existence
        stmt = (
            select(ImageVector.photo_id, ImageVector.embedding)
            .join(Photo, ImageVector.photo_id == Photo.id)
            .where(Photo.owner_id == self.user_id)
        )
        results = self.db.execute(stmt).all()

        if not results:
            return []

        photo_ids = [str(r.photo_id) for r in results]
        embeddings = [np.array(r.embedding) for r in results]
        
        if not embeddings:
            return []

        X = np.array(embeddings)
        
        # Normalize vectors to use cosine distance effectively if not already normalized
        # But usually CLIP embeddings are normalized or we use cosine_distance which handles it?
        # scikit-learn's AgglomerativeClustering with "cosine" metric expects normalized vectors for correct "distance" interpretation?
        # Actually "cosine" distance is 1 - cosine_similarity.
        # If threshold is 0.9 similarity, distance threshold is 0.1.
        
        # Normalize
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        # Avoid division by zero
        norms[norms == 0] = 1
        X_normalized = X / norms

        # 2. Cluster
        # distance_threshold: The linkage distance threshold above which, clusters will not be merged.
        # For cosine distance, it's between 0 and 2.
        # If we want similarity > 0.9, distance < 0.1.
        distance_threshold = 1 - threshold
        
        clustering = AgglomerativeClustering(
            n_clusters=None,
            metric='cosine',
            linkage='average', # average linkage is often good for "all items in cluster are similar"
            distance_threshold=distance_threshold
        )
        labels = clustering.fit_predict(X_normalized)

        # 3. Group by label
        groups: Dict[int, List[str]] = {}
        for photo_id, label in zip(photo_ids, labels):
            if label not in groups:
                groups[label] = []
            groups[label].append(photo_id)

        # Filter out singletons (groups with only 1 photo)
        similar_groups = [p_ids for p_ids in groups.values() if len(p_ids) > 1]

        # 4. Fetch details and sort
        result_groups = []
        for p_ids in similar_groups:
            # Fetch photo details
            photos_stmt = (
                select(Photo, ImageDescription)
                .outerjoin(ImageDescription, Photo.id == ImageDescription.photo_id)
                .where(Photo.id.in_(p_ids))
            )
            photos = self.db.execute(photos_stmt).all()
            
            group_items = []
            for photo, desc in photos:
                score = 0
                if desc:
                    score = (desc.memory_score or 0) + (desc.quality_score or 0)
                
                group_items.append({
                    "id": str(photo.id),
                    "filename": photo.filename,
                    "photo_time": photo.photo_time,
                    "score": score,
                    "thumbnail_path": thumbnail_url(self.user_id, photo.id), # Helper for frontend
                    "src": f"/api/medias/{photo.id}/preview" # Helper for frontend
                })

            # Sort: Score desc, then Photo Time desc
            group_items.sort(key=lambda x: (x['score'], x['photo_time'] or datetime.min), reverse=True)
            result_groups.append(group_items)

        return result_groups
