"""2026-11-19 nightly coverage for ``app/service/disk_budget.py``.

``DiskBudget.volume`` / ``slot`` / ``slots``, ``BudgetedFile`` and
``media_io`` were never referenced by any test file.  This module is the
admission control that keeps media IO from saturating a storage volume, and
its two subtle rules matter: a slot is reentrant (nested reads share the
outer slot) and multi-volume jobs acquire their volumes in a stable order so
opposite-direction copies cannot deadlock.
"""

from __future__ import annotations

import io
import threading

import pytest

from app.service import disk_budget
from app.service.disk_budget import BudgetedFile, DiskBudget, budgeted_open, media_io


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_volume_is_stable_for_two_paths_on_the_same_volume(tmp_path):
    budget = DiskBudget()

    assert budget.volume(tmp_path / "a.jpg") == budget.volume(tmp_path / "b.jpg")


def test_configure_clamps_the_limit_to_at_least_one():
    budget = DiskBudget()

    budget.configure(0)

    assert budget.limit == 1


def test_a_slot_is_reentrant_for_the_same_volume(tmp_path):
    budget = DiskBudget(limit=1)

    with budget.slot(tmp_path):
        # A nested slot on the same volume must not block on itself.
        with budget.slot(tmp_path):
            pass

    assert not any(budget._active.values())


def test_a_slot_is_released_even_when_the_body_raises(tmp_path):
    budget = DiskBudget(limit=1)

    with pytest.raises(RuntimeError):
        with budget.slot(tmp_path):
            raise RuntimeError("boom")

    assert not any(budget._active.values())


def test_a_second_thread_waits_for_the_slot_to_be_released(tmp_path):
    budget = DiskBudget(limit=1)
    order: list[str] = []

    def worker(name):
        with budget.slot(tmp_path):
            order.append(f"{name}-in")
            threading.Event().wait(0.05)
            order.append(f"{name}-out")

    first = threading.Thread(target=worker, args=("a",))
    second = threading.Thread(target=worker, args=("b",))
    first.start()
    first.join()
    second.start()
    second.join()

    # With a limit of one, the two jobs must not interleave.
    assert order == ["a-in", "a-out", "b-in", "b-out"]


def test_slots_acquires_several_volumes_at_once(tmp_path):
    budget = DiskBudget(limit=4)

    with budget.slots(tmp_path / "a.jpg", tmp_path / "b.jpg"):
        pass

    assert not any(budget._active.values())


def test_slots_ignores_none_paths(tmp_path):
    budget = DiskBudget(limit=1)

    with budget.slots(None, tmp_path):
        pass

    assert not any(budget._active.values())


def test_budgeted_open_reads_the_file_contents(tmp_path):
    target = tmp_path / "photo.bin"
    target.write_bytes(b"hello trailsnap")

    with budgeted_open(target, "rb") as handle:
        assert handle.read() == b"hello trailsnap"


def test_a_budgeted_file_keeps_the_path_as_its_name(tmp_path):
    target = tmp_path / "photo.bin"
    target.write_bytes(b"x")

    with budgeted_open(target, "rb") as handle:
        assert handle.name == str(target)


def test_a_budgeted_file_does_not_expose_fileno(tmp_path):
    target = tmp_path / "photo.bin"
    target.write_bytes(b"x")

    with budgeted_open(target, "rb") as handle:
        # Exposing fileno() would let Pillow bypass the admission slot.
        with pytest.raises(io.UnsupportedOperation):
            handle.fileno()


def test_a_budgeted_file_can_be_written_through(tmp_path):
    target = tmp_path / "photo.bin"

    with budgeted_open(target, "wb") as handle:
        handle.write(b"payload")

    assert target.read_bytes() == b"payload"


def test_media_io_admits_the_job_using_the_named_path_argument(tmp_path):
    target = tmp_path / "photo.bin"
    target.write_bytes(b"payload")
    observed: list[str] = []

    @media_io("path")
    def read_it(path):
        observed.append(path)
        return path.read_bytes()

    assert read_it(target) == b"payload"
    assert observed == [target]


def test_media_io_supports_several_path_arguments(tmp_path):
    source = tmp_path / "a.bin"
    target = tmp_path / "b.bin"
    source.write_bytes(b"payload")

    @media_io("source", "target")
    def copy(source, target):
        target.write_bytes(source.read_bytes())

    copy(source, target)

    assert target.read_bytes() == b"payload"


def test_media_io_keeps_the_wrapped_function_metadata():
    @media_io("path")
    def documented(path):
        """Doc string."""
        return path

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "Doc string."


def test_the_module_level_budget_is_a_shared_instance():
    assert isinstance(disk_budget.disk_budget, DiskBudget)
    assert isinstance(disk_budget.disk_budget, DiskBudget)

