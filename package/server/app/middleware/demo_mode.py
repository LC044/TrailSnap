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
