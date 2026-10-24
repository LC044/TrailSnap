"""Nightly coverage for the location branch of POST /toolbox/organize/preview-options.

location_granularity / location_format 的六种组合、以及「照片没有位置信息」时
补充「未知位置」这一段此前没有任何断言覆盖。本文件用真实 SQLite 会话补齐。
"""

import os
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import toolbox
from app.api.deps import get_current_user
from app.db.base import Base
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.dependencies import get_db


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture
def toolbox_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def add_photo(db, owner_id, province=None, city=None, district=None, with_metadata=True):
    photo = Photo(
        id=uuid4(), owner_id=owner_id, file_path=f"/{uuid4()}.jpg",
        photo_time=datetime(2025, 3, 1), file_type=FileType.image,
        image_type=ImageType.CAMERA, is_deleted=False, size=1024,
    )
    db.add(photo)
    if with_metadata:
        db.add(PhotoMetadata(
            photo_id=photo.id, province=province, city=city, district=district,
        ))
    db.commit()
    return photo


def _client(db, owner_id):
    app = FastAPI()
    app.include_router(toolbox.router, prefix="/toolbox")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner_id)
    return TestClient(app)


def _options(db, owner_id, **body):
    payload = {"strategy": "location"}
    payload.update(body)
    with _client(db, owner_id) as client:
        response = client.post("/toolbox/organize/preview-options", json=payload)
    assert response.status_code == 200
    return set(response.json()["data"]["options"])


@pytest.mark.parametrize("granularity,expected", [
    ("province", {"上海市"}),
    ("city", {"上海"}),
    ("district", {"黄浦区"}),
    ("province_city", {"上海市-上海"}),
    ("city_district", {"上海-黄浦区"}),
    ("province_city_district", {"上海市-上海-黄浦区"}),
])
def test_location_options_follow_requested_granularity(toolbox_session, granularity, expected):
    db = toolbox_session
    owner_id = uuid4()
    add_photo(db, owner_id, province="上海市", city="上海", district="黄浦区")

    assert _options(db, owner_id, location_granularity=granularity) == expected


def test_nested_format_joins_parts_with_path_separator(toolbox_session):
    db = toolbox_session
    owner_id = uuid4()
    add_photo(db, owner_id, province="上海市", city="上海", district="黄浦区")

    options = _options(
        db, owner_id,
        location_granularity="province_city",
        location_format="nested",
    )
    # nested 模式用 os.path.join 拼接，分隔符随平台（Windows 是 路径分隔符）。
    assert options == {os.path.join("上海市", "上海")}


def test_photo_without_metadata_is_reported_as_unknown_location(toolbox_session):
    db = toolbox_session
    owner_id = uuid4()
    add_photo(db, owner_id, province="上海市", city="上海", district="黄浦区")
    add_photo(db, owner_id, with_metadata=False)

    options = _options(db, owner_id, location_granularity="city")
    assert options == {"上海", "未知位置"}


def test_photo_with_blank_location_columns_is_reported_as_unknown(toolbox_session):
    db = toolbox_session
    owner_id = uuid4()
    add_photo(db, owner_id, province="", city=None, district="")

    options = _options(db, owner_id, location_granularity="city")
    assert options == {"未知位置"}


def test_other_owners_photos_do_not_contribute_options(toolbox_session):
    db = toolbox_session
    owner_id = uuid4()
    add_photo(db, uuid4(), province="广东省", city="广州", district="天河区")

    assert _options(db, owner_id, location_granularity="city") == set()
