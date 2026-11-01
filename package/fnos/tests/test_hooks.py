"""Exercise the real configure hook with Docker calls captured, without a NAS."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = (r'C:\Program Files\Git\bin\bash.exe' if os.name == 'nt' else shutil.which('bash'))


@unittest.skipUnless(BASH and Path(BASH).exists(), 'Bash required')
class HookTests(unittest.TestCase):
    def invoke(self, folders, **settings):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data-path').write_text('/vol2/1000/TrailSnap\n', newline='\n')
            (root / 'installation.json').write_text('{"wizard_generation": 1}\n', newline='\n')
            env = dict(os.environ, TRIM_PKGVAR=root.as_posix(), TRIM_APPDEST='/vol2/app',
                       TRIM_DATA_SHARE_PATHS='/vol2/@appshare/trailsnap/data:/vol2/@appshare/trailsnap/photos',
                       wizard_library_action_0123456789abcdef='remove', HOOK=(ROOT/'src/hooks.sh').as_posix(),
                       CAPTURE=(root/'args').as_posix())
            env.pop('TRIM_DATA_ACCESSIBLE_PATHS', None)
            if folders is not None: env['TRIM_DATA_ACCESSIBLE_PATHS'] = folders
            env.update(settings)
            script = '''
docker() { printf '%s\\n' CALL "$@" >> "$CAPTURE"; }
realpath() { printf '%s\\n' "${@: -1}"; }
id() { printf '0'; }
runuser() { if [[ "${@: -2:1}" = -w && "${@: -1}" = *ReadOnly* ]]; then return 1; fi; return 0; }
test() { if [[ "$1" = -d && "$2" = /vol* ]]; then return 0; fi; builtin test "$@"; }
export -f docker realpath id runuser test
source "$HOOK" configure
'''
            result = subprocess.run([BASH, '-c', script], env=env, capture_output=True)
            capture = root/'args'
            args = capture.read_text(encoding='utf-8') if capture.exists() else ''
            return result, args

    def test_batch_mounts_spaces_modes_and_wizard_are_forwarded(self):
        result, args = self.invoke('/vol1/1000/Family Photos:/vol2/1000/旅行:/vol2/@appshare/trailsnap/data')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('source=/vol1/1000/Family Photos,target=/candidate/native-0,readonly', args)
        self.assertIn('source=/vol2/1000/旅行,target=/candidate/native-1,readonly', args)
        self.assertIn('wizard_library_action_0123456789abcdef', args)
        self.assertIn('TS_NATIVE_MODE_0=rw', args)
        self.assertIn('TS_NATIVE_COUNT=2', args)
        self.assertNotIn('source=/vol2/@appshare/trailsnap/data', args)
        self.assertIn('target=/wizard', args)
        self.assertEqual(2, args.splitlines().count('CALL'))

    def test_bad_second_path_never_invokes_docker(self):
        for folders in ['/vol1/1000/Photos:/etc', '/vol1/1000/Photos\n/vol2/1000/Photos',
                        '/vol1/1000/Photos:/vol2/1000/$(invalid)']:
            result, args = self.invoke(folders)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual('', args)

    def test_missing_and_empty_context_are_distinct_and_acl_downgrades_to_ro(self):
        result, args = self.invoke(None)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn('TS_NATIVE_COUNT', args)
        result, args = self.invoke('')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('TS_NATIVE_COUNT=0', args)
        result, args = self.invoke('/vol1/1000/ReadOnly')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('TS_NATIVE_MODE_0=ro', args)

    def test_runtime_addition_uses_only_the_current_form_field(self):
        result, args = self.invoke(None, wizard_new_photo_1='/vol1/1000/New Photos', wizard_add_photo_mode='rw')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('source=/vol1/1000/New Photos,target=/candidate/0,readonly', args)
        self.assertIn('TS_ADD_PHOTOS=/vol1/1000/New Photos', args)
        self.assertIn('TS_ADD_MODE=rw', args)
        result, args = self.invoke(None, wizard_new_photo_0='/vol1/1000/Stale')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn('/vol1/1000/Stale', args)

    def test_runtime_batch_trims_paths_and_rejects_bad_batch_before_docker(self):
        result, args = self.invoke(None, wizard_new_photo_1=' /vol1/1000/Family Photos ; ; /vol2/1000/旅行; ', wizard_add_photo_mode='rw')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('source=/vol1/1000/Family Photos,target=/candidate/0,readonly', args)
        self.assertIn('source=/vol2/1000/旅行,target=/candidate/1,readonly', args)
        self.assertIn('TS_ADD_MODE=rw', args)
        for value in ['/vol1/1000/Photos;/etc', '/vol1/1000/Photos\n/vol2/1000/Other']:
            result, args = self.invoke(None, wizard_new_photo_1=value)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual('', args)
