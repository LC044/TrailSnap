"""Deterministic, silent one-second rendering for both preview and export."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont, ImageOps
from sqlalchemy import update

from app.core.paths import BUNDLE_ROOT, DATA_DIR

logger = logging.getLogger(__name__)


class RenderCancelled(Exception):
    pass


def ffmpeg_path() -> str | None:
    configured = os.environ.get("TS_FFMPEG_PATH")
    return shutil.which(configured or "ffmpeg")


def ffprobe_path() -> str | None:
    ffmpeg = ffmpeg_path()
    if ffmpeg:
        adjacent = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if adjacent.is_file():
            return str(adjacent)
    return shutil.which("ffprobe")


def font_path() -> str | None:
    candidates = [os.environ.get("TS_VIDEO_FONT"),
                  str(Path(BUNDLE_ROOT, "resources", "fonts", "NotoSansCJK-Regular.ttc")),
                  str(Path(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "msyh.ttc")),
                  "/System/Library/Fonts/PingFang.ttc",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]
    return next((path for path in candidates if path and os.path.isfile(path)), None)


@lru_cache(maxsize=1)
def capabilities() -> dict:
    if not ffmpeg_path() or not ffprobe_path():
        return {"available": False, "reason": "当前实例未安装 FFmpeg/FFprobe，暂不支持影片生成；仍可选择每日瞬间。"}
    path = font_path()
    if not path:
        return {"available": False, "reason": "当前实例缺少中文字体，安装 Noto Sans CJK 或配置 TS_VIDEO_FONT 后重启服务。"}
    try:
        ImageFont.truetype(path, 32)
        encoders = subprocess.run([ffmpeg_path(), "-hide_banner", "-encoders"], capture_output=True,
                                  timeout=10, check=True, **process_options()).stdout
        if b"libx264" not in encoders:
            return {"available": False, "reason": "当前 FFmpeg 不支持 H.264 编码，请安装包含 libx264 的版本。"}
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "reason": "当前实例的影片编码器或中文字体无法使用，请检查配置。"}
    return {"available": True, "reason": None}


def process_options() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def probe_duration(path: str) -> float | None:
    probe = ffprobe_path()
    if not probe:
        # OpenCV is already part of the desktop runtime; selecting clips remains
        # possible even when the optional export tools have not been installed.
        try:
            import cv2
            capture = cv2.VideoCapture(path)
            try:
                fps = capture.get(cv2.CAP_PROP_FPS)
                frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
                return frames / fps if fps > 0 and frames > 0 else None
            finally:
                capture.release()
        except Exception:
            return None
    try:
        result = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=duration:format=duration", "-of", "json", path],
                                capture_output=True, timeout=15, check=True, **process_options())
        info = json.loads(result.stdout)
        values = [s.get("duration") for s in info.get("streams", [])] + [info.get("format", {}).get("duration")]
        import math
        for value in values:
            try:
                duration = float(value)
                if math.isfinite(duration) and duration > 0:
                    return duration
            except (TypeError, ValueError):
                continue
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def output_root(owner_id: UUID) -> Path:
    # Anchor works to stable per-user application data, independent of external gallery paths.
    root = Path(DATA_DIR, "users", str(owner_id), "daily-frame")
    root.mkdir(parents=True, exist_ok=True)
    return root


def remove_output(owner_id: UUID, output: str) -> None:
    target, root = Path(output).resolve(), output_root(owner_id).resolve()
    if target.parent != root or target.suffix != ".mp4":
        logger.warning("Refusing unexpected daily-frame output path")
        return
    target.unlink(missing_ok=True)
    target.with_suffix(".jpg").unlink(missing_ok=True)


def dimensions(settings: dict) -> tuple[int, int]:
    return (1080, 1920) if settings["orientation"] == "portrait" else (1920, 1080)


def make_overlay(item: dict, settings: dict) -> Image.Image:
    width, height = dimensions(settings)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    lines = []
    if settings["show_date"]:
        lines.append(item["day"].replace("-", "."))
    caption = item["caption"] if settings["show_caption"] else ""
    size = 42
    font = ImageFont.truetype(font_path(), size)
    current = ""
    for char in caption:
        if current and draw.textlength(current + char, font=font) > width * 0.8:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    if not lines:
        return overlay
    # Maximum 30 characters produce at most two caption lines at these dimensions.
    line_height = 60
    bottom = height - round(height * 0.07)
    top = bottom - len(lines) * line_height - 24
    margin = round(width * 0.07)
    draw.rounded_rectangle((margin, top, width - margin, bottom), radius=18, fill=(0, 0, 0, 170))
    y = top + 12
    for line in lines:
        draw.text((width / 2, y), line, font=font, anchor="mt", fill="white")
        y += line_height
    return overlay


def compose_still(path: str, item: dict, settings: dict, destination: Path) -> None:
    width, height = dimensions(settings)
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
        if settings["fit"] == "cover":
            image = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
        else:
            image.thumbnail((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), settings["background"])
        canvas.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
        canvas.alpha_composite(make_overlay(item, settings))
        canvas.convert("RGB").save(destination)


def run_encoder(args: list[str], working: Path, check_cancelled, timeout: int = 180) -> None:
    started = time.monotonic()
    # stderr may exceed a pipe buffer for malformed videos. A file cannot deadlock.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args],
                                   cwd=working, stdout=subprocess.DEVNULL, stderr=errors, **process_options())
        try:
            while process.poll() is None:
                check_cancelled()
                if time.monotonic() - started > timeout:
                    raise RuntimeError("素材处理超时，请更换素材后重试")
                time.sleep(0.3)
            if process.returncode:
                errors.seek(0)
                logger.error("Daily-frame encoder failed: %s", errors.read(4000).decode("utf-8", errors="replace"))
                raise RuntimeError("素材无法解码，请更换素材后重试")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def encode_segment(path: str, item: dict, settings: dict, temporary: Path,
                   index: int, preview: bool, check_cancelled) -> Path:
    width, height = dimensions(settings)
    destination = temporary / f"{index:04d}.mp4"
    preview_scale = ",scale=360:640" if preview and width < height else ",scale=640:360" if preview else ""
    output_args = ["-an", "-frames:v", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)]
    if item["mode"] == "still":
        still = temporary / "still.png"
        try:
            compose_still(path, item, settings, still)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise RuntimeError("照片无法解码，请更换素材后重试") from exc
        run_encoder(["-loop", "1", "-framerate", "30", "-i", str(still), "-vf", "setsar=1" + preview_scale,
                     *output_args], temporary, check_cancelled)
    else:
        duration = probe_duration(path)
        if duration is None or item["start_seconds"] > max(0, duration - 1) + 0.001:
            raise RuntimeError("动态素材时长已变化，请重新选择片段")
        overlay = temporary / "overlay.png"
        make_overlay(item, settings).save(overlay)
        if settings["fit"] == "cover":
            fitting = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        else:
            fitting = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                       f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={settings['background']}")
        filters = (f"[0:v]{fitting},setsar=1,fps=30,tpad=stop_mode=clone:stop_duration=1[base];"
                   f"[base][1:v]overlay=0:0,trim=duration=1,setpts=PTS-STARTPTS{preview_scale}[out]")
        run_encoder(["-ss", str(item["start_seconds"]), "-i", path, "-i", str(overlay),
                     "-filter_complex_threads", "1", "-filter_complex", filters, "-map", "[out]", *output_args],
                    temporary, check_cancelled)
    return destination


def render_work(work_id: UUID, generation: int, task_id: UUID) -> dict:
    from app.db.models.daily_frame import DailyFrameWork
    from app.db.models.task import Task
    from app.db.session import SessionLocal
    from app.service.daily_frame import owned_photo, source_path

    with SessionLocal() as db:
        work = db.get(DailyFrameWork, work_id)
        if (work is None or work.generation != generation or work.task_id != task_id or work.deleted_at
                or work.status not in ("queued", "processing")):
            raise RenderCancelled()
        owner_id, snapshot, preview = work.owner_id, work.snapshot, work.is_preview
        changed = db.execute(update(DailyFrameWork).where(DailyFrameWork.id == work_id,
            DailyFrameWork.generation == generation, DailyFrameWork.status.in_(["queued", "processing"]),
            DailyFrameWork.deleted_at.is_(None)).values(status="processing", error=None, processed_items=0))
        if changed.rowcount != 1:
            raise RenderCancelled()
        db.commit()
    root = output_root(owner_id)
    output = root / f"{work_id}-{generation}.mp4"
    published = False

    def check_cancelled():
        with SessionLocal() as current:
            row = current.get(DailyFrameWork, work_id)
            task = current.get(Task, task_id)
            if (not row or row.deleted_at or row.generation != generation or row.task_id != task_id
                    or row.status not in ("queued", "processing") or not task or task.status not in ("pending", "processing")):
                raise RenderCancelled()

    try:
        check_cancelled()
        with tempfile.TemporaryDirectory(prefix="render-", dir=root) as folder:
            temporary = Path(folder)
            for index, item in enumerate(snapshot["frames"]):
                check_cancelled()
                with SessionLocal() as current:
                    photo = owned_photo(current, owner_id, UUID(item["photo_id"]))
                    path, reason = source_path(photo, item["mode"])
                if reason:
                    raise RuntimeError(f"{item['day']}：{reason}")
                try:
                    encode_segment(path, item, snapshot["settings"], temporary, index, preview, check_cancelled)
                except RuntimeError as exc:
                    raise RuntimeError(f"{item['day']}：{exc}") from exc
                with SessionLocal() as current:
                    current.execute(update(DailyFrameWork).where(DailyFrameWork.id == work_id,
                                    DailyFrameWork.generation == generation, DailyFrameWork.task_id == task_id)
                                    .values(processed_items=index + 1))
                    current.execute(update(Task).where(Task.id == task_id).values(processed_items=index + 1))
                    current.commit()
            playlist = temporary / "segments.txt"
            playlist.write_text("".join(f"file '{i:04d}.mp4'\n" for i in range(len(snapshot["frames"]))), encoding="utf-8")
            run_encoder(["-f", "concat", "-safe", "1", "-i", str(playlist), "-c", "copy", "-movflags", "+faststart",
                         str(temporary / "result.mp4")], temporary, check_cancelled)
            run_encoder(["-i", str(temporary / "0000.mp4"), "-frames:v", "1", "-vf", "scale=480:-2",
                         str(temporary / "poster.jpg")], temporary, check_cancelled)
            check_cancelled()
            # Revalidate every source immediately before publishing. The work row
            # lock fences cancellation/deletion and retries while the file is moved.
            with SessionLocal() as current:
                row = current.query(DailyFrameWork).filter_by(id=work_id).with_for_update().first()
                if (not row or row.deleted_at or row.generation != generation or row.task_id != task_id
                        or row.status != "processing"):
                    raise RenderCancelled()
                for item in snapshot["frames"]:
                    photo = owned_photo(current, owner_id, UUID(item["photo_id"]))
                    reason = source_path(photo, item["mode"])[1]
                    if reason:
                        raise RuntimeError(f"{item['day']}：{reason}")
                # SQLite also needs a write lock before the final state check.
                changed = current.execute(update(DailyFrameWork).where(DailyFrameWork.id == work_id,
                    DailyFrameWork.generation == generation, DailyFrameWork.task_id == task_id,
                    DailyFrameWork.status == "processing", DailyFrameWork.deleted_at.is_(None))
                    .values(status="ready", output_path=str(output)))
                if changed.rowcount != 1:
                    raise RenderCancelled()
                os.replace(temporary / "result.mp4", output)
                os.replace(temporary / "poster.jpg", output.with_suffix(".jpg"))
                current.commit()
                published = True
        return {"work_id": str(work_id), "duration": len(snapshot["frames"])}
    except RenderCancelled:
        raise
    except Exception as exc:
        with SessionLocal() as current:
            current.execute(update(DailyFrameWork).where(DailyFrameWork.id == work_id,
                DailyFrameWork.generation == generation, DailyFrameWork.task_id == task_id,
                DailyFrameWork.status.in_(["queued", "processing"]))
                .values(status="failed", error=str(exc) if isinstance(exc, RuntimeError) else "生成失败，请检查素材后重试"))
            current.commit()
        raise
    finally:
        if not published:
            remove_output(owner_id, str(output))
