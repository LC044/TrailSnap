"""夜间盲区补测：视觉描述模型的 JSON 文本修复回路。

覆盖 app/service/tasks/visual_description.py 的
``parse_visual_result_with_repair``（此前未被任何单测按名引用）。
"""
import json

import pytest

from app.service.tasks import visual_description as vd

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

VALID = {
    "description": "夕阳下的海边栈桥",
    "tags": ["旅行", "海边"],
    "memory_score": 80,
    "beauty_score": 75,
    "reason": "画面通透",
    "narrative": "那天风很大。",
}


class _Response:
    def __init__(self, content):
        self.content = content


class _RepairClient:
    """只记录调用并按队列返回内容的假客户端。"""

    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return _Response(self._contents.pop(0))


@pytest.mark.asyncio
async def test_valid_payload_is_returned_without_repair_call():
    """已经是合法 JSON 时不得再调用模型，避免无谓的二次请求。"""
    client = _RepairClient([])

    result = await vd.parse_visual_result_with_repair(client, json.dumps(VALID), "photo-1")

    assert result["description"] == VALID["description"]
    assert result["tags"] == ["旅行", "海边"]
    assert client.calls == []


@pytest.mark.asyncio
async def test_invalid_payload_triggers_text_only_repair():
    """非法输出必须走一次纯文本修复，并且不得重新携带图片做推理。"""
    client = _RepairClient([json.dumps(VALID)])

    result = await vd.parse_visual_result_with_repair(client, "这不是 JSON", "photo-2")

    assert result["narrative"] == "那天风很大。"
    assert len(client.calls) == 1
    prompt = json.dumps(client.calls[0], ensure_ascii=False)
    assert "image_url" not in prompt
    assert "这不是 JSON" in prompt


@pytest.mark.asyncio
async def test_repair_attempts_are_bounded_and_then_raise():
    """修复次数有上限，超过上限必须抛出格式错误而不是无限重试。"""
    client = _RepairClient(["依然不是 JSON", "依然不是 JSON"])

    with pytest.raises(vd.VisualDescriptionFormatError):
        await vd.parse_visual_result_with_repair(client, "坏输出", "photo-3")

    assert len(client.calls) == vd.VISUAL_JSON_REPAIR_ATTEMPTS


@pytest.mark.asyncio
async def test_repair_accepts_fenced_json_response():
    """模型把 JSON 包在代码围栏里时，修复回路应能解析出合法结果。"""
    fenced = "```json\n" + json.dumps(VALID, ensure_ascii=False) + "\n```"
    client = _RepairClient([])

    result = await vd.parse_visual_result_with_repair(client, fenced, "photo-4")

    assert result["tags"] == ["旅行", "海边"]
    assert client.calls == []
