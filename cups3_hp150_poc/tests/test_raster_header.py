"""Header-only shim and real CUPS differential fixtures; no print actions."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('raster_stage', ROOT / 'scripts/job-stage.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
VALUES = (13, 3, 600, 600, 8, 24, 3, 39, 1, 0, 0, 0, 0, 0)


def record(values=VALUES):
    return b'HP150_RASTER_HEADER 1 ' + b' '.join(str(v).encode() for v in values)


class RasterLoggingTests(unittest.TestCase):
    def test_fields_rounding_relations_and_maximum_bounds(self):
        message = stage.raster_header_message(record())
        for key, value in zip(stage.RASTER_FIELDS, VALUES):
            self.assertIn(f'{key}={value}', message)
        self.assertIn('expected_bytes_per_line=39 packed_relation=equal', message)
        for actual, relation in [(1, 'below'), (2, 'equal'), (3, 'above')]:
            values = list(VALUES)
            values[5], values[7] = 1, actual
            self.assertIn(f'expected_bytes_per_line=2 packed_relation={relation}',
                          stage.raster_header_message(record(values)))
        message = stage.raster_header_message(record([0xffffffff] * 14))
        self.assertIn('expected_bytes_per_line=2305843008139952129', message)
        self.assertLess(len(message), 768)
        self.assertLess(len(record([0xffffffff] * 14)), 256)

    def test_malformed_records_never_expose_input(self):
        for data in (b'SECRET', record() + b' SECRET', record()[:-2],
                     record().replace(b'13', b'-1', 1),
                     record().replace(b'13', b'4294967296', 1),
                     record().replace(b'13', b'00000000000', 1),
                     record().replace(b'13', b'\xff', 1),
                     b'x' * 10000, b'HP150_RASTER_HEADER 2 ' + record()):
            self.assertIsNone(stage.raster_header_message(data), data)

    def test_supervisor_first_only_fragmented_bounded_and_stage_scoped(self):
        valid = record() + b'\n'
        payload = b'SECRET\n' + b'x' * 300 + valid + b'\n' + valid * 1000
        # The first valid record is split across writes. Overlong lines drop fully.
        code = ('import os; os.write(2,' + repr(payload[:330]) + ');'
                'os.write(2,' + repr(payload[330:]) + ');')
        with contextlib.redirect_stderr(io.StringIO()) as log:
            result = stage.supervise('rastertospl', [sys.executable, '-c', code], '7', 3)
        self.assertEqual(result, 0)
        self.assertEqual(log.getvalue().count('raster-header page=first'), 1)
        self.assertNotIn('SECRET', log.getvalue())
        self.assertLess(len(log.getvalue()), 1000)
        with contextlib.redirect_stderr(io.StringIO()) as log:
            stage.supervise('usb', [sys.executable, '-c',
                                   'import os; os.write(2,' + repr(valid) + ')'], '7', 3)
        self.assertNotIn('raster-header', log.getvalue())

    def test_raster_child_has_no_preload_and_tokens_remain_scrubbed(self):
        class Stop(Exception):
            pass
        for name in ('usb', 'rastertospl'):
            with patch.dict(os.environ, {'SUPERVISOR_TOKEN': 'SECRET', 'HASSIO_TOKEN': 'SECRET'}), \
                 patch.object(stage.subprocess, 'Popen', side_effect=Stop) as spawn, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(Stop):
                    stage.supervise(name, ['dummy'], '7')
            env = spawn.call_args.kwargs['env']
            self.assertNotIn('SUPERVISOR_TOKEN', env)
            self.assertNotIn('HASSIO_TOKEN', env)
            if name == 'rastertospl':
                self.assertNotIn('LD_PRELOAD', env)
            else:
                self.assertEqual(env.get('LD_PRELOAD'), os.environ.get('LD_PRELOAD'))
            self.assertNotIn('stdin', spawn.call_args.kwargs)
            self.assertNotIn('stdout', spawn.call_args.kwargs)
            self.assertFalse(spawn.call_args.kwargs['close_fds'])

    def test_existing_preload_is_removed_without_logging(self):
        class Stop(Exception):
            pass
        with patch.dict(os.environ, {'LD_PRELOAD': 'PRELOAD_SECRET'}),              patch.object(stage.subprocess, 'Popen', side_effect=Stop) as spawn,              contextlib.redirect_stderr(io.StringIO()) as log:
            with self.assertRaises(Stop):
                stage.supervise('rastertospl', ['dummy'], '7')
        self.assertNotIn('LD_PRELOAD', spawn.call_args.kwargs['env'])
        self.assertNotIn('PRELOAD_SECRET', log.getvalue())

    def test_no_stream_pixel_or_capture_code_and_build_integration(self):
        source = (ROOT / 'scripts/raster-header-diagnostics.c').read_text()
        for forbidden in ('cupsRasterReadPixels(', 'cupsRasterOpen(', 'read(', 'fopen(',
                          'getenv(', 'cupsRasterReadHeader2(r, &full);\n  cupsRaster'):
            self.assertNotIn(forbidden, source)
        self.assertEqual(source.count('cupsRasterReadHeader2(r, &full)'), 1)
        self.assertIn('errno = saved_errno;', source)
        docker = (ROOT / 'Dockerfile').read_text()
        self.assertIn('-o /opt/poc/lib/raster-header-diagnostics.so -lcups', docker)


@unittest.skipUnless(Path('/usr/include/cups/raster.h').exists() and shutil.which('cc'),
                     'real CUPS development headers required (run in Debian build environment)')
class RasterDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name)
        cls.shim = cls.path / 'shim.so'
        cls.probe = cls.path / 'probe'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-O2', '-fPIC', '-shared',
                        str(ROOT / 'scripts/raster-header-diagnostics.c'),
                        '-o', str(cls.shim), '-lcups'], check=True, capture_output=True)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-Wno-deprecated-declarations',
                        str(ROOT / 'tests/fixtures/raster-header.c'),
                        '-o', str(cls.probe), '-lcups'], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def raster(self, mode=1, layout=0):
        result = subprocess.run([str(self.probe), 'write', str(mode), str(layout)],
                                capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def compare(self, data, filename=False, closed_stderr=False):
        env = dict(os.environ)
        env.pop('LD_PRELOAD', None)
        args = [str(self.probe), 'read']
        if filename:
            path = self.path / 'FILENAME_SECRET'
            path.write_bytes(data)
            args.append(str(path))
        stderr = subprocess.DEVNULL if closed_stderr else subprocess.PIPE
        baseline = subprocess.run(args, input=b'' if filename else data, env=env,
                                  stdout=subprocess.PIPE, stderr=stderr, timeout=3)
        measured = subprocess.run(args, input=b'' if filename else data,
                                  env={**env, 'LD_PRELOAD': str(self.shim)},
                                  stdout=subprocess.PIPE, stderr=stderr, timeout=3)
        self.assertEqual(measured.returncode, baseline.returncode)
        self.assertEqual(measured.stdout, baseline.stdout)  # full headers, errno, pixel bytes
        if not closed_stderr:
            lines = measured.stderr.splitlines()
            self.assertLessEqual(len(lines), 1)
            for line in lines:
                self.assertIsNotNone(stage.raster_header_message(line))
                self.assertLess(len(line), 256)
                for secret in (b'HEADER_SECRET', b'SIZE_SECRET', b'FILENAME_SECRET'):
                    self.assertNotIn(secret, line)
        return measured

    def test_legacy_compressed_pwg_and_layouts_two_pages(self):
        for mode in (1, 2, 3):  # v1, compressed v2, PWG
            for layout in (0, 1, 2, 3):  # RGB chunked/banded/planar, packed 1-bit
                if mode == 3 and layout in (1, 2):
                    continue  # PWG requires chunked order
                with self.subTest(mode=mode, layout=layout):
                    result = self.compare(self.raster(mode, layout))
                    self.assertEqual(len(result.stderr.splitlines()), 1)
                    msg = stage.raster_header_message(result.stderr.strip())
                    self.assertIn('cupsNumColors=' + ('1' if layout == 3 else '3'), msg)
                    self.assertIn('packed_relation=' + ('above' if layout == 1 else 'equal'), msg)

    def test_named_file_input_and_suppressed_diagnostics(self):
        self.compare(self.raster(), filename=True)
        self.compare(self.raster(2), closed_stderr=True)

    def test_real_shim_through_supervisor_preserves_stdout_and_redacts(self):
        data = self.raster(2)
        baseline = subprocess.run([str(self.probe), 'read'], input=data,
                                  capture_output=True, timeout=3)
        runner = (
            'import importlib.util,sys; '
            f's=importlib.util.spec_from_file_location("stage",{str(ROOT / "scripts/job-stage.py")!r}); '
            'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
            f'm.RASTER_SHIM={str(self.shim)!r}; '
            f'sys.exit(m.supervise("rastertospl",[{str(self.probe)!r},"read"],"7",3))')
        result = subprocess.run([sys.executable, '-c', runner], input=data,
                                capture_output=True, timeout=5,
                                env={**os.environ, 'SUPERVISOR_TOKEN': 'TOKEN_SECRET'})
        self.assertEqual(result.returncode, baseline.returncode)
        self.assertEqual(result.stdout, baseline.stdout)
        self.assertEqual(result.stderr.count(b'raster-header page=first'), 1)
        self.assertIn(b'cupsNumColors=3', result.stderr)
        self.assertIn(b'expected_bytes_per_line=39 packed_relation=equal', result.stderr)
        self.assertIn(b'finished exit=0', result.stderr)
        for forbidden in (b'HEADER_SECRET', b'SIZE_SECRET', b'TOKEN_SECRET',
                          b'HP150_RASTER_HEADER'):
            self.assertNotIn(forbidden, result.stderr)

    def test_empty_corrupt_and_truncated_raster(self):
        data = self.raster()
        for broken in (b'', b'INVALID_SECRET', data[:4], data[:100], data[:424],
                       data[:430], data[:-5]):
            with self.subTest(length=len(broken)):
                self.compare(broken)

    def test_exact_abi_return_errno_and_no_second_decoder(self):
        # Fake the extended decoder to control every byte and errno, count calls,
        # and expose zero-on-failure. Link the production shim itself, not a copy.
        source = r'''
#include <cups/raster.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
static unsigned calls;
unsigned cupsRasterReadHeader2(cups_raster_t *r, cups_page_header2_t *h) {
  (void)r; calls++;
  memset(h, calls == 1 ? 0x01 : 0, sizeof(*h));
  errno = EAGAIN;
  return calls == 1 ? 1 : 0;
}
int main(void) {
  cups_page_header_t h;
  for (unsigned call=1; call<=2; call++) {
    errno = EACCES;
    unsigned result = cupsRasterReadHeader(NULL, &h);
    if (calls != call || result != (call == 1) || errno != EAGAIN) return 1;
    unsigned char expected[sizeof(h)];
    memset(expected, call == 1 ? 0x01 : 0, sizeof(expected));
    if (memcmp(&h, expected, sizeof(h))) return 2;
  }
  return 0;
}
'''
        p = self.path / 'fake.c'
        p.write_text(source)
        binary = self.path / 'fake'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-Wno-deprecated-declarations', str(p),
                        str(ROOT / 'scripts/raster-header-diagnostics.c'),
                        '-o', str(binary)], check=True, capture_output=True)
        result = subprocess.run([str(binary)], capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stderr.splitlines()), 1)
