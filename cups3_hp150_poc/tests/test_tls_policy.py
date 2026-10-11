import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tls_patch', ROOT / 'scripts/patch-pappl-tls.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TLSPolicyTests(unittest.TestCase):
    def test_both_txt_paths_are_guarded_and_source_drift_fails_closed(self):
        source = ('  TXTRecordSetValue(&txt, "TLS", 3, "1.2");\n'
                  '  txt = avahi_string_list_add_printf(txt, "TLS=1.2");\n')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dnssd.c'
            path.write_text(source)
            module.patch(path)
            self.assertEqual(path.read_text().count('if (!(printer->system->options & PAPPL_SOPTIONS_NO_TLS))'), 2)
            for drift in ('', source + source, path.read_text()):
                path.write_text(drift)
                with self.assertRaises(ValueError):
                    module.patch(path)
                self.assertEqual(path.read_text(), drift)

    def test_release_launch_enforces_no_tls(self):
        entry = (ROOT / 'scripts/entrypoint.sh').read_text()
        self.assertIn('-o server-options=no-tls', entry)
        docker = (ROOT / 'Dockerfile').read_text()
        self.assertIn('dpkg-buildpackage -b -uc -us -j2', docker)
        self.assertIn('python3 /tmp/patch-pappl-tls.py pappl/dnssd.c', docker)


if __name__ == '__main__':
    unittest.main()
