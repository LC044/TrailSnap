"""Build the fnOS x86 package from checked-in sources and immutable images."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
REVISION = 8  # Increment for fnOS-only revisions without a product version change.
VERSION_PATTERN = r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?"


def product_version() -> str:
    return tomllib.loads((REPO / 'package/server/pyproject.toml').read_text(encoding='utf-8'))['project']['version']


def asset_name(version: str) -> str:
    if not re.fullmatch(VERSION_PATTERN, version):
        raise ValueError(f'Invalid product version: {version}')
    return f'TrailSnap-{version}-fnos-x86.fpk'


def validate_lock(lock: dict, version: str) -> dict[str, str]:
    asset_name(version)
    if lock.get('version') != version:
        raise ValueError('Image lock and package product versions differ')
    images = lock.get('images', {})
    if set(images) != {'server', 'frontend', 'ai', 'postgres'}:
        raise ValueError('Exactly four locked service images are required')
    for service, image in images.items():
        if not isinstance(image, str) or not re.fullmatch(r'[a-zA-Z0-9._:/-]+@sha256:[a-f0-9]{64}', image):
            raise ValueError(f'{service} must use an immutable sha256 image reference')
        if service != 'postgres':
            expected = version + ('-cpu' if service == 'ai' else '')
            if image.split('@')[0].rsplit(':', 1)[-1] != expected:
                raise ValueError(f'{service} image is not the requested product version')
    return images


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + '\n', encoding='utf-8', newline='\n')


def build_source(output: Path, version: str, lock: dict) -> Path:
    images = validate_lock(lock, version)
    if output.exists() and any(output.iterdir()):
        raise ValueError(f'Output directory must be empty: {output}')
    shutil.copytree(ROOT / 'template', output, dirs_exist_ok=True)
    description = (ROOT / 'description.html').read_text(encoding='utf-8').strip()
    if any(char in description for char in ('`', '\n', '\r')):
        raise ValueError('Description must be single-line HTML without backticks')
    manifest = (output / 'manifest').read_text(encoding='utf-8')
    manifest = re.sub(r'^version=.*$', f'version={version}-{REVISION}', manifest, flags=re.M)
    manifest = re.sub(r'^desc=.*$', lambda _: f'desc=`{description}`', manifest, flags=re.M)
    write(output / 'manifest', manifest)
    compose = json.loads((output / 'app/docker/compose-template.json').read_text(encoding='utf-8'))
    for name, service in compose['services'].items():
        service['image'] = images['server' if name == 'bootstrap' else name]
    for name in ['compose-template.json', 'docker-compose.yaml']:
        write(output / 'app/docker' / name, json.dumps(compose, ensure_ascii=False, indent=2))
    for name in ['runtime.py', 'backup.py']:
        write(output / 'app' / name, (ROOT / 'src' / name).read_text(encoding='utf-8').replace('@@APP@@', 'trailsnap'))
    for source, destination in [('hooks.sh', 'helper'), ('upgrade.sh', 'upgrade_init')]:
        content = (ROOT / 'src' / source).read_text(encoding='utf-8')
        write(output / 'cmd' / destination, content.replace('@@APP@@', 'trailsnap').replace('@@IMAGE@@', images['server']))
    for path in (output / 'cmd').iterdir():
        path.chmod(0o755)
    return output


def verify_package(package: Path, version: str, lock: dict) -> None:
    images = validate_lock(lock, version)
    with tarfile.open(package) as archive:
        manifest = archive.extractfile('manifest').read().decode('utf-8')
        fields = dict(re.findall(r'^(\w+)\s*=\s*(.*)$', '\n'.join(manifest.splitlines()), re.M))
        if fields.get('version') != f'{version}-{REVISION}' or fields.get('appname') != 'trailsnap':
            raise ValueError('Wrong packaged application/version')
        description = fields.get('desc', '').strip('`')
        if description != (ROOT / 'description.html').read_text(encoding='utf-8').strip():
            raise ValueError('fnpack truncated or changed the application description')
        wizard = json.load(archive.extractfile('wizard/install'))
        hints = [item.get('helpText') for item in wizard[0]['items'] if item['type'] == 'tips']
        if hints != ['填写本地照片文件夹的完整路径，留空可稍后添加。', '选择一个空白文件夹用于保存用户数据']:
            raise ValueError('Installation wording changed')
        for name, size in [('ICON.PNG', 64), ('ICON_256.PNG', 256)]:
            data = archive.extractfile(name).read()
            if data[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', data[16:24]) != (size, size):
                raise ValueError(f'Invalid {name}')
        with tarfile.open(fileobj=io.BytesIO(archive.extractfile('app.tgz').read())) as app:
            compose = json.load(app.extractfile('docker/compose-template.json'))
            for name, service in compose['services'].items():
                if service['image'] != images['server' if name == 'bootstrap' else name]:
                    raise ValueError(f'Wrong packaged image for {name}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=product_version())
    parser.add_argument('--images-lock', type=Path, default=ROOT / 'images.lock.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--fnpack', default='fnpack')
    parser.add_argument('--source-only', action='store_true')
    args = parser.parse_args()
    lock = json.loads(args.images_lock.read_text(encoding='utf-8'))
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='trailsnap-fnos-') as temporary:
        work = Path(temporary)
        source = build_source(work / 'source', args.version, lock)
        if args.source_only:
            with tarfile.open(args.output / 'trailsnap-fnos-source.tar.gz', 'w:gz') as archive:
                for path in sorted(source.rglob('*')):
                    archive.add(path, arcname=path.relative_to(source).as_posix(), recursive=False)
            return
        subprocess.run([args.fnpack, 'build', '--directory', str(source)], cwd=work, check=True)
        built = work / 'trailsnap.fpk'
        verify_package(built, args.version, lock)
        target = args.output / asset_name(args.version)
        shutil.copy2(built, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    write(target.with_suffix('.fpk.sha256'), f'{digest}  {target.name}')
    write(target.with_suffix('.images.json'), json.dumps(lock, ensure_ascii=False, indent=2))
    print(target)


if __name__ == '__main__':
    main()
