import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('compat', ROOT / 'scripts/check-pappl1-compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


class CompatibilityGateTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'config.h').write_text('#define HAVE_PAPPL1 1\n')
        (root / 'pappl-retrofit').mkdir()
        header = root / 'pappl-retrofit/pappl1-private.h'
        header.write_text('# define papplJobGetDocumentFormat(job, doc) papplJobGetFormat(job)\n'
                          '# define papplJobGetDocumentFilename(job, doc) papplJobGetFilename(job)\n')
        return header

    def test_compile_link_only_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            with patch.object(compat.subprocess, 'run') as run:
                compat.main(root)
            run.assert_called_once()
            args = run.call_args.args[0]
            self.assertEqual(args[:3], ['make', '-f', 'Makefile'])
            self.assertTrue(run.call_args.kwargs['check'])
            self.assertEqual(run.call_args.kwargs['cwd'], root)
            probe = Path(next(a.split('=', 1)[1] for a in args if a.startswith('POC_COMPAT_SOURCE=')))
            self.assertFalse(probe.parent.exists())

    def test_rejects_wrong_configuration_and_mapping_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = self.fixture(root)
            with patch.object(compat.subprocess, 'run') as run:
                (root / 'config.h').write_text('/* #undef HAVE_PAPPL1 */\n')
                with self.assertRaises(ValueError):
                    compat.main(root)
                (root / 'config.h').write_text('#define HAVE_PAPPL1 1\n')
                for suffix in ['Format', 'Filename']:
                    original = header.read_text()
                    header.write_text(original.replace('papplJobGet' + suffix + '(job)', 'unexpected(job)'))
                    with self.assertRaises(ValueError):
                        compat.main(root)
                    header.write_text(original)
                run.assert_not_called()

    def test_docker_gate_before_build(self):
        docker = (ROOT / 'Dockerfile').read_text()
        gate = docker.index('&& python3 /tmp/check-pappl1-compat.py /tmp/retrofit')
        self.assertLess(docker.rindex('./configure', 0, gate), gate)
        self.assertLess(gate, docker.index('&& make -j2', gate))
