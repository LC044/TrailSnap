from datetime import datetime
from uuid import uuid4

import pytest
from app.crud.location import get_location_photos
from app.crud.location_stats import get_person_places
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import Photo, FileType
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.db.models.user import User
from app.service.relations import region_key

pytestmark = [pytest.mark.smoke, pytest.mark.module_location_stats]


@pytest.fixture
def records(face_sqlite_session):
    db = face_sqlite_session
    owner = User(id=uuid4(), username='place-owner', hashed_password='x')
    other = User(id=uuid4(), username='place-other', hashed_password='x')
    person = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name='小周', is_hidden=False, is_deleted=False)
    foreign = FaceIdentity(id=uuid4(), owner_id=other.id, identity_name='小周', is_hidden=False, is_deleted=False)
    scene = Scene(id=uuid4(), name='同名景区', owner_id=owner.id)
    foreign_scene = Scene(id=uuid4(), name='同名景区', owner_id=other.id)
    db.add_all([owner, other, person, foreign, scene, foreign_scene])
    db.flush()
    photos = []
    for i, (city, province, moment) in enumerate([
        ('杭州', '浙江', datetime(2024, 2, 29, 10)),
        ('杭州', '浙江', datetime(2024, 2, 29, 12)),
        ('苏州', '江苏', datetime(2024, 3, 2)),
        ('杭州', '浙江', None),
        ('杭州', '浙江', datetime(2025, 1, 1)),
        ('杭州', '浙江', datetime(2024, 2, 29)),
        ('杭州', '浙江', datetime(2024, 2, 29)),
        ('杭州', '浙江', datetime(2024, 2, 29)),
    ]):
        photo = Photo(id=uuid4(), owner_id=other.id if i == 5 else owner.id,
                      filename=f'p{i}.jpg', file_path=f'/p{i}.jpg', file_type=FileType.image,
                      photo_time=moment, is_deleted=i == 6)
        db.add(photo)
        db.flush()
        db.add(PhotoMetadata(photo_id=photo.id, country='中国', province=province,
                             city=city, district='同名区', scene_id=foreign_scene.id if i == 7 else scene.id))
        db.add(Face(photo_id=photo.id, face_identity_id=person.id, is_deleted=i == 7))
        photos.append(photo)
    # A duplicated face must not inflate photo counts.
    db.add(Face(photo_id=photos[0].id, face_identity_id=person.id, is_deleted=False))
    db.add(Face(photo_id=photos[0].id, face_identity_id=foreign.id, is_deleted=False))
    db.commit()
    return db, owner, other, person, foreign, photos, scene, foreign_scene


def test_person_places_counts_unique_photos_days_and_preserves_undated(records):
    db, owner, _, person, _, _, _, _ = records
    result = get_person_places(db, owner.id, person.id)
    assert result.total_photos == 5
    assert result.total_places == 2
    assert result.total_days == 3
    hangzhou = result.places[0]
    assert (hangzhou.name, hangzhou.photo_count, hangzhou.record_days) == ('杭州', 4, 2)
    assert hangzhou.first_date == '2024-02-29'
    assert hangzhou.last_date == '2025-01-01'


def test_person_places_date_and_parent_filter_matches_drilldown(records):
    db, owner, _, person, _, photos, _, _ = records
    result = get_person_places(db, owner.id, person.id, 'city', '2024-02-01', '2024-02-29', '浙江')
    assert (result.total_photos, result.total_days, result.total_places) == (2, 1, 1)
    place = result.places[0]
    details = get_location_photos(db, owner.id, place.name, 'city', start_date='2024-02-01',
                                 end_date='2024-02-29', place_key=place.place_key, person_id=person.id)
    assert {p.id for p in details} == {photos[0].id, photos[1].id}
    assert len(get_location_photos(db, owner.id, place.name, 'city', skip=1, limit=1,
                                  start_date='2024-02-01', end_date='2024-02-29',
                                  place_key=place.place_key, person_id=person.id)) == 1


def test_same_named_districts_are_distinct_and_drilldown_is_exact(records):
    db, owner, _, person, _, _, _, _ = records
    result = get_person_places(db, owner.id, person.id, 'district')
    assert result.total_places == 2
    assert len({p.place_key for p in result.places}) == 2
    place = next(p for p in result.places if p.parent_label == '江苏 · 苏州')
    details = get_location_photos(db, owner.id, place.name, 'district', place_key=place.place_key, person_id=person.id)
    assert len(details) == 1
    assert details[0].metadata_info.city == '苏州'


@pytest.mark.parametrize('state', ['foreign', 'hidden', 'deleted', 'missing'])
def test_person_scope_is_enforced_for_aggregate_and_drilldown(records, state):
    db, owner, other, person, foreign, _, _, _ = records
    identity = foreign.id if state == 'foreign' else uuid4() if state == 'missing' else person.id
    if state == 'hidden': person.is_hidden = True
    if state == 'deleted': person.is_deleted = True
    db.commit()
    assert get_person_places(db, owner.id, identity).total_photos == 0
    assert get_location_photos(db, owner.id, '杭州', 'city', person_id=identity) == []


def test_scene_stats_keep_ids_and_ignore_foreign_owned_scene(records):
    db, owner, _, person, _, photos, scene, foreign_scene = records
    # Make the only foreign-scene face active; it must still be excluded.
    db.query(Face).filter(Face.photo_id == photos[7].id).update({'is_deleted': False})
    db.commit()
    result = get_person_places(db, owner.id, person.id, 'scene')
    assert result.total_places == 1
    assert result.places[0].scene_id == str(scene.id)
    assert result.total_photos == 5
    assert get_location_photos(db, owner.id, foreign_scene.name, 'scene', scene_id=foreign_scene.id, person_id=person.id) == []


def test_person_place_api_returns_envelope_and_rejects_invalid_inputs(records):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.location_stats import router
    from app.api.deps import get_current_user
    from app.dependencies import get_db
    db, owner, _, person, _, _, _, _ = records
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(app) as client:
        response = client.get('/person-places', params={'person_id': str(person.id), 'level': 'city'})
        assert response.status_code == 200
        payload = response.json()
        assert payload['code'] == 0
        assert payload['data']['total_photos'] == 5
        assert client.get('/person-places', params={'person_id': 'bad'}).status_code == 422
        assert client.get('/person-places', params={'person_id': str(person.id), 'level': 'bad'}).status_code == 422
        reverse = client.get('/person-places', params={'person_id': str(person.id), 'start_date': '2024-03-01', 'end_date': '2024-02-29'})
        assert reverse.json()['code'] == 400



def test_top_people_are_ranked_by_distinct_location_photos_and_bounded(records):
    from app.crud.location_stats import get_top_person_places
    db, owner, _, person, _, photos, _, _ = records
    additions = [FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name=f'同伴{i}', is_hidden=False, is_deleted=False) for i in range(7)]
    db.add_all(additions)
    db.flush()
    for identity in additions:
        for photo in photos[:3]:
            db.add(Face(photo_id=photo.id, face_identity_id=identity.id, is_deleted=False))
        db.add(Face(photo_id=photos[0].id, face_identity_id=identity.id, is_deleted=False))
    additions[-1].is_hidden = True
    additions[-2].is_deleted = True
    db.commit()
    result = get_top_person_places(db, owner.id)
    assert len(result) == 5
    assert result[0].person_id == str(person.id)
    assert [p.total_photos for p in result] == [5, 3, 3, 3, 3]
    assert {p.person_id for p in result}.isdisjoint({str(additions[-1].id), str(additions[-2].id)})
    assert all(p.cover_photo_id in {str(photo.id) for photo in photos} for p in result)
    filtered = get_top_person_places(db, owner.id, 'city', '2024-02-01', '2024-02-29', '浙江')
    assert all(p.total_photos == 2 and p.total_days == 1 for p in filtered)
    assert all(p.total_places == 1 for p in filtered)
    assert get_top_person_places(db, owner.id, parent_region='无记录地区') == []
