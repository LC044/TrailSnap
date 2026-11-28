"""Nightly 2026-11-28: app/service/toolbox_plans.py 重命名元数据指纹盲区。

覆盖 rename_metadata 的 country/person/category 提取与过滤规则、fingerprint 按需附加
rename_metadata，以及 toolbox_execution.matches_fingerprint 的重命名指纹比对。
"""
from types import SimpleNamespace

import pytest

from app.service.toolbox_execution import matches_fingerprint
from app.service.toolbox_plans import RENAME_METADATA_FIELDS, fingerprint, rename_metadata

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


def _identity(name, *, deleted=False, hidden=False):
    return SimpleNamespace(identity_name=name, id="id-" + (name or "blank"),
                            is_deleted=deleted, is_hidden=hidden)


def _face(name=None, *, face_deleted=False, identity=None):
    if identity is None:
        identity = _identity(name)
    return SimpleNamespace(identity=identity, is_deleted=face_deleted)


def _tag(name, *, deleted=False):
    return SimpleNamespace(id="tag-" + (name or "blank"), tag_name=name, is_deleted=deleted)


def _photo(tmp_path, *, country="Japan", faces=(), tags=(), name="photo.jpg"):
    path = tmp_path / name
    path.write_bytes(b"payload")
    return SimpleNamespace(
        file_path=str(path),
        photo_time=None,
        upload_time=None,
        metadata_info=SimpleNamespace(country=country, province=None, city=None,
                                      district=None, address=None, make=None,
                                      model=None, exif_info=None),
        faces=list(faces),
        tags=list(tags),
    )


def test_rename_metadata_extracts_requested_fields(tmp_path):
    photo = _photo(tmp_path, country="  Japan  ",
                    faces=[_face("Alice"), _face("Bob")],
                    tags=[_tag("beach"), _tag("travel")])
    values = rename_metadata(photo, RENAME_METADATA_FIELDS)
    assert values["country"] == "Japan"
    assert values["person"] == "Alice+Bob"
    assert values["category"] == "beach+travel"


def test_rename_metadata_skips_unusable_identities_and_tags(tmp_path):
    photo = _photo(
        tmp_path,
        faces=[
            _face("Alice"),
            _face(identity=_identity("", deleted=True)),
            _face(identity=_identity("Ghost", hidden=True)),
            _face("Bob", face_deleted=True),
            _face(identity=_identity("Carol", deleted=True)),
        ],
        tags=[_tag("beach"), _tag("old", deleted=True), _tag("   ")],
    )
    values = rename_metadata(photo, {"person", "category"})
    assert values["person"] == "Alice"
    assert values["category"] == "beach"


def test_rename_metadata_returns_only_requested_fields(tmp_path):
    photo = _photo(tmp_path, faces=[_face("Alice")], tags=[_tag("beach")])
    assert rename_metadata(photo, set()) == {}
    assert rename_metadata(photo, {"person"}) == {"person": "Alice"}


def test_fingerprint_adds_rename_metadata_only_when_requested(tmp_path):
    photo = _photo(tmp_path, country="Japan")
    plain = fingerprint(photo)
    assert "rename_metadata" not in plain
    enriched = fingerprint(photo, {"country"})
    assert enriched["rename_metadata"] == {"country": "Japan"}
    assert enriched["size"] == plain["size"]
    assert enriched["data"] == plain["data"]


def test_matches_fingerprint_accepts_unchanged_rename_metadata(tmp_path):
    photo = _photo(tmp_path, faces=[_face("Alice")])
    assert matches_fingerprint(photo, fingerprint(photo, {"person"})) is True


def test_matches_fingerprint_rejects_changed_rename_metadata(tmp_path):
    photo = _photo(tmp_path, faces=[_face("Alice")])
    expected = fingerprint(photo, {"person"})
    photo.faces = [_face("Bob")]
    assert matches_fingerprint(photo, expected) is False


def test_matches_fingerprint_compares_plain_fingerprints(tmp_path):
    photo = _photo(tmp_path)
    assert matches_fingerprint(photo, fingerprint(photo)) is True
    assert matches_fingerprint(photo, {"size": 1, "mtime_ns": 1, "data": "x"}) is False
