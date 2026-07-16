#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Description : 文件夹 / 相对路径相关的公共工具。

设计说明（对应 Issue #78「按文件夹管理」）：
- 系统并未把「文件夹层级」单独建模，目录信息隐含在 ``Photo.file_path`` 里。
- 由于 ``storage._get_storage_root`` 返回相对路径 ``./data/uploads``，而扫描导入的
  ``external_directories`` 通常是绝对路径，因此库中同时存在「相对路径」与「绝对路径」
  两种形态。这里统一用 ``os.path.abspath`` 归一后再做前缀匹配，保证两种形态都能正确
  剥离出「相对于根目录的文件夹路径」。
- 所有需要「相对路径 / 文件夹」的地方（AI 分析、AI 搜索、文件夹浏览）都应复用本模块，
  避免逻辑分散、口径不一致。
"""

import os
from typing import List, Optional, Tuple
from uuid import UUID


def _normalize(path: str) -> str:
    """统一分隔符为 / 并去掉结尾斜杠。"""
    if not path:
        return ""
    return os.path.abspath(path).replace("\\", "/").rstrip("/")


def get_user_roots(user_id: UUID, db) -> List[str]:
    """组装某用户的所有「照片根目录」，用于计算相对路径。

    包含：
      - photo_storage_path 及其 uploads 子目录（上传照片实际落在 {root}/uploads/年/月）
      - 所有 external_directories（扫描导入，保留原始层级）

    返回按路径长度降序排列的归一化绝对路径列表（长的优先匹配，避免父根抢占子根）。
    """
    try:
        from app.core.config_manager import config_manager
        config = config_manager.get_user_config(user_id, db)
        storage_cfg = config.storage
        primary = storage_cfg.photo_storage_path or "./data/uploads"
        external = storage_cfg.external_directories or []
    except Exception:
        primary = "./data/uploads"
        external = []

    roots = set()
    if primary:
        roots.add(_normalize(primary))
        # 上传文件落在 {primary}/uploads 下，把它也作为根，剥离后更贴近用户视角
        roots.add(_normalize(os.path.join(primary, "uploads")))
    for ext in external:
        if ext:
            roots.add(_normalize(ext))

    roots.discard("")
    # 长路径优先，保证子目录根不会被父目录根提前匹配
    return sorted(roots, key=len, reverse=True)


def compute_relative_path(file_path: str, roots: List[str]) -> Tuple[str, str]:
    """根据根目录列表，从完整 file_path 计算 (相对文件夹路径, 文件名)。

    - 命中某个 root：返回相对该 root 的文件夹路径（如 ``旅游/景点``）与文件名。
    - 未命中任何 root：降级为 file_path 的父目录名 + 文件名。
    - 统一使用 / 分隔符。
    """
    if not file_path:
        return "", ""

    norm = _normalize(file_path)
    filename = os.path.basename(norm)

    matched_root = ""
    for r in roots or []:
        if not r:
            continue
        if norm == r:
            matched_root = r
            break
        if norm.startswith(r + "/") and len(r) > len(matched_root):
            matched_root = r

    if matched_root:
        rel = norm[len(matched_root) + 1:]  # 去掉 root 前缀与其后的 /
        folder = os.path.dirname(rel)
    else:
        # 兜底：无法归属到任何根，取父目录名
        folder = os.path.basename(os.path.dirname(norm))

    return folder, filename


def compute_relative_folder(file_path: str, roots: List[str]) -> str:
    """只取相对文件夹路径的便捷方法。"""
    folder, _ = compute_relative_path(file_path, roots)
    return folder


def compute_browse_path(file_path: str, roots: List[str]) -> Tuple[str, str]:
    """用于「文件夹浏览」的相对路径：以扫描根目录名作为顶层文件夹。

    与 :func:`compute_relative_path` 的区别：本函数会 **保留匹配到的根目录名**
    作为第一级文件夹（如 ``旅游/景点``、``picture``），使多个扫描根在浏览时各自
    成为独立的顶层文件夹，而不会把各根下的直属照片压平到同一个「根层」。

    - 命中某个 root：返回 ``{根目录名}/{根内文件夹}`` 与文件名。
    - 未命中任何 root：降级为 file_path 的父目录名 + 文件名。
    """
    if not file_path:
        return "", ""

    norm = _normalize(file_path)
    filename = os.path.basename(norm)

    matched_root = ""
    for r in roots or []:
        if not r:
            continue
        if norm.startswith(r + "/") and len(r) > len(matched_root):
            matched_root = r

    if matched_root:
        within = norm[len(matched_root) + 1:]       # 根内相对路径（含文件名）
        within_folder = os.path.dirname(within)     # 根内文件夹（不含文件名）
        root_label = os.path.basename(matched_root) or matched_root
        folder = root_label + ("/" + within_folder if within_folder else "")
    else:
        # 兜底：无法归属到任何根，取父目录名
        folder = os.path.basename(os.path.dirname(norm))

    return folder, filename


def build_folder_list(paths_with_meta, roots: List[str]) -> List[dict]:
    """根据 (file_path, ...) 列表构建「文件夹列表」。

    为避免「相对/绝对路径混存」在 SQL 过滤时出错，这里按 **原始 dirname(file_path)**
    分组（与现有 /stats/folder 口径一致）；节点同时提供 ``rel_path``（相对路径，用于展示）。

    参数:
        paths_with_meta: 可迭代对象，每项至少含 file_path（取 [0]）。
        roots: get_user_roots 的结果。
    返回:
        列表，每项:
          {
            "value": 原始文件夹路径（用于按前缀精确过滤，如 /mnt/nas/旅游/景点）,
            "rel_path": 相对根目录的展示路径（如 旅游/景点）,
            "name": 末级文件夹名,
            "count": 照片数
          }
    """
    folder_map = {}
    for row in paths_with_meta:
        # 兼容三种输入：纯字符串、(file_path, ...) 元组、SQLAlchemy Row 对象
        if isinstance(row, str):
            fp = row
        else:
            try:
                fp = row[0]
            except (TypeError, KeyError, IndexError):
                fp = row
        if not fp or not isinstance(fp, str):
            continue
        raw_folder = os.path.dirname(fp.replace("\\", "/"))
        if raw_folder not in folder_map:
            rel_folder, _ = compute_relative_path(fp, roots)
            folder_map[raw_folder] = {"count": 0, "rel_path": rel_folder}
        folder_map[raw_folder]["count"] += 1

    result = []
    for raw_folder, info in folder_map.items():
        rel = info["rel_path"]
        name = (rel.split("/")[-1] if rel else "") or os.path.basename(raw_folder) or "根目录"
        result.append({
            "value": raw_folder,
            "rel_path": rel,
            "name": name,
            "count": info["count"],
        })
    result.sort(key=lambda x: x["rel_path"] or x["value"])
    return result


def build_folder_tree_level(paths_with_meta, roots: List[str], parent: str = "") -> dict:
    """按「层级」返回某个父目录下的下一层内容（用于层级树浏览，Issue #78）。

    参数:
        paths_with_meta: 可迭代对象，每项至少含 file_path（取 [0]）。
        roots: get_user_roots 的结果。
        parent: 相对父目录路径（如 "" 表示根、"旅游" 表示进入旅游层）。统一用 / 分隔。
    返回:
        {
          "parent": 规范化后的父路径,
          "breadcrumb": [{"name","path"}...] 面包屑（不含"全部"根，前端自行补），
          "own_count": 本层直属照片数（直接位于 parent 下、无更深子目录的照片）,
          "children": [
             {"name": 子目录名, "path": 子目录相对路径, "count": 该子树照片总数, "has_children": bool}
          ]
        }
    """
    parent = (parent or "").replace("\\", "/").strip("/")
    prefix = (parent + "/") if parent else ""

    child_agg = {}   # child_name -> {"count": int, "has_children": bool}
    own_count = 0

    for row in paths_with_meta:
        if isinstance(row, str):
            fp = row
        else:
            try:
                fp = row[0]
            except (TypeError, KeyError, IndexError):
                fp = row
        if not fp or not isinstance(fp, str):
            continue

        # 浏览用相对路径：以扫描根目录名作为顶层文件夹，避免多根压平到同一根层
        rel_folder, _ = compute_browse_path(fp, roots)
        rel_folder = (rel_folder or "").replace("\\", "/").strip("/")

        # 只关心处于 parent 之下（或恰好等于 parent）的照片
        if parent:
            if rel_folder == parent:
                own_count += 1
                continue
            if not rel_folder.startswith(prefix):
                continue
            remainder = rel_folder[len(prefix):]
        else:
            if rel_folder == "":
                own_count += 1
                continue
            remainder = rel_folder

        # remainder 形如 "景点" 或 "景点/黄山"
        segments = remainder.split("/")
        child = segments[0]
        info = child_agg.setdefault(child, {"count": 0, "has_children": False})
        info["count"] += 1
        if len(segments) > 1:
            info["has_children"] = True

    children = []
    for name, info in child_agg.items():
        child_path = (prefix + name) if prefix else name
        children.append({
            "name": name,
            "path": child_path,
            "count": info["count"],
            "has_children": info["has_children"],
        })
    children.sort(key=lambda x: x["name"])

    # 面包屑
    breadcrumb = []
    if parent:
        acc = []
        for seg in parent.split("/"):
            acc.append(seg)
            breadcrumb.append({"name": seg, "path": "/".join(acc)})

    return {
        "parent": parent,
        "breadcrumb": breadcrumb,
        "own_count": own_count,
        "children": children,
    }
