"""朋友圈"每日精选"服务：5 分钟切段 + 余弦相似度 0.9 聚类 → 组内取
``memory_score+quality_score`` 最大者 → 按 (score, photo_time) 倒序取前 ``limit``。
视频无 embedding 自动排除；每次实时计算，不落库。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.image_description import ImageDescription
from app.db.models.image_vector import ImageVector
from app.db.models.photo import Photo

logger = logging.getLogger(__name__)

# 与 app/service/tasks/similar.py 保持一致：5 分钟切段 + 余弦相似度 0.9；
# 单段上限 200 张防止极端旅行导入触发 O(N²) 聚类。
_GAP_SECONDS = 300
_SIMILARITY_THRESHOLD = 0.9
_MAX_SEGMENT_SIZE = 200
# 泛化去重（dedup_photo_ids）的 O(N²) 安全上限：超过则分批聚类，
# 可能漏掉跨批的重复，但保底不崩。拼图单省池上限 800，远低于此值。
_MAX_CLUSTER_INPUT = 1000


def _day_bounds_naive(day: date) -> Tuple[datetime, datetime]:
    """返回 ``day`` 那天的 naive 边界 ``[start, end)``。"""
    start = datetime(day.year, day.month, day.day, 0, 0, 0)
    end = start + timedelta(days=1)
    return start, end


def _fetch_day_candidates(
    db: Session,
    user_id: UUID,
    day: date,
) -> List[dict]:
    """拉出当天可以进入精选池的照片。

    返回列表元素含 ``id / photo_time / embedding / score``。
    视频没有 ``ImageVector`` 记录，会被 JOIN 掉，自动排除。
    """
    start, end = _day_bounds_naive(day)

    stmt = (
        select(
            Photo.id,
            Photo.photo_time,
            ImageVector.embedding,
            ImageDescription.memory_score,
            ImageDescription.quality_score,
        )
        .join(ImageVector, ImageVector.photo_id == Photo.id)
        .outerjoin(ImageDescription, ImageDescription.photo_id == Photo.id)
        .where(
            Photo.owner_id == user_id,
            Photo.is_deleted.is_(False),
            Photo.photo_time.isnot(None),
            Photo.photo_time >= start,
            Photo.photo_time < end,
        )
        .order_by(Photo.photo_time.asc())
    )

    rows = db.execute(stmt).all()
    candidates: List[dict] = []
    for r in rows:
        m = r.memory_score or 0.0
        q = r.quality_score or 0.0
        candidates.append(
            {
                "id": r.id,
                "photo_time": r.photo_time,
                "embedding": r.embedding,
                "score": float(m) + float(q),
            }
        )
    return candidates


def _segment_by_time(candidates: List[dict]) -> List[List[dict]]:
    """按 photo_time 5 分钟 gap 切段，超长段再按 ``_MAX_SEGMENT_SIZE`` 硬切。"""
    if not candidates:
        return []

    segments: List[List[dict]] = []
    current: List[dict] = []
    last_ts: Optional[float] = None

    def _flush_current():
        if len(current) <= _MAX_SEGMENT_SIZE:
            segments.append(current[:])
        else:
            for i in range(0, len(current), _MAX_SEGMENT_SIZE):
                segments.append(current[i : i + _MAX_SEGMENT_SIZE])

    for item in candidates:
        pt: datetime = item["photo_time"]
        ts = pt.timestamp()
        if last_ts is not None and (ts - last_ts) > _GAP_SECONDS:
            _flush_current()
            current = []
        current.append(item)
        last_ts = ts

    if current:
        _flush_current()

    return segments


def _cluster_segment(segment: List[dict]) -> List[List[dict]]:
    """段内跑相似度聚类；单张段直接返回单元素分组。"""
    if len(segment) <= 1:
        return [segment]

    # 局部导入以避免模块加载时就 import sklearn
    from sklearn.cluster import AgglomerativeClustering

    vecs = []
    for item in segment:
        emb = item["embedding"]
        vecs.append(np.asarray(emb, dtype=np.float32))
    X = np.stack(vecs)

    # 归一化到单位球，与工具箱 similar.py 保持一致
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    X = X / norms

    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=1 - _SIMILARITY_THRESHOLD,
    )
    try:
        labels = clustering.fit_predict(X)
    except Exception as e:  # pragma: no cover - 极端 embedding 场景保底
        logger.warning("[moment.highlights] cluster failed (%s), fall back to no-cluster", e)
        return [[item] for item in segment]

    groups: Dict[int, List[dict]] = defaultdict(list)
    for item, label in zip(segment, labels):
        groups[int(label)].append(item)
    return list(groups.values())


def _pick_group_representative(group: List[dict]) -> Tuple[dict, int]:
    """``score`` 降序；``score`` 相同取 ``photo_time`` 更晚的。返回 (代表, 组大小)。"""
    if not group:
        raise ValueError("empty group")

    def _key(item: dict):
        return (item["score"], item.get("photo_time") or datetime.min)

    return max(group, key=_key), len(group)


def get_day_highlights(
    db: Session,
    user_id: UUID,
    day: date,
    limit: int = 9,
) -> Tuple[List[dict], int]:
    """计算某天的精选照片列表。

    返回 ``(highlights, total_candidates)``：
    - ``highlights`` 元素含 ``id / photo_time / score / group_size``；
    - ``total_candidates`` 是参与精选池的候选总数（照片，非视频）。
    """
    candidates = _fetch_day_candidates(db, user_id, day)
    total_candidates = len(candidates)
    if total_candidates == 0:
        return [], 0

    segments = _segment_by_time(candidates)

    reps: List[dict] = []
    for seg in segments:
        for group in _cluster_segment(seg):
            rep, size = _pick_group_representative(group)
            reps.append(
                {
                    "id": rep["id"],
                    "photo_time": rep["photo_time"],
                    "score": rep["score"],
                    "group_size": size,
                }
            )

    reps.sort(
        key=lambda r: (r["score"], r["photo_time"] or datetime.min),
        reverse=True,
    )
    return reps[:limit], total_candidates


def get_range_highlights(
    db: Session,
    user_id: UUID,
    start: date,
    end: date,
    limit: int = 9,
) -> List[dict]:
    """批量计算 ``[start, end]`` 每一天的精选。逐天独立计算，方便日后按天缓存。"""
    if start > end:
        return []

    result: List[dict] = []
    day = start
    while day <= end:
        photos, total = get_day_highlights(db, user_id, day, limit=limit)
        if photos:
            result.append(
                {
                    "day": day,
                    "photos": photos,
                    "total_candidates": total,
                }
            )
        day = day + timedelta(days=1)
    return result


def dedup_day_photo_ids(
    db: Session,
    user_id: UUID,
    day: date,
) -> Tuple[set, dict]:
    """与 ``get_day_highlights`` 同样的聚类但**不截断**：返回当天所有 burst 代表。

    返回 ``(kept_ids, stats)``：``kept_ids`` 为代表 photo_id 集合；
    ``stats = {"total_candidates": N, "kept": M}``（N=参与聚类总数，M=去重后组数）。
    供文案素材去重使用（需保留全天不同瞬间，不适合取 top-N）。
    """
    candidates = _fetch_day_candidates(db, user_id, day)
    if not candidates:
        return set(), {"total_candidates": 0, "kept": 0}

    kept: set = set()
    for seg in _segment_by_time(candidates):
        for group in _cluster_segment(seg):
            rep, _size = _pick_group_representative(group)
            kept.add(rep["id"])

    return kept, {"total_candidates": len(candidates), "kept": len(kept)}


def _cluster_ids_by_embedding(
    items: List[Tuple[UUID, Any]],
    threshold: float,
) -> set:
    """对 ``(photo_id, embedding)`` 列表跑余弦聚类，返回每簇**首个出现**的 photo_id 集合。

    ``items`` 必须按期望的代表优先级排序——单遍扫描时 ``setdefault`` 取到的就是
    输入序最早的 id，与 moments「组内最高分代表」语义一致（拼图按策略拉取，
    最早出现 = 该簇最高分 / 最新 / 任意，取决于策略，均可接受）。

    与 ``_cluster_segment`` 同样的 sklearn 配置（cosine + average linkage +
    ``distance_threshold = 1 - threshold``）；sklearn 失败时回退为全保留
    （不去重是永远安全的状态，只是池里多一些重复）。
    """
    from sklearn.cluster import AgglomerativeClustering

    X = np.stack([np.asarray(emb, dtype=np.float32) for _, emb in items])
    # 归一化到单位球，与 _cluster_segment 保持一致；零向量兜底避免除零
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    X = X / norms

    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=1 - threshold,
    )
    try:
        labels = clustering.fit_predict(X)
    except Exception as e:  # pragma: no cover - 极端 embedding 场景保底
        logger.warning("[dedup] cluster failed (%s), skip dedup", e)
        return {pid for pid, _ in items}

    cluster_first: Dict[int, UUID] = {}
    for (pid, _), label in zip(items, labels):
        cluster_first.setdefault(int(label), pid)
    return set(cluster_first.values())


def dedup_photo_ids(
    db: Session,
    user_id: UUID,
    photo_ids: List[UUID],
    threshold: float = _SIMILARITY_THRESHOLD,
) -> List[UUID]:
    """对给定 photo_id 列表按 CLIP embedding 余弦相似度去重，保持输入顺序，**不截断**。

    与按天的 ``dedup_day_photo_ids`` 区别在于：① 接受任意 id 集合（不限定某天），
    供拼图按省 / 按筛选条件去重；② 整池一次聚类，不做 5 分钟时间切段——拼图池
    按策略排序而非时间，且跨时间的近重复（cosine > 0.9 本就是近乎同一张）也该合并，
    拼图要的是视觉多样性；③ 无 embedding 的照片**原样透传**而非丢弃（不能判重的不
    敢丢，避免破坏「数量足够」；对齐 ``day_caption_service._dedup_similar_photos``
    的「没 embedding：保留」策略）。

    - 相似度 >= ``threshold`` 归为一组，保留组内输入序最早的那张；
    - 无 ``ImageVector`` 记录的 id 原样保留在原位；
    - 返回 = 全部组代表 + 无向量透传项，按输入顺序输出；
    - 超过 ``_MAX_CLUSTER_INPUT`` 时分批聚类（可能漏跨批重复，保底不崩）。
    """
    if not photo_ids:
        return []

    # 输入里可能有重复 id，按首次出现位置去重并保序
    seen: set = set()
    ordered_ids: List[UUID] = []
    for pid in photo_ids:
        if pid not in seen:
            seen.add(pid)
            ordered_ids.append(pid)

    # 拉取这些 id 的 embedding（owner + is_deleted 防御性过滤，对齐 _fetch_day_candidates）
    stmt = (
        select(ImageVector.photo_id, ImageVector.embedding)
        .join(Photo, ImageVector.photo_id == Photo.id)
        .where(
            Photo.owner_id == user_id,
            Photo.is_deleted.is_(False),
            ImageVector.photo_id.in_(ordered_ids),
        )
    )
    rows = db.execute(stmt).all()
    emb_map: Dict[UUID, Any] = {r.photo_id: r.embedding for r in rows}

    # 按输入顺序整理出有 embedding 的子序列（顺序决定代表选择）
    embeddable: List[Tuple[UUID, Any]] = [
        (pid, emb_map[pid]) for pid in ordered_ids if pid in emb_map
    ]
    no_embedding: set = set(ordered_ids) - set(emb_map.keys())

    if len(embeddable) <= 1:
        return list(ordered_ids)

    kept_embeddable: set = set()
    for i in range(0, len(embeddable), _MAX_CLUSTER_INPUT):
        chunk = embeddable[i : i + _MAX_CLUSTER_INPUT]
        kept_embeddable |= _cluster_ids_by_embedding(chunk, threshold)

    kept_set = kept_embeddable | no_embedding
    return [pid for pid in ordered_ids if pid in kept_set]
