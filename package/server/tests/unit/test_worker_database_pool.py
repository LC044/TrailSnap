"""Regression coverage for process-safe SQLAlchemy pool handling."""

from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_dispose_inherited_connections_replaces_pool_without_closing_parent_connections():
    from app.db import session

    fake_engine = MagicMock()
    with patch.object(session, "engine", fake_engine):
        session.dispose_inherited_connections()

    fake_engine.dispose.assert_called_once_with(close=False)


def test_worker_discards_inherited_pool_before_process_initialization():
    from app import worker

    order: list[str] = []

    with patch.object(worker, "dispose_inherited_connections", side_effect=lambda: order.append("dispose")), \
         patch.object(worker, "setup_logging", side_effect=lambda *_: order.append("logging")), \
         patch.object(worker, "lower_worker_priority"), \
         patch.object(worker, "ensure_rg_seed"), \
         patch.object(worker, "_run", return_value=MagicMock()), \
         patch.object(worker.asyncio, "run", side_effect=KeyboardInterrupt):
        worker.run_worker()

    assert order == ["dispose", "logging"]
