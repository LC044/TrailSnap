# -*- coding: utf-8 -*-
"""gallery_service 单元测试。

覆盖路径归一化、层级关系判断（含 family vs family2 误判防护）、候选发现只枚举
一级子目录、批量添加的原子性/幂等/数量限制、根目录边界与符号链接逃逸。
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 把 package/server 加进 sys.path，便于直接 import app.*
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.service import gallery_service  # noqa: E402


# --------------------------------------------------------------------------- #
# normalize_path / relation
# --------------------------------------------------------------------------- #
def test_normalize_strips_and_absolutizes(tmp_path):
    rel = os.path.join(str(tmp_path), '..', '.')
    norm = gallery_service.normalize_path(rel)
    assert os.path.isabs(norm)
    assert '..' not in norm


def test_relation_family_does_not_match_family2():
    # 字符串前缀会误判，结构化比较必须区分
    a = '/app/Photos/family'
    b = '/app/Photos/family2'
    assert gallery_service.relation(a, b) == 'none'
    assert gallery_service.relation(b, a) == 'none'


def test_relation_parent_child():
    parent = '/app/Photos/family'
    child = '/app/Photos/family/2025'
    assert gallery_service.relation(child, parent) == 'child'
    assert gallery_service.relation(parent, child) == 'parent'
    assert gallery_service.relation(parent, parent) == 'equal'


def test_relation_different_roots():
    assert gallery_service.relation('/app/Photos/a', '/app/Other/a') == 'none'


def test_is_within_root():
    assert gallery_service.is_within_root('/app/Photos/family') is True
    assert gallery_service.is_within_root('/app/Photos') is True
    assert gallery_service.is_within_root('/etc/passwd') is False


# --------------------------------------------------------------------------- #
# list_candidates —— 只枚举一级子目录
# --------------------------------------------------------------------------- #
def test_list_candidates_only_direct_children(tmp_path, monkeypatch):
    # 造两级目录
    (tmp_path / 'family').mkdir()
    (tmp_path / 'travel').mkdir()
    (tmp_path / 'family' / '2025').mkdir()  # 深层，不应出现
    (tmp_path / 'readme.txt').write_text('x')  # 非目录，不应出现

    monkeypatch.setattr(gallery_service, 'EXTERNAL_GALLERY_ROOT', str(tmp_path))
    # 无已登记
    monkeypatch.setattr(gallery_service, '_registered_keys', lambda uid, db: [])

    data = gallery_service.list_candidates('u', db=None)
    assert data['root_exists'] is True
    names = [d['name'] for d in data['directories']]
    assert names == ['family', 'travel']
    # 深层 2025 不出现
    assert '2025' not in names


def test_list_candidates_root_missing(monkeypatch):
    monkeypatch.setattr(gallery_service, 'EXTERNAL_GALLERY_ROOT', '/definitely/not/exists/xyz')
    monkeypatch.setattr(gallery_service, '_registered_keys', lambda uid, db: [])
    data = gallery_service.list_candidates('u', db=None)
    assert data['root_exists'] is False
    assert data['directories'] == []


def test_list_candidates_marks_registered(tmp_path, monkeypatch):
    family = tmp_path / 'family'
    family.mkdir()
    monkeypatch.setattr(gallery_service, 'EXTERNAL_GALLERY_ROOT', str(tmp_path))
    monkeypatch.setattr(gallery_service, '_registered_keys',
                        lambda uid, db: [(gallery_service._key(str(family)), str(family))])
    data = gallery_service.list_candidates('u', db=None)
    fam = next(d for d in data['directories'] if d['name'] == 'family')
    assert fam['registered'] is True


# --------------------------------------------------------------------------- #
# validate_path
# --------------------------------------------------------------------------- #
def test_validate_not_found(monkeypatch):
    monkeypatch.setattr(gallery_service, '_registered_keys', lambda uid, db: [])
    res = gallery_service.validate_path('/no/such/dir/xyz', 'u', db=None)
    assert res['valid'] is False
    assert res['error'] == gallery_service.ERR_NOT_FOUND


def test_validate_not_a_directory(tmp_path, monkeypatch):
    f = tmp_path / 'a.txt'
    f.write_text('x')
    monkeypatch.setattr(gallery_service, '_registered_keys', lambda uid, db: [])
    res = gallery_service.validate_path(str(f), 'u', db=None)
    assert res['valid'] is False
    assert res['error'] == gallery_service.ERR_INVALID


def test_validate_already_added(tmp_path, monkeypatch):
    d = tmp_path / 'family'
    d.mkdir()
    key = gallery_service._key(str(d))
    monkeypatch.setattr(gallery_service, '_registered_keys',
                        lambda uid, db: [(key, str(d))])
    res = gallery_service.validate_path(str(d), 'u', db=None)
    assert res['valid'] is False
    assert res['error'] == gallery_service.ERR_ALREADY_ADDED


def test_validate_parent_conflict(tmp_path, monkeypatch):
    parent = tmp_path / 'family'
    parent.mkdir()
    child = parent / '2025'
    child.mkdir()
    # 已登记 parent，再校验 child → PARENT_CONFLICT
    monkeypatch.setattr(gallery_service, '_registered_keys',
                        lambda uid, db: [(gallery_service._key(str(parent)), str(parent))])
    res = gallery_service.validate_path(str(child), 'u', db=None)
    assert res['valid'] is False
    assert res['error'] == gallery_service.ERR_PARENT_CONFLICT


def test_validate_outside_root_warns_but_passes(tmp_path, monkeypatch):
    d = tmp_path / 'custom'
    d.mkdir()
    monkeypatch.setattr(gallery_service, '_registered_keys', lambda uid, db: [])
    res = gallery_service.validate_path(str(d), 'u', db=None)
    assert res['valid'] is True
    assert 'outside_root' in res['warnings']


# --------------------------------------------------------------------------- #
# batch_add —— 原子性 / 幂等 / 数量限制
# --------------------------------------------------------------------------- #
def _mock_config_manager(monkeypatch, existing):
    """让 batch_add 读到 existing、写到的 merged 被记录。"""
    cfg = MagicMock()
    cfg.storage.external_directories = list(existing)
    cfg.model_dump.return_value = {'storage': {'external_directories': list(existing)}}
    captured = {'merged': None}

    def fake_update(uid, settings, db):
        captured['merged'] = settings.get('storage', {}).get('external_directories')

    gallery_service.config_manager.get_user_config = MagicMock(return_value=cfg)
    gallery_service.config_manager.update_user_config = MagicMock(side_effect=fake_update)
    return captured


def test_batch_add_atomic_on_failure(tmp_path, monkeypatch):
    good = tmp_path / 'family'; good.mkdir()
    missing = '/no/such/dir/xyz'
    _mock_config_manager(monkeypatch, [])
    monkeypatch.setattr(gallery_service.TaskManager, 'get_instance',
                        lambda: MagicMock(add_task=MagicMock(return_value=MagicMock(id='t1'))))

    res = gallery_service.batch_add([str(good), missing], 'u', db=None)
    assert res['added'] == []
    assert res['task_id'] is None
    missing_norm = gallery_service.normalize_path(missing)
    assert any(e['path'] == missing_norm for e in res['errors'])
    # 配置未写入
    gallery_service.config_manager.update_user_config.assert_not_called()


def test_batch_add_idempotent_skips_existing(tmp_path, monkeypatch):
    d = tmp_path / 'family'; d.mkdir()
    _mock_config_manager(monkeypatch, [str(d)])
    add_task = MagicMock(return_value=MagicMock(id='t1'))
    monkeypatch.setattr(gallery_service.TaskManager, 'get_instance',
                        lambda: MagicMock(add_task=add_task))

    res = gallery_service.batch_add([str(d)], 'u', db=None)
    assert res['added'] == []
    assert res['skipped'] == [str(d)]
    # 全部已存在 → 不建任务、不写配置
    add_task.assert_not_called()
    gallery_service.config_manager.update_user_config.assert_not_called()


def test_batch_add_success_creates_single_scan_task(tmp_path, monkeypatch):
    a = tmp_path / 'family'; a.mkdir()
    b = tmp_path / 'travel'; b.mkdir()
    captured = _mock_config_manager(monkeypatch, [])
    add_task = MagicMock(return_value=MagicMock(id='task-42'))
    monkeypatch.setattr(gallery_service.TaskManager, 'get_instance',
                        lambda: MagicMock(add_task=add_task))

    res = gallery_service.batch_add([str(a), str(b)], 'u', db=None)
    assert set(res['added']) == {str(a), str(b)}
    assert res['task_id'] == 'task-42'
    # 只创建一个任务，且 scan_roots 仅含新增
    assert add_task.call_count == 1
    payload = add_task.call_args.args[2]
    assert set(payload['scan_roots']) == {str(a), str(b)}
    # 配置一次性写入，merged 含两条
    assert set(captured['merged']) == {str(a), str(b)}


def test_batch_add_rejects_parent_child_in_same_request(tmp_path, monkeypatch):
    parent = tmp_path / 'family'; parent.mkdir()
    child = parent / '2025'; child.mkdir()
    _mock_config_manager(monkeypatch, [])
    monkeypatch.setattr(gallery_service.TaskManager, 'get_instance',
                        lambda: MagicMock(add_task=MagicMock()))

    res = gallery_service.batch_add([str(parent), str(child)], 'u', db=None)
    assert res['added'] == []
    assert res['task_id'] is None
    assert res['errors']
    gallery_service.config_manager.update_user_config.assert_not_called()


def test_batch_add_enforces_limit(monkeypatch):
    paths = [f'/app/Photos/g{i}' for i in range(gallery_service.BATCH_MAX_PATHS + 1)]
    with pytest.raises(ValueError):
        gallery_service.batch_add(paths, 'u', db=None)


# --------------------------------------------------------------------------- #
# 符号链接逃逸
# --------------------------------------------------------------------------- #
def test_symlink_escape_detected(tmp_path, monkeypatch):
    inside_root = tmp_path / 'root'
    inside_root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    link = inside_root / 'escape'
    try:
        os.symlink(str(outside), link)
    except (OSError, NotImplementedError):
        pytest.skip('symlink not supported')

    monkeypatch.setattr(gallery_service, 'EXTERNAL_GALLERY_ROOT', str(inside_root))
    monkeypatch.setattr(gallery_service, '_registered_keys', lambda uid, db: [])

    data = gallery_service.list_candidates('u', db=None)
    # resolve 后候选 path 指向 outside，不在根内 —— registered=False，但 exists=True
    esc = next(d for d in data['directories'] if d['name'] == 'escape')
    assert esc['exists'] is True
    # 关键：解析后的路径不应被认为在根内
    assert gallery_service.is_within_root(esc['path']) is False
