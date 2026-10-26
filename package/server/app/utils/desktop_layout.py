"""The same immutable program layout for ZIP packages and Windows installers."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from app.utils.portable_library import write_json
from app.utils.windows_paths import filesystem_path, publish_directory


def stage_program(root: Path, program: Path, server: Path, launcher: Path, catalog: Path,
                  version: str, arch: str, webview_runtime: Path | None = None, ai: Path | None = None):
    inputs = [(program / 'trailsnap-desktop.exe', 'trailsnap-desktop.exe'),
              (launcher, 'portable-launcher.exe')]
    if ai is None and catalog is not None:
        inputs.append((catalog, 'ai-extensions.json'))
    if ai is not None:
        if not (ai / 'trailsnap-ai.exe').is_file():
            raise ValueError('安装包缺少完整 AI 程序')
        for component in (server, ai):
            metadata = json.loads((component / 'runtime-version.json').read_text(encoding='utf-8'))
            if metadata['version'] != version:
                raise ValueError('Server、AI 与桌面版本不一致')
        inputs.extend((p, 'ai/' + p.relative_to(ai).as_posix()) for p in sorted(ai.rglob('*')) if p.is_file())
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
        if relative == 'trailsnap-desktop.exe':
            # Tauri patches this three-byte distribution marker while building
            # NSIS, then restores UNK in target/release. It is format metadata,
            # not another program build. Never modify the copied executable
            # itself (which may carry a platform code signature).
            with open(filesystem_path(path), 'rb') as stream:
                contents = stream.read()
            marker = b'__TAURI_BUNDLE_TYPE_VAR_'
            if contents.count(marker) == 1:
                offset = contents.index(marker) + len(marker)
                if contents[offset:offset + 3] in {b'UNK', b'NSS', b'WIX'}:
                    contents = contents[:offset] + b'UNK' + contents[offset + 3:]
            digest.update(contents)
            continue
        with open(filesystem_path(path), 'rb') as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    build = f'{version}-{digest.hexdigest()[:16]}'
    manifest = {'schemaVersion': 1, 'version': version, 'buildId': build,
                'bundledAI': ai is not None, 'platform': f'windows-{arch}', 'minLauncherVersion': 2, 'executable': 'trailsnap-desktop.exe'}
    app = root / 'app'
    app.mkdir(parents=True, exist_ok=True)
    target = app / build
    def intact():
        if not target.is_dir() or target.is_symlink():
            return False
        try:
            if json.loads((target / 'manifest.json').read_text(encoding='utf-8')) != manifest:
                return False
            from app.utils.portable_library import file_hash
            expected = {relative for _, relative in inputs} | {'manifest.json', 'archive.sha256'}
            if any(p.is_file() and p.relative_to(target).as_posix() not in expected for p in target.rglob('*')):
                return False
            return all((target / relative).is_file() and file_hash(path) == file_hash(target / relative)
                       for path, relative in inputs)
        except (OSError, ValueError):
            return False
    if not intact():
        staging = Path(tempfile.mkdtemp(prefix='.install-', dir=app))
        retired = app / ('.repair-' + uuid.uuid4().hex)
        try:
            for path, relative in inputs:
                destination = Path(filesystem_path(staging / relative))
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(filesystem_path(path), destination)
            write_json(staging / 'manifest.json', manifest)
            if target.exists():
                # Program-only directories may be repaired; never traverse links.
                descriptor = root / 'instance.json'
                if descriptor.is_file():
                    data_root = json.loads(descriptor.read_text(encoding='utf-8')).get('dataRoot')
                    if data_root:
                        data = root / data_root['path'] if data_root['kind'] == 'relative' else Path(data_root['path'])
                        if data.resolve().is_relative_to(target.resolve()):
                            raise ValueError('图库位于程序目录内，已停止修复，请先迁移图库')
                if any(p.name == 'library.json' or p.suffix == '.sqlite' for p in target.rglob('*')):
                    raise ValueError('程序目录含图库数据，已停止修复')
                if target.is_symlink() or (hasattr(target, 'is_junction') and target.is_junction()) or any(
                    p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in target.rglob('*')):
                    raise ValueError('已有程序目录含链接，已停止修复')
                target.rename(retired)
            try:
                publish_directory(staging, target)
            except BaseException:
                if retired.exists() and not target.exists():
                    retired.rename(target)
                raise
            if retired.exists():
                shutil.rmtree(filesystem_path(retired))
        finally:
            if staging.exists():
                shutil.rmtree(filesystem_path(staging))
    shutil.copy2(launcher, root / 'TrailSnap.exe')
    # Distribution descriptor only. Never overwrite instance.json or userdata.
    write_json(root / 'portable.json', {'schemaVersion': 1, 'activeBuild': build})
    return build


def finalize_install(root: Path, version: str):
    import platform
    root = root.resolve(strict=True)
    return stage_program(root, root, root / 'server', root / 'portable-launcher.exe',
                         None, version,
                         'aarch64' if platform.machine().lower() in {'arm64', 'aarch64'} else 'x86_64', ai=root / 'ai')
