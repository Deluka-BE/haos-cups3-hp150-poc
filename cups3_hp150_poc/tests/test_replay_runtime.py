"""Replay safety and comparable runtime metadata, without HP or USB hardware."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('replay', ROOT / 'scripts/replay-runtime.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ReplayTests(unittest.TestCase):
    def test_sandbox_has_no_host_devices_network_or_channels(self):
        cmd = m.sandbox_command(Path('/evidence'), Path('/saved.raster'), Path('/saved.ppd'), ['worker'])
        for flag in ('--unshare-all', '--die-with-parent', '--new-session'):
            self.assertIn(flag, cmd)
        self.assertIn(['--dev', '/dev'], [cmd[i:i+2] for i in range(len(cmd))])
        for path in ('/sys', '/run', '/tmp'):
            self.assertIn(['--tmpfs', path], [cmd[i:i+2] for i in range(len(cmd))])
        self.assertEqual(cmd.count('--bind'), 1)
        self.assertIn(['--ro-bind', '/', '/'], [cmd[i:i+3] for i in range(len(cmd))])
        self.assertNotIn('usb', ' '.join(cmd))

    def test_replay_preserves_options_and_captures_metadata(self):
        boundary = {'argv': [m.FILTER, '7', 'user', 'title', '1', 'Screen=Normal x="a b"', '/old/input'],
                    'environment': {'PPD': '/old/ppd', 'LD_LIBRARY_PATH': '/work/lib',
                                    'LD_PRELOAD': 'bad', 'DEVICE_URI': 'usb://bad',
                                    'SUPERVISOR_TOKEN': 'secret'}}
        seen = {}
        class Child:
            def __init__(self, command, **kwargs):
                seen.update(command=command, **kwargs)
                kwargs['stdout'].write(b'SPL')
                kwargs['stderr'].write(b'  123: file=/work/lib/libscmssc.so [0]; dynamically loaded\n')
            def wait(self, timeout=None):
                return 0
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.object(m, 'probe', side_effect=lambda *args: {'exit': 0, 'text': 'z-package 2\na-package 1 0x7fff12345678\n'}), \
                 patch.object(m, 'identity', side_effect=lambda p: {'path': str(p), 'sha256': 'abc'}), \
                 patch.object(m.subprocess, 'Popen', Child), \
                 patch('builtins.open', unittest.mock.mock_open(read_data=b'RaS2')):
                self.assertEqual(m.replay(boundary, out, 10), 0)
            report = json.loads((out / 'report.json').read_text())
            self.assertEqual(seen['command'], boundary['argv'][:6])
            self.assertTrue(seen['close_fds'])
            self.assertTrue(seen['start_new_session'])
            self.assertEqual(seen['env']['LD_DEBUG'], 'libs,files,versions')
            for key in ('LD_PRELOAD', 'DEVICE_URI', 'SUPERVISOR_TOKEN'):
                self.assertNotIn(key, seen['env'])
            self.assertIn('file=/work/lib/libscmssc.so', report['loader_trace'])
            self.assertNotIn('0x7fff12345678', report['ldd']['text'])
            self.assertEqual(report['packages']['text'].splitlines()[0], 'a-package 1 0x7fff12345678')
            self.assertNotIn('123:', report['loader_trace'])
            for key in ('elf', 'ldd', 'glibc', 'packages', 'runtime_files', 'output', 'ppd', 'input'):
                self.assertIn(key, report)
            self.assertIn('/work/lib/libscmssc.so', [p['path'] for p in report['runtime_files']])
            self.assertEqual((out / 'replay.spl').read_bytes(), b'SPL')

    def test_boundary_cannot_select_a_backend_or_shell(self):
        for executable in ('/opt/poc/backend/usb.real', '/bin/sh', 'rastertospl'):
            with self.subTest(executable=executable), patch.object(m.subprocess, 'Popen') as child:
                with self.assertRaises(ValueError):
                    m.replay({'environment': {}, 'argv': [executable, '1', 'u', 't', '1', '']}, Path('/unused'), 10)
                child.assert_not_called()

    def test_no_fallback_if_sandbox_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'in').write_bytes(b'RaS2data')
            (root / 'boundary').write_text(json.dumps({'ppd': {'text': '*PPD'}, 'environment': {}, 'argv': []}))
            args = ['replay', '--boundary', str(root / 'boundary'), '--raster', str(root / 'in'),
                    '--output-dir', str(root / 'out')]
            with patch('sys.argv', args), patch.object(m.subprocess, 'run', side_effect=FileNotFoundError) as run:
                self.assertEqual(m.main(), 1)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][0], '/usr/bin/bwrap')
                self.assertTrue(run.call_args.kwargs['close_fds'])
                self.assertNotIn('SUPERVISOR_TOKEN', run.call_args.kwargs['env'])
            self.assertFalse((root / 'out/replay.spl').exists())
            self.assertEqual((root / 'out').stat().st_mode & 0o777, 0o700)
            with patch('sys.argv', args), self.assertRaises(FileExistsError):
                m.main()

    def test_explicit_unsandboxed_selection_and_private_staging(self):
        for opt_in in (False, True):
            with self.subTest(opt_in=opt_in), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'protected' / 'raster'
                source.parent.mkdir(mode=0o700)
                source.write_bytes(b'RaS2captured')
                boundary = root / 'boundary'
                boundary.write_text(json.dumps({'ppd': {'text': '*PPD'},
                                                'environment': {}, 'argv': []}))
                out = root / 'out'
                args = ['replay', '--boundary', str(boundary), '--raster', str(source),
                        '--output-dir', str(out)]
                if opt_in:
                    args.append('--offline-unsandboxed-ok')
                with patch('sys.argv', args), patch.object(m.subprocess, 'run') as run:
                    run.return_value.returncode = 1
                    self.assertEqual(m.main(), 1)
                command = run.call_args.args[0]
                self.assertEqual(command[0], '/usr/bin/python3' if opt_in else '/usr/bin/bwrap')
                self.assertNotIn(str(source), command)
                self.assertEqual((out / 'input.raster').read_bytes(), source.read_bytes())
                for file in out.iterdir():
                    self.assertEqual(file.stat().st_mode & 0o777, 0o600)
                self.assertEqual(run.call_count, 1)  # no automatic retry on nonzero exit
                self.assertEqual(run.call_args.kwargs['env'], {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
                self.assertTrue(run.call_args.kwargs['close_fds'])

    def test_unsandboxed_filter_real_stdin_output_environment_and_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = ("import os,sys,resource; "
                    "assert not {'DEVICE_URI','LD_PRELOAD','SUPERVISOR_TOKEN'} & os.environ.keys(); "
                    "assert resource.getrlimit(resource.RLIMIT_FSIZE) == (536870912,)*2; "
                    "assert resource.getrlimit(resource.RLIMIT_CORE) == (0,0); "
                    "sys.stderr.write('fixture stderr'); "
                    "sys.stdout.buffer.write(b'SPL:'+sys.stdin.buffer.read())")
            raster = root / 'input.raster'
            raster.write_bytes(b'RaS2payload')
            ppd = root / 'input.ppd'
            ppd.write_text('*PPD')
            boundary = {'argv': [sys.executable, '-c', code, 't', '1', '', '/ignored'],
                        'environment': {'DEVICE_URI': 'usb://bad', 'LD_PRELOAD': 'bad',
                                        'SUPERVISOR_TOKEN': 'secret'}}
            with patch.object(m, 'FILTER', sys.executable):
                self.assertEqual(m.replay(boundary, root, 10, raster, ppd,
                                          'offline-unsandboxed'), 0, (root / 'report.json').read_text())
            report = json.loads((root / 'report.json').read_text())
            self.assertEqual(report['mode'], 'offline-unsandboxed')
            self.assertEqual((root / 'replay.spl').read_bytes(), b'SPL:RaS2payload')
            self.assertEqual(report['input']['sha256'], m.identity(raster)['sha256'])
            self.assertTrue(report['loader_trace'])
            self.assertIn('runtime_files', report)

    def test_unsandboxed_timeout_kills_filter_group_and_keeps_report(self):
        boundary = {'argv': [m.FILTER, '1', 'u', 't', '1', ''], 'environment': {}}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            source = out / 'input'
            source.write_bytes(b'RaS2')
            with patch.object(m, 'probe', return_value={'error': 'unavailable'}), \
                 patch.object(m.subprocess, 'Popen') as launch, patch.object(m.os, 'killpg') as kill:
                launch.return_value.pid = 12345
                launch.return_value.wait.side_effect = [subprocess.TimeoutExpired('filter', 1), -9]
                self.assertEqual(m.replay(boundary, out, 1, source, source,
                                          'offline-unsandboxed'), 1)
                kill.assert_called_once_with(12345, m.signal.SIGKILL)
            report = json.loads((out / 'report.json').read_text())
            self.assertTrue(report['timed_out'])
            self.assertEqual(report['filter_exit'], -9)
            self.assertIn('sha256', report['output'])

    def test_identity_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lib'
            path.write_bytes(b'abc')
            self.assertEqual(m.identity(path)['sha256'], 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

    def test_real_sandbox_device_isolation_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'input'
            source.write_bytes(b'RaS2')
            output = root / 'output'
            output.mkdir()
            code = ('from pathlib import Path; '
                    'assert not Path("/dev/bus/usb").exists(); '
                    'assert not Path("/sys/bus/usb").exists(); '
                    'assert not Path("/run/cups").exists(); '
                    'Path("/tmp/replay/proof").write_text("isolated")')
            command = m.sandbox_command(output, source, source, ['/usr/bin/python3', '-c', code])
            try:
                result = subprocess.run(command, capture_output=True, timeout=10, close_fds=True)
            except FileNotFoundError:
                self.skipTest('bubblewrap unavailable')
            if result.returncode and b'namespace' in result.stderr:
                self.skipTest('host blocks bubblewrap namespaces; fail-closed path covered separately')
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertEqual((output / 'proof').read_text(), 'isolated')
