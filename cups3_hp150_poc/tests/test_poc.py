import importlib.util
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
