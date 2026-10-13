"""Compile and execute the actual injected metadata code; no PAPPL jobs/devices."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('metadata_patch', ROOT / 'scripts/patch-job-path.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name)
        compiler = shutil.which('cc')
        if not compiler:
            raise RuntimeError('C compiler required for metadata tests')
        for tool in ('pdfinfo', 'exiftool'):
            subprocess.run([compiler, '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'tests/fixtures/metadata-helper.c'),
                            '-o', str(cls.path / tool)], check=True, capture_output=True)
        original = (ROOT / 'scripts/pdf-metadata-upstream.c').read_text()
        source = patcher.bound_metadata("//\n// '_prASCII85()'\n" + 'pappl_content_t\n' + original)
        cls.production = source
        source = source.replace('"/usr/bin/pdfinfo"', '"' + str(cls.path / 'pdfinfo') + '"')
        source = source.replace('"/usr/bin/exiftool"', '"' + str(cls.path / 'exiftool') + '"')
        preamble = r"""#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <stdlib.h>
#include <stdarg.h>
#include <errno.h>
typedef void pappl_job_t;
typedef int pappl_content_t;
#define PAPPL_CONTENT_AUTO 1
#define PAPPL_CONTENT_GRAPHIC 2
#define PAPPL_CONTENT_PHOTO 4
#define PAPPL_CONTENT_TEXT 8
#define PAPPL_CONTENT_TEXT_AND_GRAPHIC 16
#define PAPPL_LOGLEVEL_INFO 3
static const char *filename;
static const char *format;
static const char *papplJobGetDocumentFormat(void *job, int n) { (void)job; (void)n; return format; }
static const char *papplJobGetDocumentFilename(void *job, int n) { (void)job; (void)n; return filename; }
static void papplLogJob(void *job, int level, const char *fmt, ...) {
 (void)job; (void)level;
 va_list ap; va_start(ap, fmt); vfprintf(stderr, fmt, ap); va_end(ap);
 fputc('\n', stderr); errno = EIO;
}
"""
        main = r"""
int main(int argc, char **argv) {
 if (argc != 3) return 7;
 filename = argv[1]; format = argv[2];
 int result = _prGetFileContentType(NULL);
 int status;
 errno = 0;
 if (waitpid(-1, &status, WNOHANG) != -1 || errno != ECHILD) return 8;
 printf("%d\n", result);
 errno = EACCES;
 pocMetadataMarker(NULL, "metadata test=errno");
 return errno == EACCES ? 0 : 9;
}
"""
        (cls.path / 'probe.c').write_text(preamble + source + main)
        subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                        str(cls.path / 'probe.c'), '-o', str(cls.path / 'probe')],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def invoke(self, pdf='success', exif='fail', expected=8, format='application/pdf'):
        filename = str(self.path / "FILE_SECRET spaces ; $(touch PWNED) ' &.pdf")
        env = {**os.environ, 'PDF_MODE': pdf, 'EXIF_MODE': exif,
               'EXPECTED_FILENAME': filename}
        start = time.monotonic()
        result = subprocess.run([str(self.path / 'probe'), filename, format],
                                env=env, capture_output=True, text=True, timeout=7)
        elapsed = time.monotonic() - start
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(expected), result.stderr)
        for secret in ('FILE_SECRET', 'METADATA_SECRET', 'STDERR_SECRET', filename):
            self.assertNotIn(secret, result.stderr)
        self.assertFalse((self.path / 'PWNED').exists())
        return elapsed, result.stderr

    def test_direct_argv_and_no_shell(self):
        for forbidden in ('popen(', 'pclose(', 'system(', 'snprintf(command', 'PDF metadata line', 'getenv('):
            self.assertNotIn(forbidden, self.production)
        self.assertIn('execv(tool, argv)', self.production)
        self.invoke()  # Fixture asserts exact argc and weird filename bytes.

    def test_success_and_marker_order(self):
        elapsed, log = self.invoke()
        self.assertLess(elapsed, 1)
        labels = ['metadata-launch phase=begin', 'metadata-launch phase=end',
                  'metadata-scan phase=begin', 'metadata-scan phase=end',
                  'metadata-wait phase=begin', 'metadata-wait phase=end',
                  'metadata outcome=complete', 'metadata detection=recognized']
        positions = [log.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(log.count('metadata-launch phase=begin'), 1)

    def test_fallback_and_content_mapping(self):
        for mode, expected in [('success', 8), ('photo', 4), ('graphics', 2), ('combined', 16), ('no-newline', 8)]:
            with self.subTest(mode=mode):
                _, log = self.invoke('fail', mode, expected)
                self.assertEqual(log.count('metadata-launch phase=begin'), 2)
        self.invoke('nonzero-output', 'photo', 4)

    def test_invalid_metadata_fails_open(self):
        for mode in ('fail', 'empty', 'unknown', 'empty-value', 'malformed', 'nul', 'large'):
            with self.subTest(mode=mode):
                elapsed, log = self.invoke(mode, 'fail', 1)
                self.assertLess(elapsed, 1)
                self.assertIn('metadata detection=auto', log)
        self.invoke('unknown', 'photo', 4)

    def test_each_deadline_and_reaping_including_closed_stdout(self):
        for mode in ('hang', 'ignore-term', 'close-hang'):
            with self.subTest(mode=mode):
                elapsed, log = self.invoke(mode, 'photo', 4)
                self.assertGreaterEqual(elapsed, 2.4)
                self.assertLess(elapsed, 3.3)
                self.assertIn('metadata outcome=bounded-failure', log)
        elapsed, _ = self.invoke('hang', 'ignore-term', 1)
        self.assertGreaterEqual(elapsed, 4.9)
        self.assertLess(elapsed, 5.8)

    def test_repeated_success_no_zombies_or_deadlock(self):
        for _ in range(20):
            self.invoke()

    def test_only_metadata_function_and_helper_change(self):
        original = (ROOT / 'scripts/pdf-metadata-upstream.c').read_text()
        source = "//\n// '_prASCII85()'\n" + original + "\n// AFTER"
        actual = patcher.bound_metadata(source)
        helper = (ROOT / 'scripts/pdf-metadata.h').read_text()
        actual = actual.replace(helper, '', 1)
        start = actual.index('_prGetFileContentType(pappl_job_t *job)')
        end = actual.index('\n}', start) + 2
        self.assertEqual(actual[:start] + original.rstrip() + actual[end:], source)

    def test_both_missing(self):
        for tool in ('pdfinfo', 'exiftool'):
            (self.path / tool).rename(self.path / (tool + '.saved'))
        try:
            self.invoke(expected=1)
        finally:
            for tool in ('pdfinfo', 'exiftool'):
                (self.path / (tool + '.saved')).rename(self.path / tool)

    def test_non_pdf_mapping_unchanged(self):
        for format, expected in [('image/jpeg', 4), ('image/png', 2), ('image/urf', 1)]:
            _, log = self.invoke(expected=expected, format=format)
            self.assertNotIn('metadata-launch', log)

    def test_whole_function_drift_rejected(self):
        original = (ROOT / 'scripts/pdf-metadata-upstream.c').read_text()
        with self.assertRaises(ValueError):
            patcher.bound_metadata("//\n// '_prASCII85()'\n" + original.replace('"Word"', '"Changed"'))
