"""Nightly gap coverage: `media_io` admission decorator.

`media_io` wraps a job so that the IO it performs holds a disk-budget slot for
the volumes of the paths it touches.  The decorator resolves the path
arguments from the wrapped callable's signature, therefore keyword and
positional invocation must behave identically.
"""

from contextlib import contextmanager

import pytest

from app.service import disk_budget as disk_budget_module
from app.service.disk_budget import media_io


pytestmark = pytest.mark.smoke


@pytest.fixture()
def recorded_slots(monkeypatch):
    recorded = []

    @contextmanager
    def fake_slots(*paths):
        recorded.append(paths)
        yield

    monkeypatch.setattr(disk_budget_module.disk_budget, "slots", fake_slots)
    return recorded


def test_media_io_admits_the_declared_path(recorded_slots):
    @media_io("file_path")
    def job(file_path):
        return file_path.upper()

    assert job(file_path="C:/photos/a.jpg") == "C:/PHOTOS/A.JPG"
    assert recorded_slots == [("C:/photos/a.jpg",)]


def test_media_io_admits_every_declared_path(recorded_slots):
    @media_io("file_path", "target_path")
    def copy(file_path, target_path):
        return target_path

    assert copy("C:/a.jpg", "D:/b.jpg") == "D:/b.jpg"
    assert recorded_slots == [("C:/a.jpg", "D:/b.jpg")]


def test_media_io_releases_the_slot_when_the_body_raises(recorded_slots):
    @media_io("file_path")
    def failing(file_path):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        failing(file_path="C:/photos/a.jpg")

    # The slot must be released, so a second job can still be admitted.
    @media_io("file_path")
    def ok(file_path):
        return "ok"

    assert ok(file_path="C:/photos/b.jpg") == "ok"
    assert len(recorded_slots) == 2


def test_media_io_ignores_paths_that_are_not_declared(recorded_slots):
    @media_io("file_path")
    def job(file_path, unrelated=None):
        return unrelated

    assert job(file_path="C:/a.jpg", unrelated="keep") == "keep"
    assert recorded_slots == [("C:/a.jpg",)]
