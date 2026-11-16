"""2026-11-16 nightly coverage for ``app/utils/template.py`` fallbacks.

The 2026-11-16 backend coverage scan reported ``utils/template.py`` at
95.8% with 6 missed lines, all of them defensive fallbacks:

* ``_format_date`` using the default format when the template does not
  provide one (line 43);
* ``_format_date`` surviving an unreadable file timestamp (lines 49-50);
* ``_format_date`` surviving an invalid format string (lines 55-56);
* ``build_extension`` falling back when the photo has no ``file_type``
  at all (line 277).
"""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.utils import template as template_mod
from app.utils.template import build_extension


pytestmark = [pytest.mark.smoke]


def _photo(**kw):
    base = {"filename": "a.jpg", "photo_time": None, "upload_time": None,
            "file_path": "", "file_type": None}
    base.update(kw)
    return SimpleNamespace(**base)


def test_format_date_uses_the_default_format_when_none_is_given():
    photo = _photo(photo_time=datetime(2026, 3, 4, 5, 6, 7))
    assert template_mod._format_date(photo, {}, None) == "20260304"


def test_format_date_falls_back_to_the_file_timestamp():
    photo = _photo()
    photo.file_path = __file__
    stamp = datetime.fromtimestamp(os.path.getmtime(__file__))
    assert template_mod._format_date(photo, {}, "%Y%m%d") == stamp.strftime("%Y%m%d")


def test_format_date_survives_an_unreadable_timestamp(monkeypatch):
    photo = _photo(file_path="/does/not/exist.jpg")

    def _boom(_path):
        raise OSError("cannot stat")

    monkeypatch.setattr(os.path, "exists", lambda _path: True)
    monkeypatch.setattr(os.path, "getmtime", _boom)
    # The timestamp cannot be read, so the date stays unknown.
    assert template_mod._format_date(photo, {}, "%Y%m%d") == "unknown"


def test_format_date_reports_unknown_without_any_time_source():
    assert template_mod._format_date(_photo(), {}, "%Y%m%d") == "unknown"


def test_format_date_survives_an_invalid_format_string():
    photo = _photo(photo_time=datetime(2026, 3, 4, 5, 6, 7))
    assert template_mod._format_date(photo, {}, "%Q") == "20260304"


def test_build_extension_falls_back_when_file_type_is_missing():
    assert build_extension(_photo(filename="a.jpg"), fallback=".png") == ".jpg"
    assert build_extension(_photo(filename=""), fallback=".png") == ".png"


def test_build_extension_uses_the_file_type_mapping():
    photo = _photo(filename="", file_type="video")
    assert build_extension(photo) == ".mp4"
    photo = _photo(filename="", file_type="live_photo")
    assert build_extension(photo) == ".mov"
    photo = _photo(filename="", file_type="unknown-kind")
    assert build_extension(photo, fallback=".bin") == ".bin"

