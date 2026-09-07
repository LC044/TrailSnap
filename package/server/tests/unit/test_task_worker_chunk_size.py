import pytest

from app.db.models.task import TaskType
from app.service import task_worker

pytestmark = [pytest.mark.smoke]


def test_high_concurrency_chunk_sizes(monkeypatch):
    monkeypatch.setattr(task_worker, "resolve_concurrency_level", lambda _level: "high")

    assert task_worker.get_chunk_size(TaskType.VISUAL_DESCRIPTION) == 1
    assert task_worker.get_chunk_size(TaskType.OCR) == 2
    assert task_worker.get_chunk_size(TaskType.RECOGNIZE_TICKET) == 2
    assert task_worker.get_chunk_size(TaskType.RECOGNIZE_FACE) == 4
    assert task_worker.get_chunk_size(TaskType.PROCESS_BASIC) == 16
    assert task_worker.get_chunk_size(TaskType.EXTRACT_METADATA) == 16
    assert task_worker.get_chunk_size(TaskType.CLASSIFY_IMAGE) == 8
    assert task_worker.get_chunk_size(TaskType.IMAGE_EMBEDDING) == 8


def test_low_concurrency_chunk_sizes(monkeypatch):
    monkeypatch.setattr(task_worker, "resolve_concurrency_level", lambda _level: "low")

    assert task_worker.get_chunk_size(TaskType.PROCESS_BASIC) == 16
    assert task_worker.get_chunk_size(TaskType.OCR) == 1
    assert task_worker.get_chunk_size(TaskType.RECOGNIZE_FACE) == 2
    assert task_worker.get_chunk_size(TaskType.CLUSTER_FACES) == 1
    assert task_worker.get_chunk_size(TaskType.IMAGE_EMBEDDING) == 8