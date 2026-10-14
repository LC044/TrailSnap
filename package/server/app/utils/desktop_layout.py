"""The same immutable program layout for ZIP packages and Windows installers."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from app.utils.portable_library import write_json
from app.utils.windows_paths import filesystem_path, publish_directory


def stage_program(root: Path, program: Path, server: Path, launcher: Path, catalog: Path,
                  version: str, arch: str, webview_runtime: Path | None = None):
    inputs = [(program / 'trailsnap-desktop.exe', 'trailsnap-desktop.exe'),
              (launcher, 'portable-launcher.exe'), (catalog, 'ai-extensions.json')]
    inputs.extend((p, 'server/' + p.relative_to(server).as_posix()) for p in sorted(server.rglob('*')) if p.is_file())
    # Tauri links the shell statically. Cargo's sibling cdylib is a build
    # artifact, not a runtime dependency, and is absent from NSIS resources.
    if webview_runtime:
        if not (webview_runtime / 'msedgewebview2.exe').is_file():
            raise ValueError('Fixed Version WebView2 runtime is incomplete')
        inputs.extend((p, 'webview-runtime/' + p.relative_to(webview_runtime).as_posix()) for p in sorted(webview_runtime.rglob('*')) if p.is_file())
    if not (server / 'trailsnap-server.exe').is_file():
        raise ValueError('安装包缺少完整后端')
    digest = hashlib.sha256()
    for path, relative in inputs:
        digest.update(relative.encode('utf-8'))
        with open(filesystem_path(path), 'rb') as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    build = f'{version}-{digest.hexdigest()[:16]}'
    manifest = {'schemaVersion': 1, 'version': version, 'buildId': build,
                'platform': f'windows-{arch}', 'minLauncherVersion': 1, 'executable': 'trailsnap-desktop.exe'}
    app = root / 'app'
    app.mkdir(parents=True, exist_ok=True)
    target = app / build
    if not target.exists():
        staging = Path(tempfile.mkdtemp(prefix='.install-', dir=app))
        try:
            for path, relative in inputs:
                destination = Path(filesystem_path(staging / relative))
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(filesystem_path(path), destination)
            write_json(staging / 'manifest.json', manifest)
            publish_directory(staging, target)
        finally:
            if staging.exists():
                shutil.rmtree(filesystem_path(staging))
    elif json.loads((target / 'manifest.json').read_text(encoding='utf-8')) != manifest:
        raise ValueError('已有程序版本目录不完整，请重新安装到空文件夹')
    shutil.copy2(launcher, root / 'TrailSnap.exe')
    # Distribution descriptor only. Never overwrite instance.json or userdata.
    write_json(root / 'portable.json', {'schemaVersion': 1, 'activeBuild': build})
    return build


def finalize_install(root: Path, version: str):
    import platform
    root = root.resolve(strict=True)
    return stage_program(root, root, root / 'server', root / 'portable-launcher.exe',
                         root / 'ai-extensions.json', version,
                         'aarch64' if platform.machine().lower() in {'arm64', 'aarch64'} else 'x86_64')
