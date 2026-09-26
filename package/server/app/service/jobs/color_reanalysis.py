"""Gradually refresh photo colors after the extraction algorithm changes."""

import logging
from datetime import datetime, timedelta, timezone

from PIL import Image
from sqlalchemy import or_

from app.db.models.photo import Photo
from app.db.models.photo_color import PhotoColor
from app.db.session import SessionLocal
from app.service import storage
from app.utils.color import CURRENT_COLOR_ANALYSIS_VERSION, extract_color_info

logger = logging.getLogger(__name__)


def reanalyze_color_batch(batch_size: int = 100) -> dict[str, int]:
    """Process a bounded batch; stale failures become eligible again tomorrow."""
    now = datetime.now(timezone.utc)
    retry_before = now - timedelta(days=1)
    processed = 0
    failed = 0
    with SessionLocal() as db:
        try:
            query = db.query(PhotoColor, Photo).join(Photo, PhotoColor.photo_id == Photo.id).filter(
                PhotoColor.analysis_version < CURRENT_COLOR_ANALYSIS_VERSION,
                Photo.is_deleted == False,
                or_(PhotoColor.analysis_attempted_at == None, PhotoColor.analysis_attempted_at < retry_before),
            ).order_by(PhotoColor.id).limit(batch_size)
            if db.bind.dialect.name == 'postgresql':
                query = query.with_for_update(of=PhotoColor, skip_locked=True)
            rows = query.all()
            for color, photo in rows:
                color.analysis_attempted_at = now
                try:
                    path = storage.get_available_photo_path(photo.owner_id, photo.id, photo.file_path)
                    if not path:
                        failed += 1
                        continue
                    with Image.open(path) as image:
                        info = extract_color_info(image)
                    if not info['dominant_colors']:
                        failed += 1
                        continue
                    color.dominant_colors = info['dominant_colors']
                    color.brightness = info['brightness']
                    color.saturation = info['saturation']
                    color.emotion_hint = info['emotion_hint']
                    color.analysis_version = CURRENT_COLOR_ANALYSIS_VERSION
                    processed += 1
                except Exception as exc:
                    failed += 1
                    logger.warning('Color reanalysis failed for photo %s: %s', photo.id, exc)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception('Color reanalysis batch failed')
            return {'processed': 0, 'failed': 0}
    if processed or failed:
        logger.info('Color reanalysis batch: processed=%d failed=%d', processed, failed)
    return {'processed': processed, 'failed': failed}
