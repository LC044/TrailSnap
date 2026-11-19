"""Lifecycle of the pending CLIP preset bucket attached to a session."""
from types import SimpleNamespace

import pytest

from app.service.clip_classification import (
    _PENDING_PRESETS,
    _clear_closed_preset_transaction,
    _discard_initialized_presets,
)

pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def _session():
    return SimpleNamespace(info={})


def test_discard_initialized_presets_clears_the_pending_bucket():
    session = _session()
    session.info[_PENDING_PRESETS] = {"a", "b"}
    _discard_initialized_presets(session, None)
    assert _PENDING_PRESETS not in session.info


def test_discard_initialized_presets_is_a_noop_without_pending_presets():
    session = _session()
    _discard_initialized_presets(session, None)
    assert session.info == {}


def test_closed_root_transaction_resets_the_pending_bucket():
    session = _session()
    session.info[_PENDING_PRESETS] = {"a"}
    _clear_closed_preset_transaction(session, SimpleNamespace(parent=None))
    assert _PENDING_PRESETS not in session.info


def test_nested_transaction_keeps_the_pending_bucket():
    session = _session()
    session.info[_PENDING_PRESETS] = {"a"}
    _clear_closed_preset_transaction(session, SimpleNamespace(parent=object()))
    assert session.info[_PENDING_PRESETS] == {"a"}
