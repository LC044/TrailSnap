import os
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

# Template variables that depend on PhotoMetadata. Callers can use this to
# decide whether a metadata lookup is needed at all (e.g. skip it for plain
# `IMG_{date}_{time}` templates).
METADATA_VARS = {"city", "location", "camera", "lens", "iso"}

# Characters not allowed in filenames on Windows/POSIX — scrubbed from any
# substituted value so a metadata field can never produce an invalid name.
_INVALID_FN_CHARS = '/\\:*?"<>|'


def _sanitize(value: Any) -> str:
    """Coerce a value to a filesystem-safe filename fragment."""
    s = str(value)
    for ch in _INVALID_FN_CHARS:
        s = s.replace(ch, "_")
    return s


def _parse_exif_info(raw: Any) -> Dict[str, Any]:
    """exif_info is stored as a JSON-encoded string (Column(Text)); parse it
    into a dict. Tolerate already-decoded dicts and empty/invalid values."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def format_export_filename(
    template: str,
    photo: Any,
    index: int,
    metadata: Any = None,
    original_filename: str = "",
) -> str:
    """
    Format the export/rename filename based on the template.

    Supported variables:
      {date} {time} {year} {month} {day} {hour} {minute}
      {city} {location}        -- from PhotoMetadata (city / address)
      {camera} {lens} {iso}    -- from PhotoMetadata.make/model and exif_info
      {original} {index} {sequence3} {sequence4}
    """
    date_obj = photo.photo_time or photo.upload_time or datetime.now()

    original_base = os.path.splitext(original_filename)[0] if original_filename else ""

    exif = _parse_exif_info(getattr(metadata, "exif_info", None))

    # Prefer the dedicated make/model columns; fall back to the EXIF dict.
    make = getattr(metadata, "make", None) or exif.get("Make") or "未知相机"
    model = getattr(metadata, "model", None) or exif.get("Model") or ""
    camera = f"{make} {model}".strip() if model else make
    lens = exif.get("LensModel") or "未知镜头"
    iso = exif.get("ISOSpeedRatings") or exif.get("ISO") or "未知ISO"

    context = {
        "date": date_obj.strftime("%Y-%m-%d"),
        "time": date_obj.strftime("%H%M%S"),
        "year": date_obj.strftime("%Y"),
        "month": date_obj.strftime("%m"),
        "day": date_obj.strftime("%d"),
        "hour": date_obj.strftime("%H"),
        "minute": date_obj.strftime("%M"),
        "city": getattr(metadata, "city", None) or "未知城市",
        "location": getattr(metadata, "address", None) or "未知地点",
        "original": original_base,
        "index": str(index),
        "sequence3": f"{index:03d}",
        "sequence4": f"{index:04d}",
        "camera": camera,
        "lens": lens,
        "iso": str(iso),
    }

    result = template
    for key, value in context.items():
        result = result.replace("{" + key + "}", _sanitize(value))

    # Any unrecognized {placeholder} left in the template is dropped so it
    # can't produce an invalid or confusing filename.
    result = re.sub(r"\{[^}]*\}", "", result)
    return result
