"""User-facing Agent errors. Provider responses belong in server logs only."""

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError


SETTINGS = "系统设置 → AI 相关配置"


class AgentConfigurationError(ValueError):
    """A configuration error containing only application-authored guidance."""


def format_agent_error(error: Exception) -> str:
    """Explain the failure without exposing provider payloads or credentials."""
    if isinstance(error, AgentConfigurationError):
        return str(error)
    # APITimeoutError subclasses APIConnectionError; check timeouts first.
    if isinstance(error, (APITimeoutError, httpx.TimeoutException, TimeoutError)):
        return (
            "AI 模型请求超时，本次回复未完成。请稍后重试；如果反复出现，"
            "请联系管理员检查模型服务响应速度及 TrailSnap 后端的网络连接。"
        )
    if isinstance(error, (APIConnectionError, httpx.ConnectError)):
        return (
            "无法连接 AI 模型服务，本次回复未完成。\n\n"
            f"请在「{SETTINGS}」检查当前连接的 Base URL 和端口，并确认模型服务已启动。"
            "自托管用户请检查 TrailSnap 后端到模型服务的网络、DNS 和代理配置；"
            "Docker 部署时，localhost / 127.0.0.1 指向容器自身，"
            "连接宿主机上的模型服务需使用容器可访问的地址。"
        )
    if isinstance(error, (APIStatusError, httpx.HTTPStatusError)):
        status = error.status_code if isinstance(error, APIStatusError) else error.response.status_code
        if status == 401:
            return f"AI 模型服务认证失败（401）。请在「{SETTINGS}」检查当前连接的 API Key 是否正确、已过期或被撤销。"
        if status == 403:
            return f"AI 模型服务拒绝访问（403）。请在「{SETTINGS}」检查当前密钥的模型访问权限，并联系服务商或管理员确认访问限制。"
        if status == 429:
            return "AI 模型服务限制了本次请求（429），可能是请求过于频繁或可用额度不足。请稍后重试；若持续出现，请检查服务商账户的额度和调用限制。"
        if status == 404:
            return f"未找到请求的 AI 接口或模型（404）。请在「{SETTINGS}」检查 Base URL 是否包含服务商要求的路径（如 /v1），以及模型名称是否正确、可用。"
        if status in (400, 422):
            return f"AI 模型服务未接受本次请求（{status}）。请在「{SETTINGS}」检查模型名称、思考等级及接口兼容性；也可尝试缩短消息或新建会话。"
        if status >= 500:
            return f"AI 模型服务暂时异常（{status}），本次回复未完成。请稍后重试；若持续出现，请联系模型服务商或管理员检查服务状态。"
        return f"AI 模型服务返回异常状态（{status}），本次回复未完成。请联系管理员结合发生时间查看 TrailSnap 后端日志。"
    return "抱歉，AI 对话处理失败，本次回复未完成。请重试；若仍然失败，请联系管理员并提供发生时间，以便查看 TrailSnap 后端日志定位原因。"
