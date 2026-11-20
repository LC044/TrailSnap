"""Toolbox scope row projection."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.service.toolbox_scope import _scope_row

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


def test_scope_row_exposes_the_photo_identity_fields():
    photo = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        filename="photo.jpg",
        photo_time=datetime(2024, 5, 1, 8, 0, 0),
        file_type="image",
    )
    row = _scope_row(photo)
    assert row["id"] == "11111111-1111-1111-1111-111111111111"
    assert row["filename"] == "photo.jpg"
    assert row["photo_time"] == datetime(2024, 5, 1, 8, 0, 0)


def test_scope_row_unwraps_an_enum_file_type():
    class FileType:
        value = "video"

    photo = SimpleNamespace(
        id="22222222-2222-2222-2222-222222222222",
        filename="clip.mp4",
        photo_time=datetime(2024, 5, 1),
        file_type=FileType(),
    )
    assert _scope_row(photo)["file_type"] == "video"


def test_scope_row_keeps_a_plain_string_file_type():
    photo = SimpleNamespace(
        id="33333333-3333-3333-3333-333333333333",
        filename="raw.cr2",
        photo_time=datetime(2024, 5, 1),
        file_type="raw",
    )
    assert _scope_row(photo)["file_type"] == "raw"
