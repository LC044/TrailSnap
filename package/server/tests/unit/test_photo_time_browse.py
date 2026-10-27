"""Exercise actual SQL for both timeline dimensions on an isolated SQLite database."""
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from app.crud.photo import get_all_photos, get_timeline_stats
from app.db.models.photo import Photo, FileType
from app.schemas.album import TimelineStats

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture
def library(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    rows = [
        Photo(id=UUID(int=1), owner_id=owner, _file_path='/a.jpg', filename='a', file_type=FileType.image,
              photo_time=datetime(2020, 5, 31, 23, 59, 59), upload_time=datetime(2026, 10, 1)),
        Photo(id=UUID(int=2), owner_id=owner, _file_path='/b.jpg', filename='b', file_type=FileType.image,
              photo_time=datetime(2020, 6, 1), upload_time=datetime(2026, 10, 1)),
        Photo(id=UUID(int=3), owner_id=owner, _file_path='/c.jpg', filename='c', file_type=FileType.image,
              photo_time=None, upload_time=datetime(2026, 9, 30)),
        Photo(id=UUID(int=4), owner_id=owner, _file_path='/deleted.jpg', file_type=FileType.image,
              photo_time=datetime(2020, 6, 1), is_deleted=True),
        Photo(id=UUID(int=5), owner_id=uuid4(), _file_path='/other.jpg', file_type=FileType.image,
              photo_time=datetime(2020, 6, 1)),
    ]
    db.add_all(rows)
    db.flush()
    return db, owner


@pytest.mark.parametrize('field,expected', [('photo_time', [(2020, 6, 1), (2020, 5, 1), (0, 0, 1)]),
                                         ('upload_time', [(2026, 10, 2), (2026, 9, 1)])])
def test_timeline_covers_counts_and_user_isolation(library, field, expected):
    db, owner = library
    stats = get_timeline_stats(db, user_id=owner, time_field=field, include_covers=True)
    parsed = TimelineStats.model_validate(stats)
    assert parsed.total_photos == 3
    assert [(m['year'], m['month'], m['count']) for m in stats['months']] == expected
    assert sum(item['count'] for item in stats['timeline']) == 3
    if field == 'upload_time':
        assert stats['months'][0]['cover']['id'] == UUID(int=2)


def test_bucket_query_and_stable_pagination(library):
    db, owner = library
    kwargs = dict(user_id=owner, order_by='upload_time', time_field='upload_time', browse_year=2026, browse_month=10)
    assert [p.id.int for p in get_all_photos(db, **kwargs)] == [2, 1]
    assert [p.id.int for p in get_all_photos(db, skip=1, limit=1, **kwargs)] == [1]
    assert [p.id.int for p in get_all_photos(db, user_id=owner, browse_year=0)] == [3]
    assert [p.id.int for p in get_all_photos(db, user_id=owner, browse_year=2020, browse_month=5)] == [1]


def test_capture_year_filter_keeps_its_meaning_when_sorting_by_added_time(library):
    db, owner = library
    stats = get_timeline_stats(db, user_id=owner, years=[2020], time_field='upload_time', include_covers=True)
    assert stats['total_photos'] == 2
    assert [(m['year'], m['month'], m['count']) for m in stats['months']] == [(2026, 10, 2)]


def test_unknown_only_library_and_microsecond_year_boundary(library):
    db, owner = library
    unknown = get_timeline_stats(db, user_id=owner, ids=[UUID(int=3)], include_covers=True)
    assert TimelineStats.model_validate(unknown).time_range == {'start': None, 'end': None}
    assert unknown['months'][0]['year'] == 0
    a, b = db.get(Photo, UUID(int=1)), db.get(Photo, UUID(int=2))
    a.photo_time = datetime(2020, 12, 31, 23, 59, 59, 999999)
    b.photo_time = datetime(2021, 1, 1)
    db.flush()
    assert [p.id.int for p in get_all_photos(db, user_id=owner, browse_year=2020, browse_month=12)] == [1]
    assert [p.id.int for p in get_all_photos(db, user_id=owner, browse_year=2021, browse_month=1)] == [2]
