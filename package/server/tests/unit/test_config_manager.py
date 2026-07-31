"""Unit tests for ``app.core.config_manager`` — the global user/App settings
singleton that backs the LLM connection picker, thumbnail quality, and a
handful of other runtime knobs.

Why this file exists:

* The current coverage scan flagged ``config_manager.py`` as a server-side
  blind spot. Many code paths embed ``config_manager.get_user_config(...)``
  calls (LLM dispatch, embedding dispatch, etc.) so any regression in the
  cache/merge logic would silently skew LLM behaviour. By smoke-testing
  the cache, merge, and migration logic in isolation we guarantee those
  callers cannot regress without us noticing.

What we cover:

* Singleton  — the private ``_instance`` sticks across instances.
* Cache      — TTL hit, TTL expiry, DB-only path, eviction (LRU size = 100).
* Update path — writing ``update_user_config`` mutates the cache *and* the
  user record (committed + ``flag_modified``) and raises on missing users.
* Migration  — the legacy ``ai.llm_settings`` / ``ai.llm_vl_settings``
  fields are stripped and the new ``connections`` array is auto-seeded.
* Built-in AI connection — ``merge_user_settings`` makes sure there is
  always a ``builtin`` connection pointing at the AI service url.

The DB is mocked throughout (no real Postgres needed for these unit tests).
``flag_modified`` is patched because ``SimpleNamespace`` does not carry the
SQLAlchemy ``_sa_instance_state`` attribute the ORM helper needs.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config_manager import (
    AppSettings,
    ConfigManager,
    config_manager,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture(autouse=True)
def _reset_singleton_cache():
    """The LRU cache lives on the class; flush it before each test so we
    never observe another test's payload."""
    config_manager._user_cache.clear()
    yield
    config_manager._user_cache.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_config_manager_is_singleton():
    """``ConfigManager.__new__`` must return the same instance forever."""
    cm1 = ConfigManager()
    cm2 = ConfigManager()
    assert cm1 is cm2
    assert cm1 is config_manager


def test_module_level_config_manager_is_default_app_settings():
    """The class-level ``config`` attribute starts as a vanilla ``AppSettings``
    so legacy callers (``system_config.config.security.*``) keep working."""
    assert isinstance(config_manager.config, AppSettings)
    assert config_manager.config.version  # default app version is set


# ---------------------------------------------------------------------------
# get_user_config cache behaviour
# ---------------------------------------------------------------------------


def _user_with_settings(settings):
    """Return a fake ORM user mirroring the ``app.db.models.user.User`` shape."""
    return SimpleNamespace(id=uuid4(), settings=settings)


def test_get_user_config_returns_default_when_user_missing():
    """No row in DB → still returns a fully-populated ``AppSettings``."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    cfg = config_manager.get_user_config(uuid4(), db)

    assert isinstance(cfg, AppSettings)
    # The default config always re-creates the built-in connection.
    ids = [c.id for c in cfg.ai.connections]
    assert "builtin" in ids


def test_get_user_config_returns_user_overrides_when_present():
    """When the user row has custom ``settings``, those override defaults."""
    db = MagicMock()
    user_id = uuid4()
    user = _user_with_settings({"image": {"thumbnail_quality": 42}})
    db.query.return_value.filter.return_value.first.return_value = user

    cfg = config_manager.get_user_config(user_id, db)

    assert cfg.image.thumbnail_quality == 42
    # Cache populated.
    assert user_id in config_manager._user_cache


def test_get_user_config_cache_hit_skips_db_after_first_call():
    """Within TTL the second call must reuse the cached config and NOT
    touch the db (asserted by ``filter.assert_not_called`` after the first
    miss)."""
    db = MagicMock()
    user_id = uuid4()
    user = _user_with_settings({})
    db.query.return_value.filter.return_value.first.return_value = user

    first = config_manager.get_user_config(user_id, db)

    # Reset the call counters to clearly observe the second call.
    db.query.reset_mock()
    db.query.return_value.filter.reset_mock()

    second = config_manager.get_user_config(user_id, db)

    # Identical object reference is the strongest cache-hit signal.
    assert first is second
    db.query.assert_not_called()


def test_get_user_config_refreshes_after_ttl_expires():
    """When TTL has elapsed, the cache entry is dropped and DB is re-queried."""
    db = MagicMock()
    user_id = uuid4()
    user = _user_with_settings({"image": {"preview_quality": 90}})
    db.query.return_value.filter.return_value.first.return_value = user

    config_manager.get_user_config(user_id, db)

    # Fast-forward well beyond the 5-second TTL.
    cached_payload = config_manager._user_cache[user_id]
    config_manager._user_cache[user_id] = (cached_payload[0], cached_payload[1] - 100)

    db.query.reset_mock()
    db.query.return_value.filter.return_value.first.return_value = user

    cfg = config_manager.get_user_config(user_id, db)
    assert cfg.image.preview_quality == 90
    db.query.assert_called_once()


def test_get_user_config_evicts_oldest_when_cache_full():
    """LRU has ``_cache_size = 100``; the 101st entry must evict the oldest."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    first_user = uuid4()
    config_manager.get_user_config(first_user, db)
    for _ in range(100):
        config_manager.get_user_config(uuid4(), db)

    assert len(config_manager._user_cache) == 100
    assert first_user not in config_manager._user_cache


# ---------------------------------------------------------------------------
# update_user_config
# ---------------------------------------------------------------------------


def test_update_user_config_writes_db_and_refreshes_cache():
    """``update_user_config`` should deep-merge, persist, then re-cache."""
    db = MagicMock()
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        settings={"image": {"thumbnail_quality": 50, "preview_quality": 70}},
    )
    db.query.return_value.filter.return_value.first.return_value = user

    with patch("sqlalchemy.orm.attributes.flag_modified") as flag_modified:
        new_cfg = config_manager.update_user_config(
            user_id,
            {"image": {"thumbnail_quality": 5}, "filter": {"enable": False}},
            db,
        )

    # Deep merge keeps unrelated keys.
    assert user.settings["image"]["preview_quality"] == 70
    assert user.settings["image"]["thumbnail_quality"] == 5
    assert user.settings["filter"]["enable"] is False
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(user)
    flag_modified.assert_called_once_with(user, "settings")
    # Cache refreshed after update.
    assert config_manager._user_cache[user_id][0] is new_cfg


def test_update_user_config_raises_value_error_when_user_missing():
    """If the user row is gone the helper must raise ``ValueError`` and
    *not* commit anything."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(ValueError):
        config_manager.update_user_config(uuid4(), {"filter": {"enable": False}}, db)

    db.commit.assert_not_called()


def test_update_user_config_migrates_legacy_ai_fields():
    """Old ``ai.llm_settings`` / ``ai.llm_vl_settings`` keys must be stripped
    and the new connection shape must be filled in."""
    db = MagicMock()
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        settings={"ai": {"llm_settings": {"foo": 1}, "llm_vl_settings": {"bar": 2}}},
    )
    db.query.return_value.filter.return_value.first.return_value = user

    with patch("sqlalchemy.orm.attributes.flag_modified") as flag_modified:
        config_manager.update_user_config(
            user_id,
            {"ai": {"analysis_model_name": "override-model"}},
            db,
        )

    ai = user.settings["ai"]
    assert "llm_settings" not in ai
    assert "llm_vl_settings" not in ai
    assert ai["analysis_model_name"] == "override-model"


# ---------------------------------------------------------------------------
# merge_user_settings helper
# ---------------------------------------------------------------------------


def test_merge_user_settings_none_falls_back_to_defaults():
    """``None`` (i.e. user existed but settings column was null) must be
    tolerated and produce a fully-default ``AppSettings``."""
    cfg = config_manager.merge_user_settings(None)
    assert isinstance(cfg, AppSettings)
    # The builtin connection is auto-seeded even on the empty branch.
    assert any(c.id == "builtin" for c in cfg.ai.connections)


def test_merge_user_settings_uses_explicit_ai_api_url_for_builtin():
    """When ``user_settings`` carries a custom ``ai.ai_api_url``, the
    auto-seeded builtin connection must follow that URL (used so agent
    dispatch still hits the AI service after deployment migrations)."""
    cfg = config_manager.merge_user_settings(
        {"ai": {"ai_api_url": "http://example.test:9876"}}
    )
    builtin = next(c for c in cfg.ai.connections if c.id == "builtin")
    assert builtin.api_base == "http://example.test:9876/v1"


def test_merge_user_settings_refreshes_existing_builtin_api_base():
    """If the user already has a builtin connection we still update its
    api_base whenever ``ai.ai_api_url`` is overridden, so that rotating
    the AI service url silently propagates."""
    cfg = config_manager.merge_user_settings(
        {
            "ai": {
                "ai_api_url": "http://rotated.test:1234",
                "connections": [
                    {
                        "id": "builtin",
                        "provider": "Old",
                        "api_base": "http://stale",
                        "api_key": "empty",
                        "model_names": ["m1"],
                        "enable": True,
                    }
                ],
            }
        }
    )
    builtin = next(c for c in cfg.ai.connections if c.id == "builtin")
    assert builtin.api_base == "http://rotated.test:1234/v1"


def test_merge_user_settings_strips_legacy_ai_settings():
    """The legacy ``llm_settings`` / ``llm_vl_settings`` keys are scrubbed
    even when merged in isolation (no DB row)."""
    cfg = config_manager.merge_user_settings(
        {"ai": {"llm_settings": {"x": 1}, "llm_vl_settings": {"y": 2}, "analysis_model_name": "M"}}
    )
    dump = cfg.ai.model_dump()
    assert "llm_settings" not in dump
    assert "llm_vl_settings" not in dump
    assert cfg.ai.analysis_model_name == "M"


def test_get_default_config_returns_serializable_dict():
    """``get_default_config`` is used by the settings export endpoint; the
    dict form must round-trip through ``AppSettings`` cleanly."""
    dump = config_manager.get_default_config()
    assert isinstance(dump, dict)
    assert "version" in dump
    assert "ai" in dump and "image" in dump and "filter" in dump
    # Round-trip back into AppSettings to confirm compatibility.
    AppSettings(**dump)
