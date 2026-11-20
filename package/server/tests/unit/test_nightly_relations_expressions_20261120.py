"""Region and UUID membership expressions used by the relations graph."""
import pytest
from sqlalchemy import String
from sqlalchemy.dialects import postgresql

from app.db.models.photo import Photo
from app.service.relations import _region_expr, _uuid_expr

pytestmark = [pytest.mark.smoke, pytest.mark.module_search]


def _sql(expression):
    return str(expression.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_uuid_expression_prefixes_the_kind_and_strips_dashes():
    sql = _sql(_uuid_expr("person", Photo.id))
    assert "person:" in sql
    assert "replace" in sql.lower()


def test_uuid_expression_casts_the_column_to_text():
    sql = _sql(_uuid_expr("photo", Photo.id))
    assert "CAST" in sql.upper()


def test_region_expression_contains_the_region_prefix():
    sql = _sql(_region_expr("province"))
    assert "place:region:province:" in sql


def test_region_expression_folds_lower_levels():
    # A city level key also contains the country and province segments.
    sql = _sql(_region_expr("city"))
    assert "place:region:city:" in sql
    assert sql.count("trim") >= 3
