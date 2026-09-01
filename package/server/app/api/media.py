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
from sqlalchemy.exc import IntegrityError

from app.crud.photo import save_and_create_photo
from app.crud import photo as crud_photo
from app.db.models.task import TaskType
from app.dependencies import get_db, BaseResponse
from app.db.models.photo import FileType, Photo
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


def _existing_backup_photo(db: Session, user_id: UUID, backup_key: Optional[str]):
    if not backup_key:
        return None
    return db.query(Photo).filter(
        Photo.owner_id == user_id,
        Photo.backup_key == backup_key,
    ).first()


@router.post('/backup/check', response_model=BaseResponse[dict])
def check_mobile_backup_assets(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    keys = payload.get("keys") if isinstance(payload, dict) else None
    if not isinstance(keys, list) or len(keys) > 200 or any(not isinstance(key, str) for key in keys):
        raise HTTPException(status_code=400, detail="keys must be a string array with at most 200 items")
    normalized = list(dict.fromkeys(key[:255] for key in keys if key))
    if not normalized:
        return BaseResponse.success(data={"existing": []})
    rows = db.query(Photo.backup_key).filter(
        Photo.owner_id == current_user.id,
        Photo.backup_key.in_(normalized),
    ).all()
    return BaseResponse.success(data={"existing": [row[0] for row in rows]})


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


def _upload_root(user_id: UUID, db: Session) -> str:
    return os.path.join(_get_storage_root(user_id, db), "uploads")


def _chunk_dir(user_id: UUID, upload_id: UUID, db: Session) -> str:
    return os.path.join(_get_storage_root(user_id, db), "chunks", str(upload_id))


@router.get('/folders', response_model=BaseResponse[dict])
def list_upload_folders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return internal upload folders and configured external directories."""
    root = _upload_root(current_user.id, db)
    os.makedirs(root, exist_ok=True)
    folders = []
    for current, dir_names, _ in os.walk(root):
        dir_names.sort(key=str.lower)
        relative = os.path.relpath(current, root)
        if relative != '.':
            folders.append(relative.replace('\\', '/'))

    external_folders: set[str] = set()
    for external_root in storage.get_external_upload_roots(current_user.id, db):
        if not os.path.isdir(external_root):
            continue
        for current, dir_names, _ in os.walk(external_root):
            dir_names.sort(key=str.lower)
            if storage._path_is_within(external_root, current):
                external_folders.add(os.path.abspath(current))

    return BaseResponse.success(data={
        "folders": folders,
        "external_folders": sorted(external_folders, key=str.lower),
    })


@router.post('/folders', response_model=BaseResponse[dict])
def create_upload_folder(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        folder = storage._validate_upload_folder(payload.get("path"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid folder path") from exc
    if not folder:
        raise HTTPException(status_code=400, detail="Folder path is required")
    path = os.path.abspath(os.path.join(_upload_root(current_user.id, db), *folder.split('/')))
    root = os.path.abspath(_upload_root(current_user.id, db))
    if os.path.commonpath((root, path)) != root:
        raise HTTPException(status_code=400, detail="Invalid folder path")
    os.makedirs(path, exist_ok=True)
    return BaseResponse.success(data={"path": folder})

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
    if ext in ('.jpg', '.jpeg'):
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

def add_tasks(db: Session, user_id: UUID, photo_id: UUID, file_path: str, live_photo_video_path: Optional[str] = None):
    payload = {'photo_id': str(photo_id), 'file_path': file_path, 'user_id': str(user_id)}
    if live_photo_video_path:
        payload.update({'is_live_photo': True, 'live_photo_video_path': live_photo_video_path})
    TaskManager.get_instance().add_tasks(db, [
        {
            'type': TaskType.PROCESS_BASIC,
            'payload': payload
        }
    ], owner_id=user_id)


def _live_photo_video_path(image_path: str, video_name: str) -> str:
    image_ext = os.path.splitext(image_path)[1].lower()
    video_ext = os.path.splitext(video_name)[1].lower()
    if image_ext not in ('.jpg', '.jpeg', '.heic', '.heif'):
        raise ValueError("Unsupported live photo image type")
    if video_ext not in ('.mp4', '.mov'):
        raise ValueError("Unsupported live photo video type")
    expected_ext = '.MOV' if image_ext in ('.heic', '.heif') else video_ext
    return os.path.splitext(image_path)[0] + expected_ext


def _attach_live_photo_video(
    db: Session,
    image_photo: Photo,
    video: UploadFile,
    companion_backup_key: Optional[str],
    user_id: UUID,
) -> str:
    image_stem = os.path.splitext(image_photo.filename or os.path.basename(image_photo.file_path))[0].casefold()
    video_stem = os.path.splitext(video.filename or '')[0].casefold()
    if not video_stem or image_stem != video_stem:
        raise ValueError("Live photo image and video names must match")
    target_path = _live_photo_video_path(image_photo.file_path, video.filename or 'live.mov')
    companion = _existing_backup_photo(db, user_id, companion_backup_key)

    # Always write the submitted companion. It was opened with
    # MediaStore.setRequireOriginal(), while a previously stored file may be a
    # redacted/transcoded MediaStore stream even when it already has this path.
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    storage.validate_target_path(target_path)
    temporary_path = target_path + f'.{uuid.uuid4().hex}.uploading'
    storage.validate_target_path(temporary_path)
    try:
        with open(temporary_path, 'wb') as output:
            shutil.copyfileobj(video.file, output)
        os.replace(temporary_path, target_path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)

    image_photo.file_type = FileType.live_photo
    db.commit()
    db.refresh(image_photo)

    if companion and companion.id != image_photo.id:
        same_file = os.path.normcase(os.path.abspath(companion.file_path)) == os.path.normcase(os.path.abspath(target_path))
        crud_photo.delete_photo(db, companion.id, is_delete_file=not same_file, user_id=user_id)
    return target_path


def _finalize_backup_file_replacement(db: Session, photo: Photo, temporary_path: str, user_id: UUID) -> Photo:
    target_path = photo.file_path
    storage.validate_target_path(target_path)
    os.replace(temporary_path, target_path)
    storage.delete_thumbnails(user_id, photo.id)
    storage.generate_thumbnail(user_id, target_path, photo.id)
    width, height, duration = storage.get_image_dimensions(target_path)
    photo.size = storage.get_file_size(target_path)
    if width is not None:
        photo.width = width
    if height is not None:
        photo.height = height
    if duration is not None:
        photo.duration = duration
    processed = dict(photo.processed_tasks or {})
    processed['metadata'] = False
    photo.processed_tasks = processed
    db.commit()
    db.refresh(photo)
    return photo


def _replace_backup_file(db: Session, photo: Photo, upload: UploadFile, user_id: UUID) -> Photo:
    temporary_path = photo.file_path + f'.{uuid.uuid4().hex}.original-upload'
    storage.validate_target_path(temporary_path)
    try:
        with open(temporary_path, 'wb') as output:
            shutil.copyfileobj(upload.file, output)
        return _finalize_backup_file_replacement(db, photo, temporary_path, user_id)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def _replace_backup_file_from_chunks(
    db: Session, photo: Photo, chunk_dir: str, chunks: list[int], user_id: UUID
) -> Photo:
    temporary_path = photo.file_path + f'.{uuid.uuid4().hex}.original-upload'
    storage.validate_target_path(temporary_path)
    try:
        with open(temporary_path, 'wb') as output:
            for chunk_index in chunks:
                with open(os.path.join(chunk_dir, str(chunk_index)), 'rb') as source:
                    shutil.copyfileobj(source, output)
        return _finalize_backup_file_replacement(db, photo, temporary_path, user_id)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        shutil.rmtree(chunk_dir, ignore_errors=True)

@router.post("", response_model=schemas.Photo)
async def upload_photo_generic(
        album_id: Optional[UUID] = Form(None),
        folder: Optional[str] = Form(None),
        backup_key: Optional[str] = Form(None),
        companion_backup_key: Optional[str] = Form(None),
        live_photo_video: Optional[UploadFile] = File(None),
        replace_existing: bool = Form(False),
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if not isinstance(live_photo_video, UploadFile):
        live_photo_video = None
    if not isinstance(companion_backup_key, str):
        companion_backup_key = None
    if not isinstance(replace_existing, bool):
        replace_existing = False
    if not isinstance(backup_key, str):
        backup_key = None
    if backup_key and len(backup_key) > 255:
        raise HTTPException(status_code=400, detail="backup_key is too long")
    if live_photo_video:
        image_stem, image_ext = os.path.splitext(file.filename or '')
        video_stem, video_ext = os.path.splitext(live_photo_video.filename or '')
        valid_pair = (
            image_stem.casefold() == video_stem.casefold()
            and image_ext.lower() in ('.jpg', '.jpeg', '.heic', '.heif')
            and video_ext.lower() in ('.mp4', '.mov')
        )
        if not valid_pair:
            raise HTTPException(status_code=400, detail="Invalid live photo pair")
    existing = await run_in_threadpool(_existing_backup_photo, db, current_user.id, backup_key)
    if existing:
        if replace_existing:
            existing = await run_in_threadpool(_replace_backup_file, db, existing, file, current_user.id)
        if live_photo_video:
            await run_in_threadpool(
                _attach_live_photo_video, db, existing, live_photo_video, companion_backup_key, current_user.id
            )
        if replace_existing:
            await run_in_threadpool(
                add_tasks, db, current_user.id, existing.id, existing.file_path,
                _live_photo_video_path(existing.file_path, live_photo_video.filename) if live_photo_video else None,
            )
        return existing
    if album_id:
        # Verify album exists
        db_album = await run_in_threadpool(crud_album.get_album, db, album_id=album_id, user_id=current_user.id)
        if not db_album:
            raise HTTPException(status_code=404, detail="Album not found")

    # Generate ID
    photo_id = uuid.uuid4()
    # Save file
    try:
        file_path = await run_in_threadpool(storage.save_upload_file, file, photo_id, current_user.id, folder, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Create and Save
    live_photo_video_path = None
    try:
        photo = await run_in_threadpool(save_and_create_photo, db, file_path, file.filename, album_id, photo_id, user_id=current_user.id, backup_key=backup_key)
        if live_photo_video:
            live_photo_video_path = await run_in_threadpool(
                _attach_live_photo_video, db, photo, live_photo_video, companion_backup_key, current_user.id
            )
    except IntegrityError:
        await run_in_threadpool(db.rollback)
        existing = await run_in_threadpool(_existing_backup_photo, db, current_user.id, backup_key)
        if not existing:
            raise
        await run_in_threadpool(os.remove, file_path)
        return existing
    # Add tasks
    await run_in_threadpool(add_tasks, db, current_user.id, photo_id, file_path, live_photo_video_path)

    return photo

# Chunked Upload Endpoints

@router.post("/upload/init")
async def init_upload(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    upload_id = uuid.uuid4()
    upload_dir = _chunk_dir(current_user.id, upload_id, db)
    await run_in_threadpool(os.makedirs, upload_dir, exist_ok=True)
    return {"upload_id": upload_id}


@router.post("/upload/chunk")
async def upload_chunk(
    upload_id: UUID = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chunk_dir = _chunk_dir(current_user.id, upload_id, db)
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
        folder: Optional[str] = Form(None),
        backup_key: Optional[str] = Form(None),
        companion_backup_key: Optional[str] = Form(None),
        live_photo_video: Optional[UploadFile] = File(None),
        replace_existing: bool = Form(False),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if not isinstance(live_photo_video, UploadFile):
        live_photo_video = None
    if not isinstance(companion_backup_key, str):
        companion_backup_key = None
    if not isinstance(replace_existing, bool):
        replace_existing = False
    if not isinstance(backup_key, str):
        backup_key = None
    if backup_key and len(backup_key) > 255:
        raise HTTPException(status_code=400, detail="backup_key is too long")
    if live_photo_video:
        image_stem, image_ext = os.path.splitext(file_name or '')
        video_stem, video_ext = os.path.splitext(live_photo_video.filename or '')
        if not (
            image_stem.casefold() == video_stem.casefold()
            and image_ext.lower() in ('.jpg', '.jpeg', '.heic', '.heif')
            and video_ext.lower() in ('.mp4', '.mov')
        ):
            raise HTTPException(status_code=400, detail="Invalid live photo pair")
    existing = await run_in_threadpool(_existing_backup_photo, db, current_user.id, backup_key)
    if existing:
        if replace_existing:
            chunk_dir = _chunk_dir(current_user.id, upload_id, db)
            exists = await run_in_threadpool(os.path.exists, chunk_dir)
            if not exists:
                raise HTTPException(status_code=404, detail="Upload session not found")
            chunks = await run_in_threadpool(
                lambda: sorted([int(name) for name in os.listdir(chunk_dir) if name.isdigit()])
            )
            if not chunks:
                raise HTTPException(status_code=400, detail="No chunks found")
            existing = await run_in_threadpool(
                _replace_backup_file_from_chunks, db, existing, chunk_dir, chunks, current_user.id
            )
        if live_photo_video:
            await run_in_threadpool(
                _attach_live_photo_video, db, existing, live_photo_video, companion_backup_key, current_user.id
            )
        if replace_existing:
            await run_in_threadpool(
                add_tasks, db, current_user.id, existing.id, existing.file_path,
                _live_photo_video_path(existing.file_path, live_photo_video.filename) if live_photo_video else None,
            )
        else:
            await run_in_threadpool(shutil.rmtree, _chunk_dir(current_user.id, upload_id, db), True)
        return existing
    if album_id:
        # Verify album exists
        db_album = await run_in_threadpool(crud_album.get_album, db, album_id=album_id, user_id=current_user.id)
        if not db_album:
            raise HTTPException(status_code=404, detail="Album not found")

    # Merge chunks
    chunk_dir = _chunk_dir(current_user.id, upload_id, db)
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

        merged_path = os.path.join(chunk_dir, "merged")
        with open(merged_path, "wb") as outfile:
            for chunk_idx in chunks:
                chunk_path = os.path.join(chunk_dir, str(chunk_idx))
                with open(chunk_path, "rb") as infile:
                    outfile.write(infile.read())
        with open(merged_path, "rb") as merged:
            _Tmp.file = merged
            final_path = storage.save_upload_file(_Tmp, photo_id, current_user.id, folder, db)

        # Clean up chunks
        shutil.rmtree(chunk_dir)
        return final_path
        
    try:
        final_path = await run_in_threadpool(merge_and_save)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Create and Save
    live_photo_video_path = None
    try:
        photo = await run_in_threadpool(save_and_create_photo, db, final_path, file_name, album_id, photo_id, user_id=current_user.id, backup_key=backup_key)
        if live_photo_video:
            live_photo_video_path = await run_in_threadpool(
                _attach_live_photo_video, db, photo, live_photo_video, companion_backup_key, current_user.id
            )
    except IntegrityError:
        await run_in_threadpool(db.rollback)
        existing = await run_in_threadpool(_existing_backup_photo, db, current_user.id, backup_key)
        if not existing:
            raise
        await run_in_threadpool(os.remove, final_path)
        return existing

    # Add tasks
    await run_in_threadpool(add_tasks, db, current_user.id, photo_id, final_path, live_photo_video_path)

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
