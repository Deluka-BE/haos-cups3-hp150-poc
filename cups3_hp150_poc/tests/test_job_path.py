import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('job_stage', ROOT / 'scripts/job-stage.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class JobPathTests(unittest.TestCase):
    def run_child(self, code, timeout=2):
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            result = stage.supervise('usb', [sys.executable, '-c', code], '7', timeout)
        return result, log.getvalue()

    def test_status_and_redaction_with_large_stderr(self):
        result, log = self.run_child('import sys; sys.stderr.write("SECRET unable to open claim write busy "*10000); sys.exit(3)')
        self.assertEqual(result, 3)
        self.assertNotIn('SECRET', log)
        self.assertLess(len(log), 1500)
        self.assertIn('exit=3', log)
        self.assertIn('vendor-marker=open', log)
        self.assertIn('vendor-marker=claim', log)

    def test_transport_state_protocol_is_sanitized(self):
        result, log = self.run_child('import sys; sys.stderr.write("STATE: +connecting-to-device\\nSTATE: SECRET\\nSTATE: -connecting-to-device\\n")')
        self.assertEqual(result, 0)
        self.assertIn('STATE: +connecting-to-device', log)
        self.assertIn('STATE: -connecting-to-device', log)
        self.assertNotIn('SECRET', log)

    def test_timeout_is_failure_without_retry(self):
        result, log = self.run_child('import time; time.sleep(30)', 0.1)
        self.assertEqual(result, 1)
        self.assertIn('timeout=true', log)
        self.assertIn('retry=none', log)
        self.assertEqual(log.count('started'), 1)

    def test_token_scrubbing(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {'SUPERVISOR_TOKEN': 'SECRET', 'HASSIO_TOKEN': 'SECRET'}):
            result, log = self.run_child('import os; assert "SUPERVISOR_TOKEN" not in os.environ; assert "HASSIO_TOKEN" not in os.environ')
        self.assertEqual(result, 0)
        self.assertNotIn('SECRET', log)

    def test_launch_errno_redacted(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()) as log:
            result = stage.supervise('usb', [tmp + '/SECRET'], '7')
        self.assertEqual(result, 1)
        self.assertIn('errno=2', log.getvalue())
        self.assertNotIn('SECRET', log.getvalue())

    def test_inherited_channels_and_binary_stdout(self):
        # Two inherited descriptors stand in for CUPS fd3/fd4. No transport calls.
        readfd, writefd = os.pipe()
        try:
            os.set_inheritable(writefd, True)
            code = f'import os; os.write({writefd}, b"channel"); os.write(1, b"\\x00\\xff")'
            runner = f'import sys; sys.path.insert(0, {str(ROOT / "scripts")!r}); import importlib.util; s=importlib.util.spec_from_file_location("j", {str(ROOT / "scripts/job-stage.py")!r}); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); sys.exit(m.supervise("usb", [sys.executable,"-c",{code!r}], "7", 2))'
            result = subprocess.run([sys.executable, '-c', runner], pass_fds=(writefd,), capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'\x00\xff')
            self.assertEqual(os.read(readfd, 7), b'channel')
        finally:
            os.close(readfd)
            os.close(writefd)

    def test_patch_is_guarded_and_has_fixed_labels(self):
        spec = importlib.util.spec_from_file_location('patch_job', ROOT / 'scripts/patch-job-path.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.replace('once', 'once', 'new'), 'new')
        for value in ('missing', 'once once'):
            with self.assertRaises(ValueError):
                module.replace(value, 'once', 'new')
        source = (ROOT / 'scripts/patch-job-path.py').read_text()
        for label in ('source=streaming', 'source=spooled', 'first-write', 'read-errno', 'filter-%d finished', 'cups-backend finished'):
            self.assertIn(label, source)


class BindingLaunchTests(unittest.TestCase):
    def invoke(self, uri, args):
        from unittest.mock import patch
        with patch.dict(os.environ, {'DEVICE_URI': uri}), patch.object(sys, 'argv', ['job-stage.py', 'usb', *args]), patch.object(stage, 'supervise', return_value=0) as child, contextlib.redirect_stderr(io.StringIO()) as log:
            result = stage.main()
        return result, log.getvalue(), child

    def test_normalized_child_launch_and_redaction(self):
        uri = 'usb://HP/Printer?serial=SERIAL_SECRET'
        args = ['42', 'CLIENT_SECRET', 'TITLE_SECRET', '1', 'OPTIONS_SECRET']
        result, log, child = self.invoke(uri, args)
        self.assertEqual(result, 0)
        child.assert_called_once_with('usb', ['/opt/poc/backend/usb.real', *args], '42')
        self.assertIn('path=/opt/poc/backend/usb.real class=usb argc=5 device-uri=usb normalized-usb=true', log)
        for secret in [uri, *args[1:3], args[4], 'SERIAL_SECRET']:
            self.assertNotIn(secret, log)
        self.assertTrue(stage.valid_usb_uri(uri))

    def test_invalid_invocations_do_not_launch(self):
        valid = ['42', 'CLIENT_SECRET', 'TITLE_SECRET', '1', 'OPTIONS_SECRET']
        cases = [(uri, valid) for uri in ('', 'usb:', 'usb://', 'cups:usb://HP/SECRET', 'capture:/hp150', 'usb://HP/SECRET\n', 'usb://HP/SECRET\x7f')]
        cases += [('usb://HP/SECRET', valid[:4]), ('usb://HP/SECRET', valid + ['FILE_SECRET', 'EXTRA_SECRET']), ('usb://HP/SECRET', ['CLIENT_SECRET', *valid[1:]])]
        for uri, args in cases:
            with self.subTest(uri=uri, argc=len(args)):
                result, log, child = self.invoke(uri, args)
                self.assertEqual(result, 1)
                child.assert_not_called()
                self.assertIn('rejected reason=invalid-usb-invocation retry=none', log)
                self.assertNotIn('SECRET', log)
                self.assertLess(len(log), 350)

    def test_optional_filename_is_preserved_without_logging(self):
        result, log, child = self.invoke('usb://HP/Printer', ['42', 'CLIENT', 'TITLE', '1', 'OPTIONS', 'FILE_SECRET'])
        self.assertEqual(result, 0)
        self.assertIn('argc=6', log)
        self.assertNotIn('FILE_SECRET', log)
        self.assertEqual(child.call_args.args[1][-1], 'FILE_SECRET')

    def test_binding_classifier_compiled_from_patch(self):
        # Execute the actual injected C helper, independent of PAPPL or hardware.
        import shutil
        import ast
        compiler = shutil.which('cc') or shutil.which('gcc')
        if not compiler:
            self.skipTest('C compiler required for binding regression')
        tree = ast.parse((ROOT / 'scripts/patch-job-path.py').read_text())
        helpers = [node.value.value for node in ast.walk(tree) if isinstance(node, ast.AugAssign) and isinstance(node.value, ast.Constant) and 'static const char *pocBinding' in str(node.value.value)]
        helper = helpers[0].split('static void pocLogBinding')[0]
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            source = Path(tmp) / 'binding.c'
            binary = Path(tmp) / 'binding'
            source.write_text('#include <stdio.h>\n#include <string.h>\n' + helper + '\nint main(int argc, char **argv) { puts(pocBinding(argc > 1 ? argv[1] : NULL)); return 0; }\n')
            subprocess.run([compiler, '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], check=True, capture_output=True)
            cases = {None: 'invalid', '': 'invalid', 'broken': 'invalid', 'usb://': 'invalid', 'cups:usb://HP/P?serial=SECRET': 'cups:usb', 'usb://HP/P?serial=SECRET': 'usb', 'capture:/hp150': 'capture', 'cups:capture:/hp150': 'capture', 'https://CLIENT:SECRET@host': 'other', 'usb://HP/SECRET\n': 'invalid'}
            for uri, expected in cases.items():
                result = subprocess.run([str(binary)] + ([] if uri is None else [uri]), check=True, capture_output=True, text=True)
                self.assertEqual(result.stdout.strip(), expected)
                self.assertNotIn('SECRET', result.stdout)
        patch_source = (ROOT / 'scripts/patch-job-path.py').read_text()
        self.assertEqual(patch_source.count('  pocLogBinding(job);'), 3)
