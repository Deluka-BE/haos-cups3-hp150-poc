"""HP quality experiment at the proprietary filter boundary only."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1] / 'scripts/job-stage.py'
spec = importlib.util.spec_from_file_location('quality_stage', STAGE)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
EXPECTED = {'Screen': 'Enhanced', 'secBrightness': '50', 'secContrast': '50',
            'secSaturation': '50', 'CyanRed': '50', 'MagentaGreen': '50', 'YellowBlue': '50'}


class QualityOptionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ppd = Path(self.tmp.name) / 'hp.ppd'
        self.ppd.write_text(''.join(f'*Default{k}: {v}\n' for k, v in EXPECTED.items()))

    def normalize(self, options):
        return stage.normalize_hp_quality(options, self.ppd)

    def test_bad_overrides_and_duplicates_replaced_by_exact_defaults(self):
        bad = 'Screen=PrinterDefault secSaturation=70 ' + ' '.join(
            f'{key}=20' for key in EXPECTED) + ' screen=Normal secSaturation="90"'
        result = self.normalize(bad).split()
        self.assertEqual(result, [f'{k}={v}' for k, v in EXPECTED.items()])
        self.assertEqual(len(result), len(EXPECTED))

    def test_correct_values_remain_correct_and_idempotent(self):
        correct = ' '.join(f'{k}={v}' for k, v in EXPECTED.items())
        self.assertEqual(self.normalize(correct), correct)
        self.assertEqual(self.normalize(self.normalize(correct)), correct)
        self.assertEqual(self.normalize(self.normalize('')), correct)

    def test_unrelated_options_preserved_with_quotes_and_escapes(self):
        unrelated = r'''Quality=600x600_1 Resolution=600dpi PageSize=A4 copies=2 ColorModel=RGB Trapping=Medium TonerSaveMode=Standard note="Screen=Normal secSaturation=70" other='two words' escaped=two\ words'''
        result = self.normalize(unrelated + ' Screen=PrinterDefault secSaturation=70')
        self.assertTrue(result.startswith(unrelated + ' '))
        self.assertEqual(self.normalize(result), result)

    def test_only_explicit_expected_ppd_defaults_are_normalized(self):
        self.ppd.write_text('*DefaultScreen: Enhanced\n*DefaultsecSaturation: 60\n')
        self.assertEqual(self.normalize('secSaturation=70 CyanRed=20 Screen=Normal'),
                         'secSaturation=70 CyanRed=20 Screen=Enhanced')
        self.ppd.write_text('*DefaultQuality: 600x600_2\n')
        self.assertEqual(self.normalize('Screen=Normal  CyanRed=20'), 'Screen=Normal  CyanRed=20')

    def test_malformed_options_rejected(self):
        with self.assertRaises(ValueError):
            self.normalize('note="unterminated Screen=Normal')

    def test_main_normalizes_before_supervision_and_boundary_capture(self):
        args = ['7', 'user', 'title', '1', 'Screen=PrinterDefault secSaturation=70', '/tmp/input.raster']
        with patch.object(sys, 'argv', ['job-stage.py', 'rastertospl', *args]), \
                patch.dict(os.environ, {'PPD': str(self.ppd)}), \
                patch.object(stage, 'supervise', return_value=0) as supervise:
            self.assertEqual(stage.main(), 0)
        kind, command, job = supervise.call_args.args
        self.assertEqual(kind, 'rastertospl')
        self.assertEqual(job, '7')
        self.assertEqual(command[:5], ['/work/filter/rastertospl.real', *args[:4]])
        self.assertEqual(command[6], args[5])
        self.assertEqual(command[5], self.normalize(args[4]))
        self.assertEqual(stage.capture_boundary(command, {'PPD': str(self.ppd)})['argv'][5],
                         command[5])
