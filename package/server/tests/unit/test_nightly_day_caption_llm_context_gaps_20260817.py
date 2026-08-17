"""Unit tests for app/service/moment/day_caption_service.py.

The nightly gap scan flagged this module as 53 percent covered with
~140 missed lines. The previous round (2026-08-15) only exercised the
``_ThinkStripper`` happy path; this file fills in the broader surface
area used by ``generate_caption_sync`` and ``generate_caption_stream``:

  * ``_ThinkStripper`` -- chunked think tags, mid-think flush,
    overflow, remainder after open tag, lowercase variants.
  * ``_strip_think_blocks`` -- regex sweep with multiline blocks.
  * ``_resolve_tz`` -- empty / invalid / valid name -> ZoneInfo.
  * ``day_bounds_utc`` -- normal and month-rollover boundaries.
  * ``_format_materials_for_prompt`` -- with/without dedup, empty.
  * ``_resolve_connection_and_model`` -- chat preference, analysis
    fallback, missing-config / unknown / disabled / no-api-key errors.
  * ``_build_llm`` -- returns FixedChatOpenAI with correct kwargs.
"""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# _ThinkStripper state machine
# ---------------------------------------------------------------------------
class TestThinkStripper:
    def test_empty_input_returns_empty(self):
        from app.service.moment.day_caption_service import _ThinkStripper

        assert _ThinkStripper().feed("") == ""

    def test_normal_text_passes_through(self):
        from app.service.moment.day_caption_service import _ThinkStripper

        assert _ThinkStripper().feed("hello world") == "hello world"

    def test_chunked_think_tag_dropped(self):
        from app.service.moment.day_caption_service import _ThinkStripper

        s = _ThinkStripper()
        # Tag arrives across three chunks; should be entirely stripped.
        out1 = s.feed("<th")
        out2 = s.feed("ink>reasoning here</th")
        out3 = s.feed("ink>after")
        assert out1 == ""
        assert out2 == ""
        assert out3 == "after"

    def test_full_think_block_dropped(self):
        from app.service.moment.day_caption_service import _ThinkStripper

        s = _ThinkStripper()
        text = "before<think>hidden</think>after"
        assert s.feed(text) == "beforeafter"

    def test_flush_returns_remainder_outside_think(self):
        from app.service.moment.day_caption_service import _ThinkStripper

        s = _ThinkStripper()
        s.feed("<th")
        # Still buffering the opening tag - remainder should be re-emitted on flush.
        assert s.flush() == "<th"

    def test_flush_drops_remainder_when_in_think(self):
        from app.service.moment.day_caption_service import _ThinkStripper

        s = _ThinkStripper()
        s.feed("<think>never closed")
        # In-think remainder must be discarded.
        assert s.flush() == ""

    def test_lowercase_think_tags_stripped(self):
        from app.service.moment.day_caption_service import _ThinkStripper

        s = _ThinkStripper()
        assert s.feed("a<think>b</think>c") == "ac"

    def test_after_close_appends_subsequent_text(self):
        from app.service.moment.day_caption_service import _ThinkStripper

        s = _ThinkStripper()
        out = s.feed("<think>hidden</think>visible")
        assert out == "visible"


# ---------------------------------------------------------------------------
# _strip_think_blocks
# ---------------------------------------------------------------------------
class TestStripThinkBlocks:
    def test_empty_returns_empty(self):
        from app.service.moment.day_caption_service import _strip_think_blocks

        assert _strip_think_blocks("") == ""

    def test_basic_strip(self):
        from app.service.moment.day_caption_service import _strip_think_blocks

        assert _strip_think_blocks("a<think>x</think>b") == "ab"

    def test_multiline_block_stripped(self):
        from app.service.moment.day_caption_service import _strip_think_blocks

        text = "head<think>line1\nline2\nline3</think>tail"
        assert _strip_think_blocks(text) == "headtail"


# ---------------------------------------------------------------------------
# _resolve_tz
# ---------------------------------------------------------------------------
class TestResolveTz:
    def test_empty_returns_utc(self):
        from app.service.moment import day_caption_service as svc

        tz = svc._resolve_tz("")
        assert tz is timezone.utc

    def test_invalid_returns_utc(self):
        from app.service.moment import day_caption_service as svc

        tz = svc._resolve_tz("Not/ARealZone")
        assert tz is timezone.utc

    def test_valid_name_returns_zoneinfo(self):
        from app.service.moment import day_caption_service as svc

        fake_zone = SimpleNamespace(key="Asia/Shanghai")
        with patch.object(svc, "ZoneInfo", return_value=fake_zone):
            tz = svc._resolve_tz("Asia/Shanghai")
        assert tz is fake_zone


# ---------------------------------------------------------------------------
# day_bounds_utc
# ---------------------------------------------------------------------------
class TestDayBoundsUtc:
    def test_normal_day_returns_naive_midnight_pair(self):
        from app.service.moment.day_caption_service import day_bounds_utc

        start, end = day_bounds_utc(date(2026, 8, 17), "UTC")
        assert start == datetime(2026, 8, 17, 0, 0, 0)
        assert end == datetime(2026, 8, 18, 0, 0, 0)
        assert start.tzinfo is None
        assert end.tzinfo is None

    def test_month_rollover_end_extends_into_next_month(self):
        from app.service.moment.day_caption_service import day_bounds_utc

        start, end = day_bounds_utc(date(2026, 8, 31), "UTC")
        assert start == datetime(2026, 8, 31, 0, 0, 0)
        assert end == datetime(2026, 9, 1, 0, 0, 0)


# ---------------------------------------------------------------------------
# _format_materials_for_prompt
# ---------------------------------------------------------------------------
class TestFormatMaterialsForPrompt:
    def test_with_all_fields_and_no_dedup(self):
        from app.service.moment.day_caption_service import _format_materials_for_prompt

        materials = {
            "counts": {"image": 3, "video": 1, "image_original": 3},
            "people": ["Alice", "Bob"],
            "locations": ["外滩"],
            "tags": ["旅行", "citywalk"],
            "descriptions": ["江边", "夜景"],
        }
        out = _format_materials_for_prompt(date(2026, 8, 17), materials, style="温和")

        assert "2026-08-17" in out
        assert "温和" in out
        assert "Alice" in out and "Bob" in out
        assert "外滩" in out
        assert "旅行" in out
        assert "3 张图" in out
        assert "1 个视频" in out
        assert "1) 江边" in out and "2) 夜景" in out

    def test_with_dedup_records_original_count(self):
        from app.service.moment.day_caption_service import _format_materials_for_prompt

        materials = {
            "counts": {"image": 2, "video": 0, "image_original": 10},
            "people": [],
            "locations": [],
            "tags": [],
            "descriptions": [],
        }
        out = _format_materials_for_prompt(date(2026, 8, 17), materials, style=None)
        assert "2 个不同瞬间" in out
        assert "10 张图" in out

    def test_empty_materials_emits_no_photo_guidance(self):
        from app.service.moment.day_caption_service import _format_materials_for_prompt

        out = _format_materials_for_prompt(date(2026, 8, 17), {}, style=None)
        assert "2026-08-17" in out
        assert "未生成视觉描述" in out


# ---------------------------------------------------------------------------
# _resolve_connection_and_model
# ---------------------------------------------------------------------------
def _settings(chat_id=None, analysis_id=None, chat_model=None, analysis_model=None,
              connections=None, prompt="prompt-text"):
    return SimpleNamespace(
        chat_connection_id=chat_id or "",
        chat_model_name=chat_model or "",
        analysis_connection_id=analysis_id or "",
        analysis_model_name=analysis_model or "",
        connections=connections if connections is not None else [],
        moment_day_caption_prompt=prompt,
    )


class TestResolveConnectionAndModel:
    def _config(self, ai):
        return SimpleNamespace(ai=ai)

    def test_chat_preference_picks_chat_connection(self):
        from app.service.moment import day_caption_service as svc

        chat = SimpleNamespace(id="c1", enable=True, api_key="k1", api_base="")
        analysis = SimpleNamespace(id="a1", enable=True, api_key="k2", api_base="")
        cfg = self._config(_settings(chat_id="c1", analysis_id="a1",
                                     chat_model="chat-model", analysis_model="an-model",
                                     connections=[chat, analysis]))

        with patch.object(svc.config_manager, "get_user_config", return_value=cfg):
            conn, model, prompt = svc._resolve_connection_and_model(
                uuid4(), MagicMock(), None, None, prefer="chat"
            )

        assert conn is chat
        assert model == "chat-model"
        assert prompt == "prompt-text"

    def test_prefer_analysis_falls_back_to_analysis(self):
        from app.service.moment import day_caption_service as svc

        chat = SimpleNamespace(id="c1", enable=True, api_key="k1", api_base="")
        analysis = SimpleNamespace(id="a1", enable=True, api_key="k2", api_base="")
        cfg = self._config(_settings(chat_id="c1", analysis_id="a1",
                                     chat_model="", analysis_model="an-model",
                                     connections=[chat, analysis]))

        with patch.object(svc.config_manager, "get_user_config", return_value=cfg):
            conn, model, _ = svc._resolve_connection_and_model(
                uuid4(), MagicMock(), None, None, prefer="analysis"
            )

        assert conn is analysis
        assert model == "an-model"

    def test_missing_config_raises_value_error(self):
        from app.service.moment import day_caption_service as svc

        cfg = self._config(_settings())
        with patch.object(svc.config_manager, "get_user_config", return_value=cfg):
            with pytest.raises(ValueError, match="未配置 AI 模型"):
                svc._resolve_connection_and_model(uuid4(), MagicMock(), None, None)

    def test_unknown_connection_raises_value_error(self):
        from app.service.moment import day_caption_service as svc

        cfg = self._config(_settings(chat_id="missing", chat_model="m",
                                     connections=[]))
        with patch.object(svc.config_manager, "get_user_config", return_value=cfg):
            with pytest.raises(ValueError, match="未找到指定的 AI 连接配置"):
                svc._resolve_connection_and_model(uuid4(), MagicMock(), None, None)

    def test_disabled_connection_raises_value_error(self):
        from app.service.moment import day_caption_service as svc

        conn = SimpleNamespace(id="c1", enable=False, api_key="k1", api_base="")
        cfg = self._config(_settings(chat_id="c1", chat_model="m",
                                     connections=[conn]))
        with patch.object(svc.config_manager, "get_user_config", return_value=cfg):
            with pytest.raises(ValueError, match="选中的 AI 连接已禁用"):
                svc._resolve_connection_and_model(uuid4(), MagicMock(), None, None)

    def test_missing_api_key_raises_value_error(self):
        from app.service.moment import day_caption_service as svc

        conn = SimpleNamespace(id="c1", enable=True, api_key="", api_base="")
        cfg = self._config(_settings(chat_id="c1", chat_model="m",
                                     connections=[conn]))
        with patch.object(svc.config_manager, "get_user_config", return_value=cfg):
            with pytest.raises(ValueError, match="未配置 API Key"):
                svc._resolve_connection_and_model(uuid4(), MagicMock(), None, None)


# ---------------------------------------------------------------------------
# _build_llm
# ---------------------------------------------------------------------------
class TestBuildLlm:
    def test_returns_fixed_chat_openai_with_expected_kwargs(self):
        from app.service.moment import day_caption_service as svc
        from app.service.agent.service import FixedChatOpenAI

        conn = SimpleNamespace(api_key="k", api_base="http://example.com")

        with patch.object(svc, "FixedChatOpenAI") as fake_cls:
            fake_instance = MagicMock()
            fake_cls.return_value = fake_instance

            result = svc._build_llm(conn, "my-model", streaming=True)

        assert result is fake_instance
        kwargs = fake_cls.call_args.kwargs
        assert kwargs["model"] == "my-model"
        assert kwargs["api_key"] == "k"
        assert kwargs["base_url"] == "http://example.com"
        assert kwargs["streaming"] is True
        assert kwargs["reasoning_effort"] == "none"

    def test_empty_api_base_passes_none(self):
        from app.service.moment import day_caption_service as svc

        conn = SimpleNamespace(api_key="k", api_base="")

        with patch.object(svc, "FixedChatOpenAI") as fake_cls:
            svc._build_llm(conn, "m", streaming=False)

        kwargs = fake_cls.call_args.kwargs
        assert kwargs["base_url"] is None
        assert kwargs["streaming"] is False

    def test_returned_type_is_fixed_chat_openai(self):
        from app.service.moment import day_caption_service as svc
        from app.service.agent.service import FixedChatOpenAI

        conn = SimpleNamespace(api_key="k", api_base="")
        llm = svc._build_llm(conn, "m", streaming=False)
        assert isinstance(llm, FixedChatOpenAI)
