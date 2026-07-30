"""朋友圈"每日精选"服务：5 分钟切段 + 余弦相似度 0.9 聚类 → 组内取
``memory_score+quality_score`` 最大者 → 按 (score, photo_time) 倒序取前 ``limit``。
视频无 embedding 自动排除；每次实时计算，不落库。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
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
