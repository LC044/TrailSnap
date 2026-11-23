"""Nightly gap coverage 2026-11-24.

Covers uncovered branches found by the nightly coverage scan:

* app/utils/filename.py            — YYYYMMDD_HH-MM-SS parsing (real bug: %-M is
  not a valid ``datetime.strptime`` directive, so the branch always raised and
  the filename date was silently dropped) plus the invalid-timestamp guard.
* app/service/person_timeline.py   — scope validation, photo serialisation and
  the representative-photo cap.
* app/api/agent_action.py          — success branches of the plan progress /
  retry / cancel / continue / update / undo routes.
* app/api/toolbox_workflows.py     — cleanup preview enqueue, scan retry and
  selection/group error handling.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import agent_action, toolbox_workflows
from app.service import person_timeline
from app.utils import filename


pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------------------
# app/utils/filename.py
# ---------------------------------------------------------------------------


def test_filename_parses_compact_date_with_separated_time():
    """YYYYMMDD_HH-MM-SS must yield the real datetime, not None."""
    parsed = filename.extract_datetime_from_filename("IMG_20240102_03-04-05.jpg")

    assert parsed == datetime(2024, 1, 2, 3, 4, 5)


def test_filename_rejects_non_numeric_timestamp():
    """A 10-character non-numeric token must be ignored instead of raising."""
    assert filename.is_valid_timestamp("abcdefghij", "photo.jpg") is None


def test_filename_rejects_timestamp_with_wrong_length():
    assert filename.is_valid_timestamp("12345", "photo.jpg") is None


def test_filename_rejects_timestamp_inside_hash_like_name():
    """Hash-like names are rejected by the timestamp guard."""
    assert filename.is_valid_timestamp(
        "1735689600000", "d41d8cd98f00b204e9800998ecf8427e.jpg"
    ) is None


# ---------------------------------------------------------------------------
# app/service/person_timeline.py
# ---------------------------------------------------------------------------


def test_person_timeline_scope_rejects_same_person():
    owner_id = uuid4()
    person_id = uuid4()

    with pytest.raises(HTTPException) as error:
        person_timeline.scope(MagicMock(), owner_id, person_id, person_id)

    assert error.value.status_code == 400
    assert "不能选择同一人物" in error.value.detail


def test_person_timeline_scope_rejects_missing_person():
    owner_id = uuid4()
    person_id = uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with pytest.raises(HTTPException) as error:
        person_timeline.scope(db, owner_id, person_id, None)

    assert error.value.status_code == 404
    assert "人物不存在或不可访问" in error.value.detail


def test_person_timeline_photo_dict_falls_back_to_generic_name():
    photo = SimpleNamespace(
        id=uuid4(),
        photo_time=datetime(2024, 5, 6, 7, 8, 9),
        filename=None,
    )

    result = person_timeline.photo_dict(photo)

    assert result["id"] == str(photo.id)
    assert result["photo_time"] == "2024-05-06T07:08:09"
    assert result["thumbnail_url"] == f"/api/medias/{photo.id}/thumbnail"
    assert result["filename"] == "照片"


def test_person_timeline_representatives_stops_after_three_days():
    rows = [
        SimpleNamespace(id=uuid4(), photo_time=datetime(2024, 1, day, 12, 0))
        for day in range(1, 6)
    ]
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    chosen = person_timeline.representatives(db, rows)

    assert len(chosen) == 3
    assert len({row.photo_time.date() for row in chosen}) == 3


# ---------------------------------------------------------------------------
# app/api/agent_action.py
# ---------------------------------------------------------------------------


@pytest.fixture()
def agent_action_user():
    return SimpleNamespace(id=uuid4())


@pytest.fixture()
def agent_action_db():
    return MagicMock()


@pytest.fixture()
def plan_row():
    return SimpleNamespace(id="plan-1", plan_type="album_metadata_repair")


@pytest.fixture()
def patched_agent_action(monkeypatch, plan_row):
    """Neutralise plan serialisation and the background worker."""
    monkeypatch.setattr(agent_action, "_serialize", lambda row: {"id": row.id})
    worker = MagicMock()
    monkeypatch.setattr(agent_action, "TaskManager", MagicMock(get_instance=MagicMock(return_value=worker)))
    return worker


def test_agent_action_confirm_starts_worker_for_album_repair(
    monkeypatch, agent_action_user, agent_action_db, plan_row, patched_agent_action
):
    monkeypatch.setattr(agent_action, "execute_plan", lambda db, user_id, plan_id: plan_row)

    response = agent_action.confirm_action_plan(
        "plan-1", current_user=agent_action_user, db=agent_action_db
    )

    assert response.code == 0
    assert response.data == {"id": "plan-1"}
    patched_agent_action.start_worker_if_needed.assert_called_once()


def test_agent_action_progress_returns_progress(
    monkeypatch, agent_action_user, agent_action_db, patched_agent_action
):
    monkeypatch.setattr(
        agent_action, "get_metadata_repair_progress", lambda db, user_id, plan_id: {"done": 3}
    )

    response = agent_action.get_action_plan_progress(
        "plan-1", current_user=agent_action_user, db=agent_action_db
    )

    assert response.code == 0
    assert response.data == {"done": 3}


def test_agent_action_retry_starts_worker(
    monkeypatch, agent_action_user, agent_action_db, plan_row, patched_agent_action
):
    monkeypatch.setattr(
        agent_action, "retry_metadata_repair_tasks", lambda db, user_id, plan_id: plan_row
    )

    response = agent_action.retry_action_plan_tasks(
        "plan-1", current_user=agent_action_user, db=agent_action_db
    )

    assert response.data == {"id": "plan-1"}
    patched_agent_action.start_worker_if_needed.assert_called_once()


def test_agent_action_cancel_returns_result(
    monkeypatch, agent_action_user, agent_action_db, patched_agent_action
):
    monkeypatch.setattr(
        agent_action, "cancel_metadata_repair_tasks", lambda db, user_id, plan_id: {"cancelled": 2}
    )

    response = agent_action.cancel_action_plan_tasks(
        "plan-1", current_user=agent_action_user, db=agent_action_db
    )

    assert response.code == 0
    assert response.data == {"cancelled": 2}


def test_agent_action_continue_returns_plan(
    monkeypatch, agent_action_user, agent_action_db, plan_row, patched_agent_action
):
    monkeypatch.setattr(
        agent_action, "continue_metadata_repair_plan", lambda db, user_id, plan_id: plan_row
    )

    response = agent_action.continue_action_plan(
        "plan-1", current_user=agent_action_user, db=agent_action_db
    )

    assert response.data == {"id": "plan-1"}


def test_agent_action_update_returns_plan(
    monkeypatch, agent_action_user, agent_action_db, plan_row, patched_agent_action
):
    monkeypatch.setattr(
        agent_action,
        "update_repair_plan_selection",
        lambda db, user_id, plan_id, selected: plan_row,
    )
    payload = agent_action.AgentRepairSelectionUpdate(selected_repair_ids=["r1"])

    response = agent_action.update_action_plan(
        "plan-1", payload, current_user=agent_action_user, db=agent_action_db
    )

    assert response.data == {"id": "plan-1"}


def test_agent_action_undo_returns_plan(
    monkeypatch, agent_action_user, agent_action_db, plan_row, patched_agent_action
):
    monkeypatch.setattr(agent_action, "undo_plan", lambda db, user_id, plan_id: plan_row)

    response = agent_action.undo_action_plan(
        "plan-1", current_user=agent_action_user, db=agent_action_db
    )

    assert response.data == {"id": "plan-1"}


# ---------------------------------------------------------------------------
# app/api/toolbox_workflows.py
# ---------------------------------------------------------------------------


@pytest.fixture()
def toolbox_user():
    return SimpleNamespace(id=uuid4(), settings=None)


@pytest.fixture()
def patched_toolbox(monkeypatch):
    worker = MagicMock()
    monkeypatch.setattr(toolbox_workflows, "TaskManager", MagicMock(get_instance=MagicMock(return_value=worker)))
    monkeypatch.setattr(toolbox_workflows, "plan_view", lambda plan: {"id": str(plan.id)})
    return worker


def test_toolbox_cleanup_preview_enqueues_scan(monkeypatch, toolbox_user, patched_toolbox):
    from app.schemas.toolbox import MediaScope, PlanRequest, ToolConfig

    request = PlanRequest(scope=MediaScope(source="all"), config=ToolConfig(kind="cleanup"))
    plan = SimpleNamespace(id=uuid4())
    calls = []

    monkeypatch.setattr(
        "app.service.cleanup_scan.enqueue_scan",
        lambda db, user, req: calls.append((db, user, req)) or plan,
    )
    db = MagicMock()

    response = toolbox_workflows.preview(request, db=db, user=toolbox_user)

    assert response.code == 0
    assert response.data == {"id": str(plan.id)}
    assert len(calls) == 1
    patched_toolbox.start_worker_if_needed.assert_called_once()


def test_toolbox_retry_resumes_failed_scan(monkeypatch, toolbox_user, patched_toolbox):
    from app.schemas.toolbox import MediaScope, PlanRequest, ToolConfig

    plan = SimpleNamespace(id=uuid4(), status="scan_failed")
    queued = []

    monkeypatch.setattr(toolbox_workflows, "get_plan", lambda db, user_id, plan_id: plan)
    monkeypatch.setattr(
        "app.service.cleanup_scan.queue_scan", lambda db, target: queued.append(target)
    )

    response = toolbox_workflows.retry(plan.id, db=MagicMock(), user=toolbox_user)

    assert response.code == 0
    assert queued == [plan]
    patched_toolbox.start_worker_if_needed.assert_called_once()


def test_toolbox_selection_rejects_stale_preview(monkeypatch, toolbox_user, patched_toolbox):
    from app.schemas.toolbox import CleanupSelectionRequest

    plan = SimpleNamespace(
        id=uuid4(),
        kind="organize",
        status="preview",
        version=9,
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    monkeypatch.setattr(toolbox_workflows, "get_plan", lambda db, user_id, plan_id: plan)
    request = CleanupSelectionRequest(version=1, item_ids=[1], selected=True)

    response = toolbox_workflows.selection(plan.id, request, db=MagicMock(), user=toolbox_user)

    assert response.code == 400
    assert "预览已变化" in response.msg


def test_toolbox_group_members_reports_missing_group(monkeypatch, toolbox_user, patched_toolbox):
    plan = SimpleNamespace(id=uuid4(), status="preview")
    monkeypatch.setattr(toolbox_workflows, "get_plan", lambda db, user_id, plan_id: plan)
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None

    response = toolbox_workflows.group_members(plan.id, 1, db=db, user=toolbox_user)

    assert response.code == 400
    assert "分组不存在" in response.msg
