"""Filter-option ordering helper for the photo list API."""
import pytest

from app.crud.photo import _sorted_by_usage

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_sorted_by_usage_orders_by_count_then_name():
    assert _sorted_by_usage([("b", 2), ("a", 2), ("c", 5)]) == ["c", "a", "b"]


def test_sorted_by_usage_handles_empty_rows():
    assert _sorted_by_usage([]) == []
