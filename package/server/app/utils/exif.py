#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/12/7 23:23
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-exif.py
@Description : 
"""
import shutil
import subprocess
import traceback
from datetime import datetime
import re
import os
from typing import Dict, Any, Optional

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from pillow_heif import register_heif_opener
# Register HEIF opener to enable HEIC/HEIF support in Pillow
register_heif_opener()

import json
import reverse_geocoder as rg

from app.utils.filename import extract_datetime_from_filename

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.tiff', '.webp', '.png', '.heic', '.heif')
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v')

# Helper Functions for Metadata
# resources/rg_data
RG_DIR = os.path.join(os.path.dirname(__file__), '../../resources/rg_data')
if not os.path.exists(RG_DIR):
    os.makedirs(RG_DIR)

def _convert_to_degrees(value):
    """
    Helper function to convert the GPS coordinates stored in the EXIF to degress in float format
    """

    def _to_float(v):
        if isinstance(v, (tuple, list)) and len(v) == 2:
            # Handle (numerator, denominator) tuple
            if v[1] == 0:
                return 0.0
            return float(v[0]) / float(v[1])
        try:
            # Handle IFDRational or simple numbers
            return float(v)
        except (TypeError, ValueError):
            # Fallback for IFDRational in some PIL versions if it doesn't cast directly
            if hasattr(v, 'numerator') and hasattr(v, 'denominator'):
                if v.denominator == 0:
                    return 0.0
                return float(v.numerator) / float(v.denominator)
            return 0.0

    d = _to_float(value[0])
    m = _to_float(value[1])
    s = _to_float(value[2])
    return d + (m / 60.0) + (s / 3600.0)


def get_gps_info(exif_data: Dict[str, Any]) -> Optional[Dict[str, float]]:
    if 'GPSInfo' not in exif_data:
        return None

    gps_info = exif_data['GPSInfo']

    lat = None
    lng = None

    if 'GPSLatitude' in gps_info and 'GPSLatitudeRef' in gps_info:
        lat = _convert_to_degrees(gps_info['GPSLatitude'])
        if gps_info['GPSLatitudeRef'] != 'N':
            lat = -lat

    if 'GPSLongitude' in gps_info and 'GPSLongitudeRef' in gps_info:
        lng = _convert_to_degrees(gps_info['GPSLongitude'])
        if gps_info['GPSLongitudeRef'] != 'E':
            lng = -lng

    if lat is not None and lng is not None:
        return {"latitude": lat, "longitude": lng}
    return None


def get_exif_data(image: Image.Image) -> Dict[str, Any]:
    exif_data = {}
    
    # 尝试使用新的 getexif() 和 get_ifd() API (Pillow 8.2.0+)
    if hasattr(image, 'getexif'):
        info = image.getexif()
        if info:
            # 1. 提取顶层标签 (IFD0)
            for tag, value in info.items():
                decoded = TAGS.get(tag, tag)
                if decoded not in ["GPSInfo", "ExifOffset"]:
                    if isinstance(value, (bytes, bytearray)):
                        try:
                            exif_data[decoded] = value.decode()
                        except:
                            exif_data[decoded] = str(value)
                    else:
                        exif_data[decoded] = value
            
            # 2. 提取 Exif IFD (0x8769) 包含 DateTimeOriginal 等
            try:
                exif_ifd = info.get_ifd(0x8769)
                if exif_ifd:
                    for tag, value in exif_ifd.items():
                        decoded = TAGS.get(tag, tag)
                        if isinstance(value, (bytes, bytearray)):
                            try:
                                exif_data[decoded] = value.decode()
                            except:
                                exif_data[decoded] = str(value)
                        else:
                            exif_data[decoded] = value
            except Exception:
                pass
            
            # 3. 提取 GPS IFD (0x8825)
            try:
                gps_ifd = info.get_ifd(0x8825)
                if gps_ifd:
                    gps_data = {}
                    for t, value in gps_ifd.items():
                        sub_decoded = GPSTAGS.get(t, t)
                        gps_data[sub_decoded] = value
                    exif_data["GPSInfo"] = gps_data
            except Exception:
                pass
            
            if exif_data:
                return exif_data

    # 如果没有取到，或者方法不支持，回退使用 _getexif()
    info = getattr(image, '_getexif', lambda: None)()
    if info:
        for tag, value in info.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                gps_data = {}
                if isinstance(value, dict):
                    for t in value:
                        sub_decoded = GPSTAGS.get(t, t)
                        gps_data[sub_decoded] = value[t]
                    exif_data[decoded] = gps_data
            else:
                # Filter out binary data or non-serializable stuff if needed
                if isinstance(value, (bytes, bytearray)):
                    try:
                        exif_data[decoded] = value.decode()
                    except:
                        exif_data[decoded] = str(value)
                else:
                    exif_data[decoded] = value
    return exif_data

def get_file_time_form_system(file_path: str) -> datetime:
    """
    Get the file modification time from the system.
    """
    try:
        stat = os.stat(file_path)
        return datetime.fromtimestamp(stat.st_mtime)
    except OSError:
        return datetime.now()


def parse_datetime_value(value: Any) -> Optional[datetime]:
    if not value:
        return None

    if isinstance(value, (bytes, bytearray)):
        value = value.decode(errors="ignore")

    value = str(value).strip().replace("\x00", "")
    formats = (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S%z",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    return None


def extract_datetime_from_exif(exif_data: Dict[str, Any]) -> tuple[Optional[datetime], Optional[str]]:
    for tag_name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
        dt = parse_datetime_value(exif_data.get(tag_name))
        if dt:
            return dt, f"exif:{tag_name}"
    return None, None


def _date_from_short_token(text: str) -> Optional[datetime]:
    match = re.search(r"(?<!\d)([0-4]\d)([01]\d)([0-3]\d)(?!\d)", text)
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return datetime(2000 + int(year), int(month), int(day))
    except ValueError:
        return None


def _date_from_month_day(text: str, year: Optional[int]) -> Optional[datetime]:
    if not year:
        return None
    match = re.search(r"(?<!\d)([01]?\d)[月_ .\-]([0-3]?\d)(?!\d)", text)
    if not match:
        return None
    month, day = match.groups()
    try:
        return datetime(year, int(month), int(day))
    except ValueError:
        return None


def extract_datetime_from_path(file_path: str) -> Optional[datetime]:
    """
    Recover a coarse capture date from dated folders, e.g. 20250227,
    2024-3-28, 211004..., or 2020.09.13/.../9.15.
    """
    inherited_year = None
    best_dt = None
    directory = os.path.dirname(file_path)
    for part in [p for p in directory.split(os.sep) if p]:
        dt = extract_datetime_from_filename(part) or _date_from_short_token(part)
        if dt:
            inherited_year = dt.year
            best_dt = dt
            continue

        month_day_dt = _date_from_month_day(part, inherited_year)
        if month_day_dt:
            best_dt = month_day_dt

    return best_dt


def extract_datetime_from_video_metadata(file_path: str) -> Optional[datetime]:
    if not shutil.which("ffprobe"):
        return None

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_entries",
                "format_tags=creation_time:stream_tags=creation_time",
                file_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=12,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        data = json.loads(result.stdout)
        creation_values = []
        for stream in data.get("streams") or []:
            creation_values.append((stream.get("tags") or {}).get("creation_time"))
        creation_values.append(((data.get("format") or {}).get("tags") or {}).get("creation_time"))

        for value in creation_values:
            if not value:
                continue
            normalized = str(value).strip()
            if normalized.endswith(("Z", "z")):
                normalized = normalized[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo:
                    dt = dt.astimezone().replace(tzinfo=None)
                return dt
            except ValueError:
                continue
    except Exception:
        return None

    return None


def extract_metadata(file_path: str, filename: str, image_obj: Optional[Image.Image] = None, extract_location_details: bool = True) -> Dict[str, Any]:
    """
    Extracts photo_time, exif_info, and location from the file.
    Priority:
    1. EXIF DateTimeOriginal / DateTimeDigitized / DateTime
    2. Video metadata creation_time if ffprobe is available
    3. Filename date
    4. Folder date
    5. File modification time
    6. Current time
    """
    metadata = {
        "photo_time": None,
        "photo_time_source": None,
        "exif_info": None,
        "location": None,
        "width": None,
        "height": None
    }

    # 1. Try EXIF
    try:
        if file_path.lower().endswith(IMAGE_EXTENSIONS):
            exif_dict = None
            img = None
            should_close = False
            
            if image_obj:
                img = image_obj
            else:
                img = Image.open(file_path)
                should_close = True
            
            try:
                metadata["width"] = img.width
                metadata["height"] = img.height
                exif_dict = get_exif_data(img)
            finally:
                if should_close:
                    img.close()

            if exif_dict:

                metadata["exif_info"] = exif_dict

                # Extract Date
                photo_time, source = extract_datetime_from_exif(exif_dict)
                if photo_time:
                    metadata["photo_time"] = photo_time
                    metadata["photo_time_source"] = source

                # Extract GPS
                gps = get_gps_info(exif_dict)
                metadata["location"] = gps
                if gps and extract_location_details:
                    try:
                        results = rg.search([(gps["latitude"], gps["longitude"])], mode=1, data_dir=RG_DIR)
                        if results:
                            res = results[0]
                            district = res.get("admin_3", "")
                            name = res.get("admin_4","")
                            if name == "":
                                name = res.get("name","")
                            metadata["location_details"] = {
                                "latitude": gps["latitude"],
                                "longitude": gps["longitude"],
                                "district": district,
                                "city": res.get("admin_2", ""),
                                "province": res.get("admin_1", ""),
                                "country": res.get("country", ""),
                                "address": f"{res.get('admin_1', '')}{res.get('admin_2', '')}{district}{name}"
                            }
                    except Exception as e:
                        print(f"Reverse geocoding error: {e}")

    except Exception as e:
        print(traceback.format_exc())
        print(f"Error extracting metadata: {e}")

    # 2. If photo_time is still None, try video container metadata
    if metadata["photo_time"] is None and file_path.lower().endswith(VIDEO_EXTENSIONS):
        try:
            photo_time = extract_datetime_from_video_metadata(file_path)
            if photo_time:
                metadata["photo_time"] = photo_time
                metadata["photo_time_source"] = "video_metadata:creation_time"
        except Exception:
            pass

    # 3. If photo_time is still None, try Filename
    if metadata["photo_time"] is None:
        try:
            photo_time = extract_datetime_from_filename(filename)
            if photo_time:
                metadata["photo_time"] = photo_time
                metadata["photo_time_source"] = "filename"
        except Exception:
            pass

    # 4. If photo_time is still None, try dated folders
    if metadata["photo_time"] is None:
        try:
            photo_time = extract_datetime_from_path(file_path)
            if photo_time:
                metadata["photo_time"] = photo_time
                metadata["photo_time_source"] = "path"
        except Exception:
            pass

    # 5. Fallback to filesystem mtime
    if metadata["photo_time"] is None:
        photo_time = get_file_time_form_system(file_path)
        metadata["photo_time"] = photo_time
        metadata["photo_time_source"] = "file_mtime"

    # 6. Fallback to current time
    if metadata["photo_time"] is None:
        metadata["photo_time"] = datetime.now()
        metadata["photo_time_source"] = "now"

    return metadata
