"""Exercise option parsing and the real shell argument construction without services."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('log_level', ROOT / 'scripts/log-level.py')
LOG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOG)


class LogLevelTests(unittest.TestCase):
    def test_defaults_and_schema(self):
        config = (ROOT / 'config.yaml').read_text()
        self.assertIn('options:\n  log_level: info\n', config)
        self.assertIn('schema:\n  log_level: list(' + '|'.join(LOG.LEVELS) + ')\n', config)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'options.json'
            self.assertEqual(LOG.read_level(path), 'info')
            path.write_text('{}')
            self.assertEqual(LOG.read_level(path), 'info')

    def launch(self, raw):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            stage = Path(tmp)
            options = stage / 'options.json'
            options.write_text(raw if raw is not None else '{}')
            helper = stage / 'log-level.py'
            helper.write_text((ROOT / 'scripts/log-level.py').read_text().replace("Path('/data/options.json')", repr(str(options))))
            source = (ROOT / 'scripts/entrypoint.sh').read_text()
            source = source[:source.index('python3 /opt/poc/scripts/validate-driver.py')] + source[source.index('export LD_LIBRARY_PATH='):]
            source = source.replace('cd /work/filter', ':')
            for name in ('state-runtime', 'runtime-check', 'usb-diagnostics', 'usb-settle'):
                source = source.replace('python3 /opt/poc/scripts/' + name + '.py', ':')
            source = source.replace('exec python3 /opt/poc/scripts/mdns-runtime.py', 'exec')
            entry = stage / 'entrypoint.sh'
            entry.write_text(source)
            app = stage / 'legacy-printer-app'
            app.write_text('#!' + sys.executable + '\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
            app.chmod(0o755)
            # Exercise the actual privileged bootstrap and real shell, with only
            # identity/setup syscalls stubbed. Delete options at the transition:
            # the app path must work without any options file access afterward.
            bootstrap = stage / 'usb-runtime.py'
            bootstrap.write_text((ROOT / 'scripts/usb-runtime.py').read_text())
            wrapper = stage / 'launch.py'
            wrapper.write_text("import os, runpy, sys\n"
                "r = runpy.run_path(sys.argv[1])\n"
                "g = r['main'].__globals__\n"
                "g['prepare_state_runtime'] = lambda: None\n"
                "g['prepare_mdns_runtime'] = lambda: None\n"
                "g['hp_groups'] = lambda: [42]\n"
                "options_path = sys.argv[3]\n"
                "def drop(groups):\n"
                "    assert groups == [42]\n"
                "    assert os.environ['POC_LOG_LEVEL'] in ('fatal', 'error', 'warn', 'info', 'debug')\n"
                "    assert 'SUPERVISOR_TOKEN' not in os.environ and 'HASSIO_TOKEN' not in os.environ\n"
                "    if os.path.exists(options_path): os.unlink(options_path)\n"
                "g['drop_privileges'] = drop\n"
                "entry = sys.argv[2]\n"
                "g['os'].execv = lambda path, args: os.execve('/bin/sh', ['sh', entry], os.environ)\n"
                "sys.argv = [sys.argv[0], 'server', sys.argv[3]]\n"
                "sys.exit(r['main']())\n")
            if raw is None:
                options.unlink()
            return subprocess.run([sys.executable, str(wrapper), str(bootstrap), str(entry), str(options)], capture_output=True, text=True,
                                  env={**os.environ, 'PATH': tmp + os.pathsep + str(Path(sys.executable).parent) + os.pathsep + os.defpath, 'POC_PORT': '8631', 'POC_LOG_LEVEL': 'SECRET', 'SUPERVISOR_TOKEN': 'SECRET', 'HASSIO_TOKEN': 'SECRET'})

    def test_each_level_exact_argv(self):
        for level in LOG.LEVELS:
            with self.subTest(level=level):
                result = self.launch(json.dumps({'log_level': level}))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout.splitlines()[-1]),
                                 ['server', '-o', 'server-port=8631', '-o', 'server-options=no-tls',
                                  '-o', 'listen-hostname=0.0.0.0', '-o', 'log-file=-', '-o', 'log-level=' + level])
                self.assertIn('INFO: lifecycle stage=startup version=0.1.24 diagnostics=enabled', result.stdout)
        result = self.launch('{}')
        self.assertEqual(json.loads(result.stdout.splitlines()[-1])[-1], 'log-level=info')

    def test_invalid_and_malformed_fail_before_launch_without_disclosure(self):
        invalid = ('', 'INFO', 'warning', 'trace', 'none', 'info\n', ' info',
                   'info -o server-options=raw-socket', '$(touch SECRET)',
                   '`touch SECRET`', 'info; touch SECRET', 'info\x00', None, 1, True, [], {})
        raws = [json.dumps({'log_level': value}) for value in invalid]
        raws += ['{', 'null', '[]', '"SECRET"', '{"log_level": NaN}']
        for raw in raws:
            with self.subTest(raw=raw):
                result = self.launch(raw)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, 'ERROR: invalid add-on log_level options; refusing server startup\n')

    def test_missing_standalone_options_defaults_before_transition(self):
        result = self.launch(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.splitlines()[-1])[-1], 'log-level=info')

    def test_entrypoint_never_reads_options(self):
        source = (ROOT / 'scripts/entrypoint.sh').read_text()
        self.assertNotIn('/data/options.json', source)
        self.assertNotIn('log-level.py', source)
        self.assertIn('fatal|error|warn|info|debug)', source)

    def test_read_error_fails_safely(self):
        with patch.object(LOG, 'read_level', side_effect=PermissionError('SECRET')):
            with patch.object(LOG.sys, 'stderr') as error:
                self.assertEqual(LOG.main(), 1)
                self.assertNotIn('SECRET', str(error.write.call_args_list))

    def test_lifecycle_markers_remain_info(self):
        # Existing lifecycle tests check all added PAPPL logger statements at INFO.
        # The log-level change must not rewrite those patches.
        for name in ('patch-pappl-lifecycle.py', 'patch-job-path.py'):
            source = (ROOT / 'scripts' / name).read_text()
            self.assertIn('PAPPL_LOGLEVEL_INFO', source)
            self.assertIn('lifecycle stage=', source)
