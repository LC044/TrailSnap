"""Nightly coverage for the error branches of ``app/service/storage.py``.

The 2026-10-28 backend coverage scan ranked ``service/storage.py`` at 84.2%
(60 missed statements). The happy paths were already covered by
``test_storage_service.py``; what stayed uncovered were the **failure**
branches -- the code that decides what happens when a disk operation, a
config lookup, or an image decode fails.

Those branches matter: they are the difference between "the upload is
rejected with a clear message" and "the request 500s". This file drives
each one directly:

* ``_validate_upload_folder``     -- rejects traversal / absolute paths
* ``_path_is_within``              -- treats unrelated drives as "outside"
* ``get_external_upload_roots``    -- swallows a broken config
* ``update_storage_root_cache``    -- survives an unwritable directory
* ``get_live_photo_vide``          -- resolves the sibling video case
* ``delete_thumbnails``            -- never raises on a locked file
* ``get_image_dimensions``         -- returns (None, None, None) on failure
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.service import storage


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def isolated_storage(tmp_path, monkeypatch):
    """Pin the storage root to a tmp dir so the real tree is never touched."""
    monkeypatch.setattr(storage, "_get_storage_root", lambda user_id, db=None: str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# _validate_upload_folder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "])
def test_validate_upload_folder_treats_blank_input_as_unset(value):
    """Edge: no folder means "use the default year/month bucket"."""
    assert storage._validate_upload_folder(value) is None


@pytest.mark.parametrize("value", [".", "./", "/", "//"])
def test_validate_upload_folder_rejects_dot_segments(value):
    """Error: a relative "." segment would escape the uploads root."""
    assert storage._validate_upload_folder(value) is None


def test_validate_upload_folder_normalizes_separators_and_strips_slashes():
    """Happy path: Windows separators become "/" and leading/trailing slashes go."""
    assert storage._validate_upload_folder("trips\\2026\\") == "trips/2026"


# Traversal segments are rejected on every platform.  Absolute paths are
# platform specific: ``os.path.isabs`` only knows the running platform, so
# ``C:\\Windows\\System32`` is a harmless relative name on Linux and
# ``/etc/passwd`` is a relative name on Windows.
_TRAVERSAL_FOLDERS = ["../secrets", "a/../../b", "a/./b"]
_ABSOLUTE_FOLDERS = ["C:\\Windows\\System32"] if os.name == "nt" else ["/etc/passwd"]


@pytest.mark.parametrize("value", _TRAVERSAL_FOLDERS + _ABSOLUTE_FOLDERS)
def test_validate_upload_folder_rejects_escaping_paths(value):
    """Error: absolute paths and traversal segments are refused outright."""
    with pytest.raises(ValueError, match="Invalid upload folder"):
        storage._validate_upload_folder(value)


# ---------------------------------------------------------------------------
# _path_is_within
# ---------------------------------------------------------------------------


def test_path_is_within_accepts_a_child_directory(tmp_path):
    """Happy path: a directory under the root is inside it."""
    child = tmp_path / "uploads" / "2026"
    child.mkdir(parents=True)
    assert storage._path_is_within(str(tmp_path), str(child))


def test_path_is_within_accepts_the_root_itself(tmp_path):
    """Edge: the root contains itself."""
    assert storage._path_is_within(str(tmp_path), str(tmp_path))


def test_path_is_within_rejects_a_sibling(tmp_path):
    """Error: a sibling directory with a shared prefix is not inside."""
    other = tmp_path.parent / f"{tmp_path.name}-other"
    assert not storage._path_is_within(str(tmp_path), str(other))


def test_path_is_within_rejects_unrelated_roots(tmp_path):
    """Error: two unrelated roots have no common path."""
    assert not storage._path_is_within(str(tmp_path), "Z:\\other\\place")


# ---------------------------------------------------------------------------
# get_external_upload_roots
# ---------------------------------------------------------------------------


def test_get_external_upload_roots_requires_a_session():
    """Edge: without a session there is no configuration to read."""
    assert storage.get_external_upload_roots(MagicMock(), None) == []


def test_get_external_upload_roots_returns_empty_when_the_config_fails():
    """Error: a broken config is logged and treated as "no external roots"."""
    user_id = MagicMock()
    db = MagicMock()
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(storage.config_manager, "get_user_config", MagicMock(side_effect=RuntimeError("boom")))
        assert storage.get_external_upload_roots(user_id, db) == []


def test_get_external_upload_roots_absolutes_and_drops_blanks(monkeypatch):
    """Happy path: configured roots become absolute paths; blanks are dropped."""
    config = MagicMock()
    config.storage.external_directories = ["", "photos"]
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(storage.config_manager, "get_user_config", MagicMock(return_value=config))
        roots = storage.get_external_upload_roots(MagicMock(), MagicMock())
    assert roots == [os.path.abspath(os.path.expanduser("photos"))]


# ---------------------------------------------------------------------------
# update_storage_root_cache
# ---------------------------------------------------------------------------


def test_update_storage_root_cache_unwraps_a_user_scoped_root():
    """Edge: a worker payload already carries /users/<id>; it must not nest twice."""
    user_id = "11111111-1111-4111-8111-111111111111"
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(storage.user_storage, "cache_storage_base", MagicMock())
        patcher.setattr(storage.user_storage, "ensure_user_layout", MagicMock())
        storage.update_storage_root_cache(user_id, f"/data/uploads/users/{user_id}")
        assert storage.user_storage.cache_storage_base.call_args[0][1] == os.path.abspath("/data/uploads")


def test_update_storage_root_cache_survives_an_unwritable_root(monkeypatch):
    """Error: a directory that cannot be created is logged, not raised."""
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(storage.user_storage, "cache_storage_base", MagicMock())
        patcher.setattr(storage.user_storage, "ensure_user_layout", MagicMock(side_effect=OSError("read-only")))
        # Must not raise.
        storage.update_storage_root_cache("22222222-2222-4222-8222-222222222222", "/data/uploads")


# ---------------------------------------------------------------------------
# get_live_photo_vide
# ---------------------------------------------------------------------------


def test_get_live_photo_vide_finds_the_mp4_sibling_of_a_jpeg(tmp_path):
    """Happy path: a .jpg with a .mp4 beside it is a live photo."""
    image = tmp_path / "IMG_0001.jpg"
    image.write_bytes(b"image")
    video = tmp_path / "IMG_0001.mp4"
    video.write_bytes(b"video")

    found = storage.get_live_photo_vide(str(image))

    assert found is not None
    assert Path(found).name == "IMG_0001.mp4"


def test_get_live_photo_vide_finds_the_mov_sibling_of_a_heic(tmp_path):
    """Happy path: a .heic with a .MOV beside it is a live photo."""
    image = tmp_path / "IMG_0002.heic"
    image.write_bytes(b"image")
    video = tmp_path / "IMG_0002.MOV"
    video.write_bytes(b"video")

    found = storage.get_live_photo_vide(str(image))

    assert found is not None
    assert Path(found).suffix.lower() == ".mov"


def test_get_live_photo_vide_returns_none_without_a_sibling(tmp_path):
    """Edge: a plain photo has no sibling video."""
    image = tmp_path / "plain.jpg"
    image.write_bytes(b"image")
    assert storage.get_live_photo_vide(str(image)) is None


def test_get_live_photo_vide_returns_none_for_an_unsupported_extension(tmp_path):
    """Edge: only HEIC/JPEG sources can carry a live-photo video."""
    other = tmp_path / "clip.mp4"
    other.write_bytes(b"video")
    assert storage.get_live_photo_vide(str(other)) is None


# ---------------------------------------------------------------------------
# delete_thumbnails
# ---------------------------------------------------------------------------


def test_delete_thumbnails_removes_the_panorama_variants(isolated_storage):
    """Happy path: the numbered panorama files are removed too."""
    user_id = uuid.uuid4()
    file_id = uuid.uuid4()
    compact = str(file_id).replace("-", "")
    base = Path(isolated_storage) / "thumbnails" / compact[:2] / compact[2:4]
    base.mkdir(parents=True)
    panorama = base / f"{compact}-pano-1.jpg"
    panorama.write_bytes(b"x")
    thumbnail = base / f"{compact}.webp"
    thumbnail.write_bytes(b"x")

    storage.delete_thumbnails(user_id, file_id)

    assert not panorama.exists()
    assert not thumbnail.exists()


def test_delete_thumbnails_never_raises_on_a_locked_file(isolated_storage, monkeypatch):
    """Error: a failing unlink is logged and swallowed, not propagated."""
    user_id = uuid.uuid4()
    file_id = uuid.uuid4()
    compact = str(file_id).replace("-", "")
    base = Path(isolated_storage) / "thumbnails" / compact[:2] / compact[2:4]
    base.mkdir(parents=True)
    (base / f"{compact}.webp").write_bytes(b"x")

    def boom(*args, **kwargs):
        raise PermissionError("locked")

    monkeypatch.setattr(storage.os, "remove", boom)

    # Must not raise.
    storage.delete_thumbnails(user_id, file_id)


# ---------------------------------------------------------------------------
# get_image_dimensions
# ---------------------------------------------------------------------------


def test_get_image_dimensions_returns_none_for_an_unknown_extension(tmp_path):
    """Edge: a file we cannot interpret yields the empty triple."""
    target = tmp_path / "notes.txt"
    target.write_text("hello")
    assert storage.get_image_dimensions(str(target)) == (None, None, None)


def test_get_image_dimensions_returns_none_for_a_corrupt_image(tmp_path):
    """Error: a corrupt image is reported as "no dimensions"."""
    target = tmp_path / "broken.jpg"
    target.write_bytes(b"not an image at all")
    assert storage.get_image_dimensions(str(target)) == (None, None, None)


def test_get_image_dimensions_reads_a_real_image(tmp_path):
    """Happy path: the sanity check that the surrounding guard is not broken."""
    target = tmp_path / "ok.png"
    Image.new("RGB", (40, 20)).save(target)
    width, height, duration = storage.get_image_dimensions(str(target))
    assert (width, height) == (40, 20)
    assert duration is None


# ---------------------------------------------------------------------------
# generate_thumbnail
# ---------------------------------------------------------------------------


def test_generate_thumbnail_returns_none_for_an_unsupported_extension(tmp_path):
    """Edge: an unsupported file type produces no thumbnail at all."""
    target = tmp_path / "notes.txt"
    target.write_text("hello")
    assert storage.generate_thumbnail(MagicMock(), str(target), MagicMock()) is None


def test_generate_thumbnail_returns_none_for_a_corrupt_image(tmp_path):
    """Error: a broken source file is logged and yields None, not an exception."""
    target = tmp_path / "broken.jpg"
    target.write_bytes(b"not an image at all")
    assert storage.generate_thumbnail(MagicMock(), str(target), MagicMock()) is None


