"""Unit tests for ``app/service/agent/memory.py`` —— 照片即记忆（抗幻觉长期记忆）。

聚焦本模块的核心价值：抗幻觉。所有涉及 DB 的地方都用 mock，不触碰 Postgres。

覆盖场景：
* get_valid_memory_anchors 会剔除指向失效照片（被删/不属于用户）的锚点，并回写自愈
* add_memory_anchor 拒绝无效照片、拒绝未达 memory_score 门槛的照片
* add_memory_anchor 对同一 photo_id 去重、超上限淘汰最旧锚点
* _collect_photo_ids 从助手回复的 Markdown 图片 URL 与工具返回中提取真实 photo_id
* _parse_extraction_result 能稳健解析被 ```json 包裹或含多余文本的模型输出
* build_memory_prompt 无有效记忆时返回空串
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.service.agent import memory as mem

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


# ---------------------------------------------------------------------------
# 抗幻觉核心：读取时剔除失效锚点
# ---------------------------------------------------------------------------

def test_get_valid_memory_anchors_removes_dangling_and_selfheals():
    """记忆里有 3 个锚点，但只有 2 张照片仍有效 → 返回 2 条，并回写清理后的记忆。"""
    user_id = str(uuid4())
    pid_ok1, pid_ok2, pid_dead = str(uuid4()), str(uuid4()), str(uuid4())
    raw = {
        "version": 1,
        "anchors": [
            {"photo_id": pid_ok1, "note": "a"},
            {"photo_id": pid_dead, "note": "b"},  # 该照片已被删/不属于用户
            {"photo_id": pid_ok2, "note": "c"},
        ],
    }
    db = MagicMock()
    # 校验查询只返回两张有效照片的 id
    db.query.return_value.filter.return_value.all.return_value = [
        (pid_ok1,), (pid_ok2,),
    ]

    with patch.object(mem, "load_raw_memory", return_value=raw), \
         patch.object(mem.agent_crud, "upsert_memory_message") as up:
        out = mem.get_valid_memory_anchors(db, user_id)

    returned_ids = {a["photo_id"] for a in out}
    assert returned_ids == {pid_ok1, pid_ok2}
    # 发现死引用后应回写清理结果（自愈）
    up.assert_called_once()
    written = up.call_args[0][2]
    assert {a["photo_id"] for a in written["anchors"]} == {pid_ok1, pid_ok2}


def test_get_valid_memory_anchors_empty_when_no_anchors():
    db = MagicMock()
    with patch.object(mem, "load_raw_memory", return_value={"version": 1, "anchors": []}):
        assert mem.get_valid_memory_anchors(db, str(uuid4())) == []


# ---------------------------------------------------------------------------
# 抗幻觉核心：写入门槛
# ---------------------------------------------------------------------------

def test_add_memory_anchor_rejects_invalid_photo():
    """照片不存在/不属于用户 → 快照为 None → 拒绝写入。"""
    db = MagicMock()
    with patch.object(mem, "_fetch_photo_snapshot", return_value=None), \
         patch.object(mem.agent_crud, "upsert_memory_message") as up:
        ok = mem.add_memory_anchor(db, str(uuid4()), str(uuid4()), "note")
    assert ok is False
    up.assert_not_called()


def test_add_memory_anchor_rejects_low_memory_score():
    """照片有效但 memory_score 未达门槛 → 拒绝写入。"""
    db = MagicMock()
    snap = {"photo_id": str(uuid4()), "memory_score": mem.MIN_MEMORY_SCORE - 1,
            "photo_time": None, "location": "x"}
    with patch.object(mem, "_fetch_photo_snapshot", return_value=snap), \
         patch.object(mem.agent_crud, "upsert_memory_message") as up:
        ok = mem.add_memory_anchor(db, str(uuid4()), snap["photo_id"], "note")
    assert ok is False
    up.assert_not_called()


def test_add_memory_anchor_accepts_and_dedupes():
    """达标照片写入成功；同一 photo_id 再次写入应去重（不重复累加）。"""
    db = MagicMock()
    user_id = str(uuid4())
    pid = str(uuid4())
    snap = {"photo_id": pid, "memory_score": 90.0,
            "photo_time": "2025-06-01 18:00:00", "location": "杭州"}

    store = {"version": 1, "anchors": [{"photo_id": pid, "note": "old"}]}
    with patch.object(mem, "_fetch_photo_snapshot", return_value=snap), \
         patch.object(mem, "load_raw_memory", return_value=store), \
         patch.object(mem.agent_crud, "upsert_memory_message") as up:
        ok = mem.add_memory_anchor(db, user_id, pid, "new note")

    assert ok is True
    written = up.call_args[0][2]
    same_pid = [a for a in written["anchors"] if a["photo_id"] == pid]
    assert len(same_pid) == 1  # 去重
    assert same_pid[0]["note"] == "new note"


def test_add_memory_anchor_evicts_oldest_over_limit():
    """超出 MAX_MEMORY_ANCHORS 时淘汰最旧锚点。"""
    db = MagicMock()
    user_id = str(uuid4())
    new_pid = str(uuid4())
    snap = {"photo_id": new_pid, "memory_score": 90.0,
            "photo_time": None, "location": "x"}
    # 预置正好装满上限的旧锚点
    existing = [{"photo_id": str(uuid4()), "note": f"n{i}"}
                for i in range(mem.MAX_MEMORY_ANCHORS)]
    store = {"version": 1, "anchors": existing}

    with patch.object(mem, "_fetch_photo_snapshot", return_value=snap), \
         patch.object(mem, "load_raw_memory", return_value=store), \
         patch.object(mem.agent_crud, "upsert_memory_message") as up:
        mem.add_memory_anchor(db, user_id, new_pid, "newest")

    written = up.call_args[0][2]["anchors"]
    assert len(written) == mem.MAX_MEMORY_ANCHORS
    assert written[-1]["photo_id"] == new_pid          # 新的在末尾
    assert existing[0]["photo_id"] not in {a["photo_id"] for a in written}  # 最旧被淘汰


# ---------------------------------------------------------------------------
# 辅助函数：photo_id 提取 & 抽取结果解析
# ---------------------------------------------------------------------------

def test_collect_photo_ids_from_reply_and_tool_returns():
    pid1 = "123e4567-e89b-12d3-a456-426614174000"
    pid2 = "223e4567-e89b-12d3-a456-426614174111"
    reply = f"这是照片 ![x](/api/medias/{pid1}/thumbnail)"
    tool_calls = [{"tool_return": f'{{"photos": [{{"photo_id": "{pid2}"}}]}}'}]
    ids = mem._collect_photo_ids(reply, tool_calls)
    assert ids == {pid1, pid2}


def test_collect_photo_ids_from_owner_qualified_thumbnail_url():
    owner_id = "323e4567-e89b-12d3-a456-426614174222"
    photo_id = "423e4567-e89b-12d3-a456-426614174333"
    reply = f"![x](/api/medias/{owner_id}/{photo_id}/thumbnail)"

    assert mem._collect_photo_ids(reply, None) == {photo_id}


def test_collect_photo_ids_empty_when_nothing():
    assert mem._collect_photo_ids("纯文字没有照片", None) == set()


def test_parse_extraction_result_plain_json():
    out = mem._parse_extraction_result('{"memories": [{"photo_id": "x", "note": "n"}]}')
    assert out == [{"photo_id": "x", "note": "n"}]


def test_parse_extraction_result_with_code_fence_and_noise():
    content = '好的，结果如下：\n```json\n{"memories": [{"photo_id": "x", "note": "n"}]}\n```'
    out = mem._parse_extraction_result(content)
    assert out == [{"photo_id": "x", "note": "n"}]


def test_parse_extraction_result_invalid_returns_empty():
    assert mem._parse_extraction_result("这不是 JSON") == []
    assert mem._parse_extraction_result("") == []


# ---------------------------------------------------------------------------
# 注入 prompt
# ---------------------------------------------------------------------------

def test_build_memory_prompt_empty_when_no_valid_anchors():
    db = MagicMock()
    with patch.object(mem, "get_valid_memory_anchors", return_value=[]):
        assert mem.build_memory_prompt(db, str(uuid4())) == ""


def test_build_memory_prompt_contains_photo_id_and_note():
    db = MagicMock()
    anchors = [{"photo_id": "pid-1", "note": "西湖日落",
                "photo_time": "2025-06-01", "location": "杭州"}]
    with patch.object(mem, "get_valid_memory_anchors", return_value=anchors):
        prompt = mem.build_memory_prompt(db, str(uuid4()))
    assert "pid-1" in prompt
    assert "西湖日落" in prompt


# ---------------------------------------------------------------------------
# 语义记忆检索：用照片向量做跨模态检索
# ---------------------------------------------------------------------------

def _anchor(pid, note="n"):
    return {"photo_id": pid, "note": note, "photo_time": None, "location": "x"}


def test_get_relevant_anchors_returns_all_when_few():
    """有效锚点数不超过 top_k 时，检索无意义，直接返回全部（不调用 embedding）。"""
    db = MagicMock()
    anchors = [_anchor(str(uuid4())) for _ in range(3)]
    with patch.object(mem, "get_valid_memory_anchors", return_value=anchors), \
         patch("app.utils.embedding.get_embedding") as emb:
        out = mem.get_relevant_memory_anchors(db, str(uuid4()), "杭州", top_k=6)
    assert out == anchors
    emb.assert_not_called()


def test_get_relevant_anchors_returns_all_when_blank_query():
    """query 为空白时不检索，返回全部有效锚点。"""
    db = MagicMock()
    anchors = [_anchor(str(uuid4())) for _ in range(10)]
    with patch.object(mem, "get_valid_memory_anchors", return_value=anchors):
        out = mem.get_relevant_memory_anchors(db, str(uuid4()), "   ", top_k=3)
    assert out == anchors


def test_get_relevant_anchors_orders_by_vector_distance():
    """锚点数大于 top_k 时，按照片向量 cosine 距离升序取 top_k。"""
    user_id = str(uuid4())
    pids = [str(uuid4()) for _ in range(5)]
    anchors = [_anchor(p, note=f"n{i}") for i, p in enumerate(pids)]

    db = MagicMock()
    # 模拟向量检索：返回距离最近的两条（pids[2], pids[0]）
    rows = [(pids[2], 0.1), (pids[0], 0.2)]
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

    with patch.object(mem, "get_valid_memory_anchors", return_value=anchors), \
         patch("app.utils.embedding.get_embedding", return_value=[0.0] * 512):
        out = mem.get_relevant_memory_anchors(db, user_id, "杭州西湖", top_k=2)

    assert [a["photo_id"] for a in out] == [pids[2], pids[0]]


def test_get_relevant_anchors_filters_by_max_distance():
    """距离超过 MEMORY_MAX_DISTANCE 的照片被过滤掉。"""
    user_id = str(uuid4())
    pids = [str(uuid4()) for _ in range(5)]
    anchors = [_anchor(p) for p in pids]

    db = MagicMock()
    # 一条近的、一条太远的（应被过滤）
    rows = [(pids[0], 0.2), (pids[1], mem.MEMORY_MAX_DISTANCE + 0.5)]
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

    with patch.object(mem, "get_valid_memory_anchors", return_value=anchors), \
         patch("app.utils.embedding.get_embedding", return_value=[0.0] * 512):
        out = mem.get_relevant_memory_anchors(db, user_id, "查询", top_k=2)

    assert [a["photo_id"] for a in out] == [pids[0]]


def test_get_relevant_anchors_fallback_recent_when_all_filtered():
    """全部被距离阈值过滤时，回退到时间上最近的 top_k 条，保证有记忆可用。"""
    user_id = str(uuid4())
    pids = [str(uuid4()) for _ in range(5)]
    anchors = [_anchor(p) for p in pids]

    db = MagicMock()
    rows = [(pids[0], mem.MEMORY_MAX_DISTANCE + 1)]  # 唯一命中也太远
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows

    with patch.object(mem, "get_valid_memory_anchors", return_value=anchors), \
         patch("app.utils.embedding.get_embedding", return_value=[0.0] * 512):
        out = mem.get_relevant_memory_anchors(db, user_id, "查询", top_k=2)

    assert out == anchors[-2:]


def test_get_relevant_anchors_fallback_all_on_embedding_error():
    """embedding 服务异常时，降级返回全部有效锚点，不影响对话。"""
    user_id = str(uuid4())
    anchors = [_anchor(str(uuid4())) for _ in range(10)]

    db = MagicMock()
    with patch.object(mem, "get_valid_memory_anchors", return_value=anchors), \
         patch("app.utils.embedding.get_embedding", side_effect=RuntimeError("ai down")):
        out = mem.get_relevant_memory_anchors(db, user_id, "查询", top_k=3)

    assert out == anchors


def test_build_memory_prompt_uses_semantic_search_when_user_input():
    """传入 user_input 时应走语义检索分支。"""
    db = MagicMock()
    anchors = [{"photo_id": "pid-1", "note": "西湖日落",
                "photo_time": "2025-06-01", "location": "杭州"}]
    with patch.object(mem, "get_relevant_memory_anchors", return_value=anchors) as rel, \
         patch.object(mem, "get_valid_memory_anchors") as full:
        prompt = mem.build_memory_prompt(db, str(uuid4()), user_input="杭州")
    rel.assert_called_once()
    full.assert_not_called()
    assert "西湖日落" in prompt
