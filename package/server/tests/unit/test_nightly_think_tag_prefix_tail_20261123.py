"""Nightly watch 2026-11-23 - app/service/agent/service.py 的 ThinkTagStreamFilter 盲区。

ThinkTagStreamFilter 把 MiniMax 风格的 <think>...</think> 内容从可见输出里
剥离到 reasoning 通道。难点在于标记可能被 chunk 边界切断，
_prefix_tail 负责算出「缓冲区末尾有多少个字符正好是标记的**开头前缀**」，
以便把这截残片留在缓冲区里等待下一块。

关键语义：_prefix_tail 判断的是「标记是否以这段尾巴**开头**」，
所以尾巴必须是标记的真前缀（完整标记本身不算残片，返回 0）；
例如缓冲区结尾是 "abc>" 时它并不是 "</think>" 的前缀，
因此不会被暂存，而结尾是 "</thi" 时会被暂存 5 个字符。

本文件覆盖：

- _prefix_tail 对真前缀 / 完整标记 / 无关文本 / 空串的判定（happy + edge）
- feed 在标记被切断时把残片留在缓冲区里（edge）
- feed 在完整标记出现时切换通道（happy）
- flush 把缓冲区里的残片交还给正确的通道（happy + edge）
"""

import pytest

from app.service.agent.service import ThinkTagStreamFilter

pytestmark = [pytest.mark.smoke]


def test_prefix_tail_matches_a_truncated_marker():
    assert ThinkTagStreamFilter._prefix_tail("<thi", "<think>") == 4
    assert ThinkTagStreamFilter._prefix_tail("<", "<think>") == 1
    assert ThinkTagStreamFilter._prefix_tail("x<th", "<think>") == 3
    assert ThinkTagStreamFilter._prefix_tail("</thi", "</think>") == 5


def test_prefix_tail_returns_zero_for_a_complete_marker():
    # 完整标记不是「真前缀」，无需暂存。
    assert ThinkTagStreamFilter._prefix_tail("<think>", "<think>") == 0


def test_prefix_tail_returns_zero_for_unrelated_text():
    assert ThinkTagStreamFilter._prefix_tail("abc", "<think>") == 0
    assert ThinkTagStreamFilter._prefix_tail("", "<think>") == 0


def test_prefix_tail_only_matches_the_beginning_of_the_marker():
    # 尾巴必须与标记的开头一致：结尾是 ">" 不是 "</think>" 的前缀。
    assert ThinkTagStreamFilter._prefix_tail("abc>", "</think>") == 0
    assert ThinkTagStreamFilter._prefix_tail(">", "</think>") == 0


def test_prefix_tail_never_exceeds_the_marker_length():
    # 最多保留 len(marker) - 1 个字符。
    assert ThinkTagStreamFilter._prefix_tail("<think>" * 3, "<think>") == 0
    assert ThinkTagStreamFilter._prefix_tail("<thi", "<think>") <= len("<think>") - 1
    assert ThinkTagStreamFilter._prefix_tail("</thi", "</think>") <= len("</think>") - 1


def test_feed_keeps_a_split_marker_in_the_buffer():
    stream = ThinkTagStreamFilter()

    visible, reasoning = stream.feed("<thi")

    assert visible == ""
    assert reasoning == ""
    assert stream.buffer == "<thi"


def test_feed_switches_channel_when_the_marker_completes():
    stream = ThinkTagStreamFilter()
    stream.feed("<thi")

    visible, reasoning = stream.feed("nk>hello")

    assert visible == ""
    assert reasoning == "hello"
    assert stream.inside is True


def test_feed_emits_visible_text_outside_the_think_block():
    stream = ThinkTagStreamFilter()

    visible, reasoning = stream.feed("<think>secret</think>answer")

    assert visible == "answer"
    assert reasoning == "secret"
    assert stream.inside is False


def test_feed_holds_back_text_before_a_partial_marker():
    stream = ThinkTagStreamFilter()

    visible, reasoning = stream.feed("hello<thi")

    assert visible == "hello"
    assert reasoning == ""
    assert stream.buffer == "<thi"


def test_feed_holds_back_a_partial_close_marker_inside_the_think_block():
    stream = ThinkTagStreamFilter()

    visible, reasoning = stream.feed("<think>abc</thi")

    assert visible == ""
    assert reasoning == "abc"
    assert stream.buffer == "</thi"


def test_flush_returns_a_pending_open_marker_tail_as_visible():
    stream = ThinkTagStreamFilter()
    stream.feed("hello<thi")

    visible, reasoning = stream.flush()

    assert visible == "<thi"
    assert reasoning == ""
    assert stream.buffer == ""


def test_flush_returns_a_pending_close_marker_tail_as_reasoning():
    stream = ThinkTagStreamFilter()
    stream.feed("<think>abc</thi")

    visible, reasoning = stream.flush()

    assert visible == ""
    assert reasoning == "</thi"
    assert stream.buffer == ""


def test_flush_on_an_empty_buffer_returns_nothing():
    stream = ThinkTagStreamFilter()

    assert stream.flush() == ("", "")
