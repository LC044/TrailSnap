"""Portable-library path resolution for the photo path column."""
import pytest
from sqlalchemy.dialects import sqlite

from app.db.models.photo import Photo
from app.service.storage_paths import photo_path_expression

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


def test_legacy_servers_keep_the_indexed_path_column(monkeypatch):
    monkeypatch.delenv("TS_DESKTOP", raising=False)
    monkeypatch.delenv("TS_DESKTOP_PORTABLE", raising=False)
    assert photo_path_expression(Photo) is Photo._file_path


def test_portable_servers_resolve_the_stored_relative_path(monkeypatch, tmp_path):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_PORTABLE", "1")
    monkeypatch.setenv("TS_DESKTOP_ROOT", str(tmp_path))
    compiled = str(photo_path_expression(Photo).compile(dialect=sqlite.dialect()))
    assert "storage_root_id" in compiled
    assert "storage_relative_path" in compiled
    assert "storage_roots" in compiled


def test_the_hybrid_expression_matches_the_portable_builder(monkeypatch, tmp_path):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_PORTABLE", "1")
    monkeypatch.setenv("TS_DESKTOP_ROOT", str(tmp_path))
    assert str(Photo.file_path.compile(dialect=sqlite.dialect())) == str(
        photo_path_expression(Photo).compile(dialect=sqlite.dialect())
    )
