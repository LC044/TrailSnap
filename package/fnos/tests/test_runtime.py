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
        self.module.WIZARD = self.root / 'wizard/config'
        self.module.WIZARD.parent.mkdir()
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
        self.assertTrue(next(v for v in mounts if v['target']=='/app/Photos/photos')['read_only'])
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

    def test_shared_defaults_initialize_and_persist(self):
        with patch.dict(os.environ, {'TS_DATA_HOST': '/vol2/@appshare/trailsnap/data',
                                     'TS_PHOTO_HOST': '/vol2/@appshare/trailsnap/photos'}):
            self.module.initialize()
            password = (self.module.STATE / 'runtime/postgres.env').read_bytes()
            self.module.initialize()
        compose = self.read_compose()
        self.assertEqual('/vol2/@appshare/trailsnap/data', compose['services']['bootstrap']['environment']['TS_DATA_HOST'])
        self.assertEqual(password, (self.module.STATE / 'runtime/postgres.env').read_bytes())
        mounts = compose['services']['server']['volumes']
        self.assertTrue(any(v.get('source') == '/vol2/@appshare/trailsnap/photos' for v in mounts if isinstance(v, dict)))
        self.assertNotIn('${wizard_data_dir', json.dumps(compose))

    def test_other_application_managed_directories_are_rejected(self):
        for value in ['', '/vol1/@appshare/other/data', '/vol2/@appdata/trailsnap',
                      '/vol2/@appshare/trailsnap', '/vol2/@appshare/trailsnap/data/child',
                      '/vol2/@appshare/trailsnap/database']:
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
            self.assertIn('/app/Photos/Photos', targets)
            self.assertIn('/app/Photos/Photos (2)', targets)
        before = (self.module.PACKAGE/'docker/docker-compose.yaml').read_bytes()
        self.module.configure()
        self.assertEqual(before, (self.module.PACKAGE/'docker/docker-compose.yaml').read_bytes())

    def batch(self, paths, mode='ro', **modes):
        for index in range(len(paths)):
            (self.module.CANDIDATE / str(index)).mkdir(exist_ok=True)
        return patch.dict(os.environ, {'TS_ADD_PHOTOS': ';'.join(paths), 'TS_ADD_MODE': mode, **modes})

    def test_primary_name_and_permissions_are_user_selected(self):
        with patch.dict(os.environ, {'TS_PHOTO_HOST': '/vol1/1000/家庭', 'TS_PHOTO_MODE': 'rw'}):
            self.module.initialize()
        for service in ['server', 'ai']:
            mount = next(v for v in self.read_compose()['services'][service]['volumes']
                         if isinstance(v, dict) and v['target'] == '/app/Photos/家庭')
            self.assertEqual(service == 'ai', mount['read_only'])

    def test_batch_add_and_wizard_list_preserve_existing_permissions(self):
        self.module.initialize()
        paths = ['/vol1/1000/Photos', '/vol2/1000/Photos', '/vol3/1000/Photos (2)', '/vol4/1000/Photos']
        with self.batch(paths, 'rw'):
            self.module.configure()
            before = self.record()['libraries']
            self.module.configure()
            self.assertEqual(before, self.record()['libraries'])
        record = json.loads((self.module.META/'installation.json').read_text(encoding='utf-8'))
        self.assertEqual(['/app/Photos/photos', '/app/Photos/Photos', '/app/Photos/Photos (2)',
                          '/app/Photos/Photos (2) (2)', '/app/Photos/Photos (3)'],
                         [e['target'] for e in record['libraries']])
        wizard = self.module.WIZARD.read_text(encoding='utf-8')
        for entry in record['libraries']:
            self.assertIn(entry['source'], wizard)
        with self.batch([], wizard_library_mode_0='rw', wizard_library_mode_1='ro'):
            self.module.configure()
        mounts = [v for v in self.read_compose()['services']['server']['volumes']
                  if isinstance(v, dict) and v['target'].startswith('/app/Photos/')]
        self.assertEqual([False, True, False, False, False], [v['read_only'] for v in mounts])

    def test_batch_error_is_atomic_and_keeps_wizard(self):
        self.module.initialize()
        before = {p: p.read_bytes() for p in [self.module.META/'installation.json', self.module.WIZARD,
                                             self.module.PACKAGE/'docker/docker-compose.yaml']}
        for paths in [['/vol1/1000/new', '/vol2/test/state/child'],
                      ['/vol1/1000/new', '/vol1/1000/new/child']]:
            with self.batch(paths, 'rw', wizard_library_mode_0='rw'):
                with self.assertRaises(RuntimeError): self.module.configure()
            for path, content in before.items(): self.assertEqual(content, path.read_bytes())
        with self.batch(['/vol1/1000/new'], 'invalid'):
            with self.assertRaises(RuntimeError): self.module.configure()

    def test_upgrade_retains_old_hash_targets_and_primary_and_access(self):
        self.module.initialize()
        record = json.loads((self.module.META/'installation.json').read_text(encoding='utf-8'))
        record.pop('libraries')
        record['extra_dirs'] = ['/vol1/1000/Photos']
        self.module.atomic(self.module.STATE/'runtime/installation.json', record)
        self.module.initialize()
        expected = ['/app/Photos/已有照片', '/app/Photos/Photos-' + self.module.hashlib.sha256(b'/vol1/1000/Photos').hexdigest()[:12]]
        with self.batch(['/vol2/1000/Photos'], 'rw'):
            self.module.configure()
        entries = json.loads((self.module.META/'installation.json').read_text(encoding='utf-8'))['libraries']
        self.assertEqual(expected + ['/app/Photos/Photos'], [v['target'] for v in entries])
        self.assertEqual([True, True, False], [v['read_only'] for v in entries])

    def native(self, paths):
        env = {'TS_NATIVE_COUNT': str(len(paths))}
        for index, (path, mode) in enumerate(paths):
            (self.module.CANDIDATE / f'native-{index}').mkdir(exist_ok=True)
            env[f'TS_NATIVE_PATH_{index}'] = path
            env[f'TS_NATIVE_MODE_{index}'] = mode
        return patch.dict(os.environ, env)

    def record(self):
        return json.loads((self.module.META/'installation.json').read_text(encoding='utf-8'))

    def test_native_authorization_add_change_remove_and_empty_snapshot(self):
        self.module.initialize()
        path = '/vol1/1000/旅行'
        with self.native([(path, 'rw')]): self.module.configure()
        self.assertEqual(False, self.record()['libraries'][-1]['read_only'])
        self.assertTrue(self.record()['libraries'][-1]['native'])
        self.assertNotIn('wizard_add_photo_dirs', self.module.WIZARD.read_text(encoding='utf-8'))
        with self.native([(path, 'ro')]): self.module.configure()
        self.assertTrue(self.record()['libraries'][-1]['read_only'])
        self.module.configure()  # No snapshot: preserve native entries.
        self.assertEqual(2, len(self.record()['libraries']))
        with self.native([]): self.module.configure()
        self.assertEqual(1, len(self.record()['libraries']))
        for service in ['server', 'ai']:
            self.assertNotIn(path, json.dumps(self.read_compose()['services'][service]['volumes'], ensure_ascii=False))

    def test_legacy_primary_removal_survives_restart_and_readd_is_stable(self):
        self.module.initialize()
        primary = '/vol2/test/photos'
        with patch.dict(os.environ, {self.module.action_field(primary): 'remove'}): self.module.configure()
        self.assertEqual([], self.record()['libraries'])
        self.module.initialize()
        self.assertEqual([], self.record()['libraries'])
        with self.native([('/vol1/new/photos', 'rw')]): self.module.configure()
        self.assertEqual('/app/Photos/photos (2)', self.record()['libraries'][0]['target'])
        with self.native([(primary, 'ro'), ('/vol1/new/photos', 'rw')]): self.module.configure()
        entry = next(e for e in self.record()['libraries'] if e['source'] == primary)
        self.assertEqual('/app/Photos/photos', entry['target'])

    def test_native_takeover_uses_old_target_then_can_revoke(self):
        self.module.initialize()
        with self.native([('/vol2/test/photos', 'rw')]): self.module.configure()
        self.assertEqual('/app/Photos/photos', self.record()['libraries'][0]['target'])
        with self.native([]): self.module.configure()
        self.assertEqual([], self.record()['libraries'])

    def test_stale_legacy_remove_action_does_not_remove_another_directory(self):
        self.module.initialize()
        primary = '/vol2/test/photos'
        with self.batch(['/vol1/other/travel']): self.module.configure()
        with patch.dict(os.environ, {self.module.action_field(primary): 'remove'}):
            self.module.configure()
            self.module.configure()
        self.assertEqual(['/vol1/other/travel'], [e['source'] for e in self.record()['libraries']])

    def test_native_bad_batch_preserves_record_and_source_files(self):
        self.module.initialize()
        sample = self.module.CANDIDATE/'native-0'
        sample.mkdir()
        photo = sample/'keep.jpg'
        photo.write_bytes(b'original')
        before = (self.module.META/'installation.json').read_bytes()
        for paths in [[('/vol1/1000/new', 'rw'), ('/vol2/test/state', 'rw')],
                      [('/vol1/1000/new', 'rw'), ('/vol1/1000/new/sub', 'ro')],
                      [('/vol1/1000/new', 'invalid')]]:
            with self.native(paths):
                with self.assertRaises(RuntimeError): self.module.configure()
            self.assertEqual(before, (self.module.META/'installation.json').read_bytes())
            self.assertEqual(b'original', photo.read_bytes())

    def test_compact_wizard_has_actual_permissions_add_and_remove_without_tips(self):
        self.module.initialize()
        with self.native([('/vol1/new/Photos', 'rw')]): self.module.configure()
        wizard = json.loads(self.module.WIZARD.read_text(encoding='utf-8'))
        items = wizard[0]['items']
        self.assertFalse(any(item['type'] == 'tips' for item in items))
        self.assertEqual('rw', items[1]['initValue'])
        self.assertEqual(['只读', '读写', '移除'], [v['label'] for v in items[1]['options']])
        self.assertEqual('新增照片目录（多个路径用 ; 分隔）', items[-2]['label'])

    def test_runtime_permissions_and_removal_take_priority_over_same_native_snapshot(self):
        self.module.initialize()
        path = '/vol1/new/Photos'
        with self.native([(path, 'rw')]): self.module.configure()
        generation = self.record()['wizard_generation']
        field = self.module.action_field(path) + '_' + str(generation)
        with self.native([(path, 'rw')]), patch.dict(os.environ, {field: 'ro'}): self.module.configure()
        self.assertTrue(self.record()['libraries'][-1]['read_only'])
        field = self.module.action_field(path) + '_' + str(self.record()['wizard_generation'])
        with self.native([(path, 'rw')]), patch.dict(os.environ, {field: 'remove'}): self.module.configure()
        self.assertNotIn(path, [e['source'] for e in self.record()['libraries']])
        with self.native([(path, 'rw')]): self.module.configure()
        self.assertNotIn(path, [e['source'] for e in self.record()['libraries']])
        with self.batch([path], 'rw'): self.module.configure()
        # The stale saved Remove belongs to an older form and is ignored.
        with patch.dict(os.environ, {field: 'remove'}): self.module.configure()
        self.assertIn(path, [e['source'] for e in self.record()['libraries']])

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
