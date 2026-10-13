"""Verify actual pinned PDF path instrumentation without submitting jobs."""
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('boundaries', ROOT / 'scripts/patch-job-path.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)
MARKER = re.compile(r'  \{ int poc_saved_errno = errno;\n    papplLogJob\(job, PAPPL_LOGLEVEL_INFO, "lifecycle stage=retrofit-[a-z-]+ phase=(?:begin|end)"\);\n    errno = poc_saved_errno; \}\n')


class RetrofitBoundaryTests(unittest.TestCase):
    def sources(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'tests/fixtures/lifecycle', root, dirs_exist_ok=True)
            # Baseline is the exact pre-0.1.23 patch, including all older diagnostics.
            instrument = patcher.instrument_retrofit
            try:
                patcher.instrument_retrofit = lambda source: source
                patcher.patch(root)
            finally:
                patcher.instrument_retrofit = instrument
            baseline = (root / 'pappl-retrofit/print-job.c').read_text()
            return baseline, instrument(baseline)

    def test_only_errno_preserving_literal_info_markers_are_added(self):
        baseline, actual = self.sources()
        markers = MARKER.findall(actual)
        self.assertEqual(len(markers), 36)
        # Whitespace-normalized identity proves every original condition, call,
        # argument, read, launch and existing diagnostic is unchanged.
        stripped = MARKER.sub('', actual)
        self.assertEqual(re.sub(r'\s+', '', baseline), re.sub(r'\s+', '', stripped))
        for operation in ('read(', 'fgets(', 'getline(', 'popen(', 'pclose(', 'open(', 'rewind(', 'cfFilterChain(', 'pocChain('):
            self.assertEqual(baseline.count(operation), actual.count(operation), operation)

    def test_spooled_pdf_order_and_conditional_metadata_scan(self):
        _, source = self.sources()
        callback = source[source.index('bool\n_prFilter('):]
        stages = ['print-options', 'job-data', 'filter-data', 'input-filename',
                  'input-open', 'format', 'conversion', 'ppd-load',
                  'backend-connect', 'pdf-scan', 'chain-setup', 'status',
                  'impressions', 'output-open']
        labels = ['retrofit-entry mode=spooled']
        for stage in stages:
            labels += [f'retrofit-{stage} phase=begin', f'retrofit-{stage} phase=end']
        labels += ['path stage=filter-chain started source=spooled', 'pocChain(fd,']
        positions = [callback.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        metadata = source[source.index('FILE *pd = popen')-250:source.index('    job_options->print_content_optimize')]
        labels = ['metadata-launch phase=begin', 'popen(command, "r")',
                  'metadata-launch phase=end', 'if (!pd)', 'else',
                  'metadata-scan phase=begin', 'while (fgets(',
                  'metadata-scan phase=end', 'metadata-wait phase=begin',
                  'pclose(pd)', 'metadata-wait phase=end']
        positions = [metadata.index(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(callback.index('strcmp(informat, "application/pdf")'), callback.index('retrofit-pdf-scan phase=begin'))
        self.assertLess(callback.index('rewind(fp)'), callback.index('retrofit-pdf-scan phase=end'))

    def test_logging_preserves_errno_even_when_logger_changes_it(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('C compiler required')
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp)
            code = '''#include <errno.h>
#define PAPPL_LOGLEVEL_INFO 3
static void papplLogJob(void *job, int level, const char *message)
{ (void)job; (void)level; (void)message; errno = EIO; }
int main(void) { void *job = 0; errno = EACCES;
'''
            code += patcher.diagnostic_marker('input-open', 'begin')
            code += patcher.diagnostic_marker('input-open', 'end')
            code += 'return errno == EACCES ? 0 : 1; }\n'
            (path / 'marker.c').write_text(code)
            subprocess.run([compiler, '-Wall', '-Wextra', '-Werror', str(path / 'marker.c'), '-o', str(path / 'marker')], check=True, capture_output=True)
            subprocess.run([str(path / 'marker')], check=True)

    def test_boundary_anchor_drift_fails_before_source_write(self):
        for anchor in ('  filename = papplJobGetDocumentFilename(job, 1);',
                       '  ppdFilterLoadPPD(job_data->filter_data);',
                       '    FILE *pd = popen(command, "r");'):
            with self.subTest(anchor=anchor), tempfile.TemporaryDirectory(dir=ROOT) as tmp:
                root = Path(tmp)
                shutil.copytree(ROOT / 'tests/fixtures/lifecycle', root, dirs_exist_ok=True)
                path = root / 'pappl-retrofit/print-job.c'
                path.write_text(path.read_text().replace(anchor, '/* drift */'))
                before = {p: p.read_bytes() for p in (root / 'pappl-retrofit').iterdir()}
                with self.assertRaises(ValueError):
                    patcher.patch(root)
                self.assertEqual(before, {p: p.read_bytes() for p in before})
