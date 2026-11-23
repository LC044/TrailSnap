"""SQL expressions that group photos into places and bound GPS values."""
import pytest
from sqlalchemy.dialects import sqlite

from app.crud.footprint import _gps_filters, _place_expressions

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _sql(expression):
    return str(expression.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


def test_place_expressions_return_the_five_place_columns():
    assert len(_place_expressions()) == 5


def test_place_key_prefers_the_city_and_falls_back_to_a_gps_cell():
    key, _country, _province, _city, _name = _place_expressions()
    compiled = _sql(key)
    assert "city:" in compiled
    assert "gps:" in compiled


def test_place_key_joins_country_province_and_location():
    key, country, province, city, name = _place_expressions()
    compiled = _sql(key)
    assert _sql(country) in compiled
    assert _sql(province) in compiled
    assert _sql(city) in compiled
    assert _sql(name)


def test_place_name_prefers_city_then_district_then_province():
    _key, _country, _province, _city, name = _place_expressions()
    compiled = _sql(name)
    assert "GPS" in compiled
    assert "district" in compiled


def test_gps_filters_bound_both_coordinates():
    filters = _gps_filters()
    assert len(filters) == 2
    compiled = " AND ".join(_sql(item) for item in filters)
    assert compiled.count("BETWEEN") == 2
    assert "-90" in compiled and "90" in compiled
    assert "-180" in compiled and "180" in compiled
