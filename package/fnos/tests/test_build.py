import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build
from release_notes import update_notes, START
from resolve_images import resolve_images


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.lock = json.loads((ROOT/'images.lock.json').read_text())

    def test_mixed_or_mutable_versions_are_rejected(self):
        for reference in ['user/server:latest', 'user/server:9.9.9@sha256:'+'a'*64]:
            lock = copy.deepcopy(self.lock)
            lock['images']['server'] = reference
            with self.assertRaises(ValueError): build.validate_lock(lock, '0.19.1')
        with self.assertRaises(ValueError): build.validate_lock(self.lock, '9.9.9')

    def test_new_release_replaces_all_images_and_metadata(self):
        lock = {'version': '2.3.4', 'images': {}}
        for name in ['server','frontend','ai']:
            lock['images'][name] = f'user/trailsnap-{name}:2.3.4'+('-cpu' if name=='ai' else '')+'@sha256:'+'a'*64
        lock['images']['postgres'] = self.lock['images']['postgres']
        with tempfile.TemporaryDirectory() as directory:
            source = build.build_source(Path(directory)/'source', '2.3.4', lock)
            manifest = (source/'manifest').read_text(encoding='utf-8')
            self.assertIn(f'version=2.3.4-{build.REVISION}', manifest)
            self.assertIn('真正属于你', manifest)
            for name in ['compose-template.json','docker-compose.yaml']:
                compose = json.loads((source/'app/docker'/name).read_text(encoding='utf-8'))
                for service, config in compose['services'].items():
                    self.assertEqual(lock['images']['server' if service=='bootstrap' else service], config['image'])
            self.assertNotIn(':0.19.1', (source/'cmd/helper').read_text(encoding='utf-8'))
            self.assertNotIn(':0.19.1', (source/'cmd/upgrade_init').read_text(encoding='utf-8'))

    def test_image_wait_locks_ready_services_and_times_out_missing_ones(self):
        calls = []
        ticks = [0]
        def inspect(reference):
            calls.append(reference)
            if '/trailsnap-ai:' in reference: raise ValueError('not published')
            return reference.split('@')[0]+'@sha256:'+'a'*64
        with self.assertRaisesRegex(TimeoutError, 'ai'):
            resolve_images('2.3.4','user', self.lock['images']['postgres'], 2, interval=1,
                           inspector=inspect, clock=lambda:ticks[0], sleep=lambda n:ticks.__setitem__(0,ticks[0]+n))
        self.assertEqual(1,sum('/trailsnap-server:' in item for item in calls))
        result = resolve_images('2.3.4','user',self.lock['images']['postgres'],0,
                                inspector=lambda ref: ref.split('@')[0]+'@sha256:'+'a'*64)
        self.assertEqual(4,len(result['images']))

    def test_release_notes_are_idempotent_and_preserve_existing_text(self):
        body = '# 更新内容\n\n已有功能与其他安装包链接。'
        first = update_notes(body,'v2.3.4','LC044/TrailSnap')
        self.assertEqual(first,update_notes(first,'v2.3.4','LC044/TrailSnap'))
        self.assertEqual(1,first.count(START))
        self.assertIn(body,first)
        self.assertIn('TrailSnap-2.3.4-fnos-x86.fpk',first)
        with self.assertRaises(ValueError): update_notes(body,'../../bad','LC044/TrailSnap')

    def test_packaged_manifest_handles_crlf_and_rejects_truncated_html(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = build.build_source(directory/'source', self.lock['version'], self.lock)
            app_bytes = io.BytesIO()
            with tarfile.open(fileobj=app_bytes, mode='w:gz') as app:
                for path in (source/'app').rglob('*'):
                    app.add(path, arcname=path.relative_to(source/'app').as_posix(), recursive=False)
            package = directory/'trailsnap.fpk'
            original = (source/'manifest').read_text(encoding='utf-8')
            for truncate in [False, True]:
                manifest = original
                if truncate:
                    manifest = '\n'.join('desc=<div style="display:flex' if line.startswith('desc=') else line for line in manifest.splitlines())
                with tarfile.open(package,'w:gz') as archive:
                    for name in ['ICON.PNG','ICON_256.PNG','wizard/install']:
                        archive.add(source/name,arcname=name)
                    for name, content in [('manifest',manifest.replace('\n','\r\n').encode()),('app.tgz',app_bytes.getvalue())]:
                        info = tarfile.TarInfo(name)
                        info.size = len(content)
                        archive.addfile(info,io.BytesIO(content))
                if truncate:
                    with self.assertRaisesRegex(ValueError,'description'):
                        build.verify_package(package,self.lock['version'],self.lock)
                else:
                    build.verify_package(package,self.lock['version'],self.lock)
