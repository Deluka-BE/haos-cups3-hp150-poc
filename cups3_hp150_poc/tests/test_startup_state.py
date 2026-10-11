import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


state = load('state-runtime')
settling = load('usb-settle')
runtime = load('usb-runtime')
URI = 'direct usb://HP/Color%20Laser%20150?serial=SERIAL_SECRET "HP"\n'


class PersistenceTests(unittest.TestCase):
    def test_migration_and_container_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / 'work/state', root / 'data/state'
            old.mkdir(parents=True)
            new.mkdir(parents=True)
            (old / state.STATE).write_bytes(b'QUEUE_SECRET')
            (old / 'p00001-inst-opt.conf').write_bytes(b'CONFIG')
            (old / 'ppd').mkdir()
            (old / 'capture').write_bytes(b'DOCUMENT_SECRET')
            self.assertEqual(state.migrate(old, new), 'migrated')
            self.assertEqual(sorted(p.name for p in new.iterdir()), [state.STATE, 'p00001-inst-opt.conf'])
            self.assertEqual((old / state.STATE).read_bytes(), b'QUEUE_SECRET')
            shutil.rmtree(root / 'work')  # A new add-on container retains only /data.
            old.mkdir(parents=True)
            (old / state.STATE).write_bytes(b'OBSOLETE')
            self.assertEqual(state.migrate(old, new), 'retained')
            self.assertEqual((new / state.STATE).read_bytes(), b'QUEUE_SECRET')
            self.assertEqual((new / 'p00001-inst-opt.conf').read_bytes(), b'CONFIG')

    def test_fresh_and_authoritative_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            new = Path(tmp)
            old = new / 'absent'
            self.assertEqual(state.migrate(old, new), 'fresh')
            (new / state.STATE).touch()
            self.assertEqual(state.migrate(old, new), 'retained')

    def test_reject_symlinks_nonregular_and_oversize_before_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / 'old', root / 'new'
            old.mkdir()
            new.mkdir()
            source = old / state.STATE
            target = root / 'secret'
            target.write_bytes(b'SECRET')
            source.symlink_to(target)
            with self.assertRaises(OSError):
                state.migrate(old, new)
            source.unlink()
            os.mkfifo(source)
            with self.assertRaises(RuntimeError):
                state.migrate(old, new)
            source.unlink()
            source.write_bytes(b'x' * (state.MAX_FILE + 1))
            with self.assertRaises(RuntimeError):
                state.migrate(old, new)
            self.assertEqual(list(new.iterdir()), [])
            source.write_bytes(b'STATE')
            (old / 'p00001-inst-opt.conf').symlink_to(target)
            with self.assertRaises(OSError):
                state.migrate(old, new)
            self.assertEqual(list(new.iterdir()), [])

    def test_entry_file_and_total_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / 'old', root / 'new'
            old.mkdir()
            new.mkdir()
            (old / state.STATE).write_bytes(b'STATE')
            for index in range(64):
                (old / f'p{index:05d}-inst-opt.conf').touch()
            with self.assertRaises(RuntimeError):
                state.migrate(old, new)
            for path in old.glob('p*'):
                path.unlink()
            for index in range(256):
                (old / f'ignored-{index}').touch()
            with self.assertRaises(RuntimeError):
                state.migrate(old, new)
            for path in old.glob('ignored*'):
                path.unlink()
            for index in range(8):
                (old / f'p{index:05d}-inst-opt.conf').write_bytes(b'x' * state.MAX_FILE)
            with self.assertRaises(RuntimeError):
                state.migrate(old, new)
            self.assertEqual(list(new.iterdir()), [])

    def test_partial_migration_does_not_overwrite_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / 'old', root / 'new'
            old.mkdir()
            new.mkdir()
            (old / state.STATE).write_bytes(b'STATE')
            (old / 'p00001-inst-opt.conf').write_bytes(b'OLD')
            (new / 'p00001-inst-opt.conf').write_bytes(b'NEW')
            self.assertEqual(state.migrate(old, new), 'migrated')
            self.assertEqual((new / 'p00001-inst-opt.conf').read_bytes(), b'NEW')
            self.assertFalse(list(new.glob('.migration-*')))

    def test_scoped_bootstrap_and_invalid_mount(self):
        with patch.object(runtime, 'Path') as paths, patch.object(runtime.os, 'chown') as chown, \
             patch.object(runtime.os, 'chmod') as chmod:
            data = paths.return_value
            data.is_symlink.return_value = False
            data.is_dir.return_value = True
            directory = data.__truediv__.return_value
            directory.is_symlink.return_value = False
            directory.is_dir.return_value = True
            directory.stat.return_value = Mock(st_uid=0, st_gid=0, st_mode=0o755)
            runtime.prepare_state_runtime()
            paths.assert_called_once_with('/data')
            chown.assert_called_once_with(directory, 10001, 10001)
            chmod.assert_called_once_with(directory, 0o700)
            directory.mkdir.assert_called_once_with(mode=0o700, exist_ok=True)
            directory.is_symlink.return_value = True
            chown.reset_mock()
            with self.assertRaises(RuntimeError):
                runtime.prepare_state_runtime()
            chown.assert_not_called()
            data.is_dir.return_value = False
            with self.assertRaises(RuntimeError):
                runtime.prepare_state_runtime()

    def test_persistence_setup_failure_is_fatal(self):
        with patch.object(runtime, 'prepare_state_runtime', side_effect=OSError('SECRET')), \
             patch.object(runtime, 'drop_privileges') as drop, \
             patch.object(runtime.os, 'execv') as execute, patch('builtins.print') as log:
            self.assertEqual(runtime.main(), 1)
        drop.assert_not_called()
        execute.assert_not_called()
        self.assertNotIn('SECRET', str(log.call_args_list))

    def test_fixed_launch_paths_and_preserved_security(self):
        entry = (ROOT / 'scripts/entrypoint.sh').read_text()
        self.assertIn('export STATE_DIR=/data/state SPOOL_DIR=/work/spool CAPTURE_DIR=/work/capture', entry)
        self.assertIn('PPD_DIRS=/work/state/ppd USER_PPD_DIR=/work/state/ppd', entry)
        self.assertLess(entry.index('unset SUPERVISOR_TOKEN HASSIO_TOKEN'), entry.index('scripts/state-runtime.py'))
        self.assertLess(entry.index('scripts/state-runtime.py'), entry.index('server)'))
        self.assertLess(entry.index('scripts/usb-settle.py'), entry.index('set -- legacy-printer-app server'))
        docker = (ROOT / 'Dockerfile').read_text()
        self.assertIn('"capture,usb", // PoC:', docker)
        self.assertIn('usb: true', (ROOT / 'config.yaml').read_text())
        self.assertIn('libc.prctl(38, 1, 0, 0, 0)', (ROOT / 'scripts/usb-runtime.py').read_text())


class SettlingTests(unittest.TestCase):
    def run_settle(self, results):
        probe = Mock(side_effect=results)
        sleep = Mock()
        with contextlib.redirect_stdout(io.StringIO()) as log:
            ready = settling.settle(probe, sleep)
        self.assertNotIn('SECRET', log.getvalue())
        for call in probe.call_args_list:
            self.assertEqual(call.kwargs, {'timeout': 8})
            self.assertIn(call.args[0], [
                ['/opt/poc/backend/usb'],
                ['/usr/bin/legacy-printer-app', 'devices', '-o', 'log-level=error', '-o', 'log-file=-']])
        return ready, probe, sleep, log.getvalue()

    def test_first_attempt_and_backend_disagreement(self):
        ready, probe, sleep, log = self.run_settle([('failed', 'SECRET'), ('ok', URI)])
        self.assertTrue(ready)
        self.assertEqual(probe.call_count, 2)
        sleep.assert_not_called()
        self.assertIn('result=ready attempts=1', log)

    def test_eventual_application_readiness(self):
        ready, probe, sleep, log = self.run_settle([
            ('ok', URI), ('timeout', URI), ('ok', URI), ('ok', 'SECRET'),
            ('ok', URI), ('ok', URI)])
        self.assertTrue(ready)
        self.assertEqual(probe.call_count, 6)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4])
        self.assertIn('result=ready attempts=3', log)

    def test_exhaustion_and_exact_upper_bound(self):
        for status in ('ok', 'timeout', 'failed', 'unavailable', 'output-limit'):
            with self.subTest(status=status):
                ready, probe, sleep, log = self.run_settle([('ok', URI), (status, 'SECRET')] * 6)
                self.assertFalse(ready)
                self.assertEqual(probe.call_count, 12)
                self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4, 8, 16, 16])
                self.assertIn('result=exhausted attempts=6', log)
        self.assertEqual(2 * settling.ATTEMPTS * settling.PROBE_TIMEOUT + sum(settling.BACKOFF), 142)
