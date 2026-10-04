"""FFmpeg-backed video reading for container runtimes without OpenCV."""
from io import BytesIO
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from PIL import Image


def _tool(name: str) -> str:
    encoder = shutil.which(os.environ.get('TS_FFMPEG_PATH') or 'ffmpeg')
    if encoder:
        adjacent = Path(encoder).with_name(name + ('.exe' if os.name == 'nt' else ''))
        if adjacent.is_file():
            return str(adjacent)
    executable = shutil.which(name)
    if not executable:
        raise FileNotFoundError(f'{name} is unavailable')
    return executable


def _run(name: str, args: list[str]) -> bytes:
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    return subprocess.check_output([_tool(name), *args], stderr=subprocess.DEVNULL, timeout=15, **options)


def probe_video(path: str) -> tuple[int | None, int | None, float | None]:
    doc = json.loads(_run('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=width,height,duration:stream_side_data=rotation:stream_tags=rotate:format=duration', '-of', 'json', path]))
    stream = next(iter(doc.get('streams', [])), {})
    duration = None
    for value in [stream.get('duration'), doc.get('format', {}).get('duration')]:
        try:
            candidate = float(value)
            if math.isfinite(candidate) and candidate >= 0:
                duration = candidate
                break
        except (ValueError, TypeError):
            pass
    width, height = stream.get('width'), stream.get('height')
    rotation = next((entry['rotation'] for entry in stream.get('side_data_list', []) if 'rotation' in entry),
                    stream.get('tags', {}).get('rotate', 0))
    try:
        if abs(float(rotation)) % 180 == 90:
            width, height = height, width
    except (TypeError, ValueError):
        pass
    return width, height, duration


def extract_video_frame(path: str, second: float) -> Image.Image | None:
    # Return raw pixels, avoiding an additional lossy compression before WebP.
    try:
        pixels = _run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-nostdin', '-ss', str(second),
            '-i', path, '-map', '0:v:0', '-frames:v', '1', '-an', '-f', 'image2pipe', '-c:v', 'png', '-'])
        if pixels:
            with Image.open(BytesIO(pixels)) as image:
                return image.convert('RGB')
    except (OSError, subprocess.SubprocessError):
        # Other seek positions can still produce a usable thumbnail.
        return None
    return None
