"""2026-11-19 nightly coverage for ``app/crud/photo_paths.py``.

``escape_like``, ``stored_prefixes``, ``under_directory`` and
``under_browse_folder`` were never referenced by any test file.  They build the
SQL predicates that match photos by folder, so the escaping of LIKE
wildcards and the historical relative-path prefixes are asserted here.
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from app.crud.photo_paths import (
    escape_like,
    normalized_file_path,
    stored_prefixes,
    under_browse_folder,
    under_directory,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _sql(expression) -> str:
    return str(expression.compile(dialect=postgresql.dialect(paramstyle="numeric_dollar"), compile_kwargs={"literal_binds": True}))


def test_escape_like_escapes_the_wildcards():
    assert escape_like("a%b") == "a\\%b"
    assert escape_like("a_b") == "a\\_b"


def test_escape_like_escapes_backslashes():
    assert escape_like("a\\b") == "a\\\\b"


def test_escape_like_leaves_an_ordinary_path_untouched():
    assert escape_like("/photos/2026") == "/photos/2026"


def test_stored_prefixes_returns_nothing_for_an_empty_directory():
    assert stored_prefixes("") == []
    assert stored_prefixes(None) == []


def test_stored_prefixes_ends_with_a_slash():
    prefixes = stored_prefixes("/photos/2026")

    assert prefixes
    assert all(prefix.endswith("/") for prefix in prefixes)


def test_stored_prefixes_normalises_windows_separators():
    assert "/photos/2026/" in stored_prefixes("\\photos\\2026")


def test_stored_prefixes_includes_the_relative_form_of_an_absolute_path():
    prefixes = stored_prefixes("/photos/2026")

    assert any(not prefix.startswith("/") for prefix in prefixes)


def test_stored_prefixes_of_a_relative_directory_keeps_it_as_is():
    assert "uploads/2026/" in stored_prefixes("uploads/2026")


def test_under_directory_builds_one_like_per_stored_prefix():
    sql = _sql(under_directory("/photos/2026"))

    assert "LIKE" in sql
    assert "/photos/2026/%" in sql


def test_under_directory_is_false_for_an_empty_directory():
    assert under_directory("") is False


def test_under_browse_folder_matches_the_folder_and_its_children():
    sql = _sql(under_browse_folder("photos/2026"))

    assert "LIKE" in sql
    assert "photos/2026/%" in sql


def test_under_browse_folder_strips_surrounding_slashes():
    sql = _sql(under_browse_folder("/photos/2026/"))

    assert "photos/2026/%" in sql


def test_under_browse_folder_escapes_wildcards():
    sql = _sql(under_browse_folder("photos/20%"))

    assert "ESCAPE" in sql
    assert "20\\\\%" in sql


def test_the_normalized_path_replaces_windows_separators():
    sql = _sql(normalized_file_path())

    assert "replace" in sql.lower()

