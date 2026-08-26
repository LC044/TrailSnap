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
from app.service import user_storage
from app.utils.path_validation import validate_target_path
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None

# Global cache for storage root (User ID -> Root Path)
_STORAGE_ROOT_CACHE = {}

def _get_storage_root(user_id: UUID, db: Session = None) -> str:
    base = user_storage.get_cached_storage_base(user_id)
    if base is None and db is not None:
        try:
            from app.db.models.user import User
            user = db.query(User).filter(User.id == user_id).first()
            base = user_storage.configured_storage_base(user.settings if user else None)
        except Exception as e:
            logging.warning("Failed to read storage root for user %s: %s", user_id, e)
    base = user_storage.cache_storage_base(user_id, base or user_storage.DEFAULT_STORAGE_BASE)
    return user_storage.ensure_user_layout(user_id, base)


def update_storage_root_cache(user_id: str, new_root: str):
    """Update the global storage root cache for a user and ensure directories exist."""
    global _STORAGE_ROOT_CACHE
    normalized = os.path.abspath(new_root)
    # Worker payloads historically carry _get_storage_root() while settings
    # updates carry the configured base. Accept both without nesting users twice.
    if os.path.basename(normalized) == str(user_id) and os.path.basename(os.path.dirname(normalized)) == 'users':
        storage_base = os.path.dirname(os.path.dirname(normalized))
    else:
        storage_base = normalized
    _STORAGE_ROOT_CACHE[str(user_id)] = storage_base
    user_storage.cache_storage_base(user_id, storage_base)
    try:
        user_storage.ensure_user_layout(user_id, storage_base)
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

def _validate_upload_folder(folder: Optional[str]) -> Optional[str]:
    if folder is None or not folder.strip():
        return None
    normalized = folder.replace('\\', '/').strip('/')
    if not normalized or normalized == '.':
        return None
    if os.path.isabs(folder) or any(part in ('', '.', '..') for part in normalized.split('/')):
        raise ValueError("Invalid upload folder")
    return normalized


def get_external_upload_roots(user_id: UUID, db: Session = None) -> list[str]:
    """Return normalized external gallery roots configured for this user."""
    if db is None:
        return []
    try:
        config = config_manager.get_user_config(user_id, db)
        roots = config.storage.external_directories or []
    except Exception as exc:
        logging.warning("Failed to read external upload roots for user %s: %s", user_id, exc)
        return []
    return [os.path.abspath(os.path.expanduser(path)) for path in roots if path]


def _path_is_within(root: str, candidate: str) -> bool:
    try:
        normalized_root = os.path.normcase(os.path.realpath(root))
        normalized_candidate = os.path.normcase(os.path.realpath(candidate))
        return os.path.commonpath((normalized_root, normalized_candidate)) == normalized_root
    except ValueError:
        return False


def _resolve_upload_directory(user_id: UUID, folder: Optional[str], db: Session = None) -> str:
    if folder and os.path.isabs(folder):
        candidate = os.path.abspath(os.path.expanduser(folder))
        if not any(_path_is_within(root, candidate) for root in get_external_upload_roots(user_id, db)):
            raise ValueError("Upload directory is not in the configured external galleries")
        return candidate

    now = datetime.now()
    relative_folder = _validate_upload_folder(folder)
    components = relative_folder.split('/') if relative_folder else (f"{now.year:04d}", f"{now.month:02d}")
    root = _get_storage_root(user_id, db) if db is not None else _get_storage_root(user_id)
    return os.path.join(root, 'uploads', *components)


def save_upload_file(upload_file: UploadFile, file_id: UUID, user_id: UUID, folder: Optional[str] = None, db: Session = None) -> str:
    base_dir = _resolve_upload_directory(user_id, folder, db)
    os.makedirs(base_dir, exist_ok=True)
    target_path = _ensure_unique_path(base_dir, upload_file.filename)
    validate_target_path(target_path)
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return target_path

def _video_thumbnail_candidate_seconds(duration: float) -> list[float]:
    """Return ordered, unique seek positions for automatic video thumbnailing."""
    if duration <= 0:
        return [0.0]

    positions = [
        0.0,
        min(0.5, duration * 0.05),
        min(1.0, duration * 0.1),
        duration * 0.25,
        duration * 0.5,
    ]
    upper_bound = max(0.0, duration - 0.05)
    unique_positions = []
    for position in positions:
        position = round(min(max(position, 0.0), upper_bound), 3)
        if position not in unique_positions:
            unique_positions.append(position)
    return unique_positions


def _score_video_thumbnail_frame(frame) -> float:
    """Score a decoded frame and reject near-black or near-white blank frames."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return float("-inf")

    pixels = frame.astype(np.float32)
    gray = pixels.mean(axis=2) if pixels.ndim == 3 else pixels
    brightness = float(gray.mean())
    dark_ratio = float(np.mean(gray < 16))
    light_ratio = float(np.mean(gray > 245))

    if brightness < 12 or brightness > 250 or dark_ratio > 0.9 or light_ratio > 0.95:
        return float("-inf")

    contrast = float(gray.std())
    horizontal_edges = float(np.abs(np.diff(gray, axis=1)).mean()) if gray.shape[1] > 1 else 0.0
    vertical_edges = float(np.abs(np.diff(gray, axis=0)).mean()) if gray.shape[0] > 1 else 0.0
    balanced_brightness = min(brightness, 255.0 - brightness)
    return contrast + horizontal_edges + vertical_edges + balanced_brightness * 0.1


def generate_video_thumbnail(file_path: str, file_id: UUID, user_id: UUID, config: ImageSettings = None):
    if cv2 is None:
        logging.warning("opencv-python not installed, skipping video thumbnail generation")
        return None
    cap = None
    try:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0

        best_frame = None
        fallback_frame = None
        best_score = float("-inf")
        for second in _video_thumbnail_candidate_seconds(duration):
            cap.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            if fallback_frame is None:
                fallback_frame = frame.copy()
            score = _score_video_thumbnail_frame(frame)
            if score > best_score:
                best_score = score
                best_frame = frame.copy()

        selected_frame = best_frame if best_frame is not None else fallback_frame
        if selected_frame is None:
            return None
        rgb_frame = cv2.cvtColor(selected_frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb_frame)
        return _save_thumbnails(img, file_id, user_id, config=config)
    except Exception as e:
        logging.error(f"Error generating video thumbnail for {file_path}: {e}")
    finally:
        if cap is not None:
            cap.release()
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


def get_available_photo_path(user_id: UUID, file_id: UUID, original_path: Optional[str]) -> Optional[str]:
    """Return an existing preview path, falling back to the original photo."""
    preview_path = get_preview_path(user_id, file_id)
    if preview_path and os.path.exists(preview_path):
        return preview_path
    if original_path and os.path.exists(original_path):
        return original_path
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

def delete_file(user_id: UUID, file_path: str, file_id: UUID, is_live_photo: bool = False):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        if is_live_photo:
            video_path = get_live_photo_vide(file_path)
            if video_path and os.path.exists(video_path):
                os.remove(video_path)
        delete_thumbnails(user_id, file_id)
    except Exception as e:
        logging.error(f"Error deleting file {user_id}/{file_path}: {e}")
