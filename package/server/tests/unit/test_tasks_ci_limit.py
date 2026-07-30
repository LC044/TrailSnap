"""Unit tests for app/service/tasks/ci_limit.py.

CI (GitHub Actions) caps AI-class tasks (OCR / VISUAL_DESCRIPTION) at 5
photos each to keep the standard runner (4 vCPU) from blowing up. These
functions are pure: they branch on os.environ and a single SQL count.
"""

import os
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture
def fake_model():
    """Stand-in for an ORM model with a ``photo_id`` column."""
    model = MagicMock()
    model.photo_id = "photo_id"
    return model


def test_is_ci_false_when_env_unset(monkeypatch):
    from app.service.tasks.ci_limit import is_ci
    monkeypatch.delenv("CI", raising=False)
    assert is_ci() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes", " 1 "])
def test_is_ci_true_for_truthy_values(monkeypatch, value):
    from app.service.tasks.ci_limit import is_ci
    monkeypatch.setenv("CI", value)
    assert is_ci() is True


def test_is_ci_false_for_unrelated_env(monkeypatch):
    from app.service.tasks.ci_limit import is_ci
    monkeypatch.setenv("CI", "no")
    assert is_ci() is False


def test_ci_task_limit_reached_returns_false_when_not_in_ci(monkeypatch, fake_model):
    """In dev / local, ci_task_limit_reached must always return False."""
    from app.service.tasks.ci_limit import ci_task_limit_reached
    monkeypatch.delenv("CI", raising=False)
    db = MagicMock()
    # Even with a 1M photo_id count, non-CI should not query the DB.
    db.query.return_value.distinct.return_value.count.return_value = 999
    assert ci_task_limit_reached(db, fake_model) is False
    db.query.assert_not_called()


def test_ci_task_limit_reached_queries_db_in_ci(monkeypatch, fake_model):
    """In CI, must count distinct photo_id rows and compare to limit."""
    from app.service.tasks.ci_limit import ci_task_limit_reached, CI_TASK_PHOTO_LIMIT
    monkeypatch.setenv("CI", "true")
    db = MagicMock()
    db.query.return_value.distinct.return_value.count.return_value = CI_TASK_PHOTO_LIMIT
    assert ci_task_limit_reached(db, fake_model) is True
    db.query.assert_called_once_with(fake_model.photo_id)


def test_ci_task_limit_reached_false_below_threshold(monkeypatch, fake_model):
    from app.service.tasks.ci_limit import ci_task_limit_reached, CI_TASK_PHOTO_LIMIT
    monkeypatch.setenv("CI", "1")
    db = MagicMock()
    db.query.return_value.distinct.return_value.count.return_value = CI_TASK_PHOTO_LIMIT - 1
    assert ci_task_limit_reached(db, fake_model) is False


def test_ci_remaining_budget_none_outside_ci(monkeypatch, fake_model):
    """Non-CI: budget is None (i.e. unlimited)."""
    from app.service.tasks.ci_limit import ci_remaining_budget
    monkeypatch.delenv("CI", raising=False)
    db = MagicMock()
    assert ci_remaining_budget(db, fake_model) is None
    db.query.assert_not_called()


def test_ci_remaining_budget_clamped_to_zero(monkeypatch, fake_model):
    """If we are already over the cap, return 0 (not negative)."""
    from app.service.tasks.ci_limit import ci_remaining_budget, CI_TASK_PHOTO_LIMIT
    monkeypatch.setenv("CI", "true")
    db = MagicMock()
    db.query.return_value.distinct.return_value.count.return_value = CI_TASK_PHOTO_LIMIT + 10
    assert ci_remaining_budget(db, fake_model) == 0


def test_ci_remaining_budget_returns_positive(monkeypatch, fake_model):
    from app.service.tasks.ci_limit import ci_remaining_budget, CI_TASK_PHOTO_LIMIT
    monkeypatch.setenv("CI", "yes")
    db = MagicMock()
    db.query.return_value.distinct.return_value.count.return_value = CI_TASK_PHOTO_LIMIT - 2
    assert ci_remaining_budget(db, fake_model) == 2
