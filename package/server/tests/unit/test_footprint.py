"""Execute footprint SQL against an isolated SQLite database, never user data."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import location as location_api
from app.crud.footprint import get_footprint, get_footprint_photos, get_map_routes, parse_bbox
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


@pytest.fixture
def footprint_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def owner():
    return uuid4()


@pytest.fixture
def photo(footprint_db, owner):
    def add(*, city="成都市", province="四川省", country="中国", lat=30.67, lng=104.06,
            at="2024-01-01T12:00:00", deleted=False, user=None, metadata=True, district=""):
        item = Photo(
            id=uuid4(), owner_id=user or owner, filename="footprint.jpg", file_path="/isolated/footprint.jpg",
            file_type=FileType.image, size=123, is_deleted=deleted,
            photo_time=datetime.fromisoformat(at) if isinstance(at, str) else at,
        )
        footprint_db.add(item)
        if metadata:
            footprint_db.add(PhotoMetadata(photo_id=item.id, country=country, province=province,
                                          city=city, district=district, latitude=lat, longitude=lng))
        footprint_db.flush()
        return item
    return add


def test_owner_deleted_and_invalid_gps_are_excluded_from_all_map_features(footprint_db, photo, owner):
    visible = photo()
    photo(user=uuid4(), city="其他人的城市")
    photo(deleted=True, city="已删除的城市")
    photo(lat=91, city="错误纬度")
    photo(lng=181, city="错误经度")
    photo(lat=None, city="缺少坐标")
    photo(metadata=False)

    result = get_footprint(footprint_db, owner)
    assert result["summary"] == dict(photo_count=5, gps_photo_count=1, province_count=1,
                                      city_count=1, country_count=1, visit_count=1)
    assert [city["cover_id"] for city in result["cities"]] == [str(visible.id)]
    assert result["timeline"] == [{"year": 2024, "photo_count": 5, "city_count": 1}]
    assert result["routes"] == []


def test_year_uses_exclusive_end_and_timeline_keeps_other_years(footprint_db, photo, owner):
    photo(at="2023-12-31T23:59:59.999999", city="Before")
    first = photo(at="2024-01-01T00:00:00")
    last = photo(at="2024-12-31T23:59:59.999999")
    photo(at="2025-01-01T00:00:00", city="After")
    photo(at=None, city="Undated")

    result = get_footprint(footprint_db, owner, year=2024)
    assert result["years"] == [2023, 2024, 2025]
    assert result["summary"]["photo_count"] == result["summary"]["gps_photo_count"] == 2
    assert result["cities"][0]["first_at"] == first.photo_time
    assert result["cities"][0]["last_at"] == last.photo_time
    assert result["cities"][0]["cover_id"] == str(last.id)
    assert [row["photo_count"] for row in result["timeline"]] == [1, 2, 1]


def test_routes_preserve_order_and_break_after_seven_days(footprint_db, photo, owner):
    photo(city="A", at="2024-01-01T10:00:00", lng=100)
    photo(city="A", at="2024-01-01T11:00:00", lng=101)
    photo(city="B", at="2024-01-02T12:00:00", lng=102)
    photo(city="A", at="2024-01-03T12:00:00", lng=103)
    photo(city="C", at="2024-01-10T12:00:00", lng=104)
    photo(city="D", at="2024-01-17T12:00:01", lng=105)
    photo(city="D", at="2024-02-20T12:00:00", lng=106)

    result = get_footprint(footprint_db, owner)
    assert [(r["from_name"], r["to_name"]) for r in result["routes"]] == [("A", "B"), ("B", "A"), ("A", "C")]
    assert result["routes"][0]["from"] == [100.0, 30.67]
    assert result["routes"][0]["to"] == [102.0, 30.67]
    assert result["routes"][0]["to"] == result["routes"][1]["from"]
    assert result["routes"][1]["to"] == result["routes"][2]["from"]
    assert result["summary"]["visit_count"] == 6
    assert {c["name"]: c["visit_count"] for c in result["cities"]} == {"A": 2, "B": 1, "C": 1, "D": 2}


def test_simultaneous_photos_do_not_invent_direction(footprint_db, photo, owner):
    photo(city="A")
    photo(city="B")
    assert get_footprint(footprint_db, owner)["routes"] == []


def test_same_named_cities_and_details_are_separated_by_country_and_province(footprint_db, photo, owner):
    target = photo(city="Springfield", country="US", province="Illinois")
    photo(city="Springfield", country="US", province="Massachusetts")
    photo(city="Springfield", country="CA", province="Illinois")
    photo(city="Springfield", country="US", province="Illinois", user=uuid4())
    photo(city="Springfield", country="US", province="Illinois", deleted=True)
    old = photo(city="Springfield", country="US", province="Illinois", at="2023-01-01")

    result = get_footprint(footprint_db, owner, year=2024)
    assert result["summary"]["city_count"] == 3
    assert result["summary"]["province_count"] == 3
    assert result["summary"]["country_count"] == 2
    city = next(item for item in result["cities"] if item["country"] == "US" and item["province"] == "Illinois")
    assert [p.id for p in get_footprint_photos(footprint_db, owner, city["id"], 2024)] == [target.id]
    assert [p.id for p in get_footprint_photos(footprint_db, owner, city["id"], skip=1, limit=1)] == [old.id]
    assert get_footprint_photos(footprint_db, uuid4(), city["id"]) == []


def test_unknown_places_keep_real_gps_and_do_not_inflate_city_counts(footprint_db, photo, owner):
    photo(city="", province="", country="", lat=20.01, lng=30.01)
    latest = photo(city="", province="", country="", lat=20.02, lng=30.02, at="2024-02-01")
    photo(city="", province="", country="", lat=-20.01, lng=-30.01)
    result = get_footprint(footprint_db, owner)
    assert result["summary"]["city_count"] == result["summary"]["province_count"] == result["summary"]["country_count"] == 0
    assert len(result["cities"]) == 2
    city = next(item for item in result["cities"] if item["lat"] > 0)
    assert (city["lat"], city["lng"], city["cover_id"]) == (20.02, 30.02, str(latest.id))
    assert len(get_footprint_photos(footprint_db, owner, city["id"])) == 2


def test_antimeridian_bbox_filters_features_without_changing_stats(footprint_db, photo, owner):
    photo(city="West", lat=10, lng=179, at="2024-01-01")
    photo(city="East", lat=10, lng=-179, at="2024-01-02")
    photo(city="Outside", lat=10, lng=100, at="2024-01-03")
    photo(city="Outside2", lat=10, lng=101, at="2024-01-04")
    result = get_footprint(footprint_db, owner, bbox="170,-20,-170,20")
    assert {city["name"] for city in result["cities"]} == {"West", "East"}
    assert result["summary"]["city_count"] == 4
    assert len(result["routes"]) == 2  # Includes an edge with one visible endpoint.
    assert result["sampled"] is False
    assert get_footprint(footprint_db, owner, bbox="0,0,1,1")["cities"] == []


def test_representative_coordinate_is_not_an_average_across_antimeridian(footprint_db, photo, owner):
    photo(city="Island", lat=10, lng=179, at="2024-01-01")
    photo(city="Island", lat=10, lng=-179, at="2024-01-02")
    result = get_footprint(footprint_db, owner)
    assert result["cities"][0]["lng"] == -179


def test_sampling_keeps_counts_and_only_original_edges(footprint_db, photo, owner):
    start = datetime(2024, 1, 1)
    for index in range(207):
        photo(city=f"City {index:03}", at=start + timedelta(hours=index))
    result = get_footprint(footprint_db, owner, max_points=200)
    assert result["sampled"] is True
    assert len(result["cities"]) == len(result["routes"]) == 200
    assert result["summary"]["photo_count"] == result["summary"]["visit_count"] == result["summary"]["city_count"] == 207
    assert result["timeline"][0]["city_count"] == 207
    assert result["routes"][0]["from_name"] == "City 000"
    assert result["routes"][-1]["to_name"] == "City 206"
    for route in result["routes"]:
        assert int(route["to_name"].split()[1]) - int(route["from_name"].split()[1]) == 1


def test_map_routes_cover_selected_history_without_inventing_edges(footprint_db, photo, owner):
    photo(city="Before", at="2023-12-31T23:00:00")
    start = datetime(2024, 1, 1)
    for index in range(61):
        photo(city=f"City {index:03}", at=start + timedelta(hours=index))
    photo(city="After", at="2024-02-01T00:00:00")

    routes = get_map_routes(footprint_db, owner, date(2024, 1, 1), date(2024, 1, 31), max_points=50)
    assert len(routes) == 50
    assert routes[0]["from_name"] == "City 000"
    assert routes[-1]["to_name"] == "City 060"
    assert all(int(route["to_name"].split()[1]) - int(route["from_name"].split()[1]) == 1 for route in routes)
    assert get_map_routes(footprint_db, owner, date(2024, 2, 1), date(2024, 2, 1)) == []


@pytest.mark.parametrize("bbox", ["1,2,3", "nan,0,1,2", "inf,0,1,2", "181,0,1,2", "0,5,1,2", "0,-91,1,2", "a,0,1,2"])
def test_invalid_bbox_is_rejected(bbox):
    with pytest.raises(ValueError):
        parse_bbox(bbox)


def test_empty_account_returns_complete_zero_shape(footprint_db, owner):
    result = get_footprint(footprint_db, owner)
    assert result["cities"] == result["routes"] == result["years"] == result["timeline"] == []
    assert set(result["summary"].values()) == {0}
    assert result["sampled"] is False


def test_http_contract_pagination_and_validation(footprint_db, photo, owner):
    photo(city="A", at="2024-01-01")
    target = photo(city="B", at="2024-01-02")
    app = FastAPI()
    app.include_router(location_api.router, prefix="/locations")
    app.dependency_overrides[location_api.get_db] = lambda: footprint_db
    app.dependency_overrides[location_api.deps.get_current_user] = lambda: SimpleNamespace(id=owner)
    with TestClient(app) as client:
        body = client.get("/locations/footprint").json()
        assert body["code"] == 0
        assert body["data"]["routes"][0]["from"] == [104.06, 30.67]
        map_routes = client.get("/locations/map-routes", params={"start_date": "2024-01-01", "end_date": "2024-01-02"}).json()
        assert map_routes["code"] == 0
        assert [(route["from_name"], route["to_name"]) for route in map_routes["data"]] == [("A", "B")]
        city_id = next(city["id"] for city in body["data"]["cities"] if city["name"] == "B")
        photos = client.get("/locations/footprint/photos", params={"city_id": city_id, "limit": 1}).json()
        assert photos["code"] == 0
        assert [item["id"] for item in photos["data"]] == [str(target.id)]
        assert "file_path" not in photos["data"][0]
        assert client.get("/locations/footprint", params={"bbox": "nan,0,1,2"}).json()["code"] == 422
        assert client.get("/locations/footprint/photos", params={"city_id": "bad!"}).json()["code"] == 422
        assert client.get("/locations/footprint", params={"year": 9999}).status_code == 422
        assert client.get("/locations/footprint", params={"max_points": 199}).status_code == 422
        assert client.get("/locations/map-routes", params={"max_points": 49}).status_code == 422
        assert client.get("/locations/footprint/photos", params={"city_id": city_id, "skip": -1}).status_code == 422
