"""Nightly gap coverage (2026-11-12) - app/service/toolbox_plans.py.

The 2026-11-12 backend coverage scan reported::

    service/toolbox_plans.py    77.3%   78 uncovered lines

The two previous nightly rounds already covered the *pure* helpers of this
module (``validate_template``, ``rule_groups``, ``grouping_paths``,
``rename_path``).  What is still uncovered lives in the parts that touch the
database and the file system:

* ``group_options`` (``106-112``) - the per-group photo counts used by the
  preset UI, which needs a real ``iter_scope`` over a database session.
* ``collision_free`` (``164``) - the "target equals the source" shortcut.
* ``prior_success`` / ``completed_copy_targets`` (``183-195``, ``213-218``)
  - the "this photo was already archived / copied" history lookups, including
  their ``OSError`` guards for a vanished target file.
* ``unsupported_reason`` (``224``) - a video file type is refused.
* ``cleanup_candidates`` duplicate mode (``252-256``) - two photos sharing an
  md5 become one duplicate group.
* ``item_for_photo`` (``298``, ``304``, ``307``, ``314``, ``320``, ``326``,
  ``330``, ``341``, ``349``) - the individual skip reasons of the plan
  builder.
* ``create_plan`` (``370``, ``373``, ``377``, ``423-424``) - the unwritable
  target, the "preserve layout needs one source folder", the 50000 photo
  ceiling and the insufficient-disk-space guard.

Every database interaction is mocked, so no real user data is touched.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.toolbox import MediaScope, OrganizeRule, PlanRequest, ToolConfig
from app.service import toolbox_plans
from app.service.toolbox_plans import (
    collision_free,
    completed_copy_targets,
    create_plan,
    group_options,
    item_for_photo,
    prior_success,
    unsupported_reason,
)

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _metadata(**values):
    base = {"province": None, "city": None, "district": None, "address": None,
            "make": None, "model": None, "exif_info": None}
    base.update(values)
    return SimpleNamespace(**base)


def _photo(tmp_path, name: str = "IMG_0001.jpg", **values):
    path = tmp_path / name
    path.write_bytes(b"x" * 32)
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
                "rules": [{"strategy": "time", "granularity": "year"}],
                "missing": "skip", "multi_group": "skip"}
    defaults.update(values)
    return ToolConfig(**defaults)


def _organize_config(target, **values):
    defaults = {"kind": "organize", "action": "move", "target": str(target),
                "layout": "rebuild", "rules": [{"strategy": "time", "granularity": "year"}],
                "missing": "skip", "multi_group": "skip"}
    defaults.update(values)
    return ToolConfig(**defaults)


def _item_for(photo, config, db=None, user=None, candidates=None, index=1, reserved=None):
    db = db or MagicMock()
    user = user or _user()
    with patch("app.service.toolbox_plans.allowed_directory",
               side_effect=lambda _db, _user, path: path):
        return item_for_photo(db, user, photo, config, index,
                              reserved if reserved is not None else set(),
                              candidates or {}, None)


def _history_db(rows):
    """A MagicMock whose plan-item query chain resolves to ``rows``."""
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value \
        .limit.return_value = list(rows)
    return db


# --------------------------------------------------------------------------- #
# collision_free
# --------------------------------------------------------------------------- #

def test_collision_free_keeps_the_source_path_unchanged(tmp_path):
    """A target that already equals the source is returned as-is."""
    source = tmp_path / "IMG_0001.jpg"
    source.write_bytes(b"x" * 8)

    result = collision_free(str(source), str(source), set())

    assert result == str(source)


def test_collision_free_appends_a_counter_when_the_target_exists(tmp_path):
    """An existing target file gets a ``(1)`` suffix."""
    source = tmp_path / "IMG_0001.jpg"
    source.write_bytes(b"x" * 8)
    taken = tmp_path / "IMG_0002.jpg"
    taken.write_bytes(b"x" * 8)

    result = collision_free(str(taken), str(source), set())

    assert result.endswith("IMG_0002(1).jpg")


# --------------------------------------------------------------------------- #
# unsupported_reason
# --------------------------------------------------------------------------- #

def test_unsupported_reason_refuses_a_video_file(tmp_path):
    """A video file type is not processed by the toolbox."""
    photo = _photo(tmp_path, "clip.mp4", file_type="video")

    assert "暂不处理视频" in unsupported_reason(photo)


def test_unsupported_reason_detects_a_sibling_raw_file(tmp_path):
    """A ``.DNG`` next to the JPEG means the pair must not be split up."""
    photo = _photo(tmp_path, "IMG_0001.jpg")
    (tmp_path / "IMG_0001.DNG").write_bytes(b"raw")

    assert "关联文件" in unsupported_reason(photo)


# --------------------------------------------------------------------------- #
# item_for_photo skip reasons
# --------------------------------------------------------------------------- #

def test_item_for_photo_rejects_a_photo_outside_the_cleanup_candidates(tmp_path):
    """A cleanup plan may only touch photos that were computed as candidates."""
    photo = _photo(tmp_path)
    config = _config(kind="cleanup", cleanup_mode="duplicate")

    item = _item_for(photo, config)

    assert item.status == "skipped"
    assert "不属于清理候选" in item.reason


def test_item_for_photo_marks_a_cleanup_candidate(tmp_path):
    """A candidate photo becomes a ``candidate`` item, not a ``ready`` one."""
    photo = _photo(tmp_path)
    config = _config(kind="cleanup", cleanup_mode="duplicate")
    candidates = {photo.id: {"group": "md5", "label": "重复组，共 2 项"}}

    item = _item_for(photo, config, candidates=candidates)

    assert item.status == "candidate"
    assert item.detail["group"] == "md5"


def test_item_for_photo_rejects_a_non_image_exif_target(tmp_path):
    """Only JPEG / WebP can receive a safe EXIF write."""
    photo = _photo(tmp_path, "clip.png")
    config = _config(kind="metadata", time_mode="auto", make="Canon", model="EOS")

    item = _item_for(photo, config)

    assert item.status == "skipped"
    assert "不支持安全写入 EXIF" in item.reason


def test_item_for_photo_skips_a_photo_with_complete_device_metadata(tmp_path):
    """``only_missing_metadata`` skips a photo that already carries make+model."""
    photo = _photo(tmp_path, "done.jpg",
                   metadata_info=SimpleNamespace(make="Canon", model="EOS"))
    config = _config(kind="metadata", time_mode="auto", only_missing_metadata=True)

    item = _item_for(photo, config)

    assert item.status == "skipped"
    assert "无需修改" in item.reason


def test_item_for_photo_skips_a_photo_without_any_writable_value(tmp_path):
    """Without a resolvable time and without device info there is nothing to write."""
    photo = _photo(tmp_path, "plain.jpg", photo_time=None, filename="plain.jpg")
    config = _config(kind="metadata", time_mode="auto", only_missing_metadata=False)

    item = _item_for(photo, config)

    assert item.status == "skipped"
    assert "没有可写入的时间或设备信息" in item.reason


def test_item_for_photo_skips_a_rename_that_changes_nothing(tmp_path):
    """A rename whose target equals the source is refused as a no-op."""
    photo = _photo(tmp_path, "IMG_0001.jpg")
    config = _config(kind="rename", template="{original}")

    item = _item_for(photo, config)

    assert item.status == "skipped"
    assert "名称已符合规则" in item.reason


def test_item_for_photo_reports_missing_archive_information(tmp_path):
    """An album plan without any matching group is skipped with the reason."""
    photo = _photo(tmp_path, metadata_info=None)
    config = _config(kind="album", missing="skip",
                      rules=[{"strategy": "location", "granularity": "city"}])

    item = _item_for(photo, config)

    assert item.status == "skipped"
    assert item.reason


# --------------------------------------------------------------------------- #
# prior_success / completed_copy_targets
# --------------------------------------------------------------------------- #

def test_prior_success_ignores_a_plan_item_with_a_different_signature(tmp_path):
    """A plan item built from another rule set must not count as a prior success."""
    photo = _photo(tmp_path)
    config = _organize_config(tmp_path)
    user = _user()

    row = SimpleNamespace(target=str(tmp_path / "moved.jpg"),
                          detail={"signature": "other", "output_fingerprint": {}})

    assert prior_success(_history_db([row]), user, photo, config) is False


def test_prior_success_ignores_a_vanished_target_file(tmp_path):
    """A missing target file must not raise - it is simply not a prior success."""
    photo = _photo(tmp_path)
    config = _organize_config(tmp_path)
    user = _user()

    row = SimpleNamespace(target=str(tmp_path / "gone" / "moved.jpg"),
                          detail={"signature": toolbox_plans.digest(config.model_dump(mode="json")),
                                  "output_fingerprint": {"size": 1, "mtime_ns": 2}})

    assert prior_success(_history_db([row]), user, photo, config) is False


def test_completed_copy_targets_skips_a_vanished_target_file(tmp_path):
    """A copy target that no longer exists is not reported as already completed."""
    photo = _photo(tmp_path)
    config = _organize_config(tmp_path, action="copy")
    user = _user()

    row = SimpleNamespace(target=str(tmp_path / "gone" / "copy.jpg"),
                          fingerprint=toolbox_plans.fingerprint(photo),
                          detail={"signature": toolbox_plans.digest(config.model_dump(mode="json"))})

    assert completed_copy_targets(_history_db([row]), user, photo, config) == set()


# --------------------------------------------------------------------------- #
# cleanup_candidates - duplicate mode
# --------------------------------------------------------------------------- #

def test_cleanup_candidates_groups_photos_with_the_same_md5(tmp_path):
    """Two photos with the same md5 form one duplicate group."""
    config = _config(kind="cleanup", cleanup_mode="duplicate")
    user = _user()
    first = _photo(tmp_path, "a.jpg")
    second = _photo(tmp_path, "b.jpg")

    md5_rows = [SimpleNamespace(id=first.id, md5="same"),
                SimpleNamespace(id=second.id, md5="same")]
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value \
        .yield_per.return_value = md5_rows

    candidates = toolbox_plans.cleanup_candidates(db, user, [first, second], config)

    assert first.id in candidates
    assert second.id in candidates
    assert candidates[first.id]["group"] == "same"
    assert len(candidates[first.id]["related_ids"]) == 2


# --------------------------------------------------------------------------- #
# group_options
# --------------------------------------------------------------------------- #

def test_group_options_counts_the_photos_of_each_group(tmp_path):
    """``group_options`` reports the id, label and count of every group."""
    rule = OrganizeRule(strategy="time", granularity="year")
    photo = _photo(tmp_path, metadata_info=_metadata())

    db = MagicMock()
    with patch("app.service.toolbox_plans.iter_scope", return_value=[photo]):
        options = group_options(db, _user(), MagicMock(), rule)

    assert len(options) == 1
    assert options[0]["count"] == 1
    assert options[0]["name"] == "2026"


# --------------------------------------------------------------------------- #
# create_plan guards
# --------------------------------------------------------------------------- #

def _plan_request(config, **scope_values):
    scope = MediaScope(**scope_values)
    return PlanRequest(scope=scope, config=config)


def test_create_plan_rejects_an_unwritable_target_directory(tmp_path):
    """A target directory that cannot be written to is refused."""
    target = tmp_path / "target"
    target.mkdir()
    config = _organize_config(target)

    with patch("app.service.toolbox_plans.allowed_directory",
               side_effect=lambda _db, _user, path: path), \
         patch("app.service.toolbox_plans.os.access", return_value=False):
        with pytest.raises(ValueError, match="目标目录不可写"):
            create_plan(MagicMock(), _user(), _plan_request(config, source="all"))


def test_create_plan_rejects_preserve_layout_without_a_single_source_folder(tmp_path):
    """``preserve`` layout needs exactly one source folder."""
    target = tmp_path / "target"
    target.mkdir()
    config = _organize_config(target, layout="preserve")

    with patch("app.service.toolbox_plans.allowed_directory",
               side_effect=lambda _db, _user, path: path), \
         patch("app.service.toolbox_plans.os.access", return_value=True):
        with pytest.raises(ValueError, match="保留目录层级需要选择一个共同源文件夹"):
            create_plan(MagicMock(), _user(), _plan_request(config, source="all"))


def test_create_plan_rejects_more_than_50000_photos(tmp_path):
    """The plan builder refuses more than 50000 photos in one request."""
    target = tmp_path / "target"
    target.mkdir()
    config = _organize_config(target)
    photos = [SimpleNamespace(file_path=str(tmp_path / f"{index}.jpg"), photo_time=None)
              for index in range(50001)]

    with patch("app.service.toolbox_plans.allowed_directory",
               side_effect=lambda _db, _user, path: path), \
         patch("app.service.toolbox_plans.os.access", return_value=True), \
         patch("app.service.toolbox_plans.iter_scope", return_value=photos):
        with pytest.raises(ValueError, match="50000"):
            create_plan(MagicMock(), _user(), _plan_request(config, source="all"))


def test_create_plan_rejects_a_copy_plan_without_enough_disk_space(tmp_path):
    """A copy plan whose projected size exceeds the free space is refused."""
    target = tmp_path / "target"
    target.mkdir()
    source = tmp_path / "IMG_0001.jpg"
    source.write_bytes(b"x" * 32)
    config = _organize_config(target, action="copy")
    photo = _photo(tmp_path, "IMG_0001.jpg")

    db = MagicMock()
    with patch("app.service.toolbox_plans.allowed_directory",
               side_effect=lambda _db, _user, path: path), \
         patch("app.service.toolbox_plans.os.access", return_value=True), \
         patch("app.service.toolbox_plans.iter_scope", return_value=[photo]), \
         patch.object(shutil, "disk_usage") as disk_usage:
        disk_usage.return_value = SimpleNamespace(free=1)
        with pytest.raises(ValueError, match="存储空间不足"):
            create_plan(db, _user(), _plan_request(config, source="all"))
    db.rollback.assert_called()



