"""Coalesce external gallery changes into the regular scan pipeline."""
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingObserver

from app.core.system_config import system_config
from app.db.models.photo import Photo
from app.db.models.user import User
from app.db.session import SessionLocal
from app.service.gallery_availability import (
    directory_identity, gallery_mounts, gallery_path_key, gallery_state_path,
    load_gallery_state, mount_inventory, save_gallery_state, unavailable_mounts,
)
from app.service.gallery_sync import contains, contains_key, external_roots
from app.service.task_manager import TaskManager
from app.utils.image_loading import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

logger = logging.getLogger(__name__)

WATCH_INTERVAL = 2
REFRESH_INTERVAL = 10
DEBOUNCE = 3
MAX_DEBOUNCE = 30
POLL_INTERVAL = 60
MOUNT_POLL_INTERVAL = 30
NATIVE_BACKSTOP_INTERVAL = 900
MAX_DIRTY_FOLDERS = 64
MEDIA_EXTENSIONS = set(IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)
POLLING_FILESYSTEMS = {"9p", "cifs", "drvfs", "fuse.sshfs", "nfs", "nfs4", "smb3", "smbfs", "virtiofs"}


def needs_polling(root, mounts):
    return any(filesystem.lower() in POLLING_FILESYSTEMS for _, filesystem in gallery_mounts(root, mounts).values())


class GalleryEvents(FileSystemEventHandler):
    def __init__(self, watch):
        self.watch = watch

    def on_any_event(self, event):
        if event.event_type not in {"created", "deleted", "moved", "modified", "closed"}:
            return
        if event.is_directory and event.event_type in {"modified", "closed"}:
            return
        for path in (event.src_path, event.dest_path):
            if path and (event.is_directory or os.path.splitext(path)[1].lower() in MEDIA_EXTENSIONS):
                self.watch.mark(os.path.dirname(path))


@dataclass
class GalleryWatch:
    root: str
    polling: bool = False
    observer: BaseObserver | None = None
    identity: tuple[int, int] | None = None
    state: dict | None = None
    offline_mounts: set[str] = field(default_factory=set)
    verify_at: float = 0
    online: bool | None = None
    retry_at: float = 0
    poll_at: float = 0
    dirty: set[str] = field(default_factory=set)
    first_event: float = 0
    last_event: float = 0
    generation: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def mark(self, folder):
        folder = os.path.abspath(folder)
        root_key = os.path.normcase(self.root)
        folder_key = os.path.normcase(folder)
        if folder_key == root_key or not contains_key(root_key, folder_key):
            folder = self.root
        now = time.monotonic()
        with self.lock:
            if not self.dirty:
                self.first_event = now
            if folder == self.root or len(self.dirty) >= MAX_DIRTY_FOLDERS:
                self.dirty = {self.root}
            elif self.root not in self.dirty:
                self.dirty.add(folder)
            self.last_event = now
            self.generation += 1

    def ready(self, now):
        with self.lock:
            if not self.online or not self.dirty:
                return None
            if now - self.last_event < DEBOUNCE and now - self.first_event < MAX_DEBOUNCE:
                return None
            return self.generation, set(self.dirty)

    def acknowledge(self, generation):
        with self.lock:
            if generation == self.generation:
                self.dirty.clear()

    def stop_observer(self):
        observer, self.observer = self.observer, None
        if observer is not None:
            observer.stop()
            if observer.is_alive():
                observer.join(timeout=1)

    def refresh(self, now, mounts, state_path, indexed_paths):
        try:
            identity = directory_identity(self.root)
            current_mounts = gallery_mounts(self.root, mounts)
            previous = self.state if self.state is not None else load_gallery_state(state_path)
            root_key = gallery_path_key(self.root)
            expected = previous["mounts"] if previous is not None else {}
            offline_mounts = unavailable_mounts(self.root, expected, mounts)
            if root_key in offline_mounts:
                raise OSError("registered filesystem is no longer mounted")
            if previous is None:
                # An upgrade can first see the empty or nonempty directory
                # beneath a disconnected mount. Preserve every unseen record
                # until its file has actually been observed online.
                unverified = sorted({gallery_path_key(path) for path in indexed_paths() if not os.path.isfile(path)})
            else:
                unverified = previous["unverified"]
                changed = previous["identity"] != list(identity)
                if unverified and (changed or now >= self.verify_at):
                    unverified = [path for path in unverified if not os.path.isfile(path)]
                    self.verify_at = now + POLL_INTERVAL
                if changed:
                    # A saved mount source with the same root inode can
                    # reconnect on a different device number. A legacy
                    # placeholder can be replaced once indexed files reappear.
                    old_parent = max((path for path in expected if contains_key(path, root_key)), key=len, default=None)
                    new_parent = max((path for path in current_mounts if contains_key(path, root_key)), key=len, default=None)
                    reconnected = old_parent and old_parent == new_parent and previous["identity"][1] == identity[1]
                    if not reconnected and unverified == previous["unverified"]:
                        raise OSError("registered directory identity changed")
                if unverified != previous["unverified"]:
                    self.mark(self.root)
                new_children = {
                    path for path in current_mounts.keys() - expected
                    if path != root_key and contains_key(root_key, path)
                }
                if new_children:
                    unverified = set(unverified)
                    for path in indexed_paths():
                        key = gallery_path_key(path)
                        if any(contains_key(child, key) for child in new_children) and not os.path.isfile(path):
                            unverified.add(key)
                    unverified = sorted(unverified)
                    self.mark(self.root)

            state = {
                "identity": list(identity),
                "mounts": {**current_mounts, **expected},
                "unverified": unverified,
            }
            if state != previous:
                save_gallery_state(state_path, state)
            if self.state is None and unverified:
                logger.warning("External gallery has unverified paths, preserving their index: %s", self.root)
            if self.offline_mounts != offline_mounts:
                for path in sorted(offline_mounts - self.offline_mounts):
                    logger.warning("External gallery submount offline, preserving its index: %s", path)
                self.mark(self.root)
                self.offline_mounts = offline_mounts
            self.state = state
        except OSError as error:
            if self.online is not False:
                logger.warning("External gallery offline, preserving its index: %s (%s)", self.root, error)
                self.stop_observer()
            self.online = False
            return

        if self.identity is not None and identity != self.identity:
            self.stop_observer()
            self.mark(self.root)
        if self.online is False:
            logger.info("External gallery recovered: %s", self.root)
            self.mark(self.root)
            self.retry_at = 0
        self.online, self.identity = True, identity

        if self.observer is not None and (
            not self.observer.is_alive() or not all(emitter.is_alive() for emitter in self.observer.emitters)
        ):
            logger.warning("External gallery observer stopped: %s", self.root)
            self.stop_observer()
            self.mark(self.root)

        if self.observer is None and now >= self.retry_at:
            self.retry_at = now + POLL_INTERVAL
            try:
                observer = PollingObserver(timeout=MOUNT_POLL_INTERVAL) if self.polling else Observer()
                self.observer = observer
                observer.schedule(GalleryEvents(self), self.root, recursive=True)
                observer.start()
                if self.polling:
                    logger.info("Polling mounted external gallery for changes: %s", self.root)
            except Exception:
                logger.warning("Native gallery events unavailable for %s; polling", self.root, exc_info=True)
                self.stop_observer()
                self.poll_at = min(self.poll_at or now + POLL_INTERVAL, now + POLL_INTERVAL)

        if not self.poll_at:
            self.poll_at = now + NATIVE_BACKSTOP_INTERVAL
        if now >= self.poll_at:
            # Incremental reconciliation also catches mounts that silently
            # omit native events (for example remote edits on a network share).
            self.mark(self.root)
            self.poll_at = now + (NATIVE_BACKSTOP_INTERVAL if self.observer else POLL_INTERVAL)


class ExternalGalleryWatcher:
    def __init__(self):
        self.watches: dict[tuple[str, str], GalleryWatch] = {}
        self.refresh_at = 0
        self.closed = False
        self.lock = threading.Lock()

    def close(self):
        with self.lock:
            self.closed = True
            self._clear()

    def _clear(self):
        for watch in self.watches.values():
            watch.stop_observer()
        self.watches.clear()
        self.refresh_at = 0

    def tick(self):
        with self.lock:
            if self.closed:
                return
            if not system_config.config.watch_external_galleries:
                self._clear()
                return
            now = time.monotonic()
            if now >= self.refresh_at:
                self._refresh(now)
                self.refresh_at = now + REFRESH_INTERVAL
            self._flush(now)

    def _refresh(self, now):
        with SessionLocal() as db:
            registered = {
                (str(user.id), os.path.normcase(os.path.abspath(root))): os.path.abspath(root)
                for user in db.query(User).all()
                for root in external_roots(user)
            }
        for key in self.watches.keys() - registered:
            self.watches.pop(key).stop_observer()
        if not registered:
            return
        mounts = mount_inventory()
        for key in sorted(registered):
            root = registered[key]
            if key not in self.watches:
                self.watches[key] = GalleryWatch(root, polling=needs_polling(key[1], mounts))
            try:
                self.watches[key].refresh(
                    now, mounts, gallery_state_path(key[0], root), lambda: self._indexed_paths(key[0], root),
                )
            except Exception:
                logger.exception("Could not refresh external gallery watcher: %s", key[1])

    @staticmethod
    def _indexed_paths(user_id, root):
        with SessionLocal() as db:
            paths = db.query(Photo.file_path).filter(Photo.owner_id == user_id).yield_per(256)
            return [path for (path,) in paths if contains(root, path)]

    def _flush(self, now):
        ready = defaultdict(list)
        for (user_id, _), watch in self.watches.items():
            batch = watch.ready(now)
            if batch is not None:
                ready[user_id].append((watch, *batch))
        for user_id, batches in ready.items():
            scopes = {}
            guards = {}
            for watch, _, folders in batches:
                try:
                    if directory_identity(watch.root) != watch.identity:
                        continue
                except OSError:
                    continue
                for folder in folders:
                    # A directory can vanish before the debounce window ends.
                    # Scan its surviving parent to reconcile the removed tree.
                    while os.path.normcase(folder) != os.path.normcase(watch.root) and not os.path.isdir(folder):
                        folder = os.path.dirname(folder)
                    scopes[folder] = {"root": watch.root, "identity": list(watch.identity)}
                guards[watch.root] = {
                    "mounts": watch.state["mounts"], "unverified": watch.state["unverified"],
                }
            if not scopes:
                continue
            with SessionLocal() as db:
                queued = TaskManager.get_instance().try_enqueue_gallery_scan(db, {
                    "user_id": user_id, "scan_roots": sorted(scopes), "watch_scopes": scopes, "watch_guards": guards,
                })
            if not queued:
                return
            roots_queued = {scope["root"] for scope in scopes.values()}
            for watch, generation, _ in batches:
                if watch.root in roots_queued:
                    watch.acknowledge(generation)
