"""Nightly watch 2026-10-30 (r3) · app/service/daily_frame_render.py 的 render_work 编排盲区。

被测模块：app/service/daily_frame_render.py（此前覆盖率 85.0%，37 行未触达）。
未触达的部分几乎全部集中在 render_work 的编排循环与发布阶段，此前只有
"作品不存在/已结束" 两个取消分支被覆盖。

本文件覆盖：
- render_work 的完整发布路径：分段编码 → 写播放列表 → 拼接 → 生成封面 →
  发布前重新校验 → 落盘 → 标记 ready。
- 取消分支：作品行丢失、generation 不匹配、任务已结束、发布前作品状态被改回 queued、
  发布阶段的状态更新没有命中任何行。
- 失败分支：素材失效、分段编码失败（都带日期前缀），并把作品标记为 failed。
- run_encoder 的兜底：进程未退出时 terminate，等待超时则 kill。
"""

import subprocess
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.service import daily_frame as frame_service
from app.service import daily_frame_render as render

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]

DAY = date(2026, 1, 2)


class FakeResult:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount


class FakeRow:
    """Stand-in for a DailyFrameWork / Task ORM row."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


class FakeSession:
    """Minimal Session double covering the statements render_work executes."""

    def __init__(self, work, task, publish_row=None):
        self.work = work
        self.task = task
        self.publish_row = publish_row
        self.commits = 0
        self.executes = 0
        self.fail_first_update = False
        self.fail_publish_update = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get(self, model, ident):
        name = getattr(model, "__name__", "")
        if name == "DailyFrameWork":
            return self.work
        if name == "Task":
            return self.task
        return None

    def execute(self, statement):
        self.executes += 1
        # ``_values`` holds only the columns the statement writes; the compiled
        # parameters would also contain the WHERE columns under the same names.
        values = {getattr(key, "name", key): getattr(bind, "value", bind)
                   for key, bind in (getattr(statement, "_values", {}) or {}).items()}
        entity = getattr(getattr(statement, "table", None), "name", "")
        if entity == "daily_frame_works":
            if "output_path" in values:
                if self.fail_publish_update:
                    return FakeResult(0)
                self.work.status = values.get("status", self.work.status)
                self.work.output_path = values.get("output_path", self.work.output_path)
            elif self.fail_first_update and self.executes == 1:
                return FakeResult(0)
            else:
                self.work.status = values.get("status", self.work.status)
                self.work.processed_items = values.get("processed_items", self.work.processed_items)
        return FakeResult(1)

    def query(self, *args, **kwargs):
        return self

    def filter_by(self, **kwargs):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.publish_row if self.publish_row is not None else self.work

    def commit(self):
        self.commits += 1


def _snapshot(frames=1):
    return {
        "settings": {"start_date": DAY.isoformat(), "end_date": DAY.isoformat(), "title": "daily",
                     "orientation": "portrait", "fit": "contain", "show_date": True,
                     "show_caption": True, "background": "#111827", "skip_invalid": False},
        "timezone": "Asia/Shanghai",
        "frames": [{"day": DAY.isoformat(), "photo_id": str(uuid4()), "mode": "still",
                    "start_seconds": 0, "caption": "", "version": 1} for _ in range(frames)],
    }


def _work(status="queued", generation=1, snapshot=None, task_id=None):
    return FakeRow(id=uuid4(), owner_id=uuid4(), task_id=task_id or uuid4(), generation=generation,
                   status=status, error=None, processed_items=0, output_path=None,
                   deleted_at=None, is_preview=False, snapshot=snapshot or _snapshot())


def _task(status="pending"):
    return FakeRow(id=uuid4(), status=status, processed_items=0)


@pytest.fixture()
def render_env(tmp_path, monkeypatch):
    """Wire render_work to a fake session, a temporary output root and a stub encoder."""
    state = {"work": None, "session": None, "encoder_calls": [], "segments": []}
    root = tmp_path / "outputs"
    root.mkdir()

    monkeypatch.setattr(render, "output_root", lambda owner_id: root)
    monkeypatch.setattr(render, "remove_output", lambda owner_id, output: Path(output).unlink(missing_ok=True))

    def fake_session():
        return state["session"]

    monkeypatch.setattr("app.db.session.SessionLocal", fake_session)

    def fake_owned_photo(session, owner_id, photo_id):
        return FakeRow(id=photo_id)

    def fake_source_path(photo, mode):
        if photo is None:
            return None, "素材已删除或不可访问"
        return "/tmp/source.jpg", None

    monkeypatch.setattr(frame_service, "owned_photo", fake_owned_photo)
    monkeypatch.setattr(frame_service, "source_path", fake_source_path)

    def fake_encode_segment(path, item, settings, temporary, index, preview, check_cancelled):
        state["segments"].append(index)
        destination = temporary / ("%04d.mp4" % index)
        destination.write_bytes(b"segment")
        return destination

    def fake_run_encoder(args, working, check_cancelled, timeout=180):
        state["encoder_calls"].append(list(args))
        Path(args[-1]).write_bytes(b"encoded")

    monkeypatch.setattr(render, "encode_segment", fake_encode_segment)
    monkeypatch.setattr(render, "run_encoder", fake_run_encoder)
    state["root"] = root
    return state


# ---------------------------------------------------------------------------
# render_work
# ---------------------------------------------------------------------------


def test_render_work_publishes_the_finished_film(render_env):
    task = _task()
    work = _work(status="queued", task_id=task.id)
    session = FakeSession(work, task)
    render_env["session"] = session
    result = render.render_work(work.id, work.generation, task.id)
    assert result == {"work_id": str(work.id), "duration": 1}
    assert work.status == "ready"
    assert work.output_path and work.output_path.endswith(".mp4")
    assert Path(work.output_path).is_file()
    assert Path(work.output_path).with_suffix(".jpg").is_file()
    assert render_env["segments"] == [0]
    # One concat call and one poster call; the per-frame segments are stubbed out.
    assert len(render_env["encoder_calls"]) == 2


def test_render_work_marks_the_work_failed_when_a_source_disappeared(render_env, monkeypatch):
    task = _task()
    work = _work(status="queued", task_id=task.id)
    render_env["session"] = FakeSession(work, task)
    monkeypatch.setattr(frame_service, "source_path", lambda photo, mode: (None, "源文件暂时不可读取"))
    with pytest.raises(RuntimeError) as failure:
        render.render_work(work.id, work.generation, task.id)
    assert "源文件暂时不可读取" in str(failure.value)
    assert work.status == "failed"


def test_render_work_reports_the_failing_day_when_a_segment_cannot_be_encoded(render_env, monkeypatch):
    task = _task()
    work = _work(status="queued", task_id=task.id)
    render_env["session"] = FakeSession(work, task)

    def boom(path, item, settings, temporary, index, preview, check_cancelled):
        raise RuntimeError("照片无法解码，请更换素材后重试")

    monkeypatch.setattr(render, "encode_segment", boom)
    with pytest.raises(RuntimeError) as failure:
        render.render_work(work.id, work.generation, task.id)
    assert str(failure.value).startswith(DAY.isoformat())
    assert "照片无法解码" in str(failure.value)
    assert work.status == "failed"


def test_render_work_is_cancelled_when_the_work_row_disappeared(render_env):
    task = _task()
    work = _work(status="queued", task_id=task.id)
    session = FakeSession(work, task)
    session.work = None
    render_env["session"] = session
    with pytest.raises(render.RenderCancelled):
        render.render_work(work.id, work.generation, task.id)


def test_render_work_is_cancelled_when_the_generation_moved_on(render_env):
    task = _task()
    work = _work(status="queued", generation=3, task_id=task.id)
    render_env["session"] = FakeSession(work, task)
    with pytest.raises(render.RenderCancelled):
        render.render_work(work.id, 2, task.id)


def test_render_work_is_cancelled_when_the_start_update_matches_no_row(render_env):
    task = _task()
    work = _work(status="queued", task_id=task.id)
    session = FakeSession(work, task)
    session.fail_first_update = True
    render_env["session"] = session
    with pytest.raises(render.RenderCancelled):
        render.render_work(work.id, work.generation, task.id)


def test_render_work_is_cancelled_when_the_task_already_finished(render_env):
    task = _task(status="failed")
    work = _work(status="queued", task_id=task.id)
    render_env["session"] = FakeSession(work, task)
    with pytest.raises(render.RenderCancelled):
        render.render_work(work.id, work.generation, task.id)


def test_render_work_is_cancelled_when_the_work_left_the_processing_state(render_env):
    task = _task()
    work = _work(status="queued", task_id=task.id)
    publish_row = _work(status="queued", task_id=task.id)
    publish_row.id = work.id
    publish_row.generation = work.generation
    publish_row.task_id = task.id
    session = FakeSession(work, task, publish_row=publish_row)
    render_env["session"] = session
    with pytest.raises(render.RenderCancelled):
        render.render_work(work.id, work.generation, task.id)


def test_render_work_is_cancelled_when_the_publish_update_matches_no_row(render_env):
    task = _task()
    work = _work(status="queued", task_id=task.id)
    session = FakeSession(work, task)
    session.fail_publish_update = True
    render_env["session"] = session
    with pytest.raises(render.RenderCancelled):
        render.render_work(work.id, work.generation, task.id)
    assert not list(render_env["root"].glob("*.mp4"))


def test_render_work_removes_a_half_written_output_when_it_fails(render_env, monkeypatch):
    task = _task()
    work = _work(status="queued", task_id=task.id)
    render_env["session"] = FakeSession(work, task)

    def boom(args, working, check_cancelled, timeout=180):
        raise RuntimeError("素材处理超时，请更换素材后重试")

    monkeypatch.setattr(render, "run_encoder", boom)
    with pytest.raises(RuntimeError):
        render.render_work(work.id, work.generation, task.id)
    assert work.status == "failed"
    assert not list(render_env["root"].glob("*.mp4"))


# ---------------------------------------------------------------------------
# run_encoder 的进程兜底
# ---------------------------------------------------------------------------


def test_run_encoder_kills_a_process_that_refuses_to_stop(tmp_path, monkeypatch):
    class StubbornProcess:
        def __init__(self):
            self.terminated = False
            self.killed = False
            self.returncode = 0

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            if self.killed:
                return 0
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout or 0)

        def kill(self):
            self.killed = True

    process = StubbornProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(render, "ffmpeg_path", lambda: "ffmpeg")
    with pytest.raises(render.RenderCancelled):
        render.run_encoder(["-i", "a.mp4"], tmp_path, lambda: (_ for _ in ()).throw(render.RenderCancelled()))
    assert process.terminated is True
    assert process.killed is True
