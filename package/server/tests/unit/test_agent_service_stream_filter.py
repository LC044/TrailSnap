from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import pytest

from app.service.agent.service import ThinkTagStreamFilter, _messages_to_text

pytestmark = [pytest.mark.smoke]


def test_think_stream_filter_splits_cross_chunk_tags():
    stream_filter = ThinkTagStreamFilter()

    visible, reasoning = stream_filter.feed("Hello <th")
    assert visible == "Hello "
    assert reasoning == ""

    visible, reasoning = stream_filter.feed("ink>hidden</think>")
    assert visible == ""
    assert reasoning == "hidden"

    visible, reasoning = stream_filter.feed("World")
    assert visible == "World"
    assert reasoning == ""


def test_think_stream_filter_flush_drops_unclosed_reasoning():
    stream_filter = ThinkTagStreamFilter()
    stream_filter.feed("Visible <think>unfinished")

    assert stream_filter.flush() == ("", "")
    assert stream_filter.buffer == ""


def test_messages_to_text_uses_readable_roles_and_ignores_system():
    messages = [
        SystemMessage(content="system prompt"),
        HumanMessage(content="查找九月的照片"),
        AIMessage(content="找到 3 张照片"),
        AIMessage(content=[{"type": "text", "text": "结构化回复"}]),
    ]

    text = _messages_to_text(messages)

    assert "用户：查找九月的照片" in text
    assert "助手：找到 3 张照片" in text
    assert "结构化回复" in text
    assert "system prompt" not in text