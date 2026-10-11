"""Process-wide, reentrant admission for media IO on each storage volume."""
import os
import threading
from contextlib import contextmanager, ExitStack
from functools import wraps
from inspect import signature


class DiskBudget:
    def __init__(self, limit=1):
        self.limit = limit
        self._condition = threading.Condition()
        self._active = {}
        self._local = threading.local()

    def configure(self, limit):
        with self._condition:
            self.limit = max(1, int(limit))
            self._condition.notify_all()

    @staticmethod
    def volume(path):
        path = os.path.abspath(os.fspath(path or os.curdir))
        if os.name == 'nt':
            return os.path.normcase(os.path.splitdrive(path)[0])
        while True:
            try:
                return os.stat(path).st_dev
            except OSError:
                parent = os.path.dirname(path)
                if parent == path:
                    return path
                path = parent

    @contextmanager
    def slot(self, path):
        volume = self.volume(path)
        held = getattr(self._local, 'held', None)
        if held is None:
            held = self._local.held = set()
        if volume in held:
            yield
            return
        with self._condition:
            self._condition.wait_for(lambda: self._active.get(volume, 0) < self.limit)
            self._active[volume] = self._active.get(volume, 0) + 1
        held.add(volume)
        try:
            yield
        finally:
            held.remove(volume)
            with self._condition:
                self._active[volume] -= 1
                self._condition.notify_all()

    @contextmanager
    def slots(self, *paths):
        # Acquire source/destination volumes in a consistent order so opposite
        # direction copies cannot deadlock. Same-volume jobs use a single slot.
        volumes = {self.volume(path): path for path in paths if path is not None}
        with ExitStack() as stack:
            for volume in sorted(volumes, key=str):
                stack.enter_context(self.slot(volumes[volume]))
            yield


disk_budget = DiskBudget()


def media_io(path_argument='file_path', *other_paths):
    """Admit one complete synchronous media job; nested reads share its slot."""
    def decorate(function):
        parameters = signature(function)
        @wraps(function)
        def wrapped(*args, **kwargs):
            arguments = parameters.bind(*args, **kwargs).arguments
            paths = [arguments.get(name) for name in (path_argument, *other_paths)]
            with disk_budget.slots(*paths):
                return function(*args, **kwargs)
        return wrapped
    return decorate
