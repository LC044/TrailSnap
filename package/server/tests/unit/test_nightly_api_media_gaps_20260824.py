"""Unit tests covering 2026-08-24 nightly coverage gap scan.

Targets app/api/media.py endpoints not exercised by the older
test_nightly_media_toolbox_storage_gaps_20260811.py round.
"""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import media as media_api


pytestmark = [pytest.mark.smoke]


def _photo(file_path="C:/photos/original.jpg", owner_id=None):
    return SimpleNamespace(
        id=uuid4(),
        owner_id=owner_id or uuid4(),
        file_path=file_path,
    )


# ---------------------------------------------------------------------------
# get_thumbnail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_thumbnail_404_when_photo_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc:
        await media_api.get_thumbnail(
            photo_id=uuid4(), size="small", format="file", db=db
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_thumbnail_404_when_thumb_file_missing(tmp_path):
    photo = _photo(owner_id=uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    with patch.object(media_api, "_get_storage_root", return_value=str(tmp_path)):
        with pytest.raises(HTTPException) as exc:
            await media_api.get_thumbnail(
                photo_id=photo.id, size="small", format="file", db=db
            )
    assert exc.value.status_code == 404
    assert "Thumbnail not found" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_thumbnail_returns_fileresponse_for_webp(tmp_path):
    photo = _photo(owner_id=uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    thumb = tmp_path / "snap-thumb.webp"
    thumb.write_bytes(b"\x52\x49\x46\x46")

    with patch.object(
        media_api, "_get_thumbnail_path", return_value=str(thumb)
    ):
        resp = await media_api.get_thumbnail(
            photo_id=photo.id, size="small", format="file", db=db
        )
    assert resp.path == str(thumb)
    assert resp.media_type == "image/webp"


@pytest.mark.asyncio
async def test_get_thumbnail_returns_fileresponse_for_jpg(tmp_path):
    photo = _photo(owner_id=uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    thumb = tmp_path / "snap-thumb.jpg"
    thumb.write_bytes(b"\xff\xd8\xff")

    with patch.object(
        media_api, "_get_thumbnail_path", return_value=str(thumb)
    ):
        resp = await media_api.get_thumbnail(
            photo_id=photo.id, size="medium", format="file", db=db
        )
    assert resp.path == str(thumb)
    assert resp.media_type == "image/jpeg"


@pytest.mark.asyncio
async def test_get_thumbnail_base64_returns_encoded_payload(tmp_path):
    photo = _photo(owner_id=uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    thumb = tmp_path / "snap-thumb.webp"
    thumb.write_bytes(b"WEBPBIN")

    with patch.object(
        media_api, "_get_thumbnail_path", return_value=str(thumb)
    ):
        result = await media_api.get_thumbnail(
            photo_id=photo.id, size="small", format="base64", db=db
        )
    assert result == {"base64": "V0VCUEJJTg=="}


@pytest.mark.asyncio
async def test_get_thumbnail_rejects_invalid_format(tmp_path):
    photo = _photo(owner_id=uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo

    thumb = tmp_path / "snap-thumb.webp"
    thumb.write_bytes(b"x")

    with patch.object(
        media_api, "_get_thumbnail_path", return_value=str(thumb)
    ):
        with pytest.raises(HTTPException) as exc:
            await media_api.get_thumbnail(
                photo_id=photo.id, size="small", format="binary", db=db
            )
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# init_upload / upload_chunk / finish_upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_upload_returns_id_and_creates_chunk_dir(tmp_path):
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    with patch.object(media_api, "_chunk_dir", return_value=str(tmp_path / "chunks")), \
         patch.object(media_api.os, "makedirs") as makedirs:
        result = await media_api.init_upload(db=db, current_user=user)
    assert "upload_id" in result
    makedirs.assert_called_once()
    args, kwargs = makedirs.call_args
    assert "chunks" in args[0]


@pytest.mark.asyncio
async def test_upload_chunk_404_when_session_missing():
    class FakeUpload:
        file = BytesIO(b"abc")

    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    with patch.object(media_api, "_chunk_dir", return_value="uploads/chunks/missing"), \
         patch.object(media_api.os.path, "exists", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await media_api.upload_chunk(
                upload_id=uuid4(), chunk_index=2, file=FakeUpload(), db=db, current_user=user
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_upload_chunk_writes_buffer_to_disk(tmp_path):
    class FakeUpload:
        def __init__(self, data):
            self.file = BytesIO(data)

        async def read(self, _size=None):
            return self.file.read()

    fake = FakeUpload(b"hello world")
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()

    fake_open = MagicMock()
    fake_buffer = MagicMock()
    fake_open.return_value.__enter__.return_value = fake_buffer

    with patch.object(media_api, "_chunk_dir", return_value=str(tmp_path)), \
         patch.object(media_api.os.path, "exists", return_value=True):
        with patch("builtins.open", fake_open):
            with patch.object(media_api.shutil, "copyfileobj") as copy:
                result = await media_api.upload_chunk(
                    upload_id=uuid4(), chunk_index=3, file=fake, db=db, current_user=user
                )

    assert result == {"status": "success"}
    copy.assert_called_once()


@pytest.mark.asyncio
async def test_finish_upload_404_when_chunk_dir_missing():
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()

    with patch.object(media_api.os.path, "exists", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await media_api.finish_upload_generic(
                upload_id=uuid4(),
                file_name="img.jpg",
                album_id=None,
                db=db,
                current_user=user,
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_finish_upload_400_when_no_chunks_present():
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()

    with patch.object(media_api.os.path, "exists", return_value=True):
        with patch.object(media_api.os, "listdir", return_value=[]):
            with pytest.raises(HTTPException) as exc:
                await media_api.finish_upload_generic(
                    upload_id=uuid4(),
                    file_name="img.jpg",
                    album_id=None,
                    db=db,
                    current_user=user,
                )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_finish_upload_happy_path_merges_and_saves(tmp_path):
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    photo_id = uuid4()

    fake_photo = SimpleNamespace(
        id=photo_id, owner_id=user.id, file_path=str(tmp_path / "saved.jpg")
    )

    fake_open = MagicMock()
    fake_buffer = MagicMock()
    fake_buffer.read.return_value = b""
    fake_open.return_value.__enter__.return_value = fake_buffer

    with patch.object(media_api, "add_tasks") as add_tasks:
        with patch.object(
            media_api.crud_album,
            "get_album",
            return_value=None,
        ):
            with patch.object(
                media_api.storage,
                "save_upload_file",
                return_value=str(tmp_path / "saved.jpg"),
            ):
                with patch.object(
                    media_api,
                    "save_and_create_photo",
                    return_value=fake_photo,
                ):
                    with patch.object(media_api.os.path, "exists", return_value=True):
                        with patch.object(
                            media_api.os,
                            "listdir",
                            return_value=["0", "1"],
                        ):
                            with patch("builtins.open", fake_open):
                                with patch.object(
                                    media_api.shutil, "rmtree"
                                ) as rmtree:
                                    result = await media_api.finish_upload_generic(
                                        upload_id=uuid4(),
                                        file_name="merged.jpg",
                                        album_id=None,
                                        db=db,
                                        current_user=user,
                                    )

    assert result is fake_photo
    add_tasks.assert_called_once()
    rmtree.assert_called_once()


# ---------------------------------------------------------------------------
# get_geojson
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_geojson_rejects_unknown_level():
    with pytest.raises(HTTPException) as exc:
        await media_api.get_geojson(level="neighborhood")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_geojson_returns_404_when_bundled_file_missing(tmp_path):
    """When the bundled GeoJSON file is absent, the endpoint surfaces a
    HTTP 404 (the source code wraps the FileNotFoundError)."""
    with patch.object(media_api, "BUNDLE_ROOT", str(tmp_path)):
        with patch.object(media_api.os.path, "exists", return_value=False):
            with pytest.raises(HTTPException) as exc:
                await media_api.get_geojson(level="province")
    assert exc.value.status_code == 404
    assert "GeoJSON" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_geojson_province_returns_fileresponse(tmp_path):
    """Without a parent filter, the endpoint streams the bundled
    province geojson via FileResponse."""
    from fastapi.responses import FileResponse

    bundle_dir = tmp_path / "resources" / "geo_data"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "中国_省.geojson").write_text("{}", encoding="utf-8")

    with patch.object(media_api, "BUNDLE_ROOT", str(tmp_path)):
        resp = await media_api.get_geojson(level="province")

    assert isinstance(resp, FileResponse)
    assert resp.path.endswith("中国_省.geojson")
    assert resp.media_type == "application/geo+json"


@pytest.mark.asyncio
async def test_get_geojson_city_filters_by_parent_province(tmp_path):
    import json as _json

    # City codes use synthetic values that actually start with the prefix the
    # endpoint computes from the parent province's GB code. Real-world codes
    # like 420100 (武汉) start with "42010", but the endpoint derives a 5-char
    # prefix "42000" from parent 420000 because it ends in "0000"; so for the
    # assertion to pass, the mock feature must declare a code beginning with
    # that exact prefix. The names stay realistic, only the codes are padded
    # to align with the source's prefix_len logic.
    city_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "武汉市", "gb": "420001"},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
            {
                "type": "Feature",
                "properties": {"name": "长沙市", "gb": "430001"},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
        ],
    }
    province_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "湖北省", "gb": "420000"},
                "geometry": {"type": "Polygon", "coordinates": []},
            }
        ],
    }
    bundle_dir = tmp_path / "resources" / "geo_data"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "中国_省.geojson").write_text(
        _json.dumps(province_geojson), encoding="utf-8"
    )
    (bundle_dir / "中国_市.geojson").write_text(
        _json.dumps(city_geojson), encoding="utf-8"
    )

    with patch.object(media_api, "BUNDLE_ROOT", str(tmp_path)):
        resp = await media_api.get_geojson(level="city", parent="湖北省")

    body = _json.loads(bytes(resp.body).decode("utf-8"))
    names = [f["properties"]["name"] for f in body["features"]]
    assert names == ["武汉市"]
