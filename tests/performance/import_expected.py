"""Count logical media before timing, accounting for paired Live Photos."""
import json
from pathlib import Path

from app.service.live_photo import live_photo_service
from app.utils.image_loading import IMAGE_EXTENSIONS

root = Path('/benchmark-photos')
video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
files = [p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in set(IMAGE_EXTENSIONS) | video_extensions]
paired_videos = set()
for image in files:
    if image.suffix.lower() not in {'.heic', '.heif', '.jpg', '.jpeg'}:
        continue
    for video in files:
        if video.suffix.lower() not in {'.mov', '.mp4'} or video.parent != image.parent or video.stem != image.stem:
            continue
        image_id = live_photo_service.get_content_identifier(str(image))
        if image_id and image_id == live_photo_service.get_content_identifier(str(video)):
            paired_videos.add(video)
print(json.dumps({'files': len(files), 'photos': len(files) - len(paired_videos)}))
