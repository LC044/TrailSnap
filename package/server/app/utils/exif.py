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
from app.utils import video_meta
from app.core.paths import RG_DATA_DIR as RG_DIR

# 图片扩展名白名单（Pillow + pillow-heif 可解码的范围）
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.tiff', '.webp', '.png', '.heic', '.heif')

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


def reverse_geocode(lat: float, lng: float) -> dict:
    try:
        results = rg.search([(lat, lng)], mode=1, data_dir=RG_DIR)
        if results:
            res = results[0]
            district = res.get("admin_3", "")
            name = res.get("admin_4", "")
            if name == "":
                name = res.get("name", "")
            return {
                "district": district,
                "city": res.get("admin_2", ""),
                "province": res.get("admin_1", ""),
                "country": res.get("country", ""),
                "address": f"{res.get('admin_1', '')}{res.get('admin_2', '')}{district}{name}"
            }
    except Exception as e:
        print(f"Reverse geocoding error: {e}")
    return {}


def _attach_location_details(metadata: Dict[str, Any], gps: Optional[Dict[str, float]],
                             extract_location_details: bool) -> None:
    """把 GPS 写入 metadata，并按需补上逆地理编码结果。

    图片与视频两条分支共用，保证视频的位置信息也能进入 city/province/scene 链路。
    """
    metadata["location"] = gps
    if not (gps and extract_location_details):
        return
    loc = reverse_geocode(gps["latitude"], gps["longitude"])
    if loc:
        loc["latitude"] = gps["latitude"]
        loc["longitude"] = gps["longitude"]
        metadata["location_details"] = loc


def extract_metadata(file_path: str, filename: str, image_obj: Optional[Image.Image] = None, extract_location_details: bool = True) -> Dict[str, Any]:
    """
    Extracts photo_time, exif_info, and location from the file.

    图片走 EXIF，视频走 ISO BMFF (MP4/MOV) 的 moov/udta/meta 解析，两者写入同一份
    metadata 结构，因此下游的时间回退、逆地理编码、入库映射全部共用。

    Priority:
    1. EXIF DateTimeOriginal（图片） / CreateDate 或 mvhd creation_time（视频）
    2. Filename (YYYYMMDD_HHMMSS or YYYYMMDD)
    3. File mtime
    4. Current Time
    """
    metadata = {
        "photo_time": None,
        "exif_info": None,
        "location": None,
        "width": None,
        "height": None
    }

    # 1. Try EXIF (image) / container metadata (video)
    try:
        lower_path = file_path.lower()
        if lower_path.endswith(IMAGE_EXTENSIONS):
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

                # Extract Date (DateTimeOriginal)
                date_str = exif_dict.get("DateTimeOriginal")
                if date_str:
                    try:
                        metadata["photo_time"] = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
                    except ValueError:
                        pass

                # Extract GPS
                _attach_location_details(metadata, get_gps_info(exif_dict), extract_location_details)

        elif video_meta.is_video_file(file_path):
            # AVI/MKV/WEBM 不是 ISO BMFF，extract_video_metadata 会返回空结果，
            # 此时自然落到下面的文件名 / mtime 回退。
            v_meta = video_meta.extract_video_metadata(file_path)

            if v_meta.get("video_info"):
                metadata["exif_info"] = v_meta["video_info"]
            if v_meta.get("video_time"):
                metadata["photo_time"] = v_meta["video_time"]
            if v_meta.get("width"):
                metadata["width"] = v_meta["width"]
            if v_meta.get("height"):
                metadata["height"] = v_meta["height"]
            for key in ("duration", "fps", "codec", "rotation"):
                if v_meta.get(key) is not None:
                    metadata[key] = v_meta[key]

            _attach_location_details(metadata, v_meta.get("location"), extract_location_details)

    except Exception as e:
        print(traceback.format_exc())
        print(f"Error extracting metadata: {e}")

    # 2. If photo_time is still None, try Filename
    if metadata["photo_time"] is None:
        try:
            photo_time = extract_datetime_from_filename(filename)
            if photo_time:
                metadata["photo_time"] = photo_time
            else:
                photo_time = get_file_time_form_system(file_path)
                metadata["photo_time"] = photo_time
        except Exception:
            pass

    # 3. Fallback to current time
    if metadata["photo_time"] is None:
        metadata["photo_time"] = datetime.now()

    return metadata

