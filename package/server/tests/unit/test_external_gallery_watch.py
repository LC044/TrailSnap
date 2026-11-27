import os
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from watchdog.events import DirDeletedEvent, FileCreatedEvent, FileMovedEvent

from app.service import gallery_availability, gallery_watch as watcher

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture
def running_watch(tmp_path, monkeypatch):
    db = MagicMock()
    db.__enter__.return_value = db
    user = SimpleNamespace(id="owner", settings={})
    db.query.return_value.all.return_value = [user]
    monkeypatch.setattr(watcher, "SessionLocal", lambda: db)
    manager = MagicMock()
    monkeypatch.setattr(watcher.TaskManager, "get_instance", lambda: manager)
    native = MagicMock()
    monkeypatch.setattr(watcher, "Observer", native)
    monkeypatch.setattr(watcher, "mount_inventory", lambda: {})
    monkeypatch.setattr(gallery_availability, "DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(watcher.system_config.config, "watch_external_galleries", True)
    clock = [100.0]
    monkeypatch.setattr(watcher.time, "monotonic", lambda: clock[0])
    service = watcher.ExternalGalleryWatcher()
    yield service, user, native, manager.try_enqueue_gallery_scan, clock
    service.close()


def register(service, user, root):
    user.settings = {"storage": {"external_directories": [str(root)]}}
    service.tick()
    key = os.path.normcase(str(root))
    return service.watches[user.id, key]


def test_batch_retained_while_busy_and_move_covers_both_folders(running_watch, tmp_path):
    service, user, _, enqueue, clock = running_watch
    watch = register(service, user, tmp_path)
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    handler = watcher.GalleryEvents(watch)
    for n in range(100):
        handler.dispatch(FileCreatedEvent(str(destination / f"{n}.jpg")))
    handler.dispatch(FileMovedEvent(str(source / "old.jpg"), str(destination / "new.jpg")))
    service.tick()
    enqueue.assert_not_called()
    clock[0] += watcher.DEBOUNCE
    enqueue.return_value = False
    service.tick()
    enqueue.return_value = True
    service.tick()
    service.tick()
    assert enqueue.call_count == 2
    payloads = [call.args[1] for call in enqueue.call_args_list]
    assert payloads[0] == payloads[1]
    assert set(payloads[0]["scan_roots"]) == {str(source), str(destination)}


def test_directory_removal_scans_surviving_parent(running_watch, tmp_path):
    service, user, _, enqueue, clock = running_watch
    watch = register(service, user, tmp_path)
    watcher.GalleryEvents(watch).dispatch(DirDeletedEvent(str(tmp_path / "gone" / "child")))
    clock[0] += watcher.DEBOUNCE
    service.tick()
    assert enqueue.call_args.args[1]["scan_roots"] == [watch.root]


def test_offline_mount_is_preserved_and_recovery_enqueues_scan(running_watch, tmp_path, monkeypatch):
    service, user, native, enqueue, clock = running_watch
    mount_path = gallery_availability.gallery_path_key(str(tmp_path))
    inventory = {mount_path: ["nas:/gallery", "nfs"]}
    monkeypatch.setattr(watcher, "mount_inventory", lambda: inventory)
    monkeypatch.setattr(watcher, "needs_polling", lambda *args: False)
    watch = register(service, user, tmp_path)
    identity = watch.identity
    identity_mock = MagicMock(return_value=(identity[0] + 1, identity[1]))
    monkeypatch.setattr(watcher, "directory_identity", identity_mock)
    inventory.clear()
    watch.mark(watch.root)
    clock[0] += watcher.REFRESH_INTERVAL
    service.tick()
    assert watch.online is False
    native.return_value.stop.assert_called_once()
    enqueue.assert_not_called()

    identity_mock.return_value = identity
    inventory[mount_path] = ["nas:/gallery", "nfs"]
    clock[0] += watcher.REFRESH_INTERVAL
    service.tick()
    clock[0] += watcher.DEBOUNCE
    service.tick()
    assert watch.online is True
    assert native.call_count == 2
    assert enqueue.call_args.args[1]["scan_roots"] == [watch.root]


def test_dynamic_registration_removal_and_switch(running_watch, tmp_path):
    service, user, native, enqueue, clock = running_watch
    register(service, user, tmp_path)
    user.settings = {}
    clock[0] += watcher.REFRESH_INTERVAL
    service.tick()
    assert not service.watches
    native.return_value.stop.assert_called_once()
    clock[0] += watcher.REFRESH_INTERVAL
    watch = register(service, user, tmp_path)
    watch.mark(watch.root)
    watcher.system_config.config.watch_external_galleries = False
    clock[0] += watcher.DEBOUNCE
    service.tick()
    assert not service.watches
    enqueue.assert_not_called()


def test_cold_nonempty_placeholder_retains_unverified_paths_until_recovery(running_watch, tmp_path, monkeypatch):
    service, user, native, enqueue, clock = running_watch
    (tmp_path / "placeholder.txt").touch()
    original = tmp_path / "restored.jpg"
    key = gallery_availability.gallery_path_key(str(original))
    monkeypatch.setattr(service, "_indexed_paths", lambda user_id, root: [str(original)])
    watch = register(service, user, tmp_path)
    assert watch.state["unverified"] == [key]

    clock[0] += watcher.NATIVE_BACKSTOP_INTERVAL
    service.tick()
    clock[0] += watcher.DEBOUNCE
    service.tick()
    assert enqueue.call_args.args[1]["watch_guards"][watch.root]["unverified"] == [key]

    service._clear()
    enqueue.reset_mock()
    watch = register(service, user, tmp_path)
    assert watch.state["unverified"] == [key]
    enqueue.assert_not_called()

    original.write_bytes(b"image")
    clock[0] += watcher.POLL_INTERVAL
    service.tick()
    clock[0] += watcher.DEBOUNCE
    service.tick()
    assert watch.online is True
    assert enqueue.call_args.args[1]["watch_guards"][watch.root]["unverified"] == []


def test_mount_disappears_across_restart_and_reconnects(running_watch, tmp_path, monkeypatch):
    service, user, _, enqueue, clock = running_watch
    path = gallery_availability.gallery_path_key(str(tmp_path))
    inventory = {path: ["nas:/gallery", "nfs"]}
    monkeypatch.setattr(watcher, "mount_inventory", lambda: inventory)
    monkeypatch.setattr(watcher, "needs_polling", lambda *args: False)
    register(service, user, tmp_path)
    service._clear()
    inventory.clear()
    watch = register(service, user, tmp_path)
    assert watch.online is False
    enqueue.assert_not_called()

    inventory[path] = ["nas:/gallery", "nfs"]
    clock[0] += watcher.REFRESH_INTERVAL
    service.tick()
    clock[0] += watcher.DEBOUNCE
    service.tick()
    assert watch.online is True
    assert enqueue.call_args.args[1]["scan_roots"] == [watch.root]


def test_native_failure_uses_polling_and_retries(running_watch, tmp_path):
    service, user, native, enqueue, clock = running_watch
    native.return_value.start.side_effect = OSError("native notification unavailable")
    watch = register(service, user, tmp_path)
    assert watch.observer is None
    clock[0] += watcher.POLL_INTERVAL
    service.tick()
    clock[0] += watcher.DEBOUNCE
    service.tick()
    assert enqueue.call_args.args[1]["scan_roots"] == [watch.root]
    assert native.call_count == 2
    native.return_value.start.side_effect = None
    clock[0] += watcher.POLL_INTERVAL
    service.tick()
    assert watch.observer is native.return_value


def test_linux_bind_mount_uses_polling_observer(running_watch, tmp_path, monkeypatch):
    service, user, native, _, _ = running_watch
    path = gallery_availability.gallery_path_key(str(tmp_path))
    monkeypatch.setattr(watcher, "mount_inventory", lambda: {path: ["host", "9p"]})
    polling = MagicMock()
    monkeypatch.setattr(watcher, "PollingObserver", polling)

    watch = register(service, user, tmp_path)

    polling.assert_called_once_with(timeout=watcher.MOUNT_POLL_INTERVAL)
    polling.return_value.start.assert_called_once()
    native.assert_not_called()
    assert watch.observer is polling.return_value


def test_mount_inventory_includes_windows_directory_volume(tmp_path, monkeypatch):
    child = tmp_path / "mounted-volume"
    child.mkdir()
    monkeypatch.setattr(gallery_availability.psutil, "disk_partitions", lambda all: [])
    monkeypatch.setattr(os, "listvolumes", lambda: ["volume-guid"], raising=False)
    monkeypatch.setattr(os, "listmounts", lambda volume: [str(child)], raising=False)
    inventory = gallery_availability.mount_inventory()
    assert gallery_availability.gallery_mounts(str(tmp_path), inventory) == {
        gallery_availability.gallery_path_key(str(child)): ["volume-guid", ""],
    }


def test_native_observer_reports_new_photo(tmp_path):
    root = os.path.normcase(str(tmp_path))
    watch = watcher.GalleryWatch(root)
    detected = threading.Event()
    handler = watcher.GalleryEvents(watch)

    def on_created(event):
        if event.src_path.endswith("new.jpg"):
            detected.set()

    handler.on_created = on_created
    observer = watcher.Observer()
    watch.observer = observer
    try:
        observer.schedule(handler, root, recursive=True)
        observer.start()
        (tmp_path / "new.jpg").write_bytes(b"image")
        assert detected.wait(timeout=5)
        assert watch.dirty == {root}
    finally:
        watch.stop_observer()
