"""Nightly coverage for ``apply_filter_task_bg`` in ``app/api/settings.py``.

The 2026-10-28 backend coverage scan ranked ``api/settings.py`` at 81.2%
(117 missed statements).  The largest untouched block is the background
"apply file filter" task: the size/dimension SQL filter, the filename
regex filter and the NAS folder-exclusion filter -- roughly 110 statements
that decide which photos get permanently deleted from a user's library.

Deleting user data is exactly the kind of path that must not regress
silently, so this file drives all three filters against a real SQLite
session and asserts **which** photos survive:

* the SQL filter removes photos that are too small / too narrow / too short;
* the filename filter removes photos whose basename matches a regex, and
  silently skips an invalid regex instead of aborting the whole task;
* the folder filter removes photos living under an excluded NAS folder
  (``@eaDir`` and friends) and matches on any path component;
* every removed photo leaves an ``IndexLog`` audit row;
* the task is owner-scoped -- another user's photos are never touched;
* a disabled filter with no folder exclusions is a no-op.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.index_log import IndexLog
from app.db.models.photo import FileType, Photo
from app.db.models.user import User


pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _photo(owner, path, size=1024 * 1024, width=4000, height=3000):
    return Photo(
        id=uuid4(), owner_id=owner, filename=path.rsplit("/", 1)[-1],
        file_path=path, file_type=FileType.image, is_deleted=False,
        size=size, width=width, height=height,
    )


def _run(db, filter_settings, user_id=None):
    """Run ``apply_filter_task_bg`` against ``db`` with the given filter config."""
    from app.api import settings as settings_api

    merged = MagicMock()
    merged.filter = filter_settings

    class _Session:
        """Delegate to the real session, but keep it open for the assertions."""

        def __init__(self, session):
            self._session = session

        def __getattr__(self, name):
            return getattr(self._session, name)

        def close(self):
            # The task closes its session in the finally block; the fixture owns
            # the lifetime of the real one.
            return None

    with patch.object(settings_api, "SessionLocal", lambda: _Session(db)), \
         patch.object(settings_api.config_manager, "merge_user_settings", lambda user_settings: merged):
        settings_api.apply_filter_task_bg(user_id)
    return db


def _filter(**overrides):
    """A filter config object with every knob disabled by default."""
    config = MagicMock()
    config.enable = False
    config.min_size_kb = 0
    config.min_width = 0
    config.min_height = 0
    config.filename_patterns = []
    config.exclude_folders = []
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


# ---------------------------------------------------------------------------
# no-op paths
# ---------------------------------------------------------------------------


def test_a_disabled_filter_without_folder_exclusions_deletes_nothing(db):
    """Edge: the task must not touch the library when there is nothing to do."""
    owner = uuid4()
    db.add(User(id=owner, username="filter-off", hashed_password="x"))
    photo = _photo(owner, "photos/a.jpg", size=1, width=1, height=1)
    db.add(photo)
    db.commit()

    _run(db, _filter(), str(owner))

    db.expire_all()
    assert db.query(Photo).count() == 1
    assert db.query(IndexLog).count() == 0


# ---------------------------------------------------------------------------
# SQL size / dimension filter
# ---------------------------------------------------------------------------


def test_the_sql_filter_removes_small_and_narrow_photos(db):
    """Happy path: photos under the size / width / height thresholds go."""
    owner = uuid4()
    db.add(User(id=owner, username="filter-sql", hashed_password="x"))
    tiny = _photo(owner, "photos/tiny.jpg", size=512, width=4000, height=3000)
    narrow = _photo(owner, "photos/narrow.jpg", size=1024 * 1024, width=100, height=3000)
    short = _photo(owner, "photos/short.jpg", size=1024 * 1024, width=4000, height=50)
    keeper = _photo(owner, "photos/keeper.jpg", size=10 * 1024 * 1024, width=4000, height=3000)
    db.add_all([tiny, narrow, short, keeper])
    db.commit()

    _run(db, _filter(enable=True, min_size_kb=10, min_width=256, min_height=256), str(owner))

    db.expire_all()
    remaining = {row.file_path for row in db.query(Photo).all()}
    assert remaining == {"photos/keeper.jpg"}
    # Every removal leaves an audit row.
    assert db.query(IndexLog).filter(IndexLog.action == "deleted").count() == 3


def test_the_sql_filter_is_owner_scoped(db):
    """Error guard: another user's small photo must survive."""
    owner, stranger = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="filter-owner", hashed_password="x"),
        User(id=stranger, username="filter-stranger", hashed_password="x"),
    ])
    mine = _photo(owner, "photos/mine.jpg", size=1)
    theirs = _photo(stranger, "photos/theirs.jpg", size=1)
    db.add_all([mine, theirs])
    db.commit()

    _run(db, _filter(enable=True, min_size_kb=10), str(owner))

    db.expire_all()
    assert {row.file_path for row in db.query(Photo).all()} == {"photos/theirs.jpg"}


# ---------------------------------------------------------------------------
# filename regex filter
# ---------------------------------------------------------------------------


def test_the_filename_filter_removes_matching_photos(db):
    """Happy path: a basename regex selects the photo to delete."""
    owner = uuid4()
    db.add(User(id=owner, username="filter-name", hashed_password="x"))
    bad = _photo(owner, "photos/IMG_thumb.jpg")
    good = _photo(owner, "photos/IMG_full.jpg")
    db.add_all([bad, good])
    db.commit()

    _run(db, _filter(enable=True, filename_patterns=[r"_thumb\.jpg$"]), str(owner))

    db.expire_all()
    assert {row.file_path for row in db.query(Photo).all()} == {"photos/IMG_full.jpg"}


def test_an_invalid_filename_regex_is_skipped_and_the_rest_still_runs(db):
    """Error: one broken pattern must not abort the whole filter task."""
    owner = uuid4()
    db.add(User(id=owner, username="filter-badregex", hashed_password="x"))
    bad = _photo(owner, "photos/IMG_thumb.jpg")
    good = _photo(owner, "photos/IMG_full.jpg")
    db.add_all([bad, good])
    db.commit()

    _run(db, _filter(enable=True, filename_patterns=["[unclosed", r"_thumb\.jpg$"]), str(owner))

    db.expire_all()
    # The valid pattern still applied.
    assert {row.file_path for row in db.query(Photo).all()} == {"photos/IMG_full.jpg"}


def test_an_empty_filename_pattern_is_ignored(db):
    """Edge: a blank pattern is skipped rather than matching everything."""
    owner = uuid4()
    db.add(User(id=owner, username="filter-emptypattern", hashed_password="x"))
    photo = _photo(owner, "photos/keep.jpg")
    db.add(photo)
    db.commit()

    _run(db, _filter(enable=True, filename_patterns=["", None]), str(owner))

    db.expire_all()
    assert db.query(Photo).count() == 1


# ---------------------------------------------------------------------------
# folder exclusion filter
# ---------------------------------------------------------------------------


def test_the_folder_filter_removes_photos_under_an_excluded_folder(db):
    """Happy path: a photo inside ``@eaDir`` is removed."""
    owner = uuid4()
    db.add(User(id=owner, username="filter-folder", hashed_password="x"))
    inside = _photo(owner, "nas/photos/@eaDir/thumb.jpg")
    outside = _photo(owner, "nas/photos/real.jpg")
    db.add_all([inside, outside])
    db.commit()

    _run(db, _filter(exclude_folders=["@eaDir"]), str(owner))

    db.expire_all()
    assert {row.file_path for row in db.query(Photo).all()} == {"nas/photos/real.jpg"}


def test_the_folder_filter_matches_any_path_component(db):
    """Edge: the pattern is tested against every component of the path."""
    owner = uuid4()
    db.add(User(id=owner, username="filter-component", hashed_password="x"))
    middle = _photo(owner, "nas/#recycle/photos/a.jpg")
    last = _photo(owner, "nas/photos/b.jpg")
    db.add_all([middle, last])
    db.commit()

    _run(db, _filter(exclude_folders=["#recycle"]), str(owner))

    db.expire_all()
    assert {row.file_path for row in db.query(Photo).all()} == {"nas/photos/b.jpg"}


def test_an_invalid_folder_pattern_is_skipped(db):
    """Error: a broken folder regex is logged and ignored."""
    owner = uuid4()
    db.add(User(id=owner, username="filter-badfolder", hashed_password="x"))
    photo = _photo(owner, "nas/photos/keep.jpg")
    db.add(photo)
    db.commit()

    _run(db, _filter(exclude_folders=["[unclosed", "@eaDir"]), str(owner))

    db.expire_all()
    assert db.query(Photo).count() == 1


def test_the_folder_filter_applies_even_when_the_file_filter_is_disabled(db):
    """The exclusion is structural and must not be gated by the enable flag."""
    owner = uuid4()
    db.add(User(id=owner, username="filter-folderonly", hashed_password="x"))
    inside = _photo(owner, "nas/@eaDir/a.jpg")
    outside = _photo(owner, "nas/b.jpg")
    db.add_all([inside, outside])
    db.commit()

    _run(db, _filter(enable=False, exclude_folders=["@eaDir"]), str(owner))

    db.expire_all()
    assert {row.file_path for row in db.query(Photo).all()} == {"nas/b.jpg"}


# ---------------------------------------------------------------------------
# failure handling
# ---------------------------------------------------------------------------


def test_a_failure_inside_the_task_is_rolled_back_and_not_raised(db):
    """Error: an unexpected failure is logged and rolled back, never propagated.

    The session is opened *before* the guarded block, so the failure has to
    happen while the task is already working -- here while the user settings
    are merged.
    """
    owner = uuid4()
    db.add(User(id=owner, username="filter-error", hashed_password="x"))
    photo = _photo(owner, "photos/keep.jpg", size=1)
    db.add(photo)
    db.commit()

    from app.api import settings as settings_api

    class _Session:
        def __init__(self, session):
            self._session = session

        def __getattr__(self, name):
            return getattr(self._session, name)

        def close(self):
            return None

    with patch.object(settings_api, "SessionLocal", lambda: _Session(db)), \
         patch.object(settings_api.config_manager, "merge_user_settings",
                      MagicMock(side_effect=RuntimeError("settings broken"))):
        # Must not raise.
        settings_api.apply_filter_task_bg(str(owner))

    db.expire_all()
    assert db.query(Photo).count() == 1


