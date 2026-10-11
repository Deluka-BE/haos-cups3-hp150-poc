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
            data = b'\x1b%-12345X@PJL ENTER LANGUAGE = QPDL\n\x00\xff'
            for _ in range(2):
                result = self.invoke(['1', 'user', 'title', '1', ''], tmp, data)
                self.assertEqual(result.returncode, 0, result.stderr)
            files = list(Path(tmp).glob('*.spl'))
            self.assertEqual(len(files), 2)
            self.assertTrue(all(path.read_bytes() == data for path in files))
            self.assertFalse(list(Path(tmp).glob('*.part')))
            import hashlib
            for path in files:
                meta = json.loads(Path(str(path) + '.json').read_text())
                self.assertEqual(meta['job_id'], 1)
                self.assertEqual(meta['size_bytes'], len(data))
                self.assertEqual(meta['sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(set(meta), {'job_id', 'size_bytes', 'sha256', 'file', 'timestamp_utc'})

    def test_filename_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input'
            source.write_bytes(b'\x1b%-12345X@PJL ENTER LANGUAGE = QPDL\r\nfile input')
            result = self.invoke(['2', 'user', 'title', '1', '', str(source)], tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(next(Path(tmp).glob('*.spl')).read_bytes(), source.read_bytes())

    def test_reject_device_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            for uri in ('usb://HP', 'capture:/../../etc/passwd', ''):
                result = self.invoke(['1', 'user', 'title', '1', ''], tmp, uri=uri)
                self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_empty_admin_open_and_failed_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.invoke(['0', 'user', 'title', '1', ''], tmp)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(list(Path(tmp).iterdir()), [])
            result = self.invoke(['1', 'user', 'SECRET', '1', '', tmp + '/SECRET'], tmp)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(b'SECRET', result.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_side_channel(self):
        import importlib.util
        import socket
        import struct
        import threading
        spec = importlib.util.spec_from_file_location('capture', BACKEND)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        client, backend = socket.socketpair()
        with client, backend:
            client.settimeout(2)
            stop = threading.Event()
            thread = threading.Thread(target=module.side_channel, args=(stop, backend.fileno()))
            thread.start()
            try:
                for command, status, payload in [(3, 1, b'\x00'), (5, 1, b'\x01'), (8, 1, b'\x01'), (2, 7, b'')]:
                    request = struct.pack('!BBH', command, 0, 0)
                    client.sendall(request[:2])
                    client.sendall(request[2:])
                    header = client.recv(4)
                    self.assertEqual(struct.unpack('!BBH', header), (command, status, len(payload)))
                    if payload:
                        self.assertEqual(client.recv(len(payload)), payload)
            finally:
                stop.set()
                thread.join(2)


class RuntimeTests(unittest.TestCase):
    def test_runtime_paths_and_permissions(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('runtime', ROOT / 'scripts/runtime-check.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            with self.assertRaises(RuntimeError):
                module.check(root, load=False, state=root / 'state')
            for name in ('filter/rastertospl', 'filter/rastertospl.real', 'lib/libscmssc.so',
                         'share/cups/model/uld-hp/cms/15xsc.cts', 'state/ppd/HP_Color_Laser_15x_Series.ppd'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
                path.chmod(0o755 if name.startswith('filter/') else 0o644)
            for name in ('capture', 'spool'):
                (root / name).mkdir()
            module.check(root, load=False, state=root / 'state')
            (root / 'filter/rastertospl.real').chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, 'Non-executable'):
                module.check(root, load=False, state=root / 'state')

    def test_capture_verifier(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('verify', ROOT / 'scripts/verify-capture.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            result = CaptureTests().invoke(['12', 'SECRET', 'SECRET', '1', 'SECRET'], tmp,
                                           b'\x1b%-12345X@PJL ENTER LANGUAGE = QPDL\n\x00\xff')
            self.assertEqual(result.returncode, 0, result.stderr)
            path = next(Path(tmp).glob('*.spl'))
            self.assertTrue(module.verify(path)['passed'])
            self.assertIn(b'PASS: capture job=12', result.stderr)
            self.assertIn(b'format=QPDL-declared signature=PJL-QPDL', result.stderr)
            self.assertNotIn(b'SECRET', result.stderr)
            path.write_bytes(b'%PDF-1.7')
            self.assertFalse(module.verify(path)['passed'])
            result = CaptureTests().invoke(['13', 'user', 'title', '1', ''], tmp, b'%PDF-1.7')
            self.assertEqual(result.returncode, 1)
            self.assertIn(b'FAIL: capture job=13', result.stderr)
            other = next(p for p in Path(tmp).glob('*.spl') if p != path)
            self.assertFalse(module.verify(other)['passed'])


    def test_verifier_failures_and_redaction(self):
        import hashlib
        verifier = ROOT / 'scripts/verify-capture.py'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'job-4-fixture.spl'
            declaration = b'\x1b%-12345X@PJL ENTER LANGUAGE = QPDL\n'
            def check(data, metadata):
                path.write_bytes(data)
                sidecar = Path(str(path) + '.json')
                if metadata is None:
                    sidecar.unlink(missing_ok=True)
                else:
                    sidecar.write_text(metadata)
                result = subprocess.run([sys.executable, str(verifier), str(path)], capture_output=True)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(len(result.stdout.splitlines()), 1)
                self.assertTrue(result.stdout.startswith(b'FAIL: capture job=4 '))
                self.assertNotIn(b'SECRET', result.stdout + result.stderr)
                self.assertEqual(result.stderr, b'')
            for metadata in (None, '{SECRET', '[]', 'null', '{}',
                             '{"job_id":"SECRET","file":"SECRET"}'):
                check(declaration, metadata)
            for data in (b'', b'%PDF-1.7 SECRET\n' + declaration,
                         b'RaS2SECRET', b'SECRET' + declaration,
                         declaration.rstrip(b'\n'), b'unknown SECRET'):
                metadata = json.dumps({'job_id': 4, 'file': path.name,
                                       'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
                check(data, metadata)
            for field, value in (('job_id', True), ('job_id', 5), ('size_bytes', True),
                                 ('sha256', 'SECRET'), ('file', 'SECRET')):
                metadata = {'job_id': 4, 'file': path.name, 'size_bytes': len(declaration),
                            'sha256': hashlib.sha256(declaration).hexdigest()}
                metadata[field] = value
                check(declaration, json.dumps(metadata))
            path.unlink()
            result = subprocess.run([sys.executable, str(verifier), str(path)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b'sha256=unavailable', result.stdout)

    def test_installed_backend_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = Path(tmp) / 'capture'
            shutil.copy(BACKEND, backend)
            shutil.copy(ROOT / 'scripts/verify-capture.py', Path(tmp) / 'verify-capture.py')
            result = subprocess.run([sys.executable, str(backend), '8', 'SECRET', 'SECRET', '1', ''],
                                    input=b'\x1b%-12345X@PJL ENTER LANGUAGE = QPDL\n',
                                    env={**os.environ, 'CAPTURE_DIR': tmp, 'DEVICE_URI': 'capture:/hp150'},
                                    capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(result.stderr.splitlines()), 2)
            self.assertIn(b'path=/opt/poc/backend/capture class=capture argc=5 normalized-usb=false device-uri=capture', result.stderr)
            self.assertIn(b'PASS: capture job=8', result.stderr)
            self.assertNotIn(b'SECRET', result.stderr)
            self.assertIn('cp /opt/poc/scripts/verify-capture.py /opt/poc/backend/verify-capture.py',
                          (ROOT / 'Dockerfile').read_text())

    def test_verifier_exception_retains_completed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = Path(tmp) / 'capture'
            shutil.copy(BACKEND, backend)
            (Path(tmp) / 'verify-capture.py').write_text(
                'def verify(path):\n    raise RuntimeError("SECRET")\n')
            result = subprocess.run([sys.executable, str(backend), '9', 'SECRET', 'SECRET', '1', ''],
                                    input=b'fixture SECRET',
                                    env={**os.environ, 'CAPTURE_DIR': tmp, 'DEVICE_URI': 'capture:/hp150'},
                                    capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(result.stderr.splitlines()), 2)
            self.assertIn(b'path=/opt/poc/backend/capture class=capture argc=5 normalized-usb=false device-uri=capture', result.stderr)
            self.assertIn(b'FAIL: capture job=9', result.stderr)
            self.assertNotIn(b'SECRET', result.stderr)
            path = next(Path(tmp).glob('*.spl'))
            self.assertEqual(path.read_bytes(), b'fixture SECRET')
            self.assertTrue(Path(str(path) + '.json').is_file())
            self.assertFalse(list(Path(tmp).glob('*.part')))

    def test_wrapper_preserves_stream_arguments_and_status(self):
        # Substitute only fixed container paths, execute the actual wrapper shell logic.
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            for name in ('lib/libscmssc.so', 'share/cups/model/uld-hp/cms/15xsc.cts', 'test.ppd'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            (root / 'filter').mkdir()
            real = root / 'filter/rastertospl.real'
            real.write_text('#!' + sys.executable + '\n' +
                            'import os, sys\n'
                            'assert "SUPERVISOR_TOKEN" not in os.environ\n'
                            'assert "HASSIO_TOKEN" not in os.environ\n'
                            'assert sys.argv[1:] == ["7", "SECRET", "SECRET", "1", ""]\n'
                            'sys.stdout.buffer.write(sys.stdin.buffer.read())\n'
                            'sys.exit(9)\n')
            real.chmod(0o755)
            (root / 'job-stage.py').write_text((ROOT / 'scripts/job-stage.py').read_text().replace('/work', tmp))
            wrapper = root / 'wrapper.sh'
            wrapper.write_text((ROOT / 'scripts/rastertospl-wrapper.sh').read_text().replace('/work', tmp).replace('/opt/poc/scripts/job-stage.py', str(root / 'job-stage.py')))
            result = subprocess.run(['sh', str(wrapper), '7', 'SECRET', 'SECRET', '1', ''],
                                    input=b'\x00\xffSPL', capture_output=True,
                                    env={**os.environ, 'PPD': str(root / 'test.ppd'),
                                         'SUPERVISOR_TOKEN': 'SECRET', 'HASSIO_TOKEN': 'SECRET'})
            self.assertEqual(result.returncode, 9, result.stderr)
            self.assertEqual(result.stdout, b'\x00\xffSPL')
            self.assertNotIn(b'SECRET', result.stderr)


class LaunchEnvironmentTests(unittest.TestCase):
    def test_app_and_child_environment(self):
        source = (ROOT / 'scripts/entrypoint.sh').read_text()
        # Stub only driver preparation and its unavailable container cwd.
        # Keep exports, sanitization, mode selection, diagnostics and exec intact.
        start = source.index('python3 /opt/poc/scripts/validate-driver.py')
        end = source.index('export LD_LIBRARY_PATH=')
        source = source[:start] + source[end:]
        source = source.replace('exec python3 /opt/poc/scripts/mdns-runtime.py', 'exec')
        source = source.replace('cd /work/filter', ': # container cwd stub')
        source = source.replace('python3 /opt/poc/scripts/state-runtime.py', ': # persistence tested separately')
        source = source.replace('python3 /opt/poc/scripts/usb-settle.py', ': # settling tested separately')
        source = source.replace('python3 /opt/poc/scripts/runtime-check.py', ': # runtime check stub')
        source = source.replace('python3 /opt/poc/scripts/usb-diagnostics.py', ': # diagnostics tested separately')
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
                            BACKEND_DIR='/opt/poc/backend', STATE_DIR='/data/state',
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
                                      'server-options=no-tls', '-o', 'listen-hostname=0.0.0.0', '-o', 'log-file=-',
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
