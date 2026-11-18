"""2026-11-18 nightly coverage for ``app/utils/upgrade_progress.py``.

No test file referenced ``app/utils/upgrade_progress.py``.  The module is the
private progress/cancel channel of the automatic upgrade: it writes a
progress file the launcher polls and it raises when the user asked for a
safe pause.

Covered here:

* the cancel file of the *current* session pauses the upgrade;
* a cancel file that belongs to another session is ignored;
* a corrupt cancel file is ignored instead of crashing the upgrade;
* the progress file carries the session, the stage and the counters;
* a non-interruptible stage is reported with ``cancellable=False``;
* without a session nothing is written at all;
* a failing write never aborts the surrounding data transaction.
"""

from __future__ import annotations

import json

import pytest

from app.utils import upgrade_progress


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("TS_AUTOMATIC_UPGRADE_SESSION", "session-42")
    return "session-42"


def _cancel_file(root, payload):
    path = root / "maintenance" / "automatic-upgrade-cancel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_the_cancel_file_of_the_current_session_pauses_the_upgrade(tmp_path, session):
    progress = upgrade_progress.UpgradeProgress(tmp_path)
    _cancel_file(tmp_path, {"session": session})

    with pytest.raises(ValueError) as excinfo:
        progress.checkpoint()

    assert "TRAILSNAP_UPGRADE_PAUSED" in str(excinfo.value)


def test_a_cancel_file_of_another_session_is_ignored(tmp_path, session):
    progress = upgrade_progress.UpgradeProgress(tmp_path)
    _cancel_file(tmp_path, {"session": "another-session"})

    progress.checkpoint()  # must not raise


def test_a_corrupt_cancel_file_is_ignored(tmp_path, session):
    progress = upgrade_progress.UpgradeProgress(tmp_path)
    path = tmp_path / "maintenance" / "automatic-upgrade-cancel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    progress.checkpoint()  # must not raise


def test_a_missing_cancel_file_is_ignored(tmp_path, session):
    progress = upgrade_progress.UpgradeProgress(tmp_path)

    progress.checkpoint()  # must not raise


def test_the_progress_file_carries_the_session_stage_and_counters(tmp_path, session):
    progress = upgrade_progress.UpgradeProgress(tmp_path)

    progress.report(stage="copying", completed=3, total=10)

    payload = json.loads(
        (tmp_path / "maintenance" / "automatic-upgrade-progress.json").read_text(encoding="utf-8")
    )
    assert payload["session"] == session
    assert payload["stage"] == "copying"
    assert payload["completed"] == 3
    assert payload["total"] == 10
    assert payload["cancellable"] is True
    assert "elapsedSeconds" in payload


def test_a_non_interruptible_stage_is_reported_as_not_cancellable(tmp_path, session):
    progress = upgrade_progress.UpgradeProgress(tmp_path)

    progress.report(stage="publishing", completed=1, total=1, cancellable=False)

    payload = json.loads(
        (tmp_path / "maintenance" / "automatic-upgrade-progress.json").read_text(encoding="utf-8")
    )
    assert payload["stage"] == "publishing"
    assert payload["cancellable"] is False


def test_nothing_is_written_without_a_session(tmp_path, monkeypatch):
    monkeypatch.delenv("TS_AUTOMATIC_UPGRADE_SESSION", raising=False)
    progress = upgrade_progress.UpgradeProgress(tmp_path)

    progress.report(stage="copying", completed=1, total=2)

    assert not (tmp_path / "maintenance" / "automatic-upgrade-progress.json").exists()


def test_a_failing_write_never_aborts_the_upgrade(tmp_path, session, monkeypatch):
    progress = upgrade_progress.UpgradeProgress(tmp_path)

    def _boom(*_args, **_kwargs):
        raise OSError("the file is locked by a scanner")

    monkeypatch.setattr(upgrade_progress, "write_json", _boom)

    progress.report(stage="copying", completed=1, total=2)  # must not raise


def test_a_paused_stage_stops_reporting_progress(tmp_path, session):
    progress = upgrade_progress.UpgradeProgress(tmp_path)
    _cancel_file(tmp_path, {"session": session})

    with pytest.raises(ValueError):
        progress.report(stage="copying", completed=1, total=2)
