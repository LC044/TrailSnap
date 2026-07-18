# -*- coding: utf-8 -*-
"""
演示模式中间件。

当环境变量 ``DEMO_MODE=true`` 时：
1. 拦截所有写操作（POST/PUT/DELETE/PATCH），仅放行白名单内的只读型 POST
   （如登录、搜索），其余返回 403 BaseResponse。
2. 对所有 JSON 响应中的敏感配置字段（API key、secret_key、存储路径等）
   进行脱敏，防止演示账号窃取真实凭证。

普通部署不设置 ``DEMO_MODE`` 时，本中间件完全透传，零影响。
"""
import os
import json
import time
import threading
from typing import Any, List, Tuple

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


# 读取一次即可，进程生命周期内不变
DEMO_MODE: bool = _truthy(os.getenv("DEMO_MODE"))

WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

# 白名单：(METHOD, path_prefix)。
# 这些是「用 POST 传 body 的只读操作」+ 登录，演示模式下必须放行。
# 匹配规则：path == prefix 或 path 以 prefix + "/" 开头，避免前缀误伤
# （例如 /search/text 不会放行 /search/textimage）。
WHITELIST: List[Tuple[str, str]] = [
    ("POST", "/auth/login"),        # 游客登录
    ("POST", "/search/text"),       # 文本搜索（只读）
    ("POST", "/search/image"),      # 以图搜图（只读）
    ("POST", "/guess-city/guess"),  # 根据坐标猜测城市（只读）
    # AI 助手对话：Agent 的工具均为只读查询（搜索/标签/人物/足迹/照片详情），
    # 不会修改相册数据；会话与消息为当前用户私有，演示模式下放行。
    ("POST", "/agent/chat"),        # 对话 + 终止流（/agent/chat/{id}/abort）
    ("DELETE", "/agent/sessions"),  # 删除会话（/agent/sessions/{id}）
    ("PUT", "/agent/sessions"),     # 置顶/取消置顶（/agent/sessions/{id}/pin）
    ("DELETE", "/agent/messages"),  # 删除会话消息
]

# JSON 响应中需要脱敏的字段名（小写精确匹配）。
# 命中后：list -> []，dict -> {}，其它 -> "******"。
SENSITIVE_KEYS = {
    "api_key", "api_keys", "api_base", "ai_api_url",
    "secret_key", "secret", "password", "passwd", "passphrase",
    "photo_storage_path", "external_directories",
    "map_key", "map_keys", "tianditu_key", "amap_key", "baidu_key",
}

DEMO_BLOCK_MSG = "演示模式已开启：写操作与敏感接口已被禁用"

# —— 演示模式限流（仅 DEMO_MODE 下生效，防白名单接口被刷 DoS）——
# 白名单写接口（登录 / 搜索 / 猜城市）虽放行，但每次都可能触发
# AI 服务推理或 bcrypt 计算，被高频刷会打满演示站。按 (IP, 路径)
# 维护令牌桶限流。
RATE_LIMIT_CAPACITY = 20           # 令牌桶容量（瞬时突发上限）
RATE_LIMIT_REFILL_PER_MIN = 20     # 每分钟补充令牌数
RATE_LIMIT_STORE_MAX = 10000       # 令牌桶字典上限，防止 IP 爆炸撑爆内存
RATE_LIMIT_MSG = "演示模式：请求过于频繁，请稍后再试"

# /agent/chat 触发 LLM 推理，单次成本远高于登录/搜索，单独收紧限流，
# 防止演示站被刷爆推理费用。
AGENT_CHAT_RATE_LIMIT_CAPACITY = 6
AGENT_CHAT_RATE_LIMIT_REFILL_PER_MIN = 6

# /search/image 上传体大小上限（字节）。仅校验 Content-Length，
# 防止超大图片打爆 AI 服务推理。
SEARCH_IMAGE_MAX_BYTES = 20 * 1024 * 1024  # 20 MB
SEARCH_IMAGE_TOO_LARGE_MSG = "演示模式：图片过大（上限 20MB）"


def is_whitelisted_write(method: str, path: str) -> bool:
    for m, prefix in WHITELIST:
        if method != m:
            continue
        if path == prefix:
            return True
        boundary = prefix.rstrip("/") + "/"
        if path.startswith(boundary):
            return True
    return False


# 令牌桶状态：key=f"{ip}:{path}" -> (剩余令牌, 上次补充的 monotonic 时间)
_rate_store: dict[str, tuple[float, float]] = {}
_rate_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    """取客户端 IP。优先 X-Forwarded-For 首段（演示站通常在 nginx 后），
    否则回退到 TCP 对端地址。注意：XFF 可被客户端伪造，演示场景下够用。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client:
        return request.client.host
    return "unknown"


def _rate_limit_allow(
    ip: str,
    path: str,
    capacity: float = RATE_LIMIT_CAPACITY,
    refill_per_min: float = RATE_LIMIT_REFILL_PER_MIN,
) -> bool:
    """令牌桶限流：每个 (ip, path) 一个独立桶。返回 True 表示放行。"""
    key = f"{ip}:{path}"
    now = time.monotonic()
    refill_per_sec = refill_per_min / 60.0
    with _rate_lock:
        tokens, last = _rate_store.get(key, (capacity, now))
        # 按时间差补充令牌，上限为容量
        tokens = min(capacity, tokens + (now - last) * refill_per_sec)
        allowed = tokens >= 1.0
        if allowed:
            tokens -= 1.0
        _rate_store[key] = (tokens, now)
        # 字典过大时清理 2 分钟未活跃的桶，防止内存无限增长
        if len(_rate_store) > RATE_LIMIT_STORE_MAX:
            cutoff = now - 120
            for k in [k for k, (_, t) in _rate_store.items() if t < cutoff]:
                _rate_store.pop(k, None)
        return allowed


def _content_length(request: Request) -> int | None:
    val = request.headers.get("content-length")
    if not val:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _mask_value(value: Any) -> Any:
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    return "******"


def mask_sensitive(obj: Any) -> Any:
    """递归地将 dict/list 中的敏感字段值替换为占位符。原对象会被就地修改。"""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k.lower() in SENSITIVE_KEYS:
                obj[k] = _mask_value(v)
            else:
                mask_sensitive(v)
    elif isinstance(obj, list):
        for item in obj:
            mask_sensitive(item)
    return obj


class DemoModeMiddleware:
    """演示模式统一拦截中间件。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not DEMO_MODE or scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        method = request.method
        path = request.url.path

        # 1) 拦截非白名单写操作
        if method in WRITE_METHODS and not is_whitelisted_write(method, path):
            response = JSONResponse(
                status_code=200,
                content={"code": 403, "msg": DEMO_BLOCK_MSG, "data": None},
            )
            await response(scope, receive, send)
            return

        # 1.5) 白名单写接口限流 + /search/image 体积限制（防 DoS）
        if method in WRITE_METHODS and is_whitelisted_write(method, path):
            # /agent/chat（含 abort）触发 LLM 推理，单独收紧令牌桶
            is_agent_chat = path == "/agent/chat" or path.startswith("/agent/chat/")
            if is_agent_chat:
                cap, ref = AGENT_CHAT_RATE_LIMIT_CAPACITY, AGENT_CHAT_RATE_LIMIT_REFILL_PER_MIN
            else:
                cap, ref = RATE_LIMIT_CAPACITY, RATE_LIMIT_REFILL_PER_MIN
            if not _rate_limit_allow(_client_ip(request), path, cap, ref):
                response = JSONResponse(
                    status_code=200,
                    content={"code": 429, "msg": RATE_LIMIT_MSG, "data": None},
                )
                await response(scope, receive, send)
                return
            if path == "/search/image" or path.startswith("/search/image/"):
                cl = _content_length(request)
                if cl is not None and cl > SEARCH_IMAGE_MAX_BYTES:
                    response = JSONResponse(
                        status_code=200,
                        content={"code": 413, "msg": SEARCH_IMAGE_TOO_LARGE_MSG, "data": None},
                    )
                    await response(scope, receive, send)
                    return

        # 2) 脱敏 JSON 响应
        is_json = False

        async def custom_send(message: dict) -> None:
            nonlocal is_json
            mtype = message["type"]
            if mtype == "http.response.start":
                ct = ""
                for name, value in message.get("headers", []):
                    if name.lower() == b"content-type":
                        ct = value.decode("latin-1")
                        break
                is_json = "application/json" in ct.lower()
                if is_json:
                    # body 可能被改写，先移除 content-length，改用分块传输
                    message["headers"] = [
                        (n, v) for (n, v) in message.get("headers", [])
                        if n.lower() != b"content-length"
                    ]
                await send(message)
            elif mtype == "http.response.body":
                # 只处理「一次性返回」的 JSON body；流式分片（more_body）原样放行
                if is_json and not message.get("more_body"):
                    body = message.get("body", b"") or b""
                    if body:
                        try:
                            data = json.loads(body.decode("utf-8"))
                            data = mask_sensitive(data)
                            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                        except Exception:
                            pass
                    message["body"] = body
                await send(message)
            else:
                await send(message)

        await self.app(scope, receive, custom_send)
