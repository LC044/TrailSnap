"""Unit tests for app/service/moment/day_highlight_service.py.

真实跑 sklearn 与内部聚类逻辑，只在 `db.execute` 边界打桩，保证核心行为
（相似去重、组内代表选择、时间窗切段、limit 生效、视频/无 embedding 排除）
真正被覆盖到。
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.service.moment import day_highlight_service as svc


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _row(photo_id, photo_time, embedding, memory_score=None, quality_score=None):
    """构造一行 select() 结果（Photo JOIN ImageVector LEFT JOIN ImageDescription）。"""
    return SimpleNamespace(
        id=photo_id,
        photo_time=photo_time,
        embedding=embedding,
        memory_score=memory_score,
        quality_score=quality_score,
    )


def _make_db(rows):
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = list(rows)
    db.execute.return_value = result
    return db


def _emb_row(photo_id, embedding):
    """构造 dedup_photo_ids 的 select() 结果行（ImageVector JOIN Photo）。"""
    return SimpleNamespace(photo_id=photo_id, embedding=embedding)


def _make_emb_db(rows):
    """dedup_photo_ids 只调用一次 db.execute(stmt).all()，复用 _make_db 即可。"""
    return _make_db(rows)


# ---------------------------------------------------------------------------
# _fetch_day_candidates: 空、无评分兜底
# ---------------------------------------------------------------------------

def test_empty_day_returns_empty():
    """当天没有任何 embedding 记录 → 精选与候选总数都是 0。"""
    db = _make_db([])
    highlights, total = svc.get_day_highlights(db, uuid4(), date(2025, 8, 5))
    assert highlights == []
    assert total == 0


def test_missing_scores_treated_as_zero():
    """memory_score / quality_score 为 None 时应当兜底为 0，而不是抛异常。"""
    p1 = uuid4()
    db = _make_db([
        _row(p1, datetime(2025, 8, 5, 10, 0, 0), [1.0, 0.0, 0.0]),
    ])
    highlights, total = svc.get_day_highlights(db, uuid4(), date(2025, 8, 5))
    assert total == 1
    assert len(highlights) == 1
    assert highlights[0]["id"] == p1
    assert highlights[0]["score"] == 0.0
    assert highlights[0]["group_size"] == 1


# ---------------------------------------------------------------------------
# 核心行为：相似去重 + 组内代表选择
# ---------------------------------------------------------------------------

def test_similar_burst_deduped_and_highest_score_wins():
    """5 分钟内同向量的两张连拍 → 聚成 1 组 → 保留 score 更高者。"""
    day = date(2025, 8, 5)
    p_low, p_high = uuid4(), uuid4()
    db = _make_db([
        _row(p_low, datetime(2025, 8, 5, 10, 0, 0), [1.0, 0.0, 0.0], memory_score=20, quality_score=10),
        _row(p_high, datetime(2025, 8, 5, 10, 0, 30), [1.0, 0.0, 0.0], memory_score=50, quality_score=40),
    ])
    highlights, total = svc.get_day_highlights(db, uuid4(), day)
    assert total == 2
    assert len(highlights) == 1
    assert highlights[0]["id"] == p_high
    assert highlights[0]["score"] == 90.0
    assert highlights[0]["group_size"] == 2


def test_tie_score_prefers_later_photo_time():
    """同 score 时，取 photo_time 更晚的作为组代表。"""
    day = date(2025, 8, 5)
    early, late = uuid4(), uuid4()
    db = _make_db([
        _row(early, datetime(2025, 8, 5, 10, 0, 0), [1.0, 0.0], memory_score=30, quality_score=30),
        _row(late, datetime(2025, 8, 5, 10, 1, 0), [1.0, 0.0], memory_score=30, quality_score=30),
    ])
    highlights, _ = svc.get_day_highlights(db, uuid4(), day)
    assert len(highlights) == 1
    assert highlights[0]["id"] == late


def test_distinct_photos_each_form_singleton_group():
    """向量差异大的照片各自成组，不会被误合并。"""
    day = date(2025, 8, 5)
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    db = _make_db([
        _row(p1, datetime(2025, 8, 5, 10, 0, 0), [1.0, 0.0, 0.0], memory_score=50, quality_score=50),
        _row(p2, datetime(2025, 8, 5, 10, 0, 30), [0.0, 1.0, 0.0], memory_score=40, quality_score=40),
        _row(p3, datetime(2025, 8, 5, 10, 1, 0), [0.0, 0.0, 1.0], memory_score=30, quality_score=30),
    ])
    highlights, total = svc.get_day_highlights(db, uuid4(), day)
    assert total == 3
    assert len(highlights) == 3
    # 每组 group_size 都是 1
    assert all(h["group_size"] == 1 for h in highlights)
    # score 降序排序：p1 → p2 → p3
    assert [h["id"] for h in highlights] == [p1, p2, p3]


# ---------------------------------------------------------------------------
# 时间窗切段：5 分钟 gap 隔开的相似向量不应被聚在一起
# ---------------------------------------------------------------------------

def test_time_gap_splits_segments():
    """相似向量若隔了 5 分钟以上，应视为不同事件，各自保留代表。"""
    day = date(2025, 8, 5)
    p_morning, p_afternoon = uuid4(), uuid4()
    db = _make_db([
        _row(p_morning, datetime(2025, 8, 5, 10, 0, 0), [1.0, 0.0], memory_score=30, quality_score=20),
        # 隔了 6 分钟，超过 5 分钟 gap → 切段
        _row(p_afternoon, datetime(2025, 8, 5, 10, 6, 0), [1.0, 0.0], memory_score=10, quality_score=10),
    ])
    highlights, total = svc.get_day_highlights(db, uuid4(), day)
    assert total == 2
    assert len(highlights) == 2
    assert {h["id"] for h in highlights} == {p_morning, p_afternoon}


# ---------------------------------------------------------------------------
# limit 生效：全天代表数超过 limit 时截断
# ---------------------------------------------------------------------------

def test_limit_caps_result_size_and_keeps_top_scored():
    """limit=2 时应只返回 score 最高的 2 张。"""
    day = date(2025, 8, 5)
    lo, mid, hi = uuid4(), uuid4(), uuid4()
    # 三张向量都不同 → 三个 singleton；score 分别 10 / 50 / 90
    db = _make_db([
        _row(lo, datetime(2025, 8, 5, 10, 0, 0), [1.0, 0.0, 0.0], memory_score=5, quality_score=5),
        _row(mid, datetime(2025, 8, 5, 10, 1, 0), [0.0, 1.0, 0.0], memory_score=25, quality_score=25),
        _row(hi, datetime(2025, 8, 5, 10, 2, 0), [0.0, 0.0, 1.0], memory_score=45, quality_score=45),
    ])
    highlights, total = svc.get_day_highlights(db, uuid4(), day, limit=2)
    assert total == 3
    assert [h["id"] for h in highlights] == [hi, mid]


# ---------------------------------------------------------------------------
# get_range_highlights: 逐天独立、无数据的天不返回
# ---------------------------------------------------------------------------

def test_range_only_includes_days_with_data():
    """区间内只有 08-06 有数据 → 结果只含 08-06。"""
    p = uuid4()
    call_dates = []

    def _execute(_stmt):
        # 每天一次调用；只有 08-06 那次返回一行
        current_day = call_dates.pop(0) if call_dates else None
        m = MagicMock()
        if current_day == date(2025, 8, 6):
            m.all.return_value = [
                _row(p, datetime(2025, 8, 6, 10, 0, 0), [1.0, 0.0], memory_score=50, quality_score=50)
            ]
        else:
            m.all.return_value = []
        return m

    call_dates.extend([date(2025, 8, 5) + timedelta(days=i) for i in range(3)])

    db = MagicMock()
    db.execute.side_effect = _execute

    result = svc.get_range_highlights(db, uuid4(), date(2025, 8, 5), date(2025, 8, 7))
    assert len(result) == 1
    assert result[0]["day"] == date(2025, 8, 6)
    assert len(result[0]["photos"]) == 1
    assert result[0]["photos"][0]["id"] == p
    assert result[0]["total_candidates"] == 1


def test_range_returns_empty_when_start_after_end():
    """start > end → 直接返回空，不查数据库。"""
    db = MagicMock()
    result = svc.get_range_highlights(db, uuid4(), date(2025, 8, 10), date(2025, 8, 1))
    assert result == []
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# dedup_photo_ids：任意 id 集合的相似度去重（拼图按省池复用）
# ---------------------------------------------------------------------------

def test_dedup_photo_ids_empty_returns_empty():
    """空输入 → 空输出，不查库。"""
    db = MagicMock()
    assert svc.dedup_photo_ids(db, uuid4(), []) == []
    db.execute.assert_not_called()


def test_dedup_photo_ids_distinct_all_kept_in_order():
    """向量两两正交 → 各自成簇 → 全部保留且保持输入顺序。"""
    a, b, c = uuid4(), uuid4(), uuid4()
    db = _make_emb_db([
        _emb_row(a, [1.0, 0.0, 0.0]),
        _emb_row(b, [0.0, 1.0, 0.0]),
        _emb_row(c, [0.0, 0.0, 1.0]),
    ])
    assert svc.dedup_photo_ids(db, uuid4(), [a, b, c]) == [a, b, c]


def test_dedup_photo_ids_similar_first_kept():
    """两张同向量（cosine=1）→ 聚成一簇 → 保留输入序最早的。"""
    a, b = uuid4(), uuid4()
    db = _make_emb_db([
        _emb_row(a, [1.0, 0.0, 0.0]),
        _emb_row(b, [1.0, 0.0, 0.0]),
    ])
    assert svc.dedup_photo_ids(db, uuid4(), [a, b]) == [a]
    # 顺序反过来 → 保留 b
    db2 = _make_emb_db([
        _emb_row(a, [1.0, 0.0, 0.0]),
        _emb_row(b, [1.0, 0.0, 0.0]),
    ])
    assert svc.dedup_photo_ids(db2, uuid4(), [b, a]) == [b]


def test_dedup_photo_ids_no_embedding_passthrough():
    """无 embedding 的 id 原样透传、保持原位（不敢丢，保证数量足够）。"""
    a, b, c = uuid4(), uuid4(), uuid4()
    # 只有 a 有 embedding；b、c 不在 emb_map 里
    db = _make_emb_db([_emb_row(a, [1.0, 0.0, 0.0])])
    assert svc.dedup_photo_ids(db, uuid4(), [a, b, c]) == [a, b, c]


def test_dedup_photo_ids_mixed_order_preserved():
    """混合：a/b 相似、c 独立、d 无 embedding → [a, c, d]，顺序保持。"""
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
    db = _make_emb_db([
        _emb_row(a, [1.0, 0.0, 0.0]),
        _emb_row(b, [1.0, 0.0, 0.0]),  # 与 a 同向量 → 被去重
        _emb_row(c, [0.0, 1.0, 0.0]),  # 独立
        # d 无 embedding → 透传
    ])
    assert svc.dedup_photo_ids(db, uuid4(), [a, b, c, d]) == [a, c, d]


def test_dedup_photo_ids_sklearn_failure_returns_input(monkeypatch):
    """sklearn 聚类抛异常时回退为全保留（不去重是永远安全的状态）。"""
    a, b = uuid4(), uuid4()

    class _BoomCluster:
        def __init__(self, *args, **kwargs):
            pass

        def fit_predict(self, _X):
            raise RuntimeError("boom")

    # _cluster_ids_by_embedding 内部 `from sklearn.cluster import AgglomerativeClustering`
    # 在调用时才执行，patch 模块属性即可生效
    import sklearn.cluster as sk_cluster
    monkeypatch.setattr(sk_cluster, "AgglomerativeClustering", _BoomCluster)

    db = _make_emb_db([
        _emb_row(a, [1.0, 0.0, 0.0]),
        _emb_row(b, [1.0, 0.0, 0.0]),
    ])
    # 即使 a/b 同向量，聚类失败 → 全保留
    assert svc.dedup_photo_ids(db, uuid4(), [a, b]) == [a, b]


def test_dedup_photo_ids_dedupes_input_duplicates():
    """输入里同一个 id 出现两次 → 仅返回一次（保序去重在聚类之前）。"""
    a, b = uuid4(), uuid4()
    db = _make_emb_db([
        _emb_row(a, [1.0, 0.0, 0.0]),
        _emb_row(b, [0.0, 1.0, 0.0]),
    ])
    assert svc.dedup_photo_ids(db, uuid4(), [a, a, b]) == [a, b]
