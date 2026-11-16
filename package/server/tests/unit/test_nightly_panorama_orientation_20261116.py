"""2026-11-16 nightly coverage for ``app/service/panorama.py``.

The 2026-11-16 backend coverage scan reported ``service/panorama.py`` at
95.1% with 2 missed lines.  The uncovered branch is the guard that
refuses to build a panorama derivative from an image whose EXIF
orientation was not normalised first (line 34): rotating the pixels
after the fact would produce a skewed panorama.

The temporary file must also be removed when the final replace fails
(line 45-46).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from PIL import Image

from app.service import panorama as panorama_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


GEOMETRY = {
    "fullWidth": 400,
    "fullHeight": 200,
    "croppedWidth": 400,
    "croppedHeight": 200,
    "croppedX": 0,
    "croppedY": 0,
}


def _write_image(path, orientation=1, size=(400, 200)):
    image = Image.new("RGB", size, "red")
    exif = image.getexif()
    exif[274] = orientation
    image.save(path, "JPEG", exif=exif)


def _photo(path):
    return SimpleNamespace(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        file_path=str(path),
        panorama_metadata=dict(GEOMETRY),
    )


def test_derivative_refuses_a_non_normalised_orientation(tmp_path, monkeypatch):
    source = tmp_path / "rotated.jpg"
    _write_image(source, orientation=6)
    monkeypatch.setattr(panorama_service, "_get_storage_root", lambda _user_id: str(tmp_path / "storage"))

    with pytest.raises(ValueError) as excinfo:
        panorama_service.derivative(_photo(source))

    assert "方向归一化" in str(excinfo.value)


def test_derivative_builds_a_cached_thumbnail(tmp_path, monkeypatch):
    source = tmp_path / "normal.jpg"
    _write_image(source, orientation=1)
    monkeypatch.setattr(panorama_service, "_get_storage_root", lambda _user_id: str(tmp_path / "storage"))

    photo = _photo(source)
    target, width, height = panorama_service.derivative(photo)

    assert (width, height) == (400, 200)
    assert target.endswith(".jpg")
    # The second call reuses the cached derivative.
    again, _, _ = panorama_service.derivative(photo)
    assert again == target


def test_derivative_removes_the_temporary_file_on_failure(tmp_path, monkeypatch):
    source = tmp_path / "normal.jpg"
    _write_image(source, orientation=1)
    monkeypatch.setattr(panorama_service, "_get_storage_root", lambda _user_id: str(tmp_path / "storage"))

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(panorama_service.os, "replace", _boom)

    with pytest.raises(OSError):
        panorama_service.derivative(_photo(source))

    leftovers = list((tmp_path / "storage").rglob("*.jpg"))
    assert all(not path.name.startswith("tmp") for path in leftovers)

