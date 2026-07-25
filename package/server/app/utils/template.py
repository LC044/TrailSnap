#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Export template renderer.

Templates are simple brace-delimited variable references, e.g.::

    {date}_{city}_{sequence3}_{index}

Supported variables are derived from the photo's metadata (see
``VARIABLE_PROVIDERS``).  Unknown variables raise :class:`TemplateError`
so the frontend preview and the background handler can fail fast and
report the offending token to the user.

The renderer also understands the short-hand sequence notation
``{sequenceN}`` which is equivalent to ``{index:N}``.
"""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

# Matches ``{name}`` or ``{name:N}`` where name is alphanumeric / underscore.
_TOKEN_RE = re.compile(r"\{(\w+)(?::(\d+))?\}")


class TemplateError(ValueError):
    """Raised when a template references an unknown variable or has the
    wrong shape.  The handler is expected to write the message to
    ``task.error`` and abort the export."""


# ---------------------------------------------------------------------------
# Variable resolvers
# ---------------------------------------------------------------------------
# Each provider is a ``(name, callable)`` pair.  ``callable(photo, ctx)`` is
# expected to return a string (or ``None`` -> treated as empty).
def _format_date(photo: Any, ctx: Dict[str, Any], fmt: Optional[str]) -> str:
    if not fmt:
        fmt = "%Y%m%d"
    moment: Optional[datetime] = photo.photo_time or photo.upload_time
    if moment is None and photo.file_path and os.path.exists(photo.file_path):
        try:
            ts = os.path.getmtime(photo.file_path)
            moment = datetime.fromtimestamp(ts)
        except Exception:
            moment = None
    if moment is None:
        return "unknown"
    try:
        return moment.strftime(fmt)
    except Exception:
        return moment.strftime("%Y%m%d")


def _resolve_index(photo: Any, ctx: Dict[str, Any], digits: int = 0) -> str:
    index = ctx.get("index", 1)
    if digits and digits > 0:
        return str(index).zfill(digits)
    return str(index)


def _resolve_original(photo: Any, ctx: Dict[str, Any]) -> str:
    name = photo.filename or ""
    base, _ = os.path.splitext(name)
    return base or "photo"


def _resolve_location_chain(photo: Any, ctx: Dict[str, Any], depth: int) -> str:
    md = getattr(photo, "metadata_info", None)
    if not md:
        return ""
    parts: List[str] = []
    if depth >= 1 and getattr(md, "country", None):
        parts.append(md.country)
    if depth >= 2 and getattr(md, "province", None):
        parts.append(md.province)
    if depth >= 3 and getattr(md, "city", None):
        parts.append(md.city)
    if depth >= 4 and getattr(md, "district", None):
        parts.append(md.district)
    return "-".join(p for p in parts if p)


def _resolve_camera_field(photo: Any, ctx: Dict[str, Any], field: str) -> str:
    md = getattr(photo, "metadata_info", None)
    if not md:
        return ""
    return str(getattr(md, field, "") or "")


def _resolve_tag(photo: Any, ctx: Dict[str, Any]) -> str:
    tags = getattr(photo, "tags", None) or []
    if not tags:
        return ""
    # Pick the tag with the highest confidence if available, else the first.
    sorted_tags = sorted(
        tags,
        key=lambda t: getattr(t, "confidence", 0) or 0,
        reverse=True,
    )
    name = getattr(sorted_tags[0], "tag_name", "") or ""
    return name


def _resolve_album(photo: Any, ctx: Dict[str, Any]) -> str:
    albums = getattr(photo, "albums", None) or []
    if not albums:
        return ""
    name = getattr(albums[0], "name", "") or ""
    return name


# (name, parser) tuples that drive ``parse_template``.
# A parser takes ``(photo, ctx)`` and returns the raw string value.
PARSERS: List[Tuple[str, Callable[[Any, Dict[str, Any]], str]]] = [
    ("date", lambda p, c: _format_date(p, c, c.get("date_format", "%Y%m%d"))),
    ("time", lambda p, c: _format_date(p, c, "%H%M%S")),
    ("year", lambda p, c: _format_date(p, c, "%Y")),
    ("month", lambda p, c: _format_date(p, c, "%m")),
    ("day", lambda p, c: _format_date(p, c, "%d")),
    ("hour", lambda p, c: _format_date(p, c, "%H")),
    ("minute", lambda p, c: _format_date(p, c, "%M")),
    ("second", lambda p, c: _format_date(p, c, "%S")),
    ("city", lambda p, c: _resolve_location_field(p, "city")),
    ("location", lambda p, c: _resolve_location_chain(p, c, 3)),
    ("province", lambda p, c: _resolve_location_field(p, "province")),
    ("country", lambda p, c: _resolve_location_field(p, "country")),
    ("album", _resolve_album),
    ("tag", _resolve_tag),
    ("original", _resolve_original),
    ("index", _resolve_index),
    ("sequence", _resolve_index),
    ("camera", lambda p, c: _resolve_camera_field(p, c, "make")),
    ("lens", lambda p, c: _resolve_camera_field(p, c, "model")),
    ("iso", lambda p, c: ""),  # ISO lives in shooting_params, keep the door open
]

# The full list of names advertised to the frontend preview UI.
SUPPORTED_VARIABLES: List[str] = [
    "date", "time", "year", "month", "day", "hour", "minute", "second",
    "city", "location", "province", "country",
    "album", "tag", "original", "index", "sequence", "sequence3", "sequence4",
    "camera", "lens", "iso",
]

_PARSER_BY_NAME = {name: fn for name, fn in PARSERS}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
class RenderResult:
    """Container returned by :func:`render` so the handler can both display
    the rendered file name and report any rendering issues that were
    encountered for individual tokens."""

    __slots__ = ("name", "errors")

    def __init__(self, name: str, errors: Optional[List[str]] = None) -> None:
        self.name = name
        self.errors = errors or []

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "errors": list(self.errors)}


def collect_tokens(template: str) -> List[Tuple[str, int]]:
    """Return ``[(name, digits), ...]`` for every token in *template* in
    left-to-right order.  ``digits`` is ``0`` when no ``:N`` suffix was
    used.  Useful for the frontend to validate the template without
    rendering."""
    tokens: List[Tuple[str, int]] = []
    for match in _TOKEN_RE.finditer(template):
        name = match.group(1)
        digits = int(match.group(2)) if match.group(2) else 0
        tokens.append((name, digits))
    return tokens


def validate_template(template: str) -> List[str]:
    """Return the list of unsupported variable names referenced in the
    template (empty list when the template is valid)."""
    if not template:
        raise TemplateError("模板不能为空")
    unsupported: List[str] = []
    for name, _ in collect_tokens(template):
        if name not in _PARSER_BY_NAME and not name.startswith("sequence"):
            unsupported.append(name)
    if unsupported:
        raise TemplateError(
            "未知变量: " + ", ".join(sorted(set(unsupported)))
        )
    return unsupported


def render(
    template: str,
    photo: Any,
    *,
    index: int = 1,
    date_format: str = "%Y%m%d",
) -> RenderResult:
    """Render *template* for *photo* and return the file name (without
    extension).  Rendering errors (unknown variables) are collected in
    ``RenderResult.errors`` so a single bad token doesn't fail the entire
    batch."""
    validate_template(template)
    errors: List[str] = []
    ctx: Dict[str, Any] = {"index": index, "date_format": date_format}

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        digits = int(match.group(2)) if match.group(2) else 0
        # Short form ``{sequence3}`` -> equivalent to ``{sequence:3}``
        if name.startswith("sequence") and name[8:].isdigit():
            digits = int(name[8:]) or digits
            name = "sequence"
        parser = _PARSER_BY_NAME.get(name)
        if parser is None:
            errors.append(f"unknown:{name}")
            return ""
        try:
            value = parser(photo, ctx)
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(f"{name}:{exc}")
            return ""
        if digits > 0 and name in ("index", "sequence"):
            value = str(index).zfill(digits)
        return _sanitize_segment(str(value or ""))

    rendered = _TOKEN_RE.sub(_replace, template)
    rendered = _sanitize_segment(rendered)
    return RenderResult(rendered, errors)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = re.compile(r'^(con|prn|aux|nul|com[0-9]|lpt[0-9])$', re.IGNORECASE)


def _sanitize_segment(value: str) -> str:
    """Make *value* safe for use as a single file or directory segment on
    Windows / macOS / Linux without altering Unicode content."""
    if value is None:
        return ""
    # Normalize to NFC so combining marks collapse into the same byte sequence
    value = unicodedata.normalize("NFC", str(value)).strip()
    value = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    value = _INVALID_FS_CHARS.sub("_", value)
    # Trim trailing dots / spaces (Windows refuses them)
    value = value.rstrip(" .")
    if _RESERVED_NAMES.match(value):
        value = f"_{value}"
    return value


def build_extension(photo: Any, fallback: str = ".jpg") -> str:
    """Return a sensible file extension for *photo* based on its
    ``file_type`` and the on-disk file name."""
    name = getattr(photo, "filename", "") or ""
    _, ext = os.path.splitext(name)
    if ext:
        return ext.lower()
    file_type = getattr(photo, "file_type", None)
    mapping = {
        "video": ".mp4",
        "live_photo": ".mov",
        "image": ".jpg",
    }
    if file_type is None:
        return fallback
    value = getattr(file_type, "value", file_type)
    return mapping.get(value, fallback)



def _resolve_location_field(photo: Any, field: str) -> str:
    md = getattr(photo, "metadata_info", None)
    if not md:
        return ""
    return str(getattr(md, field, "") or "")
