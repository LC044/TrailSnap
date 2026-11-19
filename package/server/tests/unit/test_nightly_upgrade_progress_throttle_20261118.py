"""2026-11-18 nightly coverage for ``app/utils/upgrade_progress.py`` (part 2).

The throttle: a stage that keeps reporting the same progress must not rewrite
the progress file on every single call.
"""

from __future__ import annotations

import json

import pytest

from app.utils import upgrade_progress


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("TS_AUTOMATIC_UPGRADE_SESSION", "session-99")
    return "session-99"


def test_repeated_progress_of_the_same_stage_is_throttled(tmp_path, session):
    progress = upgrade_progress.UpgradeProgress(tmp_path)
    path = tmp_path / "maintenance" / "automatic-upgrade-progress.json"

    progress.report(stage="copying", completed=1, total=10)
    first = json.loads(path.read_text(encoding="utf-8"))
    progress.report(stage="copying", completed=2, total=10)
    second = json.loads(path.read_text(encoding="utf-8"))

    # The second call was throttled, so the file still shows the first snapshot.
    assert second == first
    assert second["completed"] == 1


def test_the_final_report_of_a_stage_is_never_throttled(tmp_path, session):
    progress = upgrade_progress.UpgradeProgress(tmp_path)
    path = tmp_path / "maintenance" / "automatic-upgrade-progress.json"

    progress.report(stage="copying", completed=1, total=10)
    progress.report(stage="copying", completed=10, total=10)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["completed"] == 10
