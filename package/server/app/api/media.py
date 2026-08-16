import json
import os
import shutil
import uuid
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status, Form, UploadFile, File, Query
from fastapi.responses import FileResponse, StreamingResponse, Response
from starlette.concurrency import run_in_threadpool
import anyio
import base64
from sqlalchemy.orm import Session

from app.crud.photo import save_and_create_photo
from app.db.models.task import TaskType
from app.dependencies import get_db
from app.db.models.photo import Photo
from app.service import storage
from app.service.storage import _get_storage_root
from app.crud import album as crud_album
from app.crud import face as crud_face

from app.schemas import photo as schemas
from app.core.paths import BUNDLE_ROOT
from app.service.task_manager import TaskManager
from app.api.deps import get_current_user
from app.db.models.user import User

router = APIRouter()


def _geojson_path(level_cn: str) -> str:
    """Resolve bundled GeoJSON independently of the process working directory."""
    return os.path.join(BUNDLE_ROOT, "resources", "geo_data", f"中国_{level_cn}.geojson")


def _get_thumbnail_path(user_id: UUID, photo_id: UUID, db: Session, size: str = 'small') -> str:
    compact = str(photo_id).replace('-', '')
    p1, p2 = compact[:2], compact[2:4]
    root = _get_storage_root(user_id, db)
    base = os.path.join(root, 'thumbnails', p1, p2)
    
    if size == 'small':
        webp = os.path.join(base, f"{compact}-thumb.webp")
        if os.path.exists(webp):
            return webp
        else:
            return os.path.join(base, f"{compact}-thumb.jpg")
    else:
        webp = os.path.join(base, f"{compact}.webp")
        if os.path.exists(webp):
            return webp
        else:
            return os.path.join(base, f"{compact}.jpg")

@router.get('/{photo_id}/video')
async def get_live_photo_video(
    photo_id: UUID,
    request: Request,
    range: str = Header(None),
    db: Session = Depends(get_db)
):
    photo = await run_in_threadpool(lambda: db.query(Photo).filter(Photo.id == photo_id).first())
    if not photo:
        raise HTTPException(status_code=404, detail="Video file not found")

    # Live photo 视频按约定生成在 thumbnail 目录下，与缩略图同名但扩展名为 .mp4
    # （见 tasks/basic.py 的 motion_photo.extract_video）。用 splitext 去掉缩略图后缀
    # 再拼 .mp4，避免对 .webp（5 字符）做 [:-4] 切片导致多出一个点。
    thumb_path = await run_in_threadpool(_get_thumbnail_path, photo.owner_id, photo_id, db, 'medium')
    file_path = os.path.splitext(thumb_path)[0] + '.mp4'

    ext = os.path.splitext(photo.file_path)[1].lower()
    if ext in ('.jpg', 'jpeg'):
        file_path = os.path.splitext(photo.file_path)[0] + '.mp4'
        exists = await run_in_threadpool(os.path.exists, file_path)
        if not exists:
            file_path = os.path.splitext(photo.file_path)[0] + '.mov'
            exists = await run_in_threadpool(os.path.exists, file_path)
            if not exists:
                thumb_path = await run_in_threadpool(_get_thumbnail_path, photo.owner_id, photo_id, db, 'medium')
                file_path = os.path.splitext(thumb_path)[0] + '.mp4'
    else:
        file_path = os.path.splitext(photo.file_path)[0] + '.MOV'

    file_size = await run_in_threadpool(os.path.getsize, file_path)

    # Determine media type (usually mp4 or mov)
    ext = os.path.splitext(file_path)[1].lower()
    media_type = f"video/{ext.lstrip('.')}"
    if ext == '.mov': media_type = "video/quicktime"

    # Handle Range header
    if range:
        try:
            start, end = range.replace("bytes=", "").split("-")
            start = int(start)
            end = int(end) if end else file_size - 1
            
            if start >= file_size:
                 # Requesting past end of file
                 headers = {"Content-Range": f"bytes */{file_size}"}
                 return Response(status_code=416, headers=headers)

            chunk_size = end - start + 1
            buffer_size = 1024 * 1024 # 1MB buffer

            async def iterfile():
                async with await anyio.open_file(file_path, "rb") as f:
                    await f.seek(start)
                    bytes_read = 0
                    while bytes_read < chunk_size:
                        # Read in larger chunks for better performance
                        read_size = min(buffer_size, chunk_size - bytes_read)
                        chunk = await f.read(read_size)
                        if not chunk:
                            break
                        bytes_read += len(chunk)
                        yield chunk
            
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": media_type,
            }
            
            return StreamingResponse(iterfile(), status_code=206, headers=headers, media_type=media_type)
        except ValueError:
            pass # Fallback to full content if range parse fails

    # Full content
    return FileResponse(file_path, media_type=media_type, headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=31536000"})

@router.get('/{photo_id}/thumbnail')
async def get_thumbnail(photo_id: UUID, size: str = 'small', format: str = 'file', db: Session = Depends(get_db)):
    photo = await run_in_threadpool(lambda: db.query(Photo).filter(Photo.id == photo_id).first())
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    path = await run_in_threadpool(_get_thumbnail_path, photo.owner_id, photo_id, db, size)
    exists = await run_in_threadpool(os.path.exists, path)
    if not exists:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    if format == 'file':
        return FileResponse(path, media_type="image/webp" if path.endswith('.webp') else "image/jpeg", headers={"Cache-Control": "public, max-age=31536000"})
    elif format == 'base64':
        with open(path, "rb") as f:
            thumbnail_base64 = base64.b64encode(f.read()).decode("utf-8")
        return {"base64": thumbnail_base64}

    raise HTTPException(status_code=400, detail="Invalid format. Use 'file' or 'base64'")

@router.get('/{photo_id}/file')
async def get_media_file(
    photo_id: UUID,
    request: Request,
    range: str = Header(None),
    db: Session = Depends(get_db)
):
    photo = await run_in_threadpool(lambda: db.query(Photo).filter(Photo.id == photo_id).first())
    if not photo:
        raise HTTPException(status_code=404, detail="File not found")
        
    exists = await run_in_threadpool(os.path.exists, photo.file_path)
    if not exists:
        raise HTTPException(status_code=404, detail="File not found")
        
    file_path = photo.file_path
    # Determine media type
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.heic':
        file_path = _get_thumbnail_path(photo.owner_id, photo_id, db, 'medium')
    file_size = await run_in_threadpool(os.path.getsize, file_path)

    media_type = "application/octet-stream"
    if ext in ('.png', '.jpg', '.jpeg', '.webp', '.tiff', '.gif'):
        media_type = f"image/{ext.lstrip('.')}"
        if ext == '.jpg': media_type = "image/jpeg"
    elif ext in ('.mp4', '.mov', '.avi', '.mkv', '.webm'):
        media_type = f"video/{ext.lstrip('.')}"
        if ext == '.mov': media_type = "video/quicktime"
        if ext == '.mkv': media_type = "video/x-matroska"

    # Handle Range header
    if range:
        try:
            start, end = range.replace("bytes=", "").split("-")
            start = int(start)
            end = int(end) if end else file_size - 1
            
            if start >= file_size:
                 # Requesting past end of file
                 headers = {"Content-Range": f"bytes */{file_size}"}
                 return Response(status_code=416, headers=headers)

            chunk_size = end - start + 1
            buffer_size = 1 * 1024 * 1024 # 1MB buffer
            
            async def iterfile():
                async with await anyio.open_file(file_path, "rb") as f:
                    await f.seek(start)
                    bytes_read = 0
                    while bytes_read < chunk_size:
                        # Read in larger chunks for better performance
                        read_size = min(buffer_size, chunk_size - bytes_read)
                        chunk = await f.read(read_size)
                        if not chunk:
                            break
                        bytes_read += len(chunk)
                        yield chunk
            
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": media_type,
            }
            
            return StreamingResponse(iterfile(), status_code=206, headers=headers, media_type=media_type)
        except ValueError:
            pass # Fallback to full content if range parse fails

    # Full content
    return FileResponse(file_path, media_type=media_type, headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=31536000"})

def add_tasks(db: Session, user_id: UUID, photo_id: UUID, file_path: str):
    TaskManager.get_instance().add_tasks(db, [
        {
            'type': TaskType.PROCESS_BASIC,
            'payload': {'photo_id': str(photo_id), 'file_path': file_path, 'user_id': str(user_id)}
        }
    ], owner_id=user_id)

@router.post("", response_model=schemas.Photo)
async def upload_photo_generic(
        album_id: Optional[UUID] = Form(None),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if album_id:
        # Verify album exists
        db_album = await run_in_threadpool(crud_album.get_album, db, album_id=album_id, user_id=current_user.id)
        if not db_album:
            raise HTTPException(status_code=404, detail="Album not found")

    # Generate ID
    photo_id = uuid.uuid4()
    # Save file
    file_path = await run_in_threadpool(storage.save_upload_file, file, photo_id, current_user.id)
    # Create and Save
    photo = await run_in_threadpool(save_and_create_photo, db, file_path, file.filename, album_id, photo_id, user_id=current_user.id)
    # Add tasks
    await run_in_threadpool(add_tasks, db, current_user.id, photo_id, file_path)

    return photo

# Chunked Upload Endpoints

@router.post("/upload/init")
async def init_upload():
    upload_id = uuid.uuid4()
    upload_dir = os.path.join("uploads", "chunks", str(upload_id))
    await run_in_threadpool(os.makedirs, upload_dir, exist_ok=True)
    return {"upload_id": upload_id}


@router.post("/upload/chunk")
async def upload_chunk(
    upload_id: UUID = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...)
):
    chunk_dir = os.path.join("uploads", "chunks", str(upload_id))
    exists = await run_in_threadpool(os.path.exists, chunk_dir)
    if not exists:
        raise HTTPException(status_code=404, detail="Upload session not found")

    chunk_path = os.path.join(chunk_dir, str(chunk_index))
    def save_chunk():
        with open(chunk_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    await run_in_threadpool(save_chunk)
    return {"status": "success"}


@router.post("/upload/finish", response_model=schemas.Photo)
async def finish_upload_generic(
        upload_id: UUID = Form(...),
        file_name: str = Form(...),
        album_id: Optional[UUID] = Form(None),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if album_id:
        # Verify album exists
        db_album = await run_in_threadpool(crud_album.get_album, db, album_id=album_id, user_id=current_user.id)
        if not db_album:
            raise HTTPException(status_code=404, detail="Album not found")

    # Merge chunks
    chunk_dir = os.path.join("uploads", "chunks", str(upload_id))
    exists = await run_in_threadpool(os.path.exists, chunk_dir)
    if not exists:
        raise HTTPException(status_code=404, detail="Upload session not found")

    def get_chunks():
        return sorted([int(f) for f in os.listdir(chunk_dir) if f.isdigit()])
        
    chunks = await run_in_threadpool(get_chunks)
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks found")

    photo_id = uuid.uuid4()
    ext = os.path.splitext(file_name)[1]
    # Save to storage_root/year/month with conflict resolution
    
    def merge_and_save():
        class _Tmp:
            filename = file_name
            file = None

        merged_path = os.path.join("uploads", "chunks", str(upload_id), "merged")
        with open(merged_path, "wb") as outfile:
            for chunk_idx in chunks:
                chunk_path = os.path.join(chunk_dir, str(chunk_idx))
                with open(chunk_path, "rb") as infile:
                    outfile.write(infile.read())
        with open(merged_path, "rb") as merged:
            _Tmp.file = merged
            final_path = storage.save_upload_file(_Tmp, photo_id, current_user.id)

        # Clean up chunks
        shutil.rmtree(chunk_dir)
        return final_path
        
    final_path = await run_in_threadpool(merge_and_save)

    # Create and Save
    photo = await run_in_threadpool(save_and_create_photo, db, final_path, file_name, album_id, photo_id, user_id=current_user.id)

    # Add tasks
    await run_in_threadpool(add_tasks, db, current_user.id, photo_id, final_path)

    return photo

@router.get('/geojson')
async def get_geojson(level: str = Query("city"), parent: Optional[str] = Query(None)):
    if level not in ["province", "city", "district"]:
        raise HTTPException(status_code=400, detail="Invalid level. Must be province, city, or district.")
    try:
        level_cn = {"province": "省", "city": "市", "district": "县"}[level]
        path = _geojson_path(level_cn)
        exists = await run_in_threadpool(os.path.exists, path)
        if not exists:
            raise FileNotFoundError

        if parent and level in ["city", "district"]:
            # Load parent level to find its gb code
            # For district level, the parent is usually a city.
            # But for municipalities (Beijing, Shanghai, etc.), the parent might be considered a province.
            # We will search in both province and city geojson to find the parent.
            parent_gb = None
            
            def get_short(name):
                for suffix in ['省', '市', '自治区', '特别行政区', '回族自治区', '壮族自治区', '维吾尔自治区', '自治州', '地区', '盟', '县', '区', '自治县']:
                    if name.endswith(suffix):
                        name = name[:-len(suffix)]
                return name
                
            def clean_name(n):
                n = get_short(n)
                for s in ['藏族', '彝族', '苗族', '土家族', '蒙古族', '回族', '壮族', '维吾尔族', '哈萨克族', '朝鲜族', '满族', '瑶族', '白族', '布依族', '侗族', '水族', '傣族', '黎族', '傈僳族', '佤族', '畲族', '高山族', '拉祜族', '族']:
                    n = n.replace(s, '')
                return n

            # Pass 1: Exact match or short match
            for parent_level in ["省", "市"]:
                parent_path = _geojson_path(parent_level)
                if os.path.exists(parent_path):
                    with open(parent_path, 'r', encoding='utf-8') as f:
                        parent_data = json.load(f)
                    
                    for feature in parent_data.get('features', []):
                        props = feature.get('properties', {})
                        name = props.get('name', '')
                        if not name: continue
                        if name == parent or get_short(name) == get_short(parent):
                            parent_gb = props.get('gb')
                            break
                if parent_gb:
                    break
                    
            # Pass 2: Clean match (if exact match fails)
            if not parent_gb:
                for parent_level in ["省", "市"]:
                    parent_path = _geojson_path(parent_level)
                    if os.path.exists(parent_path):
                        with open(parent_path, 'r', encoding='utf-8') as f:
                            parent_data = json.load(f)
                        
                        for feature in parent_data.get('features', []):
                            props = feature.get('properties', {})
                            name = props.get('name', '')
                            if not name: continue
                            if clean_name(name) == clean_name(parent):
                                parent_gb = props.get('gb')
                                break
                    if parent_gb:
                        break

            if parent_gb:
                if parent_gb.endswith('0000'):
                    prefix_len = 5
                elif parent_gb.endswith('00'):
                    prefix_len = 7
                else:
                    prefix_len = len(parent_gb)
                
                prefix = parent_gb[:prefix_len]
                
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                filtered_features = []
                for feature in data.get('features', []):
                    gb = feature.get('properties', {}).get('gb', '')
                    if gb.startswith(prefix):
                        filtered_features.append(feature)
                
                data['features'] = filtered_features
                return Response(content=json.dumps(data), media_type="application/geo+json", headers={"Cache-Control": "public, max-age=31536000"})

        return FileResponse(path, media_type="application/geo+json", headers={"Cache-Control": "public, max-age=31536000"})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"GeoJSON file for {level} not found.")
