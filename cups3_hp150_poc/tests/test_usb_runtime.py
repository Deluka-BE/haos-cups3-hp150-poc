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
             patch.object(runtime, 'hp_groups', side_effect=setup), \
             patch.object(runtime, 'drop_privileges') as drop, \
             patch.object(runtime.os, 'execv') as execute, \
             patch.object(runtime.sys, 'argv', ['usb-runtime.py', 'drivers']), \
             patch('builtins.print'):
            runtime.main()
        drop.assert_called_once_with([7])
        execute.assert_called_once_with('/opt/poc/scripts/entrypoint.sh', ['entrypoint.sh', 'drivers'])

    def test_drop_failure_never_launches(self):
        with patch.object(runtime, 'hp_groups', return_value=[]), \
             patch.object(runtime, 'drop_privileges', side_effect=PermissionError('SECRET')), \
             patch.object(runtime.os, 'execv') as execute, patch('builtins.print') as log:
            self.assertEqual(runtime.main(), 1)
        execute.assert_not_called()
        self.assertNotIn('SECRET', str(log.call_args))
