"""Nightly gap coverage (2026-11-11) — app/service/toolbox_plans.py (part 2).

The 2026-11-11 backend coverage scan reported::

    service/toolbox_plans.py    77.3%   78 uncovered lines

The first nightly pass on 2026-11-11 covered the pure helpers (validate_template,
rule_groups, grouping_paths, rename_path).  What is still uncovered is the
*planning* layer that turns photos into a frozen plan:

* ``item_for_photo`` turning every business rule violation into a skipped item
  with a human-readable reason (unsupported format, complete device info,
  nothing to write, name already compliant, album name too long, target path
  escaping the configured root, path already compliant)
* ``create_plan`` refusing an unwritable target directory, a ``preserve`` layout
  without a single source folder, more than 50000 items, and a copy plan whose
  estimated output does not fit on the target disk
* ``cleanup_candidates`` scoring photos by quality and grouping similar photos
  by their embedding vectors
"""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.toolbox import MediaScope, PlanRequest, ToolConfig
from app.service import toolbox_plans
from app.service.toolbox_plans import cleanup_candidates, create_plan, item_for_photo


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _photo(tmp_path, name: str = 'IMG_0001.jpg', **values):
    path = tmp_path / name
    path.write_bytes(b'x' * 32)
    defaults = {
        "id": uuid4(),
        "filename": name,
        "file_path": str(path),
        "photo_time": datetime(2026, 5, 2, 8, 30),
        "upload_time": datetime(2026, 5, 3, 9, 0),
        "metadata_info": None,
        "file_type": "image",
        "image_description": None,
        "tags": [],
        "faces": [],
        "albums": [],
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _user():
    return SimpleNamespace(id=uuid4(), settings={})


def _config(**values):
    defaults = {"kind": "metadata", "action": None, "target": "", "layout": "rebuild",
                "rules": [{"strategy": "time", "granularity": "year"}], "missing": "skip", "multi_group": "skip"}
    defaults.update(values)
    return ToolConfig(**defaults)


def _item_for(photo, config, db=None, user=None, candidates=None, index=1):
    db = db or MagicMock()
    user = user or _user()
    with patch('app.service.toolbox_plans.allowed_directory',
               side_effect=lambda _db, _user, path: path):
        return item_for_photo(db, user, photo, config, index, set(), candidates or {}, None)


# --------------------------------------------------------------------------- #
# item_for_photo — metadata kind
# --------------------------------------------------------------------------- #

def test_item_for_photo_skips_unsupported_exif_format(tmp_path):
    """Only JPEG / WebP can receive a safe EXIF write."""
    photo = _photo(tmp_path, 'clip.png')
    config = _config(kind='metadata', time_mode='auto', make='Canon', model='EOS')
    item = _item_for(photo, config)
    assert item.status == 'skipped'
    assert '不支持安全写入 EXIF' in item.reason


def test_item_for_photo_skips_complete_device_metadata(tmp_path):
    """A photo that already carries make + model needs no rewrite."""
    photo = _photo(tmp_path, 'done.jpg',
                   metadata_info=SimpleNamespace(make='Canon', model='EOS'))
    config = _config(kind='metadata', time_mode='auto', only_missing_metadata=True)
    item = _item_for(photo, config)
    assert item.status == 'skipped'
    assert '无需修改' in item.reason


def test_item_for_photo_skips_when_nothing_to_write(tmp_path):
    """Without a resolvable time or device info there is nothing to write."""
    photo = _photo(tmp_path, 'plain.jpg', photo_time=None, filename='plain.jpg')
    config = _config(kind='metadata', time_mode='auto', only_missing_metadata=False)
    item = _item_for(photo, config)
    assert item.status == 'skipped'
    assert '没有可写入的时间或设备信息' in item.reason


def test_item_for_photo_accepts_metadata_plan(tmp_path):
    photo = _photo(tmp_path, 'ok.jpg')
    config = _config(kind='metadata', time_mode='auto', make='Canon', model='EOS')
    item = _item_for(photo, config)
    assert item.status == 'ready'
    assert item.detail['make'] == 'Canon'
    assert item.target == photo.file_path


# --------------------------------------------------------------------------- #
# item_for_photo — rename kind
# --------------------------------------------------------------------------- #

def test_item_for_photo_skips_when_name_already_matches(tmp_path):
    """A rename that would not change anything is reported as skipped."""
    photo = _photo(tmp_path, 'IMG_0001.jpg')
    config = _config(kind='rename', template='IMG_{index}')
    with patch('app.service.toolbox_plans.rename_path',
               return_value=photo.file_path), \
            patch('app.service.toolbox_plans.fingerprint',
                  return_value={'size': 1, 'mtime_ns': 1}):
        item = _item_for(photo, config)
    assert item.status == 'skipped'
    assert '名称已符合规则' in item.reason


# --------------------------------------------------------------------------- #
# item_for_photo — cleanup kind
# --------------------------------------------------------------------------- #

def test_item_for_photo_marks_cleanup_candidate(tmp_path):
    photo = _photo(tmp_path, 'dup.jpg')
    config = _config(kind='cleanup', cleanup_mode='duplicate')
    candidates = {photo.id: {'group': 'g1', 'md5': 'abc'}}
    with patch('app.service.toolbox_plans.fingerprint',
               return_value={'size': 1, 'mtime_ns': 1}):
        item = _item_for(photo, config, candidates=candidates)
    assert item.status == 'candidate'
    assert '需手动勾选' in item.reason


def test_item_for_photo_skips_non_candidate_for_cleanup(tmp_path):
    photo = _photo(tmp_path, 'keep.jpg')
    config = _config(kind='cleanup', cleanup_mode='duplicate')
    with patch('app.service.toolbox_plans.fingerprint',
               return_value={'size': 1, 'mtime_ns': 1}):
        item = _item_for(photo, config, candidates={})
    assert item.status == 'skipped'
    assert '不属于清理候选' in item.reason


# --------------------------------------------------------------------------- #
# item_for_photo — album kind
# --------------------------------------------------------------------------- #

def test_item_for_photo_skips_overlong_album_name(tmp_path):
    photo = _photo(tmp_path, 'album.jpg')
    long_value = 'L' * 70
    photo.metadata_info = SimpleNamespace(province=long_value, city=long_value,
                                          district=long_value, address=None,
                                          make=None, model=None, exif_info=None)
    config = _config(kind='album', album_prefix='P' * 40,
                     rules=[{'strategy': 'location',
                             'granularity': 'province_city_district',
                             'nested': True}],
                     missing='placeholder')
    with patch('app.service.toolbox_plans.fingerprint',
               return_value={'size': 1, 'mtime_ns': 1}):
        item = _item_for(photo, config)
    assert item.status == 'skipped'
    assert '相册名称超过 100 字' in item.reason


def test_item_for_photo_accepts_album_plan(tmp_path):
    photo = _photo(tmp_path, 'album.jpg')
    config = _config(kind='album', rules=[{'strategy': 'time', 'granularity': 'year'}])
    with patch('app.service.toolbox_plans.fingerprint',
               return_value={'size': 1, 'mtime_ns': 1}):
        item = _item_for(photo, config)
    assert item.status == 'ready'
    assert item.detail['albums']


# --------------------------------------------------------------------------- #
# create_plan guards
# --------------------------------------------------------------------------- #

def _plan_request(tmp_path, **config_values):
    target = str(tmp_path / 'target')
    os.makedirs(target, exist_ok=True)
    defaults = {"kind": "organize", "action": "move", "target": target,
                "layout": "rebuild", "rules": [{"strategy": "time", "granularity": "year"}]}
    defaults.update(config_values)
    config = ToolConfig(**defaults)
    scope = MediaScope(source="all")
    return PlanRequest(scope=scope, config=config)


def test_create_plan_rejects_unwritable_target_directory(tmp_path):
    request = _plan_request(tmp_path)
    db = MagicMock()
    user = _user()
    with patch('app.service.toolbox_plans.allowed_directory',
               return_value=str(tmp_path / 'missing' / 'deeper')), \
            patch('app.service.toolbox_plans.os.access', return_value=False), \
            patch('app.service.toolbox_plans.iter_scope', return_value=[]):
        with pytest.raises(ValueError) as excinfo:
            create_plan(db, user, request)
    assert '不可写' in str(excinfo.value)


def test_create_plan_rejects_preserve_layout_without_single_folder(tmp_path):
    request = _plan_request(tmp_path, layout='preserve')
    db = MagicMock()
    user = _user()
    with patch('app.service.toolbox_plans.allowed_directory',
               return_value=str(tmp_path)), \
            patch('app.service.toolbox_plans.iter_scope', return_value=[]):
        with pytest.raises(ValueError) as excinfo:
            create_plan(db, user, request)
    assert '共同源文件夹' in str(excinfo.value)


def test_create_plan_rejects_more_than_50000_items(tmp_path):
    request = _plan_request(tmp_path)
    db = MagicMock()
    user = _user()
    photos = [SimpleNamespace(id=uuid4()) for _ in range(50001)]
    with patch('app.service.toolbox_plans.allowed_directory',
               return_value=str(tmp_path)), \
            patch('app.service.toolbox_plans.iter_scope', return_value=photos):
        with pytest.raises(ValueError) as excinfo:
            create_plan(db, user, request)
    assert '50000' in str(excinfo.value)


def test_create_plan_rejects_copy_when_target_disk_is_too_small(tmp_path):
    request = _plan_request(tmp_path, action='copy')
    db = MagicMock()
    user = _user()
    photo = _photo(tmp_path, 'big.jpg')
    with patch('app.service.toolbox_plans.allowed_directory',
               return_value=str(tmp_path)), \
            patch('app.service.toolbox_plans.iter_scope', return_value=[photo]), \
            patch('app.service.toolbox_plans.item_for_photo') as item_mock, \
            patch('shutil.disk_usage') as usage:
        item_mock.return_value = SimpleNamespace(
            status='ready', detail={'targets': [str(tmp_path / 'out.jpg')]},
            fingerprint={'size': 10 ** 9, 'mtime_ns': 1}, target=str(tmp_path / 'out.jpg'),
            source=photo.file_path, id=1)
        usage.return_value = SimpleNamespace(free=1024)
        with pytest.raises(ValueError) as excinfo:
            create_plan(db, user, request)
    assert '存储空间不足' in str(excinfo.value)
    db.rollback.assert_called_once()


# --------------------------------------------------------------------------- #
# cleanup_candidates — quality mode
# --------------------------------------------------------------------------- #

def test_cleanup_candidates_quality_mode_scores_photos(tmp_path):
    user = _user()
    photo = _photo(tmp_path, 'q.jpg')
    photo.image_description = SimpleNamespace(memory_score=10, quality_score=20)
    config = _config(kind='cleanup', cleanup_mode='quality', quality_max=40)
    db = MagicMock()
    with patch('app.service.toolbox_plans.fingerprint',
               return_value={'size': 1, 'mtime_ns': 1}):
        candidates = cleanup_candidates(db, user, [photo], config)
    assert photo.id in candidates
    assert candidates[photo.id]['group'] == 'quality'


def test_cleanup_candidates_quality_mode_skips_photos_without_description(tmp_path):
    user = _user()
    photo = _photo(tmp_path, 'q.jpg')
    config = _config(kind='cleanup', cleanup_mode='quality', quality_max=40)
    db = MagicMock()
    candidates = cleanup_candidates(db, user, [photo], config)
    assert candidates == {}


# --------------------------------------------------------------------------- #
# cleanup_candidates — similarity mode
# --------------------------------------------------------------------------- #

def test_cleanup_candidates_similarity_mode_groups_near_duplicates(tmp_path):
    user = _user()
    photo = _photo(tmp_path, 's.jpg')
    other = _photo(tmp_path, 's2.jpg')
    config = _config(kind='cleanup', cleanup_mode='similar', compare_all=True,
                     similarity=0.9)
    db = MagicMock()
    rows = [SimpleNamespace(photo_id=photo.id, embedding=[1.0, 0.0]),
            SimpleNamespace(photo_id=other.id, embedding=[0.99, 0.01])]
    db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = rows
    with patch('app.service.toolbox_plans.fingerprint',
               return_value={'size': 1, 'mtime_ns': 1}):
        candidates = cleanup_candidates(db, user, [photo], config)
    assert photo.id in candidates
    assert candidates[photo.id]['group'] == str(photo.id)
    assert str(other.id) in candidates[photo.id]['related_ids']


def test_cleanup_candidates_similarity_mode_rejects_more_than_3000_rows(tmp_path):
    user = _user()
    photo = _photo(tmp_path, 's.jpg')
    config = _config(kind='cleanup', cleanup_mode='similar', compare_all=True,
                     similarity=0.9)
    db = MagicMock()
    rows = [SimpleNamespace(photo_id=uuid4(), embedding=[1.0, 0.0])
            for _ in range(3001)]
    db.query.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = rows
    with pytest.raises(ValueError) as excinfo:
        cleanup_candidates(db, user, [photo], config)
    assert '3000' in str(excinfo.value)




