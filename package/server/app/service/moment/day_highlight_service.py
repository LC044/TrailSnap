"""朋友圈"每日精选"服务。

职责：
1. 按 (user, day) 从数据库拉出当天所有已 embedding 的照片（视频天然无 embedding，会被
   ``JOIN ImageVector`` 排除掉），同时 LEFT JOIN ``ImageDescription`` 拿评分；
2. 按 photo_time 排序，按 5 分钟 gap 切段；
3. 段内跑 ``AgglomerativeClustering(cosine, average, distance_threshold=1-0.9)``，把 burst
   聚成一组；
4. 每组只留 ``memory_score + quality_score`` 最大者（同分取 ``photo_time`` 更晚的）；
5. 全天代表按 ``score desc, photo_time desc`` 排序，取前 ``limit`` 张；
6. 结果不落库，每次实时计算。

photos.photo_time 是 naive 的墙上时间（EXIF 原样），当天区间直接构造 naive 边界
``[day 00:00, day+1 00:00)`` 即可，与 ``day_caption_service`` 保持一致。
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

# ---------------------------------------------------------------------------
# 常量：与 app/service/tasks/similar.py 保持一致
# ---------------------------------------------------------------------------
# 5 分钟以内的连续照片视为同一段 burst，段内才做相似度聚类，避免全天两两比较导致 O(N²)。
_GAP_SECONDS = 300
# 与工具箱"相似照片清理"保持同一相似度阈值 0.9（余弦距离 0.1）。
_SIMILARITY_THRESHOLD = 0.9
# 单段照片数上限。超过则再按硬时间点强制切段，避免极端旅行导入把段撑爆。
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
    """按 photo_time 5 分钟 gap 切段，并对超长段做二次硬切。

    切段是为了：
    - 避免全天照片两两比较（O(N²)）；
    - burst 语义上本来就限定"相隔很近的拍摄"；
    - 极端情况下（几千张）也能把每段控制在 ``_MAX_SEGMENT_SIZE`` 以内。
    """
    if not candidates:
        return []

    segments: List[List[dict]] = []
    current: List[dict] = []
    last_ts: Optional[float] = None

    def _flush_current():
        # 超长段进一步硬切
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
    """挑组内代表 + 返回该组大小。

    排序规则：``score`` 降序；``score`` 相同取 ``photo_time`` 更晚的。
    """
    if not group:
        raise ValueError("empty group")

    # datetime.min 用于兜底 None，虽然当前上游已过滤 photo_time None，但保险
    def _key(item: dict):
        pt = item.get("photo_time") or datetime.min
        return (item["score"], pt)

    representative = max(group, key=_key)
    return representative, len(group)


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

    # 全天代表按 score desc, photo_time desc 排序
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
    """批量计算 ``[start, end]`` 每一天的精选。

    调用方通常按可见月份触发，一次请求 30~31 天。逐天独立计算，方便日后单天缓存。
    """
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
