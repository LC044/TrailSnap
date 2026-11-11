"""Nightly gap coverage (2026-11-11) — app/service/toolbox_plans.py & toolbox_scope.py.

The 2026-11-11 backend coverage scan reported::

    service/toolbox_plans.py    77.3%   78 uncovered lines
    service/toolbox_scope.py    93.5%    6 uncovered lines

The plans module is almost pure business logic, so its uncovered branches are
reached without any I/O:

* ``validate_template`` rejecting an empty template / illegal path characters
* ``rule_groups`` placeholder fall-backs for missing time and location
* the ``person`` strategy (identity names) and the "no group at all" case
* the ``rule.groups`` allow-list filter
* ``grouping_paths`` ambiguity / overflow / multi-group modes
* ``rename_path`` refusing a template whose variables cannot be filled

``toolbox_scope`` covers the ``is_below`` guard for paths on different drives
and the ``iter_scope`` guard that skips photos whose path cannot be resolved.
"""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.toolbox import OrganizeRule, ToolConfig
from app.service import toolbox_scope
from app.service.toolbox_plans import grouping_paths, rename_path, rule_groups, validate_template

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _metadata(**values):
    base = {"province": None, "city": None, "district": None, "address": None,
            "make": None, "model": None, "exif_info": None}
    base.update(values)
    return SimpleNamespace(**base)


def _tag(name):
    return SimpleNamespace(id=uuid4(), tag_name=name)


def _identity(name):
    return SimpleNamespace(id=uuid4(), identity_name=name)


def _face(name):
    identity = _identity(name)
    return SimpleNamespace(identity=identity)


def _photo(**values):
    defaults = {
        "id": uuid4(),
        "filename": "IMG_0001.jpg",
        "file_path": os.path.join("C:\\photos", "IMG_0001.jpg"),
        "photo_time": datetime(2026, 5, 2, 8, 30),
        "upload_time": datetime(2026, 5, 3, 9, 0),
        "metadata_info": _metadata(province="浙江省", city="杭州市", district="西湖区", make="Canon"),
        "tags": [],
        "faces": [],
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _config(rule, **values):
    defaults = {"kind": "album", "rules": [rule], "missing": "placeholder", "multi_group": "all"}
    defaults.update(values)
    return ToolConfig(**defaults)


# --------------------------------------------------------------------------- #
# validate_template
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("template", ["", "   ", "a/b.jpg", "a:b.jpg", "a*b.jpg"])
def test_validate_template_rejects_empty_or_illegal_templates(template):
    """An empty template or one with illegal path characters is refused."""
    with pytest.raises(ValueError):
        validate_template(template)


def test_validate_template_accepts_a_known_variable():
    assert validate_template("IMG_{date}_{index}") == {"date", "index"}


# --------------------------------------------------------------------------- #
# rule_groups
# --------------------------------------------------------------------------- #

def test_time_strategy_without_any_time_uses_the_placeholder_group():
    """A photo without a shooting time falls into the "未知时间" group."""
    rule = OrganizeRule(strategy="time", granularity="year")
    photo = _photo(photo_time=None, upload_time=None)

    groups = rule_groups(photo, rule, _config(rule))

    assert groups == [("unknown", ["未知时间"])]


def test_time_strategy_without_time_and_without_placeholder_is_skipped():
    """With ``missing="skip"`` such a photo produces no group at all."""
    rule = OrganizeRule(strategy="time", granularity="year")
    photo = _photo(photo_time=None, upload_time=None)

    assert rule_groups(photo, rule, _config(rule, missing="skip")) == []


def test_location_strategy_without_metadata_uses_the_placeholder_group():
    """Missing province/city falls into the "未知位置" group."""
    rule = OrganizeRule(strategy="location", granularity="province_city")
    photo = _photo(metadata_info=_metadata())

    groups = rule_groups(photo, rule, _config(rule))

    assert groups == [("unknown", ["未知位置"])]


def test_person_strategy_groups_by_identity_name():
    """The person strategy groups a photo by its identified people."""
    rule = OrganizeRule(strategy="person", granularity="year")
    photo = _photo(faces=[_face("张三"), _face("李四")])

    groups = rule_groups(photo, rule, _config(rule))

    assert [key for key, _ in groups] == [str(face.identity.id) for face in photo.faces]
    assert [parts for _, parts in groups] == [["张三"], ["李四"]]


def test_category_strategy_without_tags_uses_the_uncategorised_group():
    """A photo without any tag still gets one placeholder group."""
    rule = OrganizeRule(strategy="category")
    photo = _photo(tags=[])

    groups = rule_groups(photo, rule, _config(rule))

    assert groups == [("unknown", ["未分类"])]


def test_rule_group_allow_list_filters_the_groups():
    """``rule.groups`` keeps only the listed group keys."""
    keep, drop = _tag("keep-me"), _tag("drop-me")
    rule = OrganizeRule(strategy="category", groups=[str(keep.id)])
    photo = _photo(tags=[keep, drop])

    groups = rule_groups(photo, rule, _config(rule))

    assert [parts for _, parts in groups] == [["keep-me"]]


# --------------------------------------------------------------------------- #
# grouping_paths
# --------------------------------------------------------------------------- #

def test_grouping_paths_reports_missing_archive_information():
    """A rule that yields nothing stops the plan with a readable reason."""
    rule = OrganizeRule(strategy="time", granularity="year")
    photo = _photo(photo_time=None, upload_time=None)

    paths, reason = grouping_paths(photo, _config(rule, missing="skip"))

    assert paths == []
    assert reason == "缺少归档信息或不在指定分组"


def test_grouping_paths_skips_ambiguous_multi_group_matches():
    """``multi_group="skip"`` refuses photos that match more than one group."""
    rule = OrganizeRule(strategy="category")
    photo = _photo(tags=[_tag("旅行"), _tag("美食")])

    paths, reason = grouping_paths(photo, _config(rule, multi_group="skip"))

    assert paths == []
    assert reason == "多个分组存在歧义，请明确归属"


def test_grouping_paths_first_mode_keeps_a_single_group():
    """``multi_group="first"`` keeps only the first matching group."""
    rule = OrganizeRule(strategy="category")
    photo = _photo(tags=[_tag("旅行"), _tag("美食")])

    paths, reason = grouping_paths(photo, _config(rule, multi_group="first"))

    assert reason == ""
    assert paths == [["旅行"]]


def test_grouping_paths_refuses_too_many_combinations():
    """More than 100 combinations are refused instead of exploding."""
    tag_rule = OrganizeRule(strategy="category")
    person_rule = OrganizeRule(strategy="person")
    photo = _photo(tags=[_tag(f"tag-{i}") for i in range(11)],
                   faces=[_face(f"person-{i}") for i in range(10)])
    config = ToolConfig(kind="album", rules=[tag_rule, person_rule],
                         missing="placeholder", multi_group="all")

    paths, reason = grouping_paths(photo, config)

    assert paths == []
    assert reason == "单个影像匹配分组过多，请缩小分组"


def test_grouping_paths_uses_nested_parts_when_asked():
    """Nested rules contribute every part of the group to the path."""
    rule = OrganizeRule(strategy="location", granularity="province_city", nested=True)
    photo = _photo(metadata_info=_metadata(province="浙江省", city="杭州市"))

    paths, reason = grouping_paths(photo, _config(rule))

    assert reason == ""
    assert paths == [["浙江省", "杭州市"]]


# --------------------------------------------------------------------------- #
# rename_path
# --------------------------------------------------------------------------- #

def test_rename_path_requires_a_shooting_time_for_time_variables():
    """A time variable without any time is refused."""
    config = ToolConfig(kind="rename", template="IMG_{date}", missing="skip")
    photo = _photo(photo_time=None, upload_time=None)

    with pytest.raises(ValueError, match="拍摄时间"):
        rename_path(photo, config, 1)


def test_rename_path_requires_location_fields_when_missing_is_skip():
    """``missing="skip"`` refuses to invent a city that does not exist."""
    config = ToolConfig(kind="rename", template="IMG_{city}", missing="skip")
    photo = _photo(metadata_info=_metadata())

    with pytest.raises(ValueError, match="地点或设备"):
        rename_path(photo, config, 1)


def test_rename_path_builds_the_target_name_from_the_template():
    """A complete template produces a new file name next to the original."""
    config = ToolConfig(kind="rename", template="IMG_{date}_{city}", missing="skip")
    photo = _photo(metadata_info=_metadata(city="杭州市"))

    target = rename_path(photo, config, 3)

    assert target.endswith("IMG_2026-05-02_杭州市.jpg")
    assert os.path.dirname(target) == os.path.dirname(photo.file_path)


# --------------------------------------------------------------------------- #
# toolbox_scope guards
# --------------------------------------------------------------------------- #

def test_is_below_returns_false_for_paths_on_different_drives():
    """``os.path.commonpath`` raises for different drives -> not below."""
    if os.name != "nt":
        pytest.skip("drive letters are a Windows-only concept")
    assert toolbox_scope.is_below("C:\\photos\\a.jpg", "D:\\photos") is False


def test_is_below_accepts_a_child_path():
    assert toolbox_scope.is_below(os.path.join(os.getcwd(), "child"),
                                  os.getcwd()) is True


def test_iter_scope_skips_photos_whose_path_cannot_be_resolved(tmp_path, monkeypatch):
    """A photo whose path raises inside ``is_below`` is skipped, not fatal."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.base import Base
    from app.db.models import Photo, User
    from app.schemas.toolbox import MediaScope

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid4(), username="scope", hashed_password="unused",
                    settings={"storage": {"external_directories": [str(tmp_path)]}})
        db.add(user)
        db.flush()
        photo = Photo(id=uuid4(), owner_id=user.id, filename="a.jpg",
                      file_path=str(tmp_path / "a.jpg"), file_type="image",
                      photo_time=datetime(2026, 5, 2))
        db.add(photo)
        db.commit()

        def _boom(path, root):
            # Only the photo path breaks; the directory guard still works.
            if str(path).endswith(".jpg"):
                raise ValueError("unresolvable path")
            return True

        monkeypatch.setattr(toolbox_scope, "is_below", _boom)
        scope = MediaScope(source="folders", folders=[str(tmp_path)])
        photos = list(toolbox_scope.iter_scope(db, user, scope))

    engine.dispose()
    assert photos == []
