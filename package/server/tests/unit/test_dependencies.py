"""Unit tests for ``app/dependencies.py``.

Covers the small but high-traffic helpers every FastAPI route depends on:

* ``get_db`` -- yields a scoped session and always closes it.
* ``BaseResponse`` / ``BaseResponse.success`` / ``BaseResponse.fail`` -- the
  uniform ``{code, msg, data}`` envelope all API handlers return.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_api]


# ----------------------------- get_db -----------------------------

def test_get_db_yields_session_and_closes_on_exit():
    """get_db must hand out a session and close it after the route finishes."""
    from app import dependencies

    fake_session = MagicMock(name="SessionLocal")
    fake_factory = MagicMock(return_value=fake_session)

    with patch.object(dependencies, "SessionLocal", fake_factory):
        gen = dependencies.get_db()
        session = next(gen)
        assert session is fake_session
        # After the generator exits, close() must be called exactly once.
        with pytest.raises(StopIteration):
            next(gen)
        fake_session.close.assert_called_once()


def test_get_db_closes_session_even_when_route_raises():
    """If the route raises, the session should still be cleaned up (no leaks)."""
    from app import dependencies

    fake_session = MagicMock(name="SessionLocal")
    fake_factory = MagicMock(return_value=fake_session)

    with patch.object(dependencies, "SessionLocal", fake_factory):
        gen = dependencies.get_db()
        next(gen)
        with pytest.raises(RuntimeError, match="boom"):
            gen.throw(RuntimeError("boom"))

    fake_session.close.assert_called_once()


# ----------------------------- BaseResponse -----------------------------

def test_base_response_success_returns_zero_code_envelope():
    from app.dependencies import BaseResponse

    response = BaseResponse[int].success(data=42, msg="ok")

    assert response.code == 0
    assert response.msg == "ok"
    assert response.data == 42


def test_base_response_fail_keeps_data_none_by_default():
    from app.dependencies import BaseResponse

    response = BaseResponse[str].fail(code=404, msg="missing")

    assert response.code == 404
    assert response.msg == "missing"
    assert response.data is None


def test_base_response_can_carry_complex_payload():
    """Response should serialize a nested payload without losing shape."""
    from app.dependencies import BaseResponse

    payload = {"items": [SimpleNamespace(id=1), SimpleNamespace(id=2)], "total": 2}
    response = BaseResponse[dict].success(data=payload)
    assert response.data == payload
    assert response.data["total"] == 2


def test_base_response_default_msg_is_success():
    from app.dependencies import BaseResponse

    response = BaseResponse.success()
    assert response.code == 0
    assert response.msg == "success"
    assert response.data is None
