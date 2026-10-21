"""Reviewed source excerpts exercise actual patch application without print jobs."""
import importlib.util
from pathlib import Path
import re
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/lifecycle'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(FIXTURES, self.root, dirs_exist_ok=True)
        self.pappl = load('patch-pappl-lifecycle')

    def test_presence_order_and_first_attempt_only(self):
        self.pappl.patch(self.root)
        def source(name):
            return (self.root / 'pappl' / name).read_text()
        job = source('job.c')
        self.assertLess(job.index('job-create begin'), job.index('job-create result=1'))
        self.assertLess(job.index('stage=registered'), job.index('_papplPrinterCheckJobs(job->printer)'))
        self.assertLess(job.index('scheduler-launch begin'), job.index('scheduler-launch result=0'))
        receipt = source('job-ipp.c')
        markers = ['document-receipt begin', 'document-spool begin', 'document-spool first-write', 'document-spool complete']
        positions = [receipt.index(x) for x in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('if (!total)\n      papplLogJob', receipt)
        process = source('job-process.c')
        self.assertIn('document-stream complete state=%d', process)
        self.assertIn('document-receipt aborted', receipt)
        for mode in ('spooled', 'streaming'):
            self.assertIn('execution mode=' + mode, process)
        self.assertLess(process.index('device-open begin'), process.index('= papplDeviceOpen'))
        self.assertLess(process.index('= papplDeviceOpen'), process.index('device-open result='))
        for text in ('device-open begin', 'device-open result='):
            pos = process.index(text)
            self.assertIn('if (first_open)', process[pos-100:pos])
        self.assertIn('IPP_OP_PRINT_JOB || op == IPP_OP_CREATE_JOB || op == IPP_OP_SEND_DOCUMENT', source('client-ipp.c'))

    def test_fail_closed_no_partial_writes_or_reapply(self):
        for mode in ('missing', 'duplicate'):
            with self.subTest(mode=mode):
                path = self.root / 'pappl/job-process.c'
                original = path.read_text()
                anchor = self.pappl.RULES['job-process.c'][-1][0]
                path.write_text(original.replace(anchor, '') if mode == 'missing' else original + '\n' + anchor)
                before = {p: p.read_bytes() for p in (self.root / 'pappl').iterdir()}
                with self.assertRaises(ValueError):
                    self.pappl.patch(self.root)
                self.assertEqual(before, {p: p.read_bytes() for p in before})
                path.write_text(original)
        self.pappl.patch(self.root)
        before = {p: p.read_bytes() for p in (self.root / 'pappl').iterdir()}
        with self.assertRaises(ValueError):
            self.pappl.patch(self.root)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_new_logs_have_no_sensitive_sources_or_named_prefix(self):
        # Check actual added logger statements, excluding retained upstream logs.
        logs = []
        for rules in self.pappl.RULES.values():
            for old, new in rules:
                for statement in re.findall(r'papplLog(?:Job)?\([^;]+;', new):
                    if 'lifecycle stage=' in statement:
                        logs.append(statement)
                        self.assertIn('PAPPL_LOGLEVEL_INFO', statement)
                        self.assertLess(len(statement), 600)
                        for forbidden in ('->name', '->username', '->device_uri', 'filename', 'strerror', 'ippGetString', 'getenv', 'papplLogClient', 'papplLogPrinter', '%p'):
                            self.assertNotIn(forbidden, statement)
                        # Every string interpolation must come from fixed ternary enums.
                        if '%s' in statement:
                            self.assertIn(' ? "', statement)
                            self.assertNotRegex(statement, r':\s*[a-zA-Z_]\w*\s*\);')
        self.assertGreater(len(logs), 20)
        self.assertNotIn('papplLogPrinter(', '\n'.join(new for rules in self.pappl.RULES.values() for old, new in rules if 'lifecycle' in new and 'papplLogPrinter' not in old))

    def test_retrofit_entries_precede_binding(self):
        load('patch-job-path').patch(self.root)
        source = (self.root / 'pappl-retrofit/print-job.c').read_text()
        for mode in ('spooled', 'raw', 'streaming'):
            entry = source.index('retrofit-entry mode=' + mode)
            binding = source.index('  pocLogBinding(job);', entry)
            self.assertLess(entry, binding)
            self.assertNotIn('  pocLogBinding(job);', source[entry:binding])
        self.assertEqual(source.count('lifecycle stage=retrofit-entry'), 3)

    def test_retrofit_entry_anchor_drift_leaves_sources_untouched(self):
        path = self.root / 'pappl-retrofit/print-job.c'
        original = path.read_text()
        anchors = (
            '  job_options = papplJobCreatePrintOptions(job, 1, INT_MAX, 1);',
            '  papplLogJob(job, PAPPL_LOGLEVEL_DEBUG,\n\t      "Printing job in streaming mode");',
            '  if (!job || !device)\n    return (false);',
        )
        for anchor in anchors:
            with self.subTest(anchor=anchor):
                path.write_text(original.replace(anchor, '/* drift */'))
                before = {p: p.read_bytes() for p in (self.root / 'pappl-retrofit').iterdir()}
                with self.assertRaises(ValueError):
                    load('patch-job-path').patch(self.root)
                self.assertEqual(before, {p: p.read_bytes() for p in before})
                path.write_text(original)

    def test_release_and_startup(self):
        self.assertIn('ARG BUILD_VERSION=0.1.27', (ROOT / 'Dockerfile').read_text())
        self.assertIn('version: "0.1.27"', (ROOT / 'config.yaml').read_text())
        self.assertIn('stage=startup version=0.1.27 diagnostics=enabled', (ROOT / 'scripts/entrypoint.sh').read_text())
        self.assertIn('python3 /tmp/patch-pappl-lifecycle.py .', (ROOT / 'Dockerfile').read_text())
