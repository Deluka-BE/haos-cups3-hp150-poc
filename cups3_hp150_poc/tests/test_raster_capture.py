"""One-shot stream capture tests; fake raster child only, never HP hardware."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'scripts/job-stage.py'

RUNNER = r'''
import importlib.util, os, pathlib, sys
spec=importlib.util.spec_from_file_location("stage", sys.argv[1])
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
os.environ["LD_PRELOAD"]="/opt/poc/lib/raster-header-diagnostics.so INHERITED_PRELOAD"
m.CAPTURE_STATE=pathlib.Path(sys.argv[2]); m.CAPTURE_DIR=pathlib.Path(sys.argv[3])
m.CAPTURE_MIN_FREE=int(os.environ.get("TEST_MIN_FREE", "0"))
m.CAPTURE_MAX_STREAM=int(os.environ.get("TEST_MAX_STREAM", str(512*1024*1024)))
code=os.environ["TEST_CHILD"]
sys.exit(m.supervise("rastertospl", [sys.executable,"-c",code], "7", 15))
'''


class RasterCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / 'state'; self.capture = root / 'capture'
        self.state.mkdir(); self.capture.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_stage(self, data, child=None, enabled=True, max_stream=None, min_free=0):
        child = child or ('import os,sys; '
                          'd=sys.stdin.buffer.read(); '
                          'sys.stdout.buffer.write(d[::-1]); sys.stdout.buffer.flush()')
        env = dict(os.environ)
        env['POC_CAPTURE_RASTER_ONCE'] = '1' if enabled else '0'
        env['TEST_CHILD'] = child
        env['TEST_MIN_FREE'] = str(min_free)
        if max_stream is not None:
            env['TEST_MAX_STREAM'] = str(max_stream)
        return subprocess.run([sys.executable, '-c', RUNNER, str(STAGE), str(self.state),
                               str(self.capture)], input=data, capture_output=True,
                              env=env, timeout=20)

    def test_boundary_preserves_options_ppd_and_excludes_credentials(self):
        spec = importlib.util.spec_from_file_location('stage', STAGE)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        ppd = Path(self.tmp.name) / 'test.ppd'
        ppd.write_bytes(b'*DefaultScreen: Enhanced\n*DefaultQuality: 600x600_2\n')
        argv = ['/work/filter/rastertospl.real', '7', 'user', 'title', '1',
                'Quality=600x600_1 Screen=Normal secBrightness=50']
        env = {'PPD': str(ppd), 'LD_LIBRARY_PATH': '/work/lib',
               'SUPERVISOR_TOKEN': 'SECRET', 'HASSIO_TOKEN': 'SECRET',
               'UNRELATED_SECRET': 'SECRET'}
        evidence = module.capture_boundary(argv, env)
        self.assertEqual(evidence['argv'], argv)
        self.assertEqual(evidence['environment'],
                         {'PPD': str(ppd), 'LD_LIBRARY_PATH': '/work/lib'})
        self.assertEqual(evidence['ppd']['sha256'], hashlib.sha256(ppd.read_bytes()).hexdigest())
        self.assertEqual(evidence['ppd']['text'], ppd.read_text())
        self.assertNotIn('SECRET', str(evidence))

    def test_boundary_publish_failure_does_not_fail_printing(self):
        self.arm()
        # Cannot replace a directory with the JSON file, even when running as root.
        (self.capture / 'cups3-reference.boundary.json').mkdir()
        result = self.run_stage(b'print continues')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'seunitnoc tnirp')
        self.assertIn(b'boundary status=unavailable', result.stderr)
        self.assertIn('boundary_sha256=unavailable',
                      (self.capture / 'cups3-reference.meta.txt').read_text())

    def arm(self):
        (self.state / 'armed').write_text('1\n', encoding='ascii')

    def test_disabled_is_exact_passthrough_and_creates_nothing(self):
        data = os.urandom(256 * 1024)
        result = self.run_stage(data, enabled=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, data[::-1])
        self.assertEqual(list(self.capture.iterdir()), [])

    def test_one_shot_captures_exact_input_output_and_metadata(self):
        self.arm()
        data = os.urandom(2 * 1024 * 1024 + 123)
        result = self.run_stage(data)
        expected = data[::-1]
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected)
        self.assertEqual((self.capture / 'cups3-reference.in.raster').read_bytes(), data)
        self.assertEqual((self.capture / 'cups3-reference.out.spl').read_bytes(), expected)
        meta = (self.capture / 'cups3-reference.meta.txt').read_text()
        self.assertIn(f'in_bytes={len(data)}', meta)
        self.assertIn(f'in_sha256={hashlib.sha256(data).hexdigest()}', meta)
        self.assertIn(f'out_sha256={hashlib.sha256(expected).hexdigest()}', meta)
        self.assertIn(b'capture status=complete', result.stderr)
        boundary = self.capture / 'cups3-reference.boundary.json'
        self.assertIn('boundary_sha256=' + hashlib.sha256(boundary.read_bytes()).hexdigest(), meta)
        self.assertEqual(boundary.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(data[:32], result.stderr)
        first_in = (self.capture / 'cups3-reference.in.raster').read_bytes()
        second = self.run_stage(b'SECOND')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout, b'DNOCES')
        self.assertEqual((self.capture / 'cups3-reference.in.raster').read_bytes(), first_in)

    def test_real_print_stage_removes_preload_with_and_without_capture(self):
        data = b'RaS2 diagnostic raster input'
        child = ('import os,sys; '
                 'assert "LD_PRELOAD" not in os.environ; '
                 'sys.stdout.buffer.write(b"SPL"+sys.stdin.buffer.read())')
        for enabled in (False, True):
            with self.subTest(capture=enabled):
                if enabled:
                    self.arm()
                result = self.run_stage(data, child=child, enabled=enabled)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, b'SPL' + data)
                if enabled:
                    self.assertEqual((self.capture / 'cups3-reference.in.raster').read_bytes(), data)
                    self.assertEqual((self.capture / 'cups3-reference.out.spl').read_bytes(), b'SPL' + data)
                    boundary = json.loads((self.capture / 'cups3-reference.boundary.json').read_text())
                    self.assertNotIn('LD_PRELOAD', boundary['environment'])
                    self.assertIn(b'capture status=complete', result.stderr)
                else:
                    self.assertEqual(list(self.capture.iterdir()), [])

    def test_metadata_records_format_dimensions_and_exit(self):
        self.arm()
        data = b'RaS2' + bytes(128)
        record = 'HP150_RASTER_HEADER 1 13 3 600 600 8 24 3 39 1 0 0 0 0 0'
        child = ('import sys; sys.stdin.buffer.read(); '
                 'sys.stderr.write(' + repr(record + '\n') + '); '
                 'sys.stdout.buffer.write(b"\\x1b%-12345X@PJL ENTER LANGUAGE=QPDL\\r\\n")')
        result = self.run_stage(data, child=child)
        self.assertEqual(result.returncode, 0, result.stderr)
        meta = (self.capture / 'cups3-reference.meta.txt').read_text()
        for field in ('in_format=CUPS-raster', 'in_magic_hex=52615332',
                      'out_format=QPDL-declared', 'out_signature=PJL-QPDL',
                      'width=13 height=3 xdpi=600 ydpi=600',
                      'cupsBitsPerPixel=24', 'cupsBytesPerLine=39', 'filter_exit=0'):
            self.assertIn(field, meta)

    def test_nonzero_exit_preserves_output_and_code(self):
        self.arm()
        child = ('import sys; d=sys.stdin.buffer.read(); '
                 'sys.stdout.buffer.write(b"OUT"+d); sys.stdout.buffer.flush(); '
                 'sys.stderr.write("write failure marker\\n"); raise SystemExit(7)')
        result = self.run_stage(b'IN', child=child)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, b'OUTIN')
        self.assertEqual((self.capture / 'cups3-reference.out.spl').read_bytes(), b'OUTIN')
        self.assertIn(b'vendor-marker=write', result.stderr)

    def test_storage_preflight_failure_fails_open(self):
        self.arm()
        data = b'unchanged-through-child'
        result = self.run_stage(data, min_free=2**63)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, data[::-1])
        self.assertIn(b'capture status=skipped reason=storage', result.stderr)
        self.assertFalse((self.capture / 'cups3-reference.in.raster').exists())

    def test_size_limit_discards_capture_but_forwards_full_stream(self):
        self.arm()
        data = os.urandom(1024 * 1024)
        result = self.run_stage(data, max_stream=64 * 1024)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, data[::-1])
        self.assertIn(b'capture status=failed reason=limit', result.stderr)
        self.assertFalse((self.capture / 'cups3-reference.in.raster').exists())

    def test_high_volume_bidirectional_no_deadlock(self):
        self.arm()
        data = os.urandom(12 * 1024 * 1024 + 17)
        # Child writes substantial stdout while consuming stdin in chunks.
        child = ('import os; '
                 'buf=b""; '
                 'exec("while True:\\n d=os.read(0,65536)\\n if not d: break\\n os.write(1,d)\\n")')
        result = self.run_stage(data, child=child)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, data)
        self.assertEqual((self.capture / 'cups3-reference.in.raster').read_bytes(), data)
        self.assertEqual((self.capture / 'cups3-reference.out.spl').read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
