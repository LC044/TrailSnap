"""2026-09-14 nightly tests for the current backend coverage priorities.

Targets selected from the latest Cobertura scan:

* ``app.crud.photo`` -- smart-album SQLite cosine ordering and metadata pre-create.
* ``app.api.media`` -- backup source-time validation and GeoJSON clean-name fallback.
* ``app.service.tasks.organize`` -- category copy, nested location move, time filter.
* ``app.service.tasks.tickets`` -- batch flight/train persistence and invalid payloads.
"""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import media as media_api
from app.crud import photo as crud_photo
from app.db.models.photo import FileType
from app.service.tasks import organize as organize_task
from app.service.tasks import tickets as tickets_task


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# app/service/tasks/tickets.py
# ---------------------------------------------------------------------------


class _FakeAIResponse:
    status = 200

    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return "AI error"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeAISession:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, *_args, **_kwargs):
        return _FakeAIResponse(self._payload)


def _ticket_photo(tmp_path, owner_id):
    return SimpleNamespace(
        id=uuid4(),
        owner_id=owner_id,
        file_type=FileType.image,
        file_path=str(tmp_path / "ticket.jpg"),
        filename="ticket.jpg",
        processed_tasks={},
        photo_time=datetime(2024, 5, 1, 10, 0),
    )


def _ticket_task(photo, owner_id):
    return SimpleNamespace(
        id=uuid4(),
        type="RECOGNIZE_TICKET",
        owner_id=owner_id,
        payload={"photo_id": str(photo.id)},
    )


async def _run_ticket_batch(tmp_path, ticket_payloads):
    owner_id = uuid4()
    photo = _ticket_photo(tmp_path, owner_id)
    photo_file = tmp_path / "ticket.jpg"
    photo_file.write_bytes(b"jpeg")
    task = _ticket_task(photo, owner_id)

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [photo]
    config = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.test:8001"))
    schedule = {
        "total_mileage": 333,
        "total_time": 45,
        "stop_stations": [{"station_name": "北京南"}],
    }

    with (
        patch.object(tickets_task.storage, "get_available_photo_path", return_value=str(photo_file)),
        patch.object(tickets_task.config_manager, "get_user_config", return_value=config),
        patch.object(tickets_task.aiohttp, "ClientSession", return_value=_FakeAISession({
            "results": [{"tickets": ticket_payloads}]
        })),
        patch.object(tickets_task.crud_train_tickets, "delete_train_ticket_by_photo_id"),
        patch.object(tickets_task.crud_flight_tickets, "delete_flight_ticket_by_photo_id"),
        patch.object(
            tickets_task.crud_train_tickets,
            "create_train_ticket",
            return_value=SimpleNamespace(id=uuid4()),
        ) as create_train,
        patch.object(
            tickets_task.crud_flight_tickets,
            "create_flight_ticket",
            return_value=SimpleNamespace(id=uuid4()),
        ) as create_flight,
        patch.object(
            tickets_task,
            "calculate_ticket_mileage_and_time",
            new=AsyncMock(return_value=schedule),
        ) as calculate,
    ):
        results = await tickets_task.RecognizeTicketStrategy().process_batch(
            MagicMock(), [task], db
        )

    assert len(results) == 1
    return results[0], photo, db, create_train, create_flight, calculate


@pytest.mark.asyncio
async def test_ticket_batch_persists_flight_and_train_tickets(tmp_path):
    result, photo, _db, create_train, create_flight, calculate = await _run_ticket_batch(
        tmp_path,
        [
            {
                "type": "flight",
                "flight_code": "CA1234",
                "departure_city": "北京",
                "arrival_city": "上海",
                "datetime": "2024-05-01 08:30",
                "price": "￥660.5",
                "name": "张三",
            },
            {
                "type": "train",
                "train_code": "G123",
                "departure_station": "北京南",
                "arrival_station": "上海虹桥",
                "datetime": "05月01日 10:20",
                "price": "not-a-price",
                "name": "李四",
                "carriage": "05",
                "seat_num": "06F",
                "seat_type": "二等座",
            },
        ],
    )

    assert result["status"] == "completed"
    assert result["result"] == {"status": "success", "tickets_added": 2}

    flight = create_flight.call_args.args[1]
    assert flight.flight_code == "CA1234"
    assert flight.date_time == datetime(2024, 5, 1, 8, 30)
    assert flight.price == 660.5

    train = create_train.call_args.args[1]
    assert train.date_time == datetime(2024, 5, 1, 10, 20)
    assert train.price == 0.0
    assert train.total_mileage == 333
    assert train.total_running_time == 45
    assert json.loads(train.stop_stations) == [{"station_name": "北京南"}]
    calculate.assert_awaited_once()
    assert photo.processed_tasks["tickets"] is True


@pytest.mark.asyncio
async def test_ticket_batch_skips_invalid_ticket_payloads(tmp_path):
    result, photo, _db, create_train, create_flight, _calculate = await _run_ticket_batch(
        tmp_path,
        [
            {"type": "flight", "datetime": "2024-05-01 08:30"},
            {"type": "train", "datetime": "not-a-date"},
            {"type": "train", "datetime": "2024-05-01 08:30", "departure_station": "北京南"},
        ],
    )

    assert result["result"] == {"status": "success", "tickets_added": 0}
    create_train.assert_not_called()
    create_flight.assert_not_called()
    assert photo.processed_tasks["tickets"] is True


# ---------------------------------------------------------------------------
# app/api/media.py
# ---------------------------------------------------------------------------


def test_backup_check_validates_source_times_and_returns_hash_only_results():
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        media_api.check_mobile_backup_assets(
            {"keys": [], "source_times": {"key": "not-a-datetime"}},
            db=db,
            current_user=user,
        )
    assert exc.value.status_code == 400

    digest = "a" * 32
    with patch.object(
        media_api, "_existing_content_hashes", return_value=[digest]
    ) as existing_hashes:
        result = media_api.check_mobile_backup_assets(
            {"keys": [], "hashes": [digest.upper()]},
            db=db,
            current_user=user,
        )

    assert result.data == {
        "existing": [],
        "complete": [],
        "live_photos": [],
        "hashes": [digest],
    }
    existing_hashes.assert_called_once_with(db, user.id, [digest])


def test_backup_check_applies_source_time_to_matching_photo(tmp_path):
    user = SimpleNamespace(id=uuid4())
    image = tmp_path / "IMG_0001.jpg"
    image.write_bytes(b"image")
    upload_time = datetime(2026, 9, 14, 8, 0, 0)
    photo = SimpleNamespace(
        id=uuid4(),
        owner_id=user.id,
        backup_key="key",
        file_type=FileType.image,
        file_path=str(image),
        photo_time=upload_time,
        upload_time=upload_time,
        md5=None,
    )

    first_query = MagicMock()
    first_query.filter.return_value.all.return_value = [photo]
    second_query = MagicMock()
    second_query.filter.return_value.all.return_value = [photo]
    db = MagicMock()
    db.query.side_effect = [first_query, second_query]

    with (
        patch.object(media_api.storage, "get_live_photo_vide", return_value=None),
        patch.object(
            media_api,
            "_get_thumbnail_path",
            return_value=str(tmp_path / "missing.webp"),
        ),
        patch.object(media_api, "_existing_content_hashes", return_value=[]),
    ):
        result = media_api.check_mobile_backup_assets(
            {
                "keys": ["key"],
                "source_times": {"key": "2024-02-03T10:20:30Z"},
            },
            db=db,
            current_user=user,
        )

    assert photo.photo_time == datetime(2024, 2, 3, 10, 20, 30)
    assert result.data["existing"] == ["key"]
    assert result.data["complete"] == ["key"]
    db.commit.assert_called()


@pytest.mark.asyncio
async def test_geojson_uses_clean_parent_name_fallback(tmp_path):
    province = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "湖南省", "gb": "430000"}, "geometry": None}
        ],
    }
    city = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "长沙市", "gb": "430001"}, "geometry": None},
            {"type": "Feature", "properties": {"name": "南昌市", "gb": "360001"}, "geometry": None},
        ],
    }
    geo_dir = tmp_path / "resources" / "geo_data"
    geo_dir.mkdir(parents=True)
    (geo_dir / "中国_省.geojson").write_text(json.dumps(province), encoding="utf-8")
    (geo_dir / "中国_市.geojson").write_text(json.dumps(city), encoding="utf-8")

    with patch.object(media_api, "BUNDLE_ROOT", str(tmp_path)):
        response = await media_api.get_geojson(level="city", parent="湖南藏族")

    body = json.loads(bytes(response.body).decode("utf-8"))
    assert [item["properties"]["name"] for item in body["features"]] == ["长沙市"]


# ---------------------------------------------------------------------------
# app/crud/photo.py
# ---------------------------------------------------------------------------


def _save_photo_with_metadata(db):
    photo_id = uuid4()
    db_photo = SimpleNamespace(
        id=photo_id,
        file_type=FileType.image,
        photo_time=datetime(2026, 9, 14, 9, 30),
        md5=None,
    )
    extracted = {
        "photo_time": db_photo.photo_time,
        "exif_info": {"Make": b"Nikon", "Orientation": 1},
    }

    with (
        patch.object(crud_photo.storage, "generate_thumbnail"),
        patch.object(crud_photo.storage, "get_file_size", return_value=1024),
        patch.object(crud_photo.storage, "get_image_dimensions", return_value=(80, 60, None)),
        patch.object(crud_photo, "extract_metadata", return_value=extracted),
        patch.object(crud_photo, "create_photo", return_value=db_photo),
    ):
        result = crud_photo.save_and_create_photo(
            db,
            file_path="C:/photos/IMG_0001.jpg",
            file_name="IMG_0001.jpg",
            album_id=None,
            photo_id=photo_id,
            user_id=uuid4(),
        )
    return result, photo_id


def test_save_photo_precreates_metadata_and_serializes_bytes():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    result, photo_id = _save_photo_with_metadata(db)

    metadata = db.add.call_args.args[0]
    assert metadata.photo_id == photo_id
    assert "Nikon" in metadata.exif_info
    db.commit.assert_called_once()
    assert result.file_type == FileType.image


def test_save_photo_rolls_back_when_metadata_precreate_fails():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.add.side_effect = RuntimeError("metadata insert failed")

    result, _photo_id = _save_photo_with_metadata(db)

    db.rollback.assert_called_once()
    assert result.file_type == FileType.image


def test_get_photos_orders_sqlite_smart_album_by_cosine_distance():
    album = SimpleNamespace(type="smart", query_embedding=[1.0, 0.0])
    photo_a, photo_b, photo_c = SimpleNamespace(name="A"), SimpleNamespace(name="B"), SimpleNamespace(name="C")
    query = MagicMock()
    query.with_entities.return_value.all.return_value = [
        (photo_c, [0.0, 1.0]),
        (photo_b, [0.6, 0.8]),
        (photo_a, [1.0, 0.0]),
    ]
    db = MagicMock()
    db.bind.dialect.name = "sqlite"

    with (
        patch.object(crud_photo, "get_album", return_value=album),
        patch.object(crud_photo, "_build_album_query", return_value=query),
    ):
        result = crud_photo.get_photos(db, uuid4(), skip=0, limit=2)

    assert result == [photo_a, photo_b]


# ---------------------------------------------------------------------------
# app/service/tasks/organize.py
# ---------------------------------------------------------------------------


class _NewPhoto:
    owner_id = "owner_id"
    is_deleted = SimpleNamespace(is_=lambda value: ("is_deleted", value))
    tags = "tags"
    faces = "faces"
    metadata_info = "metadata_info"
    __table__ = SimpleNamespace(columns=[])

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _SourcePhoto:
    __table__ = SimpleNamespace(columns=[])

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _organize_task(payload):
    return SimpleNamespace(
        id=str(uuid4()),
        type="ORGANIZE_PHOTOS",
        owner_id=str(uuid4()),
        payload=payload,
        total_items=0,
        processed_items=0,
    )


def _organize_db(photos):
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.options.return_value = query
    query.all.return_value = photos
    db.query.return_value = query
    return db


def test_organize_category_copy_creates_one_record_per_tag(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image")
    photo = _SourcePhoto(
        file_path=str(source),
        filename="source.jpg",
        photo_time=None,
        upload_time=None,
        tags=[
            SimpleNamespace(tag_name="Travel", confidence=0.9),
            SimpleNamespace(tag_name="Family", confidence=0.8),
        ],
    )
    db = _organize_db([photo])
    worker = MagicMock()
    target = tmp_path / "organized"
    task = _organize_task({
        "target_root_path": str(target),
        "strategy": "category",
        "action": "copy",
    })

    with (
        patch.object(organize_task, "Photo", _NewPhoto),
        patch.object(organize_task, "joinedload", return_value=MagicMock()),
    ):
        result = asyncio.run(
            organize_task.OrganizePhotosStrategy().process(worker, task, db)
        )

    assert result == {"success_count": 2, "total_processed": 1}
    assert (target / "Travel" / "source.jpg").read_bytes() == b"image"
    assert (target / "Family" / "source.jpg").read_bytes() == b"image"
    assert source.read_bytes() == b"image"
    assert worker.get_instance.return_value.add_task.call_count == 2
    assert db.add.call_count == 2


def test_organize_location_move_uses_nested_admin_units(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image")
    photo = _SourcePhoto(
        file_path=str(source),
        filename="source.jpg",
        photo_time=None,
        upload_time=None,
        metadata_info=SimpleNamespace(province="浙江省", city="杭州市", district="西湖区"),
    )
    db = _organize_db([photo])
    target = tmp_path / "organized"
    task = _organize_task({
        "target_root_path": str(target),
        "strategy": "location",
        "action": "move",
        "location_granularity": "province_city_district",
        "location_format": "nested",
    })

    with (
        patch.object(organize_task, "Photo", _NewPhoto),
        patch.object(organize_task, "joinedload", return_value=MagicMock()),
    ):
        result = asyncio.run(
            organize_task.OrganizePhotosStrategy().process(MagicMock(), task, db)
        )

    expected = target / "浙江省" / "杭州市" / "西湖区" / "source.jpg"
    assert result == {"success_count": 1, "total_processed": 1}
    assert expected.read_bytes() == b"image"
    assert not source.exists()
    assert photo.file_path == str(expected)


def test_organize_time_range_skips_photo_outside_range(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image")
    photo = _SourcePhoto(
        file_path=str(source),
        filename="source.jpg",
        photo_time=datetime(2024, 3, 1, 10, 0),
        upload_time=None,
    )
    db = _organize_db([photo])
    target = tmp_path / "organized"
    task = _organize_task({
        "target_root_path": str(target),
        "strategy": "time",
        "action": "move",
        "time_granularity": "ym",
        "time_format": "flat",
        "time_range": ["2024-01-01 00:00:00", "2024-01-02"],
    })

    result = asyncio.run(
        organize_task.OrganizePhotosStrategy().process(MagicMock(), task, db)
    )

    assert result == {"success_count": 0, "total_processed": 1}
    assert task.processed_items == 1
    assert source.read_bytes() == b"image"
    assert not (target / "2024-03").exists()

