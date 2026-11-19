"""2026-11-18 nightly coverage for ``app/service/agent/errors.py``.

No test file referenced ``app/service/agent/errors.py``.  The formatter is
the only place where an AI provider failure becomes text the user sees, so
two properties matter:

* every known failure class gets an actionable Chinese message that points at
  「系统设置 → AI 相关配置」;
* the raw provider payload, the API key and the Base URL must never leak
  into that message - only application-authored guidance may.
"""

from __future__ import annotations

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.service.agent.errors import SETTINGS, AgentConfigurationError, format_agent_error


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _status_error(status: int) -> APIStatusError:
    request = httpx.Request("POST", "https://provider.example/v1/chat/completions")
    response = httpx.Response(status, request=request)
    return APIStatusError(
        f"provider said {status}: secret-key-abcdef body={{'detail': 'private payload'}}",
        response=response,
        body=None,
    )


def test_a_configuration_error_is_shown_verbatim():
    assert format_agent_error(AgentConfigurationError("缺少模型名称")) == "缺少模型名称"


def test_a_timeout_is_reported_as_a_timeout():
    request = httpx.Request("POST", "https://provider.example/v1/chat/completions")
    message = format_agent_error(APITimeoutError(request=request))

    assert "超时" in message
    assert "secret-key-abcdef" not in message


def test_an_httpx_timeout_is_reported_as_a_timeout():
    message = format_agent_error(httpx.TimeoutException("timed out"))

    assert "超时" in message


def test_a_connection_error_points_at_the_base_url():
    request = httpx.Request("POST", "https://provider.example/v1/chat/completions")
    message = format_agent_error(APIConnectionError(request=request))

    assert "Base URL" in message
    assert SETTINGS in message


def test_an_httpx_connect_error_points_at_the_base_url():
    message = format_agent_error(httpx.ConnectError("connection refused"))

    assert "Base URL" in message


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "认证失败"),
        (403, "拒绝访问"),
        (429, "限制"),
        (404, "未找到"),
        (400, "未接受"),
        (422, "未接受"),
        (500, "暂时异常"),
        (503, "暂时异常"),
    ],
)
def test_every_known_status_gets_a_dedicated_message(status, expected):
    message = format_agent_error(_status_error(status))

    assert expected in message
    assert str(status) in message


def test_an_unknown_status_still_gets_a_generic_message():
    message = format_agent_error(_status_error(418))

    assert "异常状态" in message
    assert "418" in message


def test_the_provider_payload_never_leaks_into_the_message():
    message = format_agent_error(_status_error(500))

    assert "secret-key-abcdef" not in message
    assert "private payload" not in message


def test_an_unknown_error_gets_the_generic_fallback():
    message = format_agent_error(RuntimeError("boom secret-key-abcdef"))

    assert "本次回复未完成" in message
    assert "secret-key-abcdef" not in message
