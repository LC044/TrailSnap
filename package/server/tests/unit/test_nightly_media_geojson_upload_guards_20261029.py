"""2026-10-29 nightly coverage for ``app/api/media.py``.

The nightly coverage scan reported ``api/media.py`` at 84.5% with 126 uncovered
lines.  The remaining holes cluster in three places:

* ``get_geojson`` -- the bundled GeoJSON endpoint, including the two-pass
  parent lookup (exact/short name first, then the "clean name" fallback that
  strips ethnic-group and administrative suffixes).
* ``finish_upload_generic`` -- the validation guards of the chunked upload
  pipeline (bad sizes, oversized backup keys, mismatched live-photo pairs,
  missing chunk sessions, out-of-sequence chunks, unknown albums).
* the small pure helpers around them (``_normalized_md5``,
  ``_normalized_sha256``, ``_is_upload_file``, ``_validate_chunk_sequence``
  and the thumbnail path resolver).

These are all failure modes that silently corrupt or strand an upload, so the
tests assert on the error codes as carefully as on the happy path.
"""

from __future__ import annotations

import json
import os
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _media():
    from app.api import media

    return media


def _user():
    return SimpleNamespace(id=uuid.uuid4())


def _write_geojson(path, features):
    payload = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _feature(name, gb):
    return {"type": "Feature", "properties": {"name": name, "gb": gb}, "geometry": None}


# ---------------------------------------------------------------------------
# get_geojson
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_geojson_rejects_an_unknown_level():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.get_geojson(level="country")

    assert excinfo.value.status_code == 400
    assert "province, city, or district" in excinfo.value.detail


@pytest.mark.asyncio
async def test_geojson_returns_404_when_the_bundle_file_is_missing(tmp_path):
    media = _media()
    missing = tmp_path / "missing.geojson"

    with patch.object(media, "_geojson_path", return_value=str(missing)):
        with pytest.raises(HTTPException) as excinfo:
            await media.get_geojson(level="city", parent=None)

    assert excinfo.value.status_code == 404
    assert "not found" in excinfo.value.detail


@pytest.mark.asyncio
async def test_geojson_serves_the_file_when_no_parent_is_requested(tmp_path):
    media = _media()
    target = _write_geojson(tmp_path / "中国_市.geojson", [_feature("武汉市", "420100")])

    with patch.object(media, "_geojson_path", return_value=str(target)):
        response = await media.get_geojson(level="city", parent=None)

    assert isinstance(response, FileResponse)
    assert response.media_type == "application/geo+json"


@pytest.mark.asyncio
async def test_geojson_filters_children_by_the_exact_parent_name(tmp_path):
    """The district file is filtered by the parent city's gb prefix.

    The bundled files use nine digit codes: a district of Wuhan starts with
    the city's own prefix (1564201...), which is what the endpoint slices.
    """
    media = _media()
    county = _write_geojson(
        tmp_path / "中国_县.geojson",
        [_feature("洪山区", "156420111"), _feature("江夏区", "156420115")],
    )
    city = _write_geojson(tmp_path / "中国_市.geojson", [_feature("武汉市", "156420100")])
    province = _write_geojson(tmp_path / "中国_省.geojson", [_feature("湖北省", "156420000")])

    def fake_path(level_cn):
        return {"省": str(province), "市": str(city), "县": str(county)}[level_cn]

    with patch.object(media, "_geojson_path", side_effect=fake_path):
        response = await media.get_geojson(level="district", parent="武汉市")

    payload = json.loads(response.body.decode("utf-8"))
    names = [feature["properties"]["name"] for feature in payload["features"]]
    assert names == ["洪山区", "江夏区"]
    assert response.media_type == "application/geo+json"


@pytest.mark.asyncio
async def test_geojson_matches_a_parent_by_its_short_name(tmp_path):
    """``湖北`` resolves to the ``湖北省`` feature via the short-name pass."""
    media = _media()
    city = _write_geojson(
        tmp_path / "中国_市.geojson",
        [_feature("武汉市", "156420100"), _feature("十堰市", "156420300")],
    )
    province = _write_geojson(tmp_path / "中国_省.geojson", [_feature("湖北省", "156420000")])

    def fake_path(level_cn):
        return {"省": str(province), "市": str(city), "县": str(city)}[level_cn]

    with patch.object(media, "_geojson_path", side_effect=fake_path):
        response = await media.get_geojson(level="city", parent="湖北")

    payload = json.loads(response.body.decode("utf-8"))
    names = [feature["properties"]["name"] for feature in payload["features"]]
    assert names == ["武汉市", "十堰市"]


@pytest.mark.asyncio
async def test_geojson_falls_back_to_cleaning_ethnic_group_suffixes(tmp_path):
    """``恩施`` only matches after the ethnic-group and administrative suffixes
    are stripped from ``恩施土家族苗族自治州``."""
    media = _media()
    city = _write_geojson(
        tmp_path / "中国_市.geojson",
        [_feature("恩施土家族苗族自治州", "156422800"), _feature("武汉市", "156420100")],
    )
    province = _write_geojson(tmp_path / "中国_省.geojson", [_feature("湖北省", "156420000")])

    def fake_path(level_cn):
        return {"省": str(province), "市": str(city), "县": str(city)}[level_cn]

    with patch.object(media, "_geojson_path", side_effect=fake_path):
        response = await media.get_geojson(level="city", parent="恩施")

    payload = json.loads(response.body.decode("utf-8"))
    names = [feature["properties"]["name"] for feature in payload["features"]]
    assert names == ["恩施土家族苗族自治州"]


@pytest.mark.asyncio
async def test_geojson_returns_the_whole_file_when_the_parent_is_unknown(tmp_path):
    media = _media()
    city = _write_geojson(tmp_path / "中国_市.geojson", [_feature("武汉市", "420100")])
    province = _write_geojson(tmp_path / "中国_省.geojson", [_feature("湖北省", "420000")])

    def fake_path(level_cn):
        return str(province if level_cn == "省" else city)

    with patch.object(media, "_geojson_path", side_effect=fake_path):
        response = await media.get_geojson(level="city", parent="并不存在的省")

    assert isinstance(response, FileResponse)


@pytest.mark.asyncio
async def test_geojson_ignores_a_parent_for_the_province_level(tmp_path):
    media = _media()
    province = _write_geojson(tmp_path / "中国_省.geojson", [_feature("湖北省", "420000")])

    with patch.object(media, "_geojson_path", return_value=str(province)):
        response = await media.get_geojson(level="province", parent="湖北省")

    assert isinstance(response, FileResponse)


# ---------------------------------------------------------------------------
# hash / upload helpers
# ---------------------------------------------------------------------------


def test_normalized_md5_lowercases_a_valid_digest():
    media = _media()
    assert media._normalized_md5("  D41D8CD98F00B204E9800998ECF8427E ") == (
        "d41d8cd98f00b204e9800998ecf8427e"
    )


def test_normalized_md5_rejects_a_non_hexadecimal_value():
    media = _media()
    with pytest.raises(HTTPException) as excinfo:
        media._normalized_md5("z" * 32)
    assert excinfo.value.status_code == 400


def test_normalized_md5_rejects_a_wrong_length_value():
    media = _media()
    with pytest.raises(HTTPException) as excinfo:
        media._normalized_md5("abc")
    assert excinfo.value.status_code == 400


def test_normalized_md5_maps_a_non_string_to_none():
    media = _media()
    assert media._normalized_md5(None) is None
    assert media._normalized_md5(12345) is None


def test_normalized_sha256_lowercases_a_valid_digest():
    media = _media()
    assert media._normalized_sha256("A" * 64) == "a" * 64


def test_normalized_sha256_rejects_an_invalid_digest():
    media = _media()
    with pytest.raises(HTTPException) as excinfo:
        media._normalized_sha256("A" * 63)
    assert excinfo.value.status_code == 400


def test_normalized_sha256_passes_none_through():
    media = _media()
    assert media._normalized_sha256(None) is None


def test_is_upload_file_only_accepts_the_starlette_type():
    media = _media()
    from starlette.datastructures import UploadFile

    assert media._is_upload_file(UploadFile(filename="a.jpg", file=object())) is True
    assert media._is_upload_file(object()) is False
    assert media._is_upload_file(None) is False


def test_validate_chunk_sequence_accepts_a_contiguous_run():
    media = _media()
    media._validate_chunk_sequence([0, 1, 2])


def test_validate_chunk_sequence_rejects_a_gap():
    media = _media()
    with pytest.raises(ValueError, match="missing or out of sequence"):
        media._validate_chunk_sequence([0, 2])


def test_validate_chunk_sequence_rejects_an_empty_run():
    media = _media()
    with pytest.raises(ValueError, match="missing or out of sequence"):
        media._validate_chunk_sequence([])


def test_validate_chunk_sequence_rejects_a_wrong_expected_count():
    media = _media()
    with pytest.raises(ValueError, match="does not match the original"):
        media._validate_chunk_sequence([0, 1], expected_chunks=3)


# ---------------------------------------------------------------------------
# _get_thumbnail_path
# ---------------------------------------------------------------------------


def test_thumbnail_path_prefers_the_small_webp_variant(tmp_path):
    media = _media()
    photo_id = uuid.uuid4()
    compact = str(photo_id).replace("-", "")
    base = tmp_path / "thumbnails" / compact[:2] / compact[2:4]
    base.mkdir(parents=True)
    (base / f"{compact}-thumb.webp").write_bytes(b"x")

    with patch.object(media, "_get_storage_root", return_value=str(tmp_path)):
        resolved = media._get_thumbnail_path(uuid.uuid4(), photo_id, MagicMock(), "small")

    assert resolved.endswith(f"{compact}-thumb.webp")


def test_thumbnail_path_falls_back_to_the_small_jpg_variant(tmp_path):
    media = _media()
    photo_id = uuid.uuid4()
    compact = str(photo_id).replace("-", "")

    with patch.object(media, "_get_storage_root", return_value=str(tmp_path)):
        resolved = media._get_thumbnail_path(uuid.uuid4(), photo_id, MagicMock(), "small")

    assert resolved.endswith(f"{compact}-thumb.jpg")


def test_thumbnail_path_uses_the_large_naming_for_other_sizes(tmp_path):
    media = _media()
    photo_id = uuid.uuid4()
    compact = str(photo_id).replace("-", "")
    base = tmp_path / "thumbnails" / compact[:2] / compact[2:4]
    base.mkdir(parents=True)
    (base / f"{compact}.webp").write_bytes(b"x")

    with patch.object(media, "_get_storage_root", return_value=str(tmp_path)):
        resolved = media._get_thumbnail_path(uuid.uuid4(), photo_id, MagicMock(), "large")

    assert resolved.endswith(f"{compact}.webp")


def test_thumbnail_path_falls_back_to_the_large_jpg_variant(tmp_path):
    media = _media()
    photo_id = uuid.uuid4()
    compact = str(photo_id).replace("-", "")

    with patch.object(media, "_get_storage_root", return_value=str(tmp_path)):
        resolved = media._get_thumbnail_path(uuid.uuid4(), photo_id, MagicMock(), "medium")

    assert resolved.endswith(f"{compact}.jpg")


# ---------------------------------------------------------------------------
# finish_upload_generic guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finish_upload_rejects_a_non_positive_expected_size():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.finish_upload_generic(
            upload_id=uuid.uuid4(),
            file_name="a.jpg",
            expected_size=0,
            db=MagicMock(),
            current_user=_user(),
        )

    assert excinfo.value.status_code == 400
    assert "expected file size" in excinfo.value.detail


@pytest.mark.asyncio
async def test_finish_upload_rejects_a_non_positive_expected_chunk_count():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.finish_upload_generic(
            upload_id=uuid.uuid4(),
            file_name="a.jpg",
            expected_chunks=-1,
            db=MagicMock(),
            current_user=_user(),
        )

    assert excinfo.value.status_code == 400
    assert "expected chunk count" in excinfo.value.detail


@pytest.mark.asyncio
async def test_finish_upload_rejects_an_oversized_backup_key():
    media = _media()

    with pytest.raises(HTTPException) as excinfo:
        await media.finish_upload_generic(
            upload_id=uuid.uuid4(),
            file_name="a.jpg",
            backup_key="k" * 256,
            db=MagicMock(),
            current_user=_user(),
        )

    assert excinfo.value.status_code == 400
    assert "backup_key is too long" in excinfo.value.detail


@pytest.mark.asyncio
async def test_finish_upload_rejects_a_mismatched_live_photo_pair():
    media = _media()
    from starlette.datastructures import UploadFile

    video = UploadFile(filename="other.mp4", file=object())

    with pytest.raises(HTTPException) as excinfo:
        await media.finish_upload_generic(
            upload_id=uuid.uuid4(),
            file_name="photo.jpg",
            live_photo_video=video,
            db=MagicMock(),
            current_user=_user(),
        )

    assert excinfo.value.status_code == 400
    assert "Invalid live photo pair" in excinfo.value.detail


@pytest.mark.asyncio
async def test_finish_upload_rejects_a_mismatched_live_photo_extension():
    media = _media()
    from starlette.datastructures import UploadFile

    video = UploadFile(filename="photo.mp4", file=object())

    with pytest.raises(HTTPException) as excinfo:
        await media.finish_upload_generic(
            upload_id=uuid.uuid4(),
            file_name="photo.png",
            live_photo_video=video,
            db=MagicMock(),
            current_user=_user(),
        )

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_finish_upload_requires_an_existing_chunk_session_to_replace(tmp_path):
    media = _media()
    user = _user()
    existing = SimpleNamespace(id=uuid.uuid4(), owner_id=user.id, backup_key="bk", file_path="a.jpg")

    with patch.object(media, "_existing_backup_photo", return_value=existing):
        with patch.object(media, "_chunk_dir", return_value=str(tmp_path / "missing")):
            with pytest.raises(HTTPException) as excinfo:
                    await media.finish_upload_generic(
                        upload_id=uuid.uuid4(),
                        file_name="a.jpg",
                        backup_key="bk",
                        replace_existing=True,
                        db=MagicMock(),
                        current_user=user,
                    )

    assert excinfo.value.status_code == 404
    assert "Upload session not found" in excinfo.value.detail


@pytest.mark.asyncio
async def test_finish_upload_rejects_an_empty_chunk_directory(tmp_path):
    media = _media()
    user = _user()
    existing = SimpleNamespace(id=uuid.uuid4(), owner_id=user.id, backup_key="bk", file_path="a.jpg")
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()

    with patch.object(media, "_existing_backup_photo", return_value=existing):
        with patch.object(media, "_chunk_dir", return_value=str(chunk_dir)):
            with pytest.raises(HTTPException) as excinfo:
                    await media.finish_upload_generic(
                        upload_id=uuid.uuid4(),
                        file_name="a.jpg",
                        backup_key="bk",
                        replace_existing=True,
                        db=MagicMock(),
                        current_user=user,
                    )

    assert excinfo.value.status_code == 400
    assert "No chunks found" in excinfo.value.detail


@pytest.mark.asyncio
async def test_finish_upload_rejects_an_out_of_sequence_chunk_set(tmp_path):
    media = _media()
    user = _user()
    existing = SimpleNamespace(id=uuid.uuid4(), owner_id=user.id, backup_key="bk", file_path="a.jpg")
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / "0").write_bytes(b"a")
    (chunk_dir / "2").write_bytes(b"b")

    with patch.object(media, "_existing_backup_photo", return_value=existing):
        with patch.object(media, "_chunk_dir", return_value=str(chunk_dir)):
            with pytest.raises(HTTPException) as excinfo:
                    await media.finish_upload_generic(
                        upload_id=uuid.uuid4(),
                        file_name="a.jpg",
                        backup_key="bk",
                        replace_existing=True,
                        db=MagicMock(),
                        current_user=user,
                    )

    assert excinfo.value.status_code == 400
    assert "out of sequence" in excinfo.value.detail


@pytest.mark.asyncio
async def test_finish_upload_rejects_an_unknown_album():
    media = _media()
    user = _user()

    with patch.object(media, "_existing_backup_photo", return_value=None):
        with patch.object(media, "_existing_content_photo", return_value=None):
            with patch.object(media.crud_album, "get_album", return_value=None):
                with pytest.raises(HTTPException) as excinfo:
                    await media.finish_upload_generic(
                        upload_id=uuid.uuid4(),
                        file_name="a.jpg",
                        album_id=uuid.uuid4(),
                        db=MagicMock(),
                        current_user=user,
                    )

    assert excinfo.value.status_code == 404
    assert "Album not found" in excinfo.value.detail


