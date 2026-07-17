# -*- coding: utf-8 -*-
"""
密码重置验证码的内存存储（「通过服务器日志重置」方式）。

设计要点：
- 验证码只写入日志（WARNING 级别），绝不返回给前端。
- 内存中只存验证码的哈希（sha256），带过期时间，用一次即焚。
- 同一用户 60 秒内只能生成一次，防日志刷屏。
- 失败尝试有次数上限，防暴力猜验证码。
- 默认始终可用，作为「安全问题」重置的兜底方案；对普通版本零影响。
- 仅存在于进程内存，重启即清空（用户重新发送即可，无需持久化）。
"""
import hashlib
import logging
import secrets
import threading
import time
from typing import Optional

logger = logging.getLogger("app.auth.reset_code")

# ------------------------------ 可调参数 ------------------------------
CODE_TTL_SECONDS = 600          # 验证码有效期：10 分钟
RESEND_INTERVAL_SECONDS = 60    # 同一用户 60 秒内只能生成一次
MAX_VERIFY_ATTEMPTS = 5         # 验证码最大失败尝试次数
CODE_DIGITS = 6                 # 验证码位数

_lock = threading.Lock()
# user_id(str) -> {"code_hash": str, "expires_at": float,
#                  "last_sent_at": float, "failed_attempts": int}
_store: dict[str, dict] = {}


def _hash_code(code: str) -> str:
    """对验证码取 sha256 哈希（内存中只存哈希，不存明文）。"""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    """生成指定位数的数字验证码。"""
    bound = 10 ** CODE_DIGITS
    return f"{secrets.randbelow(bound):0{CODE_DIGITS}d}"


def issue_code(user_id: str, identifier: str) -> Optional[str]:
    """
    为用户生成新的重置验证码。

    :param user_id: 用户 ID（字符串）
    :param identifier: 用户名或邮箱（仅用于日志展示）
    :return: 明文验证码（仅供写入日志）；若因频率限制未生成则返回 None。
    """
    now = time.time()
    with _lock:
        entry = _store.get(user_id)
        if entry and now - entry["last_sent_at"] < RESEND_INTERVAL_SECONDS:
            return None
        code = _generate_code()
        _store[user_id] = {
            "code_hash": _hash_code(code),
            "expires_at": now + CODE_TTL_SECONDS,
            "last_sent_at": now,
            "failed_attempts": 0,
        }
    # 关键：验证码只写入日志，绝不返回给前端
    logger.warning(
        "【密码重置验证码】用户 %s 的服务器日志重置验证码：%s（有效期 %d 分钟，请勿向他人泄露）",
        identifier, code, CODE_TTL_SECONDS // 60,
    )
    return code


def verify_code(user_id: str, code: str, identifier: str = "") -> bool:
    """
    校验验证码。

    正确且未过期则立即失效（用一次即焚）并返回 True；否则返回 False。
    每次失败累计失败次数，超过上限后验证码失效。

    :param user_id: 用户 ID（字符串）
    :param code: 待校验的明文验证码
    :param identifier: 用户名或邮箱（仅用于日志展示）
    """
    now = time.time()
    with _lock:
        entry = _store.get(user_id)
        if not entry:
            return False
        # 过期或失败次数过多 → 直接失效
        if now > entry["expires_at"] or entry["failed_attempts"] >= MAX_VERIFY_ATTEMPTS:
            _store.pop(user_id, None)
            return False
        if _hash_code(code) == entry["code_hash"]:
            _store.pop(user_id, None)  # 用一次即焚
            return True
        entry["failed_attempts"] += 1
        remaining = MAX_VERIFY_ATTEMPTS - entry["failed_attempts"]
        logger.warning(
            "【密码重置验证码】用户 %s 验证码校验失败，剩余尝试次数 %d",
            identifier or user_id, max(remaining, 0),
        )
        if remaining <= 0:
            _store.pop(user_id, None)
        return False
