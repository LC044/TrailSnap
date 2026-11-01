"""Wait for versioned release images and write a lock for the fnOS builder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from build import ROOT, asset_name, validate_lock


def inspect_image(image: str) -> str:
    result = subprocess.run(['docker', 'buildx', 'imagetools', 'inspect', image,
                             '--format', '{{.Manifest.Digest}}'],
                            check=True, capture_output=True, text=True, timeout=45)
    digest = result.stdout.strip()
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError(f'Invalid image digest for {image}')
    pinned = image.split('@')[0] + '@' + digest
    raw = subprocess.run(['docker', 'buildx', 'imagetools', 'inspect', pinned, '--raw'],
                         check=True, capture_output=True, text=True, timeout=45)
    manifest = json.loads(raw.stdout)
    if not any(item.get('platform', {}).get('os') == 'linux' and
               item.get('platform', {}).get('architecture') == 'amd64'
               for item in manifest.get('manifests', [])):
        raise ValueError(f'{image} has no linux/amd64 image in its manifest list')
    return pinned


def resolve_images(version: str, namespace: str, postgres: str, timeout: float,
                   interval: float = 20, inspector=inspect_image, clock=time.monotonic,
                   sleep=time.sleep) -> dict:
    asset_name(version)
    if not re.fullmatch(r'[a-zA-Z0-9._/-]+(?::[0-9]+)?(?:/[a-zA-Z0-9._/-]+)?', namespace):
        raise ValueError('Invalid image namespace')
    pending = {'server': f'{namespace}/trailsnap-server:{version}',
               'frontend': f'{namespace}/trailsnap-frontend:{version}',
               'ai': f'{namespace}/trailsnap-ai:{version}-cpu', 'postgres': postgres}
    resolved = {}
    deadline = clock() + timeout
    while pending:
        for name, reference in list(pending.items()):
            try:
                resolved[name] = inspector(reference)
                del pending[name]
                print(f'{name}: image ready', flush=True)
            except (ValueError, subprocess.SubprocessError):
                pass
        if pending:
            if clock() >= deadline:
                raise TimeoutError('Required release images not ready: ' + ', '.join(sorted(pending)))
            print('Waiting for: ' + ', '.join(sorted(pending)), flush=True)
            sleep(min(interval, max(0, deadline - clock())))
    lock = {'version': version, 'images': resolved}
    validate_lock(lock, version)
    return lock


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--namespace', default='siyuan044')
    parser.add_argument('--postgres', default=json.loads((ROOT/'images.lock.json').read_text())['images']['postgres'])
    parser.add_argument('--timeout', type=int, default=2400)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    lock = resolve_images(args.version, args.namespace, args.postgres, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(lock, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
