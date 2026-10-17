"""Validated GPano metadata; image shape alone never opts a photo into 360 mode."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Any

NAMESPACE = "{http://ns.google.com/photos/1.0/panorama/}"
MAX_XMP_BYTES = 2 * 1024 * 1024
DIMENSIONS = {
    "fullWidth": "FullPanoWidthPixels", "fullHeight": "FullPanoHeightPixels",
    "croppedWidth": "CroppedAreaImageWidthPixels", "croppedHeight": "CroppedAreaImageHeightPixels",
    "croppedX": "CroppedAreaLeftPixels", "croppedY": "CroppedAreaTopPixels",
}


def validate_geometry(data: dict[str, Any], width: int, height: int) -> dict:
    result = {}
    for key in DIMENSIONS:
        value = data[key]
        if isinstance(value, bool) or not str(value).isdigit():
            raise ValueError("全景尺寸必须是整数")
        result[key] = int(value)
    fw, fh = result["fullWidth"], result["fullHeight"]
    cw, ch = result["croppedWidth"], result["croppedHeight"]
    x, y = result["croppedX"], result["croppedY"]
    if not (0 < fw <= 100000 and 0 < fh <= 50000 and fw == 2 * fh):
        raise ValueError("完整全景画布必须为2:1")
    if cw != width or ch != height or cw <= 0 or ch <= 0 or x + cw > fw or y + ch > fh:
        raise ValueError("全景裁剪区域与图片尺寸不匹配")
    for key in ("poseHeading", "posePitch", "poseRoll", "initialHeading", "initialPitch", "initialFov"):
        if key in data:
            value = float(data[key])
            if not math.isfinite(value):
                raise ValueError("全景角度无效")
            if key in ("posePitch", "initialPitch") and not -90 <= value <= 90:
                raise ValueError("全景角度超出范围")
            if key == "poseRoll" and not -180 <= value <= 180:
                raise ValueError("全景横滚角超出范围")
            if key == "initialFov" and not 1 <= value <= 179:
                raise ValueError("全景视野超出范围")
            result[key] = value
    return result


def parse_gpano(xmp: bytes | str | None, width: int, height: int, orientation: int = 1) -> dict | None:
    if not xmp or len(xmp) > MAX_XMP_BYTES or orientation != 1:
        return None
    raw = xmp.encode() if isinstance(xmp, str) else xmp
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        return None
    try:
        root = ET.fromstring(raw)
        values = {}
        for element in root.iter():
            if element.tag.startswith(NAMESPACE) and element.text:
                values[element.tag[len(NAMESPACE):]] = element.text.strip()
            values.update({k[len(NAMESPACE):]: v.strip() for k, v in element.attrib.items() if k.startswith(NAMESPACE)})
        if values.get("ProjectionType", "").lower() != "equirectangular":
            return None
        if values.get("UsePanoramaViewer", "true").lower() in ("false", "0"):
            return None
        geometry = {key: values[tag] for key, tag in DIMENSIONS.items()}
        for key, tag in {"poseHeading": "PoseHeadingDegrees", "posePitch": "PosePitchDegrees",
                         "poseRoll": "PoseRollDegrees", "initialHeading": "InitialViewHeadingDegrees",
                         "initialPitch": "InitialViewPitchDegrees", "initialFov": "InitialHorizontalFOVDegrees"}.items():
            if tag in values:
                geometry[key] = values[tag]
        return validate_geometry(geometry, width, height)
    except (ET.ParseError, ValueError, KeyError, TypeError, OverflowError):
        return None


def full_geometry(width: int, height: int) -> dict:
    return validate_geometry(dict(fullWidth=width, fullHeight=height, croppedWidth=width,
                                  croppedHeight=height, croppedX=0, croppedY=0), width, height)


def scaled_geometry(data: dict, width: int, height: int) -> dict:
    """PSV coordinates describe the actual texture, including its cropped canvas."""
    sx, sy = width / data["croppedWidth"], height / data["croppedHeight"]
    return {key: round(value * (sx if key in ("fullWidth", "croppedWidth", "croppedX") else sy))
            if key in DIMENSIONS else value for key, value in data.items()}


def apply_detection(photo, data: dict | None) -> None:
    """Keep the automatic result separate so manual decisions survive reprocessing."""
    photo.panorama_detected = data
    if data:
        photo.width, photo.height = data["croppedWidth"], data["croppedHeight"]
    if not photo.panorama_override:
        photo.panorama_metadata = data
        photo.panorama_projection = "equirectangular" if data else None
