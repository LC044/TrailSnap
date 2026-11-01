import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('fnos_build', ROOT / 'build.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        cls.source_temp = tempfile.TemporaryDirectory()
        cls.source = Path(cls.source_temp.name)/'source'
        lock = json.loads((ROOT/'images.lock.json').read_text())
        builder.build_source(cls.source, lock['version'], lock)

    @classmethod
    def tearDownClass(cls):
        cls.source_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location('fnos_runtime', self.source / 'app/runtime.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module.META = self.root / 'meta'
        self.module.STATE = self.root / 'state'
        self.module.STATE.mkdir()
        self.module.CANDIDATE = self.root / 'candidate'
        self.module.CANDIDATE.mkdir()
        self.module.PACKAGE = self.root / 'package'
        shutil.copytree(self.source / 'app', self.module.PACKAGE)
        self.environment = patch.dict(os.environ, {'TS_UID': '1000', 'TS_GID': '1001',
            'TS_DATA_HOST': '/vol2/test/state', 'TS_PHOTO_HOST': '/vol2/test/photos', 'TS_PORT': '3333',
            'TS_NEW_PORT': '', 'TS_ADD_PHOTO': ''})
        self.environment.start()
        self.chown = patch.object(self.module.os, 'chown', lambda *args: None, create=True)
        self.chown.start()
    def tearDown(self):
        self.chown.stop()
        self.environment.stop()
        self.temp.cleanup()
    def read_compose(self):
        return json.loads((self.module.PACKAGE / 'docker/docker-compose.yaml').read_text(encoding='utf-8'))
    def test_selected_port_and_data_persist_and_secrets_do_not_rotate(self):
        self.module.initialize()
        password = (self.module.STATE / 'runtime/postgres.env').read_bytes()
        self.module.initialize()
        self.assertEqual(password, (self.module.STATE / 'runtime/postgres.env').read_bytes())
        compose = self.read_compose()
        self.assertEqual(['3333:80'], compose['services']['frontend']['ports'])
        upload = next(v for v in compose['services']['server']['volumes'] if isinstance(v,dict) and v['target']=='/app/data')
        self.assertEqual('/vol2/test/state/data', upload['source'])
    def test_extra_gallery_keeps_primary_mount_and_port(self):
        self.module.initialize()
        with patch.dict(os.environ, {'TS_NEW_PORT': '3434', 'TS_ADD_PHOTO': '/vol2/travel/another'}):
            self.module.configure()
        compose = self.read_compose()
        self.assertEqual(['3333:80'], compose['services']['frontend']['ports'])
        mounts = [v for v in compose['services']['server']['volumes'] if isinstance(v,dict)]
        self.assertTrue(next(v for v in mounts if v['target']=='/app/Photos/已有照片')['read_only'])
        self.assertTrue(next(v for v in mounts if v['target']==self.module.library_target('/vol2/travel/another'))['read_only'])
        self.assertEqual('${wizard_port}', json.loads((self.module.PACKAGE/'ui/config').read_text(encoding='utf-8'))['.url']['trailsnap.Application']['port'])
    def test_duplicate_gallery_failure_preserves_previous_configuration(self):
        self.module.initialize()
        before = (self.module.META/'installation.json').read_bytes()
        with patch.dict(os.environ, {'TS_ADD_PHOTO': '/vol2/test/photos/child'}):
            with self.assertRaises(RuntimeError): self.module.configure()
        self.assertEqual(before, (self.module.META/'installation.json').read_bytes())
    def test_repeated_saved_fields_are_idempotent(self):
        self.module.initialize()
        with patch.dict(os.environ, {'TS_NEW_PORT': '3434', 'TS_ADD_PHOTO': '/vol2/travel/another'}):
            self.module.configure()
            self.module.configure()
        record = json.loads((self.module.META/'installation.json').read_text())
        self.assertEqual(['/vol2/travel/another'], record['extra_dirs'])
        self.assertEqual(3333, record['port'])
    def test_foreign_data_directory_is_rejected_without_overwrite(self):
        photo = self.module.STATE / 'keep-my-file.txt'
        photo.write_text('unchanged')
        with self.assertRaises(RuntimeError): self.module.initialize()
        self.assertEqual('unchanged', photo.read_text())
        self.assertFalse((self.module.STATE/'runtime/postgres.env').exists())
    def test_invalid_port_system_path_and_overlapping_data_are_rejected(self):
        for value in ['0', '1023', '65536', 'abc', '3180:80']:
            with self.assertRaises(RuntimeError): self.module.port(value)
        with self.assertRaises(RuntimeError): self.module.host_path('/etc')
        with patch.dict(os.environ, {'TS_PHOTO_HOST':'/vol2/test/state/photos'}):
            with self.assertRaises(RuntimeError): self.module.initialize()

    def test_required_data_cannot_use_application_managed_directory(self):
        for value in ['', '/vol1/@appshare/trailsnap/data', '/vol2/@appdata/trailsnap']:
            with patch.dict(os.environ, {'TS_DATA_HOST': value}):
                with self.assertRaises(RuntimeError): self.module.initialize()

    def test_same_named_libraries_have_distinct_stable_readonly_targets(self):
        self.module.initialize()
        for path in ['/vol1/1000/Photos', '/vol2/1000/Photos']:
            with patch.dict(os.environ, {'TS_ADD_PHOTO': path}): self.module.configure()
        compose = self.read_compose()
        for service in ['server', 'ai']:
            targets = [v['target'] for v in compose['services'][service]['volumes']
                       if isinstance(v, dict) and v['target'].startswith('/app/Photos/')]
            self.assertEqual(3, len(set(targets)))
            self.assertEqual(2, sum(t.startswith('/app/Photos/Photos-') for t in targets))
        before = (self.module.PACKAGE/'docker/docker-compose.yaml').read_bytes()
        self.module.configure()
        self.assertEqual(before, (self.module.PACKAGE/'docker/docker-compose.yaml').read_bytes())

    def test_legacy_layout_is_not_silently_migrated(self):
        self.module.initialize()
        marker = self.module.STATE/'runtime/installation.json'
        record = json.loads(marker.read_text())
        record.pop('layout')
        marker.write_text(json.dumps(record))
        before = (self.module.PACKAGE/'docker/docker-compose.yaml').read_bytes()
        with self.assertRaises(RuntimeError): self.module.initialize()
        self.assertEqual(before, (self.module.PACKAGE/'docker/docker-compose.yaml').read_bytes())

if __name__ == '__main__':
    unittest.main()
