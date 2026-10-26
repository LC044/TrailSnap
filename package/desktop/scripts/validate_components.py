"""Reject desktop payloads assembled from missing or mixed-version runtimes."""
import json
import os
from pathlib import Path


def validate(root: Path):
    desktop = root / 'package/desktop'
    version = json.loads((desktop/'src-tauri/tauri.conf.json').read_text(encoding='utf-8'))['version']
    for name in ('server', 'ai'):
        runtime = desktop/f'{name}-dist'/f'trailsnap-{name}'
        executable = runtime/(f'trailsnap-{name}.exe' if os.name == 'nt' else f'trailsnap-{name}')
        if not executable.is_file():
            raise ValueError(f'Missing bundled {name}: {executable}')
        metadata = json.loads((runtime/'runtime-version.json').read_text(encoding='utf-8'))
        if metadata['version'] != version:
            raise ValueError(f'Desktop {version} does not match {name} {metadata["version"]}')
    return version


if __name__ == '__main__':
    print('Complete desktop payload:', validate(Path(__file__).resolve().parents[3]))
