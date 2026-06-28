"""
AI 微服务 pytest 全局配置。

职责：加载单一环境变量源 ../../tests/.env.test（与 docker / 前端 e2e / 后端共享）。
改 tests/.env.test 一处，AI 测试即跟着变。
"""
import os
from pathlib import Path

from dotenv import dotenv_values

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / "tests" / ".env.test"


def _load_shared_env() -> None:
    if not _ENV_FILE.exists():
        return
    for key, value in dotenv_values(_ENV_FILE).items():
        if value is None:
            continue
        if key not in os.environ:
            os.environ[key] = value


_load_shared_env()


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def ts_test_env() -> str:
    return os.environ.get("TS_TEST_ENV", "dev")
