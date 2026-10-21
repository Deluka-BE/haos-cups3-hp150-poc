import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/usb-runtime.py'
spec = importlib.util.spec_from_file_location('usb_runtime', SCRIPT)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class USBRuntimeTests(unittest.TestCase):
    def test_only_hp_usbfs_character_node_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, product in [('1-2', 'ea2a'), ('1-3', '1234')]:
                device = root / name
                device.mkdir()
                for field, value in {'idVendor': '03f0', 'idProduct': product,
                                     'busnum': '1', 'devnum': '2'}.items():
                    (device / field).write_text(value)
                (device / 'serial').write_text('SECRET')
            info = Mock(st_mode=stat.S_IFCHR | 0o664, st_gid=42,
                        st_rdev=os.makedev(189, 1))
            with patch.object(Path, 'lstat', return_value=info) as checked:
                self.assertEqual(runtime.hp_groups(root), [42])
                checked.assert_called_once_with()
                info.st_gid = 0
                self.assertEqual(runtime.hp_groups(root), [])
                info.st_gid = 7
                info.st_rdev = os.makedev(1, 3)
                self.assertEqual(runtime.hp_groups(root), [])
                info.st_rdev = os.makedev(189, 1)
                for kind in (stat.S_IFREG, stat.S_IFLNK):
                    info.st_mode = kind | 0o664
                    self.assertEqual(runtime.hp_groups(root), [])
            (root / '1-2/devnum').write_text('../SECRET')
            with patch.object(Path, 'lstat') as checked:
                self.assertEqual(runtime.hp_groups(root), [])
                checked.assert_not_called()

    def test_missing_sysfs_or_node_is_capture_safe(self):
        self.assertEqual(runtime.hp_groups(Path('/nonexistent')), [])
        with tempfile.TemporaryDirectory() as tmp:
            device = Path(tmp) / '1-2'
            device.mkdir()
            for name, value in {'idVendor': '03f0', 'idProduct': 'ea2a',
                                'busnum': '1', 'devnum': '2'}.items():
                (device / name).write_text(value)
            self.assertEqual(runtime.hp_groups(Path(tmp), Path(tmp) / 'absent'), [])

    def test_drop_order_all_ids_and_no_new_privileges(self):
        calls = []
        libc = Mock()
        libc.prctl.side_effect = lambda *args: calls.append(('prctl', args)) or 0
        with patch.object(runtime.os, 'setgroups', side_effect=lambda g: calls.append(('groups', g))), \
             patch.object(runtime.os, 'setresgid', side_effect=lambda *g: calls.append(('gid', g))), \
             patch.object(runtime.os, 'setresuid', side_effect=lambda *g: calls.append(('uid', g))), \
             patch.object(runtime.os, 'getresuid', return_value=(10001,) * 3), \
             patch.object(runtime.os, 'getresgid', return_value=(10001,) * 3), \
             patch.object(runtime.ctypes, 'CDLL', return_value=libc):
            runtime.drop_privileges([42])
        self.assertEqual(calls, [('groups', [42]), ('gid', (10001,) * 3),
                                ('uid', (10001,) * 3), ('prctl', (38, 1, 0, 0, 0))])

    def test_restriction_failure_is_fatal(self):
        for result, identity in [(1, (10001,) * 3), (0, (0,) * 3)]:
            with self.subTest(result=result, identity=identity), \
                 patch.object(runtime.os, 'setgroups'), \
                 patch.object(runtime.os, 'setresgid'), \
                 patch.object(runtime.os, 'setresuid'), \
                 patch.object(runtime.os, 'getresuid', return_value=identity), \
                 patch.object(runtime.os, 'getresgid', return_value=(10001,) * 3), \
                 patch.object(runtime.ctypes, 'CDLL', return_value=Mock(prctl=Mock(return_value=result))):
                with self.assertRaises((OSError, RuntimeError)):
                    runtime.drop_privileges([7])

    def test_tokens_removed_before_setup_and_exec(self):
        def setup():
            self.assertNotIn('SUPERVISOR_TOKEN', os.environ)
            self.assertNotIn('HASSIO_TOKEN', os.environ)
            return [7]
        with patch.dict(os.environ, {'SUPERVISOR_TOKEN': 'SECRET', 'HASSIO_TOKEN': 'SECRET'}), \
             patch.object(runtime, 'prepare_state_runtime'), \
             patch.object(runtime, 'hp_groups', side_effect=setup), \
             patch.object(runtime, 'prepare_mdns_runtime') as prepare, \
             patch.object(runtime, 'drop_privileges') as drop, \
             patch.object(runtime.os, 'execv') as execute, \
             patch.object(runtime.sys, 'argv', ['usb-runtime.py', 'drivers']), \
             patch('builtins.print'):
            runtime.main()
        drop.assert_called_once_with([7])
        execute.assert_called_once_with('/opt/poc/scripts/entrypoint.sh', ['entrypoint.sh', 'drivers'])

    def test_options_validated_before_drop_and_never_read_at_uid10001(self):
        for level in ('fatal', 'error', 'warn', 'info', 'debug'):
            identity = [0]
            def read():
                self.assertEqual(identity[0], 0)
                return level
            def drop(groups):
                identity[0] = 10001
            def execute(*args):
                self.assertEqual(identity[0], 10001)
                self.assertEqual(os.environ['POC_LOG_LEVEL'], level)
            with self.subTest(level=level), patch.dict(os.environ, {'POC_LOG_LEVEL': 'SECRET'}), \
                 patch.object(runtime.runpy, 'run_path', return_value={'read_level': Mock(side_effect=read)}) as loader, \
                 patch.object(runtime, 'prepare_state_runtime'), \
                 patch.object(runtime, 'prepare_mdns_runtime'), \
                 patch.object(runtime, 'hp_groups', return_value=[42]), \
                 patch.object(runtime, 'drop_privileges', side_effect=drop), \
                 patch.object(runtime.os, 'execv', side_effect=execute), \
                 patch.object(runtime.sys, 'argv', ['usb-runtime.py']), patch('builtins.print'):
                runtime.main()
                loader.return_value['read_level'].assert_called_once_with()

    def test_options_failure_precedes_setup_drop_and_launch(self):
        for error in (ValueError('SECRET'), PermissionError('SECRET'), UnicodeError('SECRET')):
            with self.subTest(error=type(error)), patch.dict(os.environ, {'POC_LOG_LEVEL': 'SECRET'}), \
                 patch.object(runtime.runpy, 'run_path', return_value={'read_level': Mock(side_effect=error)}), \
                 patch.object(runtime, 'prepare_state_runtime') as setup, \
                 patch.object(runtime, 'drop_privileges') as drop, \
                 patch.object(runtime.os, 'execv') as execute, \
                 patch.object(runtime.sys, 'argv', ['usb-runtime.py', 'server']), patch('builtins.print') as log:
                self.assertEqual(runtime.main(), 1)
                self.assertNotIn('POC_LOG_LEVEL', os.environ)
                setup.assert_not_called()
                drop.assert_not_called()
                execute.assert_not_called()
                self.assertNotIn('SECRET', str(log.call_args_list))

    def test_fresh_runtime_dir_has_only_scoped_ownership(self):
        with patch.object(runtime, 'Path') as paths, patch.object(runtime.os, 'chown') as chown:
            paths.return_value.is_symlink.return_value = False
            paths.return_value.is_dir.return_value = True
            runtime.prepare_mdns_runtime()
            paths.assert_called_once_with('/run/avahi-daemon')
            paths.return_value.mkdir.assert_called_once_with(mode=0o755, exist_ok=True)
            chown.assert_called_once_with(paths.return_value, 10001, 10001)

    def test_runtime_setup_failure_preserves_usb_launch(self):
        with patch.object(runtime, 'Path') as paths, patch.object(runtime, 'prepare_state_runtime'), \
             patch.object(runtime.sys, 'argv', ['usb-runtime.py', 'drivers']), \
             patch.dict(os.environ, {'POC_CAPTURE_RASTER_ONCE': '0'}), \
             patch.object(runtime, 'hp_groups', return_value=[7]), \
             patch.object(runtime, 'drop_privileges') as drop, patch.object(runtime.os, 'execv') as execute, \
             patch('builtins.print') as log:
            paths.return_value.mkdir.side_effect = PermissionError('SECRET')
            runtime.main()
        drop.assert_called_once_with([7])
        execute.assert_called_once()
        self.assertNotIn('SECRET', str(log.call_args_list))

    def test_drop_failure_never_launches(self):
        with patch.object(runtime, 'prepare_state_runtime'), \
             patch.object(runtime, 'hp_groups', return_value=[]), \
             patch.object(runtime, 'drop_privileges', side_effect=PermissionError('SECRET')), \
             patch.object(runtime.os, 'execv') as execute, patch('builtins.print') as log:
            self.assertEqual(runtime.main(), 1)
        execute.assert_not_called()
        self.assertNotIn('SECRET', str(log.call_args))
