# -*- coding: utf-8 -*-
"""
外部图库接入服务层。

把「候选发现 / 路径校验 / 批量添加」集中到一处，供 ``app/api/settings.py`` 的
目录管理端点复用。核心约定：

- 统一发现根目录 ``EXTERNAL_GALLERY_ROOT``（默认 ``/app/Photos``，可由同名环境变量
  覆盖）。自动发现只枚举该根的一级子目录，不递归，不开放任意路径遍历。
- 路径比较一律走结构化 API（``os.path.commonpath`` / ``Path.relative_to``），
  禁止字符串前缀匹配——否则 ``/app/Photos/family`` 会误判 ``/app/Photos/family2``。
- 第一阶段不引入新 ORM 模型，仍把图库写在用户配置 ``storage.external_directories``
  里，由 ``config_manager`` 落库。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config_manager import config_manager
from app.db.models.task import TaskType
from app.service.task_manager import TaskManager

logger = logging.getLogger("app.service.gallery_service")

# 发现根目录：install.ps1 按 /app/Photos/<源目录名> 挂载，这里只枚举其一级子目录。
EXTERNAL_GALLERY_ROOT: str = os.getenv("EXTERNAL_GALLERY_ROOT", "/app/Photos")

# 批量添加单次路径上限，防止误传巨型列表
BATCH_MAX_PATHS = 50
TREE_MAX_ENTRIES = 500

# 结构化错误码 —— 前端按 code 显示针对性处理建议
ERR_NOT_FOUND = "DIRECTORY_NOT_FOUND"
ERR_NOT_READABLE = "DIRECTORY_NOT_READABLE"
ERR_ALREADY_ADDED = "DIRECTORY_ALREADY_ADDED"
ERR_PARENT_CONFLICT = "DIRECTORY_PARENT_CONFLICT"
ERR_CHILD_CONFLICT = "DIRECTORY_CHILD_CONFLICT"
ERR_OUTSIDE_ROOT = "DIRECTORY_OUTSIDE_ALLOWED_ROOT"
ERR_INVALID = "DIRECTORY_INVALID"


# --------------------------------------------------------------------------- #
# 路径归一化
# --------------------------------------------------------------------------- #
def normalize_path(path: str) -> str:
    """归一化展示路径：去空白、解析 ``.``/``..`` 与符号链接、转绝对路径。

    保留原始大小写用于展示与存储；比较时请用 :func:`_key`。
    """
    if not path:
        return ""
    p = Path(path.strip()).expanduser()
    try:
        # resolve 解析符号链接与相对段；strict=False 允许路径不存在（校验场景需要）
        p = p.resolve(strict=False)
    except (OSError, RuntimeError):
        # resolve 失败时退回 abspath，至少把相对段抹平
        p = Path(os.path.abspath(str(p)))
    return str(p)


def _key(path: str) -> str:
    """比较键：normcase 后的归一化路径，保证 Windows 大小写/分隔符差异不误判。"""
    return os.path.normcase(normalize_path(path))


def relation(a: str, b: str) -> str:
    """判断 a 相对 b 的层级关系。

    返回 ``equal`` / ``parent``（a 是 b 的父目录）/ ``child``（a 是 b 的子目录）
    / ``none``。使用 ``commonpath``，绝不依赖字符串前缀。
    """
    ka, kb = _key(a), _key(b)
    if ka == kb:
        return "equal"
    try:
        common = os.path.commonpath([ka, kb])
    except ValueError:
        # 不同盘符 / 混合绝对相对路径 → 无层级关系
        return "none"
    if common == kb:
        return "child"   # a 落在 b 之下
    if common == ka:
        return "parent"  # a 在 b 之上
    return "none"


def is_within_root(path: str) -> bool:
    """路径是否落在发现根目录之下（含根本身）。"""
    rel = relation(path, EXTERNAL_GALLERY_ROOT)
    return rel in ("equal", "child")


# --------------------------------------------------------------------------- #
# 用户配置读取
# --------------------------------------------------------------------------- #
def _get_external_directories(user_id: str, db: Session) -> List[str]:
    """读取目标用户已登记的外部图库（原始字符串）。"""
    try:
        config = config_manager.get_user_config(user_id, db)
        return list(config.storage.external_directories or [])
    except Exception as e:
        logger.warning(f"读取 external_directories 失败 user={user_id}: {e}")
        return []


def _registered_keys(user_id: str, db: Session) -> List[Tuple[str, str]]:
    """返回 [(key, display_path)]，供候选/校验做命中与冲突比对。"""
    return [(_key(p), p) for p in _get_external_directories(user_id, db) if p]


# --------------------------------------------------------------------------- #
# 候选发现
# --------------------------------------------------------------------------- #
def _probe_directory(path: str) -> Dict[str, Any]:
    """探测单个目录的可访问性，不抛异常。"""
    exists = os.path.exists(path)
    is_dir = exists and os.path.isdir(path)
    readable = bool(is_dir and os.access(path, os.R_OK))
    # 只读判断：可读且不可写 → True；可读且可写 → False；其余 → None（未知）
    read_only: Optional[bool] = None
    if readable:
        read_only = not os.access(path, os.W_OK)
    return {"exists": exists, "is_dir": is_dir, "readable": readable, "read_only": read_only}


def list_candidates(user_id: str, db: Session) -> Dict[str, Any]:
    """枚举发现根目录的一级子目录作为候选图库。

    不递归遍历 NAS；不为客户端开放任意根路径。
    """
    root = EXTERNAL_GALLERY_ROOT
    root_exists = os.path.isdir(root)
    directories: List[Dict[str, Any]] = []

    if root_exists:
        registered = _registered_keys(user_id, db)
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if not entry.is_dir():
                        continue
                    path = entry.path
                    probe = _probe_directory(path)
                    key = _key(path)
                    registered_hit = next((disp for k, disp in registered if k == key), None)
                    # 与已登记目录的父子冲突（候选在已登记之下或之上）
                    conflict_path = None
                    for k, disp in registered:
                        if k == key:
                            continue
                        rel = relation(path, disp)
                        if rel in ("parent", "child"):
                            conflict_path = disp
                            break
                    directories.append({
                        "name": entry.name,
                        "path": path,
                        "exists": probe["exists"],
                        "readable": probe["readable"],
                        "read_only": probe["read_only"],
                        "registered": registered_hit is not None,
                        "conflict_path": conflict_path,
                    })
        except OSError as e:
            logger.warning(f"枚举候选目录失败 root={root}: {e}")

    directories.sort(key=lambda d: d["name"].lower())
    return {"root": root, "root_exists": root_exists, "directories": directories}


def list_directory_tree(path: Optional[str] = None) -> Dict[str, Any]:
    """List folders below the configured gallery root for the web picker.

    Clients cannot choose a host path directly from a browser. This endpoint
    deliberately exposes only the server/container-visible gallery root.
    """
    root = normalize_path(EXTERNAL_GALLERY_ROOT)
    target = normalize_path(path) if path else root
    if relation(target, root) not in ("equal", "child"):
        raise PermissionError("Directory is outside the external gallery root")
    if not os.path.isdir(target):
        raise FileNotFoundError(target)

    directories: List[Dict[str, Any]] = []
    with os.scandir(target) as entries:
        for entry in entries:
            if len(directories) >= TREE_MAX_ENTRIES:
                break
            try:
                if not entry.is_dir(follow_symlinks=True):
                    continue
                resolved = normalize_path(entry.path)
                if relation(resolved, root) not in ("equal", "child"):
                    continue
                directories.append({
                    "name": entry.name,
                    "path": resolved,
                    "is_leaf": not _has_visible_subdirectory(resolved, root),
                })
            except OSError:
                continue
    directories.sort(key=lambda item: item["name"].lower())
    return {"root": root, "path": target, "directories": directories}


def _has_visible_subdirectory(path: str, root: str) -> bool:
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=True):
                    resolved = normalize_path(entry.path)
                    if relation(resolved, root) in ("equal", "child"):
                        return True
    except OSError:
        return False
    return False


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
def validate_path(path: str, user_id: str, db: Session) -> Dict[str, Any]:
    """校验单个容器内路径是否可登记，返回结构化结果。

    根目录外的自定义路径不阻断（兼容旧部署），仅在 warnings 标注 outside_root。
    """
    raw = (path or "").strip()
    if not raw:
        return _validate_result(raw, valid=False, error=ERR_INVALID, msg="路径为空")

    norm = normalize_path(raw)

    if not os.path.exists(norm):
        return _validate_result(norm, valid=False, error=ERR_NOT_FOUND,
                                msg="该目录不存在，请确认路径是否正确")
    if not os.path.isdir(norm):
        return _validate_result(norm, valid=False, error=ERR_INVALID, msg="路径不是目录")
    if not os.access(norm, os.R_OK):
        return _validate_result(norm, valid=False, error=ERR_NOT_READABLE,
                                msg="TrailSnap 无法读取该目录，请检查目录权限")

    registered = _registered_keys(user_id, db)
    for k, disp in registered:
        rel = relation(norm, disp)
        if rel == "equal":
            return _validate_result(norm, valid=False, error=ERR_ALREADY_ADDED,
                                    msg="该图库已接入，无需重复添加", registered_path=disp)
        if rel == "child":
            # 新目录落在某个已登记图库之下
            return _validate_result(norm, valid=False, error=ERR_PARENT_CONFLICT,
                                    msg="该目录已经包含在现有图库中", conflict_path=disp)
        if rel == "parent":
            # 新目录包含某个已登记图库
            return _validate_result(norm, valid=False, error=ERR_CHILD_CONFLICT,
                                    msg="该目录包含一个已接入图库，请调整选择范围", conflict_path=disp)

    warnings: List[str] = []
    if not is_within_root(norm):
        warnings.append("outside_root")

    return _validate_result(norm, valid=True, error=None, msg="ok", warnings=warnings)


def _validate_result(
    path: str,
    valid: bool,
    error: Optional[str] = None,
    msg: str = "",
    registered_path: Optional[str] = None,
    conflict_path: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "path": path,
        "valid": valid,
        "exists": bool(path and os.path.exists(path)),
        "readable": bool(path and os.path.exists(path) and os.access(path, os.R_OK)),
        "registered": registered_path is not None,
        "registered_path": registered_path,
        "conflict": conflict_path,
        "error": error,
        "msg": msg,
        "warnings": warnings or [],
    }


# --------------------------------------------------------------------------- #
# 批量添加
# --------------------------------------------------------------------------- #
def batch_add(paths: List[str], user_id: str, db: Session) -> Dict[str, Any]:
    """全有或全无的批量登记，成功时为新增路径创建单个 SCAN_FOLDER 任务。

    返回 ``{added, skipped, task_id, errors}``。任一路径校验失败则不写配置、
    不建任务，errors 列出逐项原因。
    """
    if not paths:
        return {"added": [], "skipped": [], "task_id": None, "errors": []}
    if len(paths) > BATCH_MAX_PATHS:
        raise ValueError(f"单次最多添加 {BATCH_MAX_PATHS} 个目录")

    # 归一化 + 请求内去重
    seen: Dict[str, str] = {}  # key -> display path
    ordered_paths: List[str] = []
    for raw in paths:
        if not raw or not raw.strip():
            continue
        norm = normalize_path(raw)
        key = _key(norm)
        if key in seen:
            continue
        seen[key] = norm
        ordered_paths.append(norm)

    if not ordered_paths:
        return {"added": [], "skipped": [], "task_id": None, "errors": []}

    errors: List[Dict[str, Any]] = []

    # 1) 逐项校验存在性/可读性/与已登记的冲突
    validated: List[Tuple[str, Dict[str, Any]]] = []
    skipped: List[str] = []
    existing = _registered_keys(user_id, db)
    for p in ordered_paths:
        res = validate_path(p, user_id, db)
        if res["valid"]:
            validated.append((p, res))
            continue
        # 已登记视为跳过而非失败（幂等）
        if res["error"] == ERR_ALREADY_ADDED:
            skipped.append(p)
            continue
        errors.append({"path": p, "error": res["error"], "msg": res["msg"]})

    # 2) 请求内父子冲突（同时选了 /a 与 /a/b）
    for i, (a, _) in enumerate(validated):
        for b, _ in validated[i + 1:]:
            rel = relation(a, b)
            if rel in ("parent", "child"):
                errors.append({"path": a, "error": ERR_PARENT_CONFLICT,
                               "msg": f"与 {b} 存在父子目录冲突，不能同时添加"})
                errors.append({"path": b, "error": ERR_PARENT_CONFLICT,
                               "msg": f"与 {a} 存在父子目录冲突，不能同时添加"})

    if errors:
        # 全有或全无：不写配置、不建任务
        return {"added": [], "skipped": [], "task_id": None, "errors": errors}

    # 3) 计算真正新增的路径（幂等：已登记的已在 skipped）
    existing_keys = {k for k, _ in existing}
    new_paths = [p for p, _ in validated if _key(p) not in existing_keys]

    if not new_paths:
        # 全部已存在，幂等返回，不建任务
        return {"added": [], "skipped": skipped, "task_id": None, "errors": []}

    # 4) 一次更新配置，避免循环刷缓存
    config = config_manager.get_user_config(user_id, db)
    merged = list(config.storage.external_directories or []) + new_paths
    settings = config.model_dump()
    settings.setdefault("storage", {})["external_directories"] = merged
    config_manager.update_user_config(user_id, settings, db)

    # 5) 仅为本批新增路径创建一个扫描任务（复用 user 级去重）
    task_id = None
    try:
        task = TaskManager.get_instance().add_task(
            db, TaskType.SCAN_FOLDER,
            {"scan_roots": new_paths, "user_id": str(user_id)},
        )
        task_id = str(task.id) if task else None
    except Exception as e:
        logger.error(f"创建扫描任务失败 user={user_id} roots={new_paths}: {e}")
        # 配置已写入但任务未启动：返回明确状态，前端可点「重新扫描」重试
        return {"added": new_paths, "skipped": skipped, "task_id": None,
                "errors": [{"path": ",".join(new_paths), "error": "SCAN_TASK_FAILED",
                            "msg": "图库已添加但扫描任务未启动，请稍后点「重新扫描」"}]}

    return {"added": new_paths, "skipped": skipped, "task_id": task_id, "errors": []}
