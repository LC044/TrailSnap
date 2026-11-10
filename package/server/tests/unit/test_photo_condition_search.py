"""Condition browsing must count and paginate the same owner-scoped photos."""
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.user import User
from app.db.models.photo import Photo, FileType
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.ocr import OCR
from app.db.models.face import Face, FaceIdentity
from app.db.models.album import Album
from app.db.models.tag import PhotoTag
from app.db.models.scene import Scene
from app.crud.photo import get_all_photos, get_timeline_stats, get_filter_options

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def library():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        owner, other = uuid4(), uuid4()
        db.add_all([User(id=owner, username='search-owner', hashed_password='x'),
                    User(id=other, username='search-other', hashed_password='x')])
        photos = []
        # More than a search page, inserted oldest first, with unknown dates.
        for i in range(63):
            photo = Photo(id=uuid4(), owner_id=other if i == 60 else owner,
                          filename=f'{i}.jpg', file_path=f'/photos/{i}.jpg',
                          file_type=FileType.image, is_deleted=i == 61,
                          photo_time=datetime(2025, 1, i % 28 + 1) if i != 62 else None,
                          upload_time=datetime(2026, 11, 1))
            db.add(photo)
            db.add(PhotoMetadata(photo_id=photo.id, city='西安市' if i != 59 else '西安市附近'))
            photos.append(photo)
        db.commit()
        yield db, owner, photos
    engine.dispose()


def test_location_counts_covers_and_paging_share_exact_predicate(library):
    db, owner, photos = library
    filters = dict(user_id=owner, search_type='location', search_text='西安市')
    stats = get_timeline_stats(db, include_covers=True, **filters)
    rows = get_all_photos(db, limit=50, **filters) + get_all_photos(db, skip=50, limit=50, **filters)
    assert stats['total_photos'] == len(rows) == 60
    assert len({p.id for p in rows}) == 60
    assert rows[-1].photo_time is None
    assert [p.photo_time for p in rows[:-1]] == sorted([p.photo_time for p in rows[:-1]], reverse=True)
    assert sum(day['count'] for day in stats['timeline']) == 60
    january = get_all_photos(db, browse_year=2025, browse_month=1, limit=100, **filters)
    assert len(january) == 59
    assert get_all_photos(db, browse_year=0, **filters)[0].id == photos[62].id


def test_ocr_duplicates_and_literal_wildcards(library):
    db, owner, photos = library
    db.add_all([OCR(photo_id=photos[0].id, text='100%完成'),
                OCR(photo_id=photos[0].id, text='100%完成'),
                OCR(photo_id=photos[1].id, text='100分完成')])
    db.commit()
    filters = dict(user_id=owner, search_type='ocr', search_text='100%')
    assert get_timeline_stats(db, **filters)['total_photos'] == 1
    assert [p.id for p in get_all_photos(db, **filters)] == [photos[0].id]


def test_date_bounds_remain_capture_filters_when_sort_changes(library):
    db, owner, _ = library
    filters = dict(user_id=owner, search_type='date', start_time=datetime(2025, 1, 1),
                   end_time=datetime(2025, 1, 2, 23, 59, 59, 999999), time_field='upload_time')
    stats = get_timeline_stats(db, **filters)
    rows = get_all_photos(db, order_by='upload_time', browse_year=2026, browse_month=11, **filters)
    assert stats['total_photos'] == len(rows) > 0
    assert all(p.photo_time.day <= 2 for p in rows)


@pytest.mark.parametrize('kind', ['person', 'album', 'tag', 'scene', 'filename', 'folder'])
def test_other_explicit_conditions_share_timeline_and_detail_scope(library, kind):
    db, owner, photos = library
    photo = photos[0]
    name = '明确条件'
    if kind == 'person':
        identity = FaceIdentity(id=uuid4(), owner_id=owner, identity_name=name)
        db.add(identity)
        db.add_all([Face(photo_id=photo.id, face_identity_id=identity.id),
                    Face(photo_id=photo.id, face_identity_id=identity.id)])
    elif kind == 'album':
        photo.albums.append(Album(id=uuid4(), owner_id=owner, name=name))
    elif kind == 'tag':
        photo.tags.append(PhotoTag(id=uuid4(), owner_id=owner, tag_name=name))
    elif kind == 'scene':
        scene = Scene(id=uuid4(), name=name)
        db.add(scene)
        photo.metadata_info.scene_id = scene.id
    elif kind == 'filename':
        name = photo.filename
    else:
        name = '/photos/trip_100%'
        photo.file_path = name + '/a.jpg'
        photos[1].file_path = '/photos/trip_100extra/b.jpg'
    db.commit()
    filters = dict(user_id=owner, search_type=kind, search_text=name)
    assert get_timeline_stats(db, include_covers=True, **filters)['total_photos'] == 1
    assert [p.id for p in get_all_photos(db, **filters)] == [photo.id]


def test_same_location_or_and_other_groups_and(library):
    db, owner, photos = library
    photos[59].metadata_info.city = '三门峡市'
    person = FaceIdentity(id=uuid4(), owner_id=owner, identity_name='小王')
    db.add(person)
    for photo in photos[:2] + [photos[59]]:
        db.add(Face(photo_id=photo.id, face_identity_id=person.id))
        photo.tags.append(PhotoTag(id=uuid4(), owner_id=owner, tag_name='风景'))
    db.commit()
    filters = dict(user_id=owner, search_type='location', search_text='西安市',
                   cities=['三门峡市'], people=['小王'], categories=['风景'])
    rows = get_all_photos(db, limit=100, **filters)
    assert {p.id for p in rows} == {photos[i].id for i in [0, 1, 59]}
    assert get_timeline_stats(db, include_covers=True, **filters)['total_photos'] == 3


@pytest.mark.parametrize('kind,key', [('person', 'people'), ('tag', 'categories')])
def test_search_condition_merges_with_same_group(library, kind, key):
    db, owner, photos = library
    for i, name in enumerate(['甲', '乙']):
        if kind == 'person':
            identity = FaceIdentity(id=uuid4(), owner_id=owner, identity_name=name)
            db.add(identity)
            db.add(Face(photo_id=photos[i].id, face_identity_id=identity.id))
        else:
            photos[i].tags.append(PhotoTag(id=uuid4(), owner_id=owner, tag_name=name))
    db.commit()
    filters = dict(user_id=owner, search_type=kind, search_text='甲', **{key: ['乙']})
    assert {p.id for p in get_all_photos(db, **filters)} == {p.id for p in photos[:2]}
    assert get_timeline_stats(db, **filters)['total_photos'] == 2


def test_date_search_and_years_are_alternatives(library):
    db, owner, photos = library
    photos[0].photo_time = datetime(2024, 6, 1)
    db.commit()
    filters = dict(user_id=owner, search_type='date', start_time=datetime(2024, 6, 1),
                   end_time=datetime(2024, 6, 2), years=[2025])
    assert get_timeline_stats(db, **filters)['total_photos'] == 60
    assert len(get_all_photos(db, limit=100, **filters)) == 60


def test_people_and_category_options_stay_owner_scoped(library):
    db, owner, photos = library
    db.add_all([FaceIdentity(owner_id=owner, identity_name='我的人物'),
                FaceIdentity(owner_id=photos[60].owner_id, identity_name='其他人物'),
                FaceIdentity(owner_id=owner, identity_name='已删除', is_deleted=True)])
    photos[0].tags.append(PhotoTag(owner_id=owner, tag_name='我的类别'))
    photos[60].tags.append(PhotoTag(owner_id=photos[60].owner_id, tag_name='其他类别'))
    db.commit()
    options = get_filter_options(db, owner)
    assert options['people'] == [options['person_options'][0]['id']]
    assert options['categories'] == ['我的类别']
    assert [person['name'] for person in options['person_options']] == ['我的人物']
    assert options['person_options'][0]['photo_id'] is None


def test_person_options_include_owned_face_crop(library):
    db, owner, photos = library
    identity = FaceIdentity(owner_id=owner, identity_name='头像人物')
    db.add(identity)
    db.flush()
    face = Face(photo_id=photos[0].id, face_identity_id=identity.id, face_rect=[0.1, 0.2, 0.4, 0.6])
    db.add(face)
    db.flush()
    identity.default_face_id = face.id
    db.commit()
    option = get_filter_options(db, owner)['person_options'][0]
    assert option['photo_id'] == str(photos[0].id)
    assert option['face_rect'] == [0.1, 0.2, 0.4, 0.6]
    photos[0].is_deleted = True
    db.commit()
    assert get_filter_options(db, owner)['person_options'][0]['photo_id'] is None


def test_all_people_are_independent_sorted_and_have_fallback_avatars(library):
    db, owner, photos = library
    people = [FaceIdentity(owner_id=owner, identity_name=name) for name in ['未命名', '未命名', '', None, '小王']]
    db.add_all(people)
    db.flush()
    for index, person in enumerate(people):
        for photo in photos[:index + 1]:
            db.add(Face(photo_id=photo.id, face_identity_id=person.id, face_rect=[0.1, 0.2, 0.4, 0.6]))
    # Duplicate face detections must not inflate the photo count.
    db.add(Face(photo_id=photos[0].id, face_identity_id=people[0].id))
    db.add(Face(photo_id=photos[61].id, face_identity_id=people[0].id))
    db.add(Face(photo_id=photos[60].id, face_identity_id=people[0].id))
    db.add(Face(photo_id=photos[8].id, face_identity_id=people[0].id, is_deleted=True))
    db.commit()
    options = get_filter_options(db, owner)['person_options']
    assert [row['id'] for row in options] == [str(person.id) for person in reversed(people)]
    assert [row['photo_count'] for row in options] == [5, 4, 3, 2, 1]
    assert [row['name'] for row in options] == ['小王'] + ['未命名'] * 4
    assert all(row['photo_id'] and row['face_rect'] for row in options)
    for person, count in zip(people, range(1, 6)):
        filters = dict(user_id=owner, people=[str(person.id)])
        assert len(get_all_photos(db, **filters)) == count
        assert get_timeline_stats(db, **filters)['total_photos'] == count
    filters = dict(user_id=owner, search_type='person', search_text='小王', people=[str(people[0].id)])
    assert get_timeline_stats(db, **filters)['total_photos'] == 5
