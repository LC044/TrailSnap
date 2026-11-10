"""覆盖 app/db/session.py 的桌面 SQLite 兜底与缺少数据库地址时的报错分支。

app/db/session.py 在 import 时根据环境变量决定数据库地址：

- ``TS_DB_URL`` / ``DB_URL`` 优先；
- 都没有时，桌面端（``TS_DESKTOP=1``）回退到 ``DATA_DIR/trailsnap.sqlite``；
- 都不是则直接抛 ``ValueError``。

这三条分支此前没有任何单测覆盖，import 期错误一旦回归只能在运行时暴露。
这里用一个独立加载的模块副本执行源码，避免污染 ``app.db.session`` 的全局状态。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SESSION_PY = Path(__file__).resolve().parents[2] / "app" / "db" / "session.py"


def _load_session(monkeypatch, name, *, env):
    """在给定环境变量下独立加载一份 app/db/session.py。"""
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    spec = importlib.util.spec_from_file_location(name, SESSION_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _clear_db_env(monkeypatch):
    monkeypatch.delenv("TS_DB_URL", raising=False)
    monkeypatch.delenv("DB_URL", raising=False)


def test_desktop_mode_falls_back_to_sqlite_file(monkeypatch, tmp_path):
    """桌面端未配置 DB_URL 时回退到 DATA_DIR 下的 sqlite 文件。"""
    import app.core.paths as paths

    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("TS_DESKTOP", "1")

    module = _load_session(
        monkeypatch,
        "nightly_session_desktop",
        env={"TS_DESKTOP": "1"},
    )

    assert module.IS_SQLITE is True
    assert module.DATABASE_URL.startswith("sqlite:///")
    assert module.DATABASE_URL.endswith("trailsnap.sqlite")
    assert str(tmp_path) in module.DATABASE_URL
    module.engine.dispose()


def test_missing_database_url_raises_value_error(monkeypatch):
    """非桌面端且没有任何数据库地址时，import 期直接报错。"""
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("TS_DESKTOP", "0")

    with pytest.raises(ValueError) as excinfo:
        _load_session(
            monkeypatch,
            "nightly_session_missing",
            env={"TS_DESKTOP": "0"},
        )

    assert "DB_URL" in str(excinfo.value)


def test_explicit_url_wins_over_desktop_fallback(monkeypatch, tmp_path):
    """显式配置的 TS_DB_URL 优先级最高，不走桌面回退。"""
    import app.core.paths as paths

    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DB_URL", "sqlite:///explicit.sqlite")

    module = _load_session(
        monkeypatch,
        "nightly_session_explicit",
        env={"TS_DESKTOP": "1", "TS_DB_URL": "sqlite:///explicit.sqlite"},
    )

    assert module.DATABASE_URL == "sqlite:///explicit.sqlite"
    assert module.IS_SQLITE is True
    module.engine.dispose()


def test_sqlite_engine_uses_wide_pool_settings(monkeypatch):
    """SQLite 分支使用放大后的连接池参数，避免批量任务把连接池打爆。"""
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("TS_DESKTOP", "1")

    module = _load_session(
        monkeypatch,
        "nightly_session_pool",
        env={"TS_DESKTOP": "1"},
    )

    pool = module.engine.pool
    assert pool.size() == 20
    assert pool._max_overflow == 40
    module.engine.dispose()
