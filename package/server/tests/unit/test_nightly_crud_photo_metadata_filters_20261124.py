"""Nightly watch 2026-11-24: ``app/crud/photo.py`` 的元数据过滤分支盲区。

2026-11-24 的后端覆盖率报告里 ``crud/photo.py`` 为 94.9%，其中
第 672-698 行（城市 / 场景 / 省 / 国家 / 相机品牌 / 相机型号这六组元数据过滤
的「多选」与「单值模糊」两条分支）从未被执行过。

这些过滤条件直接决定照片搜索的结果集：单值走 ``ilike`` 模糊匹配，
多选走 ``in_`` 精确匹配，两条路径写错会让用户搜不到自己的照片。

这里用真实 SQLite 会话和真实数据验证过滤结果，而不是验证查询字符串。
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from app.crud import photo as photo_crud
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene


pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db(tmp_path):
    import app.db.models  # noqa: F401
    from app.db.base import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'crud-photo.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def owner_id():
    return uuid4()


def _photo_with_metadata(db, owner_id, name="a.jpg", city="杭州市", province="浙江省",
                         country="中国", make="Canon", model="EOS R5",
                         latitude=30.25, longitude=120.15, scene=None):
    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename=name,
        _file_path=f"/library/{name}",
        file_type=FileType.image,
        photo_time=datetime(2024, 5, 1, 10, 0),
        upload_time=datetime(2024, 5, 1, 10, 0),
        is_deleted=False,
    )
    db.add(photo)
    db.flush()
    metadata = PhotoMetadata(
        photo_id=photo.id,
        city=city,
        province=province,
        country=country,
        make=make,
        model=model,
        latitude=latitude,
        longitude=longitude,
    )
    if scene is not None:
        metadata.scene_id = scene.id
    db.add(metadata)
    db.commit()
    return photo


def _ids(result):
    return {row.id for row in result}


def test_filter_by_city_matches_a_partial_name(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, city="杭州市")

    result = photo_crud.get_all_photos(db, city="杭州")

    assert _ids(result) == {photo.id}


def test_filter_by_cities_uses_an_exact_match(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, city="杭州市")

    result = photo_crud.get_all_photos(db, cities=["杭州市"])

    assert _ids(result) == {photo.id}


def test_filter_by_cities_excludes_other_cities(db, owner_id):
    _photo_with_metadata(db, owner_id, name="a.jpg", city="杭州市")
    other = _photo_with_metadata(db, owner_id, name="b.jpg", city="北京市")

    result = photo_crud.get_all_photos(db, cities=["北京市"])

    assert _ids(result) == {other.id}


def test_filter_by_province(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, province="浙江省")

    result = photo_crud.get_all_photos(db, province="浙江")

    assert _ids(result) == {photo.id}


def test_filter_by_provinces(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, province="浙江省")

    result = photo_crud.get_all_photos(db, provinces=["浙江省"])

    assert _ids(result) == {photo.id}


def test_filter_by_country(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, country="中国")

    result = photo_crud.get_all_photos(db, country="中")

    assert _ids(result) == {photo.id}


def test_filter_by_countries(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, country="中国")

    result = photo_crud.get_all_photos(db, countries=["中国"])

    assert _ids(result) == {photo.id}


def test_filter_by_camera_make(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, make="Canon")

    result = photo_crud.get_all_photos(db, make="canon")

    assert _ids(result) == {photo.id}


def test_filter_by_makes(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, make="Canon")

    result = photo_crud.get_all_photos(db, makes=["Canon"])

    assert _ids(result) == {photo.id}


def test_filter_by_camera_model(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, model="EOS R5")

    result = photo_crud.get_all_photos(db, model="EOS")

    assert _ids(result) == {photo.id}


def test_filter_by_models(db, owner_id):
    photo = _photo_with_metadata(db, owner_id, model="EOS R5")

    result = photo_crud.get_all_photos(db, models=["EOS R5"])

    assert _ids(result) == {photo.id}


def test_filter_by_scene_name(db, owner_id):
    scene = Scene(name="西湖", description="杭州的湖")
    db.add(scene)
    db.commit()
    photo = _photo_with_metadata(db, owner_id, scene=scene)

    result = photo_crud.get_all_photos(db, scene="西湖")

    assert _ids(result) == {photo.id}


def test_filter_by_scenes(db, owner_id):
    scene = Scene(name="西湖", description="杭州的湖")
    db.add(scene)
    db.commit()
    photo = _photo_with_metadata(db, owner_id, scene=scene)

    result = photo_crud.get_all_photos(db, scenes=["西湖"])

    assert _ids(result) == {photo.id}


def test_filter_by_coordinates(db, owner_id):
    inside = _photo_with_metadata(db, owner_id, name="a.jpg", latitude=30.25, longitude=120.15)
    _photo_with_metadata(db, owner_id, name="b.jpg", latitude=40.00, longitude=116.40)

    result = photo_crud.get_all_photos(db, lat_min=30.0, lat_max=31.0)

    assert _ids(result) == {inside.id}


def test_combined_filters_only_return_matching_photos(db, owner_id):
    matched = _photo_with_metadata(db, owner_id, name="a.jpg", city="杭州市", make="Canon")
    _photo_with_metadata(db, owner_id, name="b.jpg", city="杭州市", make="Nikon")

    result = photo_crud.get_all_photos(db, city="杭州", make="Canon")

    assert _ids(result) == {matched.id}
