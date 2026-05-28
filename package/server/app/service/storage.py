import os
import traceback
import shutil
from uuid import UUID
from typing import Optional
from fastapi import UploadFile
from PIL import Image
from pillow_heif import register_heif_opener
# Register HEIF opener to enable HEIC/HEIF support in Pillow
register_heif_opener()

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.config_manager import config_manager, ImageSettings
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None

# Global cache for storage root (User ID -> Root Path)
_STORAGE_ROOT_CACHE = {}

RAW_EXTENSIONS = {
    '.arw', '.cr2', '.cr3', '.dng', '.nef', '.nrw', '.orf',
    '.pef', '.raf', '.raw', '.rw2', '.srw', '.x3f'
}

def _get_storage_root(user_id: UUID, db: Session = None) -> str:
    try:
        root = './data/uploads'  # Default path
        # Ensure directories exist
        try:
            os.makedirs(root, exist_ok=True)
            os.makedirs(os.path.join(root, 'uploads'), exist_ok=True)
            os.makedirs(os.path.join(root, 'thumbnails'), exist_ok=True)
        except Exception as e:
            logging.error(f"Failed to create directories for {root}: {e}")
        return root
    finally:
        pass


def update_storage_root_cache(user_id: str, new_root: str):
    """Update the global storage root cache for a user and ensure directories exist."""
    global _STORAGE_ROOT_CACHE
    _STORAGE_ROOT_CACHE[user_id] = new_root
    try:
        os.makedirs(new_root, exist_ok=True)
        os.makedirs(os.path.join(new_root, 'uploads'), exist_ok=True)
        os.makedirs(os.path.join(new_root, 'thumbnails'), exist_ok=True)
    except Exception as e:
        logging.error(f"Failed to create directories for {new_root}: {e}")

def _ensure_unique_path(dir_path: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dir_path, filename)
    idx = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dir_path, f"{base}({idx}){ext}")
        idx += 1
    return candidate

def save_upload_file(upload_file: UploadFile, file_id: UUID, user_id: UUID) -> str:
    ext = os.path.splitext(upload_file.filename)[1]
    now = datetime.now()
    year = f"{now.year:04d}"
    month = f"{now.month:02d}"
    root = _get_storage_root(user_id)
    base_dir = os.path.join(root, 'uploads', year, month)
    os.makedirs(base_dir, exist_ok=True)
    target_path = _ensure_unique_path(base_dir, upload_file.filename)
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return target_path

def generate_video_thumbnail(file_path: str, file_id: UUID, user_id: UUID, config: ImageSettings = None):
    if cv2 is None:
        logging.warning("opencv-python not installed, skipping video thumbnail generation")
        return None
    try:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb_frame)
        return _save_thumbnails(img, file_id, user_id, config=config)
    except Exception as e:
        logging.error(f"Error generating video thumbnail for {file_path}: {e}")
    finally:
        del frame
    return None

def _save_thumbnails(img: Image.Image, file_id: UUID, user_id: UUID, config: ImageSettings = None) -> str:
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    compact = str(file_id).replace('-', '')
    p1, p2 = compact[:2], compact[2:4]
    root = _get_storage_root(user_id)
    base = os.path.join(root, 'thumbnails', p1, p2)
    os.makedirs(base, exist_ok=True)
    jm = os.path.join(base, f"{compact}.jpg")
    js = os.path.join(base, f"{compact}-thumb.jpg")
    if os.path.exists(jm):
        os.remove(jm)
    if os.path.exists(js):
        os.remove(js)
    m_path = os.path.join(base, f"{compact}.webp")
    s_path = os.path.join(base, f"{compact}-thumb.webp")

    # Use default config if not provided
    if not config:
        # Get settings
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            config = config_manager.get_user_config(user_id, db).image
        finally:
            db.close()

    t_size = config.thumbnail_size
    p_size = config.preview_size
    t_qual = config.thumbnail_quality
    p_qual = config.preview_quality

    m = img.copy()
    m.thumbnail((p_size, p_size))
    m.save(m_path, "WEBP", quality=p_qual)

    s = img.copy()
    s.thumbnail((t_size, t_size))
    # s.save(s_path, "JPEG", quality=t_qual)
    s.save(s_path, "WEBP", quality=t_qual)
    return m_path

def get_preview_path(user_id: UUID, file_id: UUID) -> Optional[str]:
    """Get the absolute path to the preview image if it exists."""
    compact = str(file_id).replace('-', '')
    p1, p2 = compact[:2], compact[2:4]
    root = _get_storage_root(user_id)
    m_path = os.path.join(root, 'thumbnails', p1, p2, f"{compact}.webp")
    if os.path.exists(m_path):
        return m_path
    else:
        m_path = os.path.join(root, 'thumbnails', p1, p2, f"{compact}.jpg")
        if os.path.exists(m_path):
            return m_path
    return None

def generate_thumbnail(user_id: UUID, file_path: str, file_id: UUID, image_obj: Optional[Image.Image] = None, config: ImageSettings = None):
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.mp4', '.mov', '.avi', '.mkv', '.webm'):
            return generate_video_thumbnail(file_path, file_id, user_id, config=config)
        if ext in ('.png', '.jpg', '.jpeg', '.webp', '.heic'):
            if image_obj:
                return _save_thumbnails(image_obj, file_id, user_id, config=config)
            else:
                with Image.open(file_path) as img:
                    return _save_thumbnails(img, file_id, user_id, config=config)
    except Exception as e:
        logging.error(f"Error generating thumbnail for {file_path}: {e}\n{traceback.format_exc()}")
    return None

def get_file_size(file_path: str) -> int:
    return os.path.getsize(file_path)

def get_image_dimensions(file_path: str, image_obj: Optional[Image.Image] = None):
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.webp', '.heic'):
            if image_obj:
                return image_obj.width, image_obj.height, None
            else:
                with Image.open(file_path) as img:
                    return img.width, img.height, None
        elif ext in ('.mp4', '.mov', '.avi', '.mkv', '.webm'):
            if cv2 is None:
                return None, None, None
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                return None, None, None
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps else 0
            cap.release()
            return width, height, duration
    except:
        pass
    return None, None, None

def delete_thumbnails(user_id: UUID, file_id: UUID):
    try:
        compact = str(file_id).replace('-', '')
        p1, p2 = compact[:2], compact[2:4]
        root = _get_storage_root(user_id)
        base = os.path.join(root, 'thumbnails', p1, p2)
        # 判断webp格式的图片是否存在
        wm = os.path.join(base, f"{compact}.webp")
        ws = os.path.join(base, f"{compact}-thumb.webp")
        if os.path.exists(wm):
            os.remove(wm)
        if os.path.exists(ws):
            os.remove(ws)
        jm = os.path.join(base, f"{compact}.jpg")
        js = os.path.join(base, f"{compact}-thumb.jpg")
        jv = os.path.join(base, f"{compact}.mp4")
        if os.path.exists(jm):
            os.remove(jm)
        if os.path.exists(js):
            os.remove(js)
        if os.path.exists(jv):
            os.remove(jv)
        # 判断base目录是否为空
        if not os.listdir(base):
            os.rmdir(base)
            base = os.path.join(root, 'thumbnails', p1)
            if not os.listdir(base):
                os.rmdir(base)
    except Exception as e:
        logging.error(f"Error deleting thumbnails for {user_id}/{file_id}: {e}")

def get_live_photo_vide(image_path: str) -> Optional[str]:
    try:
        base, ext = os.path.splitext(image_path)
        if ext.lower() in ('.heic', '.heif'):
            video_path = base + '.mov'
            if os.path.exists(video_path):
                return video_path
        elif ext.lower() in ('.jpg', '.jpeg'):
            video_path = base + '.mp4'
            if os.path.exists(video_path):
                return video_path
    except Exception as e:
        logging.error(f"Error getting live photo video for {image_path}: {e}")
    return None

def _raw_candidate_dirs(file_path: str):
    parent = os.path.abspath(os.path.dirname(file_path))
    seen = set()

    def add(path: str):
        path = os.path.abspath(path)
        if path not in seen and os.path.isdir(path):
            seen.add(path)
            yield path

    yield from add(parent)

    def add_raw_dir_with_children(path: str):
        if 'raw' not in os.path.basename(path).lower():
            return
        yield from add(path)
        try:
            for name in os.listdir(path):
                child = os.path.join(path, name)
                if os.path.isdir(child):
                    yield from add(child)
        except OSError as e:
            logging.warning(f"Could not inspect RAW sidecar directory {path}: {e}")

    try:
        for name in os.listdir(parent):
            yield from add_raw_dir_with_children(os.path.join(parent, name))
    except OSError as e:
        logging.warning(f"Could not inspect photo directory {parent}: {e}")

    grandparent = os.path.dirname(parent)
    if grandparent and grandparent != parent:
        try:
            for name in os.listdir(grandparent):
                yield from add_raw_dir_with_children(os.path.join(grandparent, name))
        except OSError as e:
            logging.warning(f"Could not inspect sibling directories for {parent}: {e}")

def delete_raw_sidecars(file_path: str):
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    if ext.lower() in RAW_EXTENSIONS:
        return

    base_name_lower = base_name.lower()
    for directory in _raw_candidate_dirs(file_path):
        try:
            names = os.listdir(directory)
        except OSError as e:
            logging.warning(f"Could not inspect RAW sidecar candidates in {directory}: {e}")
            continue

        for name in names:
            candidate_base, candidate_ext = os.path.splitext(name)
            if candidate_base.lower() == base_name_lower and candidate_ext.lower() in RAW_EXTENSIONS:
                candidate = os.path.join(directory, name)
                try:
                    os.remove(candidate)
                    logging.info(f"Deleted RAW sidecar: {candidate}")
                except OSError as e:
                    logging.error(f"Error deleting RAW sidecar {candidate}: {e}")

def delete_file(user_id: UUID, file_path: str, file_id: UUID, is_live_photo: bool = False):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        if is_live_photo:
            video_path = get_live_photo_vide(file_path)
            if video_path and os.path.exists(video_path):
                os.remove(video_path)
        delete_raw_sidecars(file_path)
        delete_thumbnails(user_id, file_id)
    except Exception as e:
        logging.error(f"Error deleting file {user_id}/{file_path}: {e}")
