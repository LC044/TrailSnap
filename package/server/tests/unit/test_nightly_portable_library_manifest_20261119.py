"""覆盖 app/utils/portable_library.py 中此前没有测试引用的三个清单校验函数。

盲区来源：函数级静态引用扫描命中 _library_id / _snapshot_matches / _matches。

它们是便携图库的「快照归属」防线：
- _library_id 读取图库唯一标识；
- _snapshot_matches 确认一份快照确实属于当前图库，
  目录结构相同不能作为依据，否则会把别的图库的快照恢复到本库；
- _matches 把绝对路径转换成便携库内的相对路径，越界的路径必须返回 None。

既有测试只走 snapshot_library / restore_library 的整体流程，
从未直接断言这三个判定函数的边界行为。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils import portable_library

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _write_library_id(root: Path, library_id: str) -> None:
    (root / "library.json").write_text(
        json.dumps({"schemaVersion": 1, "libraryId": library_id}), encoding="utf-8"
    )


def test_library_id_is_missing_without_a_library_manifest(tmp_path):
    assert portable_library._library_id(tmp_path) is None


def test_library_id_reads_the_manifest(tmp_path):
    _write_library_id(tmp_path, "library-abc")
    assert portable_library._library_id(tmp_path) == "library-abc"


def test_snapshot_matches_accepts_the_same_source_directory(tmp_path):
    assert portable_library._snapshot_matches(tmp_path, {"source": str(tmp_path)}) is True


def test_snapshot_matches_accepts_a_moved_copy_of_the_same_library(tmp_path):
    _write_library_id(tmp_path, "library-abc")
    manifest = {"source": str(tmp_path / "elsewhere"), "libraryId": "library-abc"}
    assert portable_library._snapshot_matches(tmp_path, manifest) is True


def test_snapshot_matches_rejects_a_snapshot_of_another_library(tmp_path):
    _write_library_id(tmp_path, "library-abc")
    manifest = {"source": str(tmp_path / "elsewhere"), "libraryId": "library-xyz"}
    assert portable_library._snapshot_matches(tmp_path, manifest) is False


def test_snapshot_matches_rejects_a_snapshot_without_a_library_id(tmp_path):
    manifest = {"source": str(tmp_path / "elsewhere")}
    assert portable_library._snapshot_matches(tmp_path, manifest) is False


def test_matches_returns_the_relative_path_inside_the_library(tmp_path):
    absolute = str(tmp_path / "data" / "photos" / "a.jpg").replace("\\", "/")
    assert portable_library._matches(absolute, tmp_path) == "data/photos/a.jpg"


def test_matches_rejects_paths_outside_the_library(tmp_path):
    outside = str(tmp_path.parent / "other" / "a.jpg").replace("\\", "/")
    assert portable_library._matches(outside, tmp_path) is None
    # 目录本身不等于「位于目录之下」。
    assert portable_library._matches(str(tmp_path).replace("\\", "/"), tmp_path) is None


def test_matches_does_not_treat_a_sibling_prefix_as_inside(tmp_path):
    sibling = str(tmp_path) + "-backup" + "/a.jpg"
    assert portable_library._matches(sibling.replace("\\", "/"), tmp_path) is None
