"""Private launcher progress channel; no server or WebView is required."""
import json
import os
import time
from pathlib import Path

from app.utils.portable_library import write_json


class UpgradeProgress:
    def __init__(self, root):
        self.root = Path(root)
        self.session = os.getenv('TS_AUTOMATIC_UPGRADE_SESSION')
        self.last_update = 0.0
        self.stage = 'checking'
        self.cancellable = True
        self.stage_started = time.monotonic()

    def checkpoint(self):
        if not self.session or not self.cancellable:
            return
        try:
            value = json.loads((self.root / 'maintenance/automatic-upgrade-cancel.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        if value.get('session') == self.session:
            raise ValueError('TRAILSNAP_UPGRADE_PAUSED: 已安全暂停升级，旧图库仍保留。下次启动会重新复制尚未完成的副本。')

    def report(self, stage=None, completed=0, total=0, *, unit='files', cancellable=True):
        # Check before entering a non-interruptible database/publication phase.
        self.checkpoint()
        changed = stage is not None and (stage != self.stage or cancellable != self.cancellable)
        if changed:
            self.stage_started = time.monotonic()
        self.stage = stage or self.stage
        self.cancellable = cancellable
        if not self.session:
            return
        now = time.monotonic()
        if not changed and (not total or completed != total) and now - self.last_update < .2:
            return
        self.last_update = now
        try:
            write_json(self.root / 'maintenance/automatic-upgrade-progress.json', {
                'session': self.session, 'stage': self.stage, 'completed': completed,
                'total': total, 'unit': unit, 'cancellable': cancellable,
                'elapsedSeconds': round(now - self.stage_started, 2),
            })
        except OSError:
            # Windows readers/scanners may briefly deny atomic replacement.
            # Telemetry must not abort a data transaction; the next report retries.
            pass
