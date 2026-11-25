"""Nightly watch 2026-11-25 · app/service/toolbox_plans.py 的复制目标守卫盲区。

覆盖扫描显示 toolbox_plans.py 未覆盖的 14 行里，有 9 行落在「复制（copy）」这条
路线上：重复归档时如何判断「这次副本已经生成过」以及「目标路径其实已经符合规则」。
这两条守卫决定了重复点击归档时是静默跳过还是覆盖用户文件，属于高风险逻辑。

本文件用假 session + 真实临时文件验证：

- prior_success：上次的输出指纹与磁盘一致时判定为「已处理」
- prior_success：输出文件已被外部删除（OSError）时不得误判
- item_for_photo：目标副本已存在时跳过并说明原因
- item_for_photo：目标路径已经符合规则时跳过并说明原因
"""

import os
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.photo import FileType
from app.db.models.toolbox import ToolboxPlanItem
from app.schemas.toolbox import OrganizeRule, ToolConfig
from app.service import toolbox_plans

pytestmark = [pytest.mark.regression, pytest.mark.module_toolbox]


class _Query:
    def __init__(self, rows):
        self._rows = list(rows)

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.added = []
        self.commits = 0

    def query(self, *args, **kwargs):
        return _Query(self.rows)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


def _photo(path):
    return SimpleNamespace(
        id=uuid4(), file_path=str(path), file_type=FileType.image,
        photo_time=datetime(2024, 5, 20, 10, 30), upload_time=datetime(2024, 5, 21, 8, 0),
        filename=os.path.basename(str(path)), tags=[], faces=[],
        metadata_info=SimpleNamespace(province=None, city=None, district=None,
                                      address=None, make=None, model=None, exif_info=None),
    )


def _config(target, **kwargs):
    options = dict(kind="organize", action="copy", target=str(target),
                   layout="rebuild", rules=[OrganizeRule(strategy="time", granularity="year")],
                   missing="skip")
    options.update(kwargs)
    return ToolConfig(**options)


def _user():
    return SimpleNamespace(id=uuid4())


def test_prior_success_accepts_an_unchanged_output(tmp_path):
    source = tmp_path / "src.jpg"
    source.write_bytes(b"photo")
    target = tmp_path / "out.jpg"
    target.write_bytes(b"photo")
    photo = _photo(source)
    config = _config(tmp_path, kind="organize", action="copy")
    signature = toolbox_plans.digest(config.model_dump(mode="json"))
    row = SimpleNamespace(
        id=1, detail={"signature": signature,
                      "output_fingerprint": toolbox_plans.file_fingerprint(str(target))},
        target=str(target),
    )
    session = _Session([row])

    assert toolbox_plans.prior_success(session, _user(), photo, config) is True


def test_prior_success_ignores_a_vanished_output(tmp_path):
    source = tmp_path / "src.jpg"
    source.write_bytes(b"photo")
    missing = tmp_path / "gone.jpg"
    photo = _photo(source)
    config = _config(tmp_path, kind="organize", action="copy")
    signature = toolbox_plans.digest(config.model_dump(mode="json"))
    row = SimpleNamespace(
        id=1, detail={"signature": signature, "output_fingerprint": {"size": 1, "mtime_ns": 1}},
        target=str(missing),
    )
    session = _Session([row])

    assert toolbox_plans.prior_success(session, _user(), photo, config) is False


def test_item_for_photo_skips_a_copy_that_already_exists(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    source = library / "shot.jpg"
    source.write_bytes(b"photo")
    output = tmp_path / "out" / "2024" / "shot.jpg"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"photo")
    photo = _photo(source)
    config = _config(tmp_path / "out")
    monkeypatch.setattr(toolbox_plans, "allowed_directory", lambda db, user, path: path)

    fingerprint = toolbox_plans.fingerprint(photo)
    signature = toolbox_plans.digest(config.model_dump(mode="json"))
    row = SimpleNamespace(
        id=1, detail={"signature": signature,
                      "requested_target": str(output),
                      "output_fingerprint": toolbox_plans.file_fingerprint(str(output))},
        target=str(output), fingerprint=fingerprint,
    )
    session = _Session([row])

    item = toolbox_plans.item_for_photo(session, _user(), photo, config, 1, set(), {}, str(library))

    assert item.status == "skipped"
    assert "相同规则的副本已生成" in item.reason


def test_item_for_photo_skips_a_path_that_already_matches_the_rule(tmp_path, monkeypatch):
    library = tmp_path / "library"
    target_root = library / "2024"
    target_root.mkdir(parents=True)
    source = target_root / "shot.jpg"
    source.write_bytes(b"photo")
    photo = _photo(source)
    config = _config(library)
    monkeypatch.setattr(toolbox_plans, "allowed_directory", lambda db, user, path: path)
    session = _Session()

    item = toolbox_plans.item_for_photo(session, _user(), photo, config, 1, set(), {}, str(library))

    assert item.status == "skipped"
    assert "路径已符合规则" in item.reason


def test_prior_success_accepts_a_move_onto_the_same_path(tmp_path):
    source = tmp_path / "shot.jpg"
    source.write_bytes(b"photo")
    photo = _photo(source)
    config = _config(tmp_path, kind="organize", action="move")
    signature = toolbox_plans.digest(config.model_dump(mode="json"))
    row = SimpleNamespace(
        id=1, detail={"signature": signature,
                      "output_fingerprint": toolbox_plans.file_fingerprint(str(source))},
        target=str(source),
    )
    session = _Session([row])

    assert toolbox_plans.prior_success(session, _user(), photo, config) is True


def test_prior_success_ignores_a_move_whose_file_disappeared(tmp_path):
    # 源文件本身已经不在磁盘上：指纹统计会抛 OSError，必须被吞掉而不是让
    # 预览接口 500。
    source = tmp_path / "shot.jpg"
    photo = _photo(source)
    config = _config(tmp_path, kind="organize", action="move")
    signature = toolbox_plans.digest(config.model_dump(mode="json"))
    row = SimpleNamespace(
        id=1, detail={"signature": signature, "output_fingerprint": {"size": 1, "mtime_ns": 1}},
        target=str(source),
    )
    session = _Session([row])

    assert toolbox_plans.prior_success(session, _user(), photo, config) is False
