import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.service.agent import service
from app.service.agent.errors import AgentConfigurationError, format_agent_error

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


@pytest.mark.parametrize("error, expected", [
    (APIConnectionError(request=httpx.Request("POST", "https://model.test")), "无法连接 AI 模型服务"),
    (httpx.ConnectError("secret"), "无法连接 AI 模型服务"),
    (APITimeoutError(request=httpx.Request("POST", "https://model.test")), "请求超时"),
    (httpx.ReadTimeout("secret"), "请求超时"),
    (TimeoutError("secret"), "请求超时"),
    (RuntimeError("secret"), "联系管理员"),
    (ValueError("secret"), "联系管理员"),
])
def test_transport_and_unknown_errors(error, expected):
    message = format_agent_error(error)
    assert expected in message
    assert "secret" not in message


@pytest.mark.parametrize("status, expected", [
    (401, "API Key"), (403, "访问权限"), (404, "Base URL"),
    (429, "额度"), (400, "接口兼容性"), (422, "思考等级"),
    (500, "暂时异常"), (503, "暂时异常"), (418, "后端日志"),
])
@pytest.mark.parametrize("sdk", [True, False])
def test_status_errors_do_not_expose_provider_response(status, expected, sdk):
    request = httpx.Request("POST", "https://user:secret@model.test/v1?key=secret")
    response = httpx.Response(status, request=request, json={"error": "secret"})
    error = (APIStatusError("secret", response=response, body={"key": "secret"}) if sdk
             else httpx.HTTPStatusError("secret", request=request, response=response))
    message = format_agent_error(error)
    assert str(status) in message
    assert expected in message
    assert "secret" not in message
    assert "model.test" not in message


def test_connection_guidance_explains_backend_and_container_network():
    message = format_agent_error(httpx.ConnectError("All connection attempts failed"))
    for text in ("系统设置", "AI 相关配置", "Base URL", "端口", "后端", "DNS", "代理", "容器自身"):
        assert text in message


def test_authored_configuration_guidance_is_preserved():
    error = AgentConfigurationError("请先选择对话模型。")
    assert format_agent_error(error) == str(error)


@pytest.mark.parametrize("during_setup", [True, False])
def test_sync_chat_maps_setup_and_model_failures(monkeypatch, during_setup):
    error = httpx.ConnectError("secret")
    executor = MagicMock()
    executor.invoke.side_effect = error
    setup = MagicMock(return_value=(executor, "system"), side_effect=error if during_setup else None)
    monkeypatch.setattr(service, "get_agent_executor", setup)
    monkeypatch.setattr(service, "get_session_history", lambda *args: [])
    monkeypatch.setattr(service, "create_message", MagicMock())
    monkeypatch.setattr(service, "config_manager", MagicMock())
    monkeypatch.setattr(service, "compress_history_if_needed", lambda messages, *args: messages)
    assert service.chat_with_agent(str(uuid4()), str(uuid4()), "你好", MagicMock()) == format_agent_error(error)


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_stream_error_is_visible_saved_and_terminated(monkeypatch, partial):
    error = httpx.ConnectError("secret")

    class Executor:
        async def astream(self, *args, **kwargs):
            if partial:
                yield AIMessageChunk(content="已生成的内容"), {"langgraph_node": "model"}
            raise error

    session_id = str(uuid4())
    monkeypatch.setattr(service, "get_agent_executor", lambda *args: (Executor(), "system"))
    # Existing history avoids launching the unrelated background title task.
    monkeypatch.setattr(service, "get_session_history", lambda *args: [SystemMessage(content="system"), HumanMessage(content="上一轮问题")])
    monkeypatch.setattr(service, "config_manager", MagicMock())
    monkeypatch.setattr(service, "compress_history_if_needed", lambda messages, *args: messages)
    saved = MagicMock()
    monkeypatch.setattr(service, "create_message", saved)
    monkeypatch.setattr(service, "SessionLocal", MagicMock())
    events = [item async for item in service.stream_chat_with_agent(str(uuid4()), session_id, "你好", MagicMock())]
    assert events[-1] == "data: [DONE]\n\n"
    displayed = "".join(json.loads(item[6:]).get("content", "") for item in events[:-1])
    expected = ("已生成的内容\n\n" if partial else "") + format_agent_error(error)
    assert displayed == expected
    assert saved.call_args.args[1].content == expected
    assert session_id not in service._aborted_sessions


@pytest.mark.asyncio
async def test_stream_configuration_failure_has_actionable_guidance(monkeypatch):
    config = SimpleNamespace(ai=SimpleNamespace(connections=[], analysis_connection_id=None, analysis_model_name=None))
    manager = MagicMock()
    manager.get_user_config.return_value = config
    monkeypatch.setattr(service, "config_manager", manager)
    monkeypatch.setattr(service, "create_message", MagicMock())
    monkeypatch.setattr(service, "SessionLocal", MagicMock())
    events = [item async for item in service.stream_chat_with_agent(str(uuid4()), str(uuid4()), "你好", MagicMock())]
    message = json.loads(events[1][6:])["content"]
    assert "系统设置" in message and "选择对话模型" in message
    assert events[-1] == "data: [DONE]\n\n"
