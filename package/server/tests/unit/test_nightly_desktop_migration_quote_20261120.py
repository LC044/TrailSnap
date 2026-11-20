"""Identifier quoting for the desktop library migration."""
import pytest

from app.utils.desktop_data_migration import _quote

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_quote_wraps_identifier_in_double_quotes():
    assert _quote("table") == '"table"'


def test_quote_doubles_embedded_quotes():
    assert _quote('a"b') == '"a""b"'


def test_quote_leaves_plain_identifiers_untouched():
    assert _quote("photo_metadata") == '"photo_metadata"'
