import logging
import traceback
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, distinct
import aiohttp

import app.crud.photo
from app.db.models import User
from app.dependencies import get_db, BaseResponse
from app.crud import crud_vector
from app.core.config_manager import config_manager
from app.schemas.photo import Photo as PhotoSchema
from app.crud import album as crud_album
from app.api.deps import get_current_user
from app.utils.embedding import async_get_embedding

# DB Models
from app.db.models.ocr import OCR
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.face import FaceIdentity, Face
from app.db.models.album import Album
from app.db.models.photo import Photo
from app.db.models.tag import PhotoTag
from app.db.models.scene import Scene

router = APIRouter()

class SearchResult(BaseModel):
    photo: PhotoSchema
    score: float

class SearchSuggestion(BaseModel):
    type: str
    value: str
    label: str

class TextSearchRequest(BaseModel):
    text: str
    limit: int = 20
    skip: int = 0
    threshold: float = 0.2
    type: Optional[str] = None # 'ocr', 'location', 'person', 'album', 'folder', 'filename', 'tag', 'scene'
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

@router.get("/suggestions", response_model=BaseResponse[List[SearchSuggestion]])
async def get_search_suggestions(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Get search suggestions based on query string.
    """
    suggestions = []
    limit = 5
    search_term = f"%{q}%"

    try:
        # 1. Person Name
        persons = db.query(distinct(FaceIdentity.identity_name))\
            .filter(FaceIdentity.owner_id == user.id, FaceIdentity.identity_name.ilike(search_term))\
            .limit(limit).all()
        for p in persons:
            if p[0]:
                suggestions.append(SearchSuggestion(type="person", value=p[0], label=f"Person: {p[0]}"))

        # 2. Location (City, Country, Province, District, Address)
        # Helper to add location suggestions
        def add_loc_suggestions(field, label_prefix):
            res = db.query(distinct(field))\
                .join(Photo, PhotoMetadata.photo_id == Photo.id)\
                .filter(Photo.owner_id == user.id)\
                .filter(field.ilike(search_term))\
                .limit(limit).all()
            for r in res:
                if r[0] and not any(s.value == r[0] and s.type == "location" for s in suggestions):
                    suggestions.append(SearchSuggestion(type="location", value=r[0], label=f"{label_prefix}: {r[0]}"))

        add_loc_suggestions(PhotoMetadata.city, "City")
        if len(suggestions) < 10: add_loc_suggestions(PhotoMetadata.country, "Country")
        if len(suggestions) < 15: add_loc_suggestions(PhotoMetadata.province, "Province")
        if len(suggestions) < 20: add_loc_suggestions(PhotoMetadata.district, "District")
        
        # 3. OCR Text
        ocr_texts = db.query(distinct(OCR.text))\
            .join(Photo, OCR.photo_id == Photo.id)\
            .filter(Photo.owner_id == user.id)\
            .filter(OCR.text.ilike(search_term))\
            .limit(limit).all()
        for t in ocr_texts:
            if t[0]:
                # Truncate long OCR text for display
                display_text = t[0][:30] + "..." if len(t[0]) > 30 else t[0]
                suggestions.append(SearchSuggestion(type="ocr", value=t[0], label=f"Text: {display_text}"))

        # 4. Album Name
        albums = db.query(distinct(Album.name))\
            .filter(Album.owner_id == user.id, Album.name.ilike(search_term))\
            .limit(limit).all()
        for a in albums:
            if a[0]:
                suggestions.append(SearchSuggestion(type="album", value=a[0], label=f"Album: {a[0]}"))

        # 5. Filename
        filenames = db.query(distinct(Photo.filename))\
            .filter(Photo.owner_id == user.id, Photo.filename.ilike(search_term))\
            .limit(limit).all()
        for f in filenames:
            if f[0]:
                 suggestions.append(SearchSuggestion(type="filename", value=f[0], label=f"File: {f[0]}"))

        # 6. Folder (Path)
        paths = db.query(distinct(Photo.file_path))\
            .filter(Photo.owner_id == user.id, Photo.file_path.ilike(search_term))\
            .limit(50).all()
        
        found_folders = set()
        for p in paths:
            if not p[0]: continue
            
            # Normalize separators to /
            normalized_path = p[0].replace('\\', '/')
            folder_path = os.path.dirname(normalized_path)
            folder_name = os.path.basename(folder_path)
            
            if q.lower() in folder_path.lower():
                if folder_path not in found_folders:
                    found_folders.add(folder_path)
                    suggestions.append(SearchSuggestion(type="folder", value=folder_path, label=f"Folder: {folder_name}"))
                    if len(found_folders) >= limit:
                        break

        # 7. Tag
        tags = db.query(distinct(PhotoTag.tag_name))\
            .filter(or_(Scene.owner_id == None, PhotoTag.owner_id == user.id), PhotoTag.tag_name.ilike(search_term))\
            .limit(limit).all()
        for t in tags:
            if t[0]:
                suggestions.append(SearchSuggestion(type="tag", value=t[0], label=f"Tag: {t[0]}"))

        # 8. Scene
        scenes = db.query(distinct(Scene.name))\
            .filter(or_(Scene.owner_id == None, Scene.owner_id == user.id), Scene.name.ilike(search_term))\
            .limit(limit).all()
        for s in scenes:
            if s[0]:
                suggestions.append(SearchSuggestion(type="scene", value=s[0], label=f"Scene: {s[0]}"))

        return BaseResponse(code=200, msg="获取成功", data=suggestions[:20]) # Return top 20 total suggestions

    except Exception as e:
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


def _build_vector_search_response(db, results, threshold):
    """results: List[Tuple[ImageVector, distance]]; 一次批取 Photo，按 threshold 过滤"""
    items = [(v, 1 - d) for v, d in results if (1 - d) >= threshold]
    if not items:
        return []
    photo_ids = [v.photo_id for v, _ in items]
    photos_map = {
        p.id: p for p in app.crud.photo.get_photos_by_ids(db, photo_ids)
    }
    return [
        SearchResult(photo=photos_map[v.photo_id], score=score)
        for v, score in items
        if v.photo_id in photos_map
    ]


@router.post("/text", response_model=BaseResponse[List[SearchResult]])
async def search_by_text(
    request: TextSearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Search photos by text query using vector similarity.
    """
    try:
        if request.type:
            # Metadata Search
            query = db.query(Photo).filter(Photo.owner_id == user.id)

            if request.start_time:
                query = query.filter(Photo.photo_time >= request.start_time)
            if request.end_time:
                query = query.filter(Photo.photo_time <= request.end_time)

            term = f"%{request.text}%"

            if request.type == 'person':
                query = query.join(Photo.faces).join(Face.identity).filter(FaceIdentity.identity_name.ilike(term))
            elif request.type == 'location':
                query = query.join(Photo.metadata_info).filter(
                    or_(
                        PhotoMetadata.city.ilike(term),
                        PhotoMetadata.province.ilike(term),
                        PhotoMetadata.country.ilike(term),
                        PhotoMetadata.district.ilike(term),
                        PhotoMetadata.address.ilike(term)
                    )
                )
            elif request.type == 'ocr':
                query = query.join(OCR, OCR.photo_id == Photo.id).filter(OCR.text.ilike(term))
            elif request.type == 'album':
                query = query.join(Photo.albums).filter(Album.name.ilike(term))
            elif request.type == 'filename':
                query = query.filter(Photo.filename.ilike(term))
            elif request.type == 'folder':
                query = query.filter(Photo.file_path.ilike(term))
            elif request.type == 'tag':
                query = query.join(Photo.tags).filter(PhotoTag.tag_name.ilike(term))
            elif request.type == 'scene':
                query = query.join(Photo.metadata_info).join(Scene).filter(Scene.name.ilike(term))
            
            # Apply limit/skip
            total = query.count() # Optional: if we needed total count
            photos = query.limit(request.limit).offset(request.skip).all()
            
            # Return with score 1.0 for exact matches
            return BaseResponse(code=200, msg="搜索成功", data=[SearchResult(photo=p, score=1.0) for p in photos])

        else:
            # 1. Get Text Embedding from AI Service
            embedding = await async_get_embedding(request.text, user.id, db)

            # 2. Search Vectors
            results = crud_vector.search_similar_vectors(db, embedding, request.limit, request.skip, user_id=user.id)

            # 3. Format Response（批取 Photo，消除原 N+1）
            response = _build_vector_search_response(db, results, request.threshold)
            return BaseResponse(code=200, msg="搜索成功", data=response)

    except Exception as e:
        logging.info(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/image", response_model=BaseResponse[List[SearchResult]])
async def search_by_image(
    file: UploadFile = File(...),
    limit: int = Form(20),
    threshold: float = Form(0.0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Search photos by image query using vector similarity.
    """
    try:
        # 1. Get Image Embedding from AI Service
        # We use /classify endpoint which returns embedding
        async with aiohttp.ClientSession() as session:
            file_content = await file.read()
            form_data = aiohttp.FormData()
            form_data.add_field('file', file_content, filename=file.filename)
            
            api_url = f"{config_manager.get_user_config(user.id, db).ai.ai_api_url}/classification/classify"
            async with session.post(
                api_url,
                data=form_data,
                params={"limit": 1} # We don't care about classification results
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=502, detail=f"AI Service error: {resp.status}")
                result = await resp.json()
                embedding = result.get("embedding")
                if not embedding:
                    raise HTTPException(status_code=500, detail="No embedding returned from AI service")

        # 2. Search Vectors
        results = crud_vector.search_similar_vectors(db, embedding, limit, user_id=user.id)

        # 3. Format Response（批取 Photo，消除原 N+1）
        response = _build_vector_search_response(db, results, threshold)
        return BaseResponse(code=200, msg="搜索成功", data=response)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
