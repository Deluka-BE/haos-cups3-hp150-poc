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
