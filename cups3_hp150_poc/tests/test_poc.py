import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'scripts/capture.py'


class CaptureTests(unittest.TestCase):
    def invoke(self, args, directory, data=b'', uri='capture:/hp150'):
        return subprocess.run([sys.executable, str(BACKEND), *args], input=data,
                              capture_output=True, env={**os.environ, 'CAPTURE_DIR': directory,
                                                       'DEVICE_URI': uri})

    def test_discovery(self):
        result = subprocess.run([sys.executable, str(BACKEND)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'capture:/hp150', result.stdout)

    def test_stdin_binary_and_unique_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = b'\x00\xffSPL\n'
            for _ in range(2):
                result = self.invoke(['1', 'user', 'title', '1', ''], tmp, data)
                self.assertEqual(result.returncode, 0, result.stderr)
            files = list(Path(tmp).glob('*.spl'))
            self.assertEqual(len(files), 2)
            self.assertTrue(all(path.read_bytes() == data for path in files))
            self.assertFalse(list(Path(tmp).glob('*.part')))

    def test_filename_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input'
            source.write_bytes(b'file input')
            result = self.invoke(['2', 'user', 'title', '1', '', str(source)], tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(next(Path(tmp).glob('*.spl')).read_bytes(), b'file input')

    def test_reject_device_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            for uri in ('usb://HP', 'capture:/../../etc/passwd', ''):
                result = self.invoke(['1', 'user', 'title', '1', ''], tmp, uri=uri)
                self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(Path(tmp).iterdir()), [])


class LaunchEnvironmentTests(unittest.TestCase):
    def test_app_and_child_environment(self):
        source = (ROOT / 'scripts/entrypoint.sh').read_text()
        # Stub only driver preparation and its unavailable container cwd.
        # Keep exports, sanitization, mode selection, diagnostics and exec intact.
        start = source.index('python3 /opt/poc/scripts/validate-driver.py')
        end = source.index('export LD_LIBRARY_PATH=')
        source = source[:start] + source[end:]
        source = source.replace('cd /work/filter', ': # container cwd stub')
        # Use the workspace because some workers mount /tmp with noexec.
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            directory = Path(tmp)
            entrypoint = directory / 'entrypoint.sh'
            entrypoint.write_text(source)
            app = directory / 'legacy-printer-app'
            app.write_text('#!' + sys.executable + '\n' +
                           'import json, os, subprocess, sys\n'
                           'child = subprocess.check_output([sys.executable, "-c", '
                           '\'import json, os; print(json.dumps(dict(os.environ)))\'])\n'
                           'print(json.dumps({"argv": sys.argv[1:], '
                           '"app": dict(os.environ), "child": json.loads(child)}))\n')
            app.chmod(0o755)
            env = {'PATH': tmp + os.pathsep + os.defpath, 'TZ': 'UTC',
                   'POC_PORT': '8631', 'SUPERVISOR_TOKEN': 'synthetic-supervisor',
                   'HASSIO_TOKEN': 'synthetic-hassio'}
            expected = {key: env[key] for key in ('PATH', 'TZ', 'POC_PORT')}
            expected.update(LD_LIBRARY_PATH='/work/lib', PPD_DIRS='/work/state/ppd',
                            USER_PPD_DIR='/work/state/ppd', FILTER_DIR='/work/filter',
                            BACKEND_DIR='/opt/poc/backend', STATE_DIR='/work/state',
                            SPOOL_DIR='/work/spool', CAPTURE_DIR='/work/capture')
            for mode in ('server', 'drivers'):
                with self.subTest(mode=mode):
                    result = subprocess.run(['sh', str(entrypoint), mode], env=env,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    payload = json.loads(result.stdout.splitlines()[-1])
                    for process in ('app', 'child'):
                        for token in ('SUPERVISOR_TOKEN', 'HASSIO_TOKEN'):
                            self.assertNotIn(token, payload[process])
                        for key, value in expected.items():
                            self.assertEqual(payload[process].get(key), value, key)
                    self.assertNotIn('synthetic-supervisor', result.stdout + result.stderr)
                    self.assertNotIn('synthetic-hassio', result.stdout + result.stderr)
                    self.assertEqual(payload['argv'], ['drivers'] if mode == 'drivers' else
                                     ['server', '-o', 'server-port=8631', '-o',
                                      'listen-hostname=0.0.0.0', '-o', 'log-file=-',
                                      '-o', 'log-level=debug'])


class ValidationTests(unittest.TestCase):
    def test_missing_files_reported_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate-driver.py'), tmp],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            for name in ('HP_Color_Laser_15x_Series.ppd', 'rastertospl', 'libscmssc.so', 'cms/15xsc.cts'):
                self.assertIn(name, result.stderr)

    def test_non_elf_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cms').mkdir()
            (root / 'HP_Color_Laser_15x_Series.ppd').write_text('*PPD-Adobe: "4.3"\n*cupsFilter: "rastertospl"\n')
            for name in ('rastertospl', 'libscmssc.so', 'cms/15xsc.cts'):
                (root / name).write_bytes(b'not ELF')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate-driver.py'), tmp],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('sha256=', result.stdout)
            self.assertIn('expected AArch64' if shutil.which('readelf') else 'readelf unavailable', result.stderr)


if __name__ == '__main__':
    unittest.main()
