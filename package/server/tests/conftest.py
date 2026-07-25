"""
后端 pytest 全局配置。

职责：
1. 加载单一环境变量源 ../../tests/.env.test（与 docker / 前端 e2e / AI 共享）。
2. 把规范变量名映射到 server app 读取的 legacy 变量名（DB_URL / AI_API_URL），
   这样改 tests/.env.test 一处，后端测试就跟着变。

注意：unit 层不依赖这些变量；integration 层会用到 DB_URL。
"""
import os
from pathlib import Path

from dotenv import dotenv_values

# 仓库根 = package/server/tests/conftest.py 往上三级
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / "tests" / ".env.test"


def _load_shared_env() -> None:
    """加载 tests/.env.test；不覆盖已在进程环境中显式设置的变量。"""
    if not _ENV_FILE.exists():
        return
    for key, value in dotenv_values(_ENV_FILE).items():
        if value is None:
            continue
        if key not in os.environ:
            os.environ[key] = value

    # 规范名 -> server app legacy 名（仅当 legacy 名未显式设置时）
    _map = {
        "DB_URL": os.environ.get("TS_DB_URL"),
        "AI_API_URL": os.environ.get("TS_AI_API_URL"),
    }
    for legacy, canonical in _map.items():
        if canonical and legacy not in os.environ:
            os.environ[legacy] = canonical


_load_shared_env()


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def ts_test_env() -> str:
    """当前测试环境标识（dev / docker / ci），供测试按环境分支。"""
    return os.environ.get("TS_TEST_ENV", "dev")
