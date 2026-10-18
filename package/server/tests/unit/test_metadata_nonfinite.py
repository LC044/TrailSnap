"""Invalid GPS must not poison an entire import completion transaction."""
import asyncio
import json
from datetime import datetime
from uuid import uuid4

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app.db.models.photo import FileType
from app.db.models.task import Task, TaskType
from app.schemas.photo import PhotoCreate
from app.schemas.metadata import PhotoMetadataCreate
from app.service.tasks import basic
from app.utils import exif
from test_basic_pipeline_performance import seed

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.mark.parametrize("lat,lng", [
    (float('nan'), 120), (30, float('inf')), (float('-inf'), 120),
    (91, 120), (-91, 120), (30, 181), (30, -181),
    (IFDRational(0, 0), 120),
])
def test_invalid_gps_is_ignored_before_geocoding(lat, lng, monkeypatch):
    monkeypatch.setattr(exif, 'reverse_geocode', lambda *_: pytest.fail('Invalid GPS reached geocoder'))
    gps = exif.get_gps_info({'GPSInfo': {
        'GPSLatitude': (lat, 0, 0), 'GPSLatitudeRef': 'N',
        'GPSLongitude': (lng, 0, 0), 'GPSLongitudeRef': 'E',
    }})
    assert gps is None
    meta = {}
    # Video/container GPS and cached metadata use this same boundary.
    exif._attach_location_details(meta, {'latitude': lat, 'longitude': lng}, True)
    assert meta == {'location': None}


@pytest.mark.parametrize("lat,lng", [(0, 0), (90, 180), (-90, -180), (30, 120)])
def test_valid_gps_boundaries_are_preserved(lat, lng):
    gps = {'latitude': lat, 'longitude': lng}
    meta = {}
    exif._attach_location_details(meta, gps, False)
    assert meta['location'] == gps


def test_cpu_extraction_produces_strict_json_with_nonfinite_metadata(tmp_path, monkeypatch):
    source = tmp_path / 'photo.jpg'
    Image.new('RGB', (10, 10)).save(source)
    monkeypatch.setattr(basic.exif, 'extract_metadata', lambda *a, **k: {
        'photo_time': datetime(2020, 1, 1),
        'location': {'latitude': float('nan'), 'longitude': 120},
        'nested': {'values': (float('inf'), float('-inf'), 1.5)},
    })
    monkeypatch.setattr(basic.storage, 'generate_thumbnail', lambda *a, **k: None)
    result = basic.process_basic_cpu_job(str(source), uuid4(), str(tmp_path), str(uuid4()))
    assert result['success'], result
    raw = result['raw_metadata']
    assert raw['location'] is None
    assert raw['nested']['values'] == [None, None, 1.5]
    assert raw['photo_time'].startswith('2020-01-01')
    json.dumps(raw, allow_nan=False)


def test_nonfinite_completion_does_not_block_other_photos(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    uid, photos = seed(db, count=2)
    # SQLite normally accepts NaN in JSON; enforce the PostgreSQL constraint.
    monkeypatch.setattr(db.get_bind().dialect, '_json_serializer',
                        lambda value: json.dumps(value, allow_nan=False))
    items = []
    for index, photo in enumerate(photos):
        raw = {'location': {'latitude': float('nan') if index == 0 else 30, 'longitude': 120},
               'nested': [float('inf'), {'value': float('-inf')}], 'width': 320}
        items.append({'status': 'completed', 'result': {'photo_create_data': {
            'photo_id': photo.id, 'file_path': photo.file_path, 'user_id': str(uid),
            'photo': PhotoCreate(filename=photo.filename, file_type=FileType.image, size=1),
            'metadata': PhotoMetadataCreate(), 'is_pre_created': True, 'raw_metadata': raw,
        }}})
    asyncio.run(basic.BasicTaskStrategy().handle_completion(None, items, db))
    db.commit()
    db.expire_all()
    tasks = db.query(Task).filter(Task.type == TaskType.EXTRACT_METADATA).all()
    assert len(tasks) == 2
    stored = {task.payload['photo_id']: task.payload['raw_metadata'] for task in tasks}
    assert stored[str(photos[0].id)]['location'] is None
    assert stored[str(photos[1].id)]['location'] == {'latitude': 30, 'longitude': 120}
    for raw in stored.values():
        assert raw['nested'] == [None, {'value': None}]
        assert raw['width'] == 320
        json.dumps(raw, allow_nan=False)
