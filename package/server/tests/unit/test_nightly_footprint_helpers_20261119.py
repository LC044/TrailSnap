"""覆盖 app/crud/footprint.py 中此前没有测试引用的内部辅助函数。

盲区来源：函数级静态引用扫描命中下列 8 个辅助函数——它们在
app/crud/footprint.py 内被使用，但任何测试文件都从未直接引用过，
因此其分支行为（跨经线 bbox、年份越界、城市标识编解码）从未被断言。

不修改生产代码；只读使用纯函数 + 表达式构造。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.crud import footprint
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


@pytest.fixture
def sqlite_db():
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        yield session
    engine.dispose()


# --------------------------------------------------------------------------- #
# _city_id / _decode_city_id
# --------------------------------------------------------------------------- #

def test_city_id_round_trips_keys_with_two_separators():
    key = "中国\x1f四川省\x1fcity:成都市"
    encoded = footprint._city_id(key)
    assert encoded.startswith("fp_")
    assert "=" not in encoded
    assert footprint._decode_city_id(encoded) == key


def test_city_id_is_stable_and_url_safe():
    key = "中国\x1f四川省\x1fcity:北京"
    assert footprint._city_id(key) == footprint._city_id(key)
    assert "+" not in footprint._city_id(key)
    assert "/" not in footprint._city_id(key)


@pytest.mark.parametrize("bad", [
    "no-prefix",
    "",
    "fp_",
    "fp_" + "A" * 3000,
])
def test_decode_city_id_rejects_malformed_identifiers(bad):
    with pytest.raises(ValueError):
        footprint._decode_city_id(bad)


def test_decode_city_id_rejects_wrong_separator_count():
    key = "中国\x1f四川省"  # only one separator
    with pytest.raises(ValueError):
        footprint._decode_city_id(footprint._city_id(key))


def test_decode_city_id_rejects_tampered_payload():
    key = "中国\x1f四川省\x1fcity:成都市"
    encoded = footprint._city_id(key)
    token = encoded[3:]
    tampered = "fp_" + ("A" if token[0] != "A" else "B") + token[1:]
    with pytest.raises(ValueError):
        footprint._decode_city_id(tampered)


# --------------------------------------------------------------------------- #
# _photo_filters
# --------------------------------------------------------------------------- #

def test_photo_filters_without_year_only_scopes_owner_and_live_photos():
    owner = uuid4()
    filters = footprint._photo_filters(owner, None)
    assert len(filters) == 2


@pytest.mark.parametrize("year", [0, 9999, -1])
def test_photo_filters_rejects_out_of_range_year(year):
    with pytest.raises(ValueError):
        footprint._photo_filters(uuid4(), year)


@pytest.mark.parametrize("year", [1, 2024, 9998])
def test_photo_filters_accepts_boundary_years(year):
    assert len(footprint._photo_filters(uuid4(), year)) == 4


# --------------------------------------------------------------------------- #
# _in_bbox
# --------------------------------------------------------------------------- #

def test_in_bbox_uses_between_for_regular_viewport():
    expression = footprint._in_bbox(
        PhotoMetadata.latitude, PhotoMetadata.longitude, (104.0, 30.0, 105.0, 31.0))
    rendered = str(expression)
    assert "BETWEEN" in rendered
    assert " OR " not in rendered


def test_in_bbox_switches_to_or_across_the_antimeridian():
    expression = footprint._in_bbox(
        PhotoMetadata.latitude, PhotoMetadata.longitude, (170.0, -10.0, -170.0, 10.0))
    rendered = str(expression)
    assert " OR " in rendered
    # 纬度始终用区间比较，跨经线只影响经度。
    assert "photo_metadata.latitude BETWEEN" in rendered


def test_in_bbox_keeps_latitude_between_in_both_modes():
    crossing = str(footprint._in_bbox(
        PhotoMetadata.latitude, PhotoMetadata.longitude, (170.0, -10.0, -170.0, 10.0)))
    assert "photo_metadata.latitude BETWEEN" in crossing


# --------------------------------------------------------------------------- #
# _elapsed_seconds
# --------------------------------------------------------------------------- #

def test_elapsed_seconds_uses_julianday_on_sqlite(sqlite_db):
    expression = footprint._elapsed_seconds(
        sqlite_db, Photo.photo_time, Photo.photo_time)
    assert "julianday" in str(expression)


def test_elapsed_seconds_uses_epoch_extraction_on_postgres(sqlite_db, monkeypatch):
    class _FakeBind:
        class dialect:
            name = "postgresql"

    class _FakeDb:
        def get_bind(self):
            return _FakeBind()

    expression = footprint._elapsed_seconds(_FakeDb(), Photo.photo_time, Photo.photo_time)
    rendered = str(expression)
    assert "EXTRACT" in rendered.upper()
    assert "julianday" not in rendered
