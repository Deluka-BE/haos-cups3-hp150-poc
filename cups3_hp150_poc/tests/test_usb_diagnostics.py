import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/usb-diagnostics.py'
spec = importlib.util.spec_from_file_location('usb_diagnostics', SCRIPT)
usb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usb)


class USBDiagnosticsTests(unittest.TestCase):
    def test_only_matching_safe_usb_uris(self):
        uri = 'usb://HP/Color%20Laser%20150a?serial=ABC123&interface=1'
        self.assertEqual(usb.hp_uris('direct ' + uri + ' "SECRET"\nSECRET'), [uri])
        for bad in ('usb://Other/Color%20Laser%20150a',
                    'usb://HP/Color%20Laser%20150a?token=SECRET',
                    'usb://HP/Color%20Laser%20150a?serial=%0aSECRET',
                    'usb://HP/Color%20Laser%201500', 'ipp://SECRET/printer'):
            self.assertEqual(usb.hp_uris(bad), [])
        self.assertEqual(usb.hp_uris('cups:' + uri), ['cups:' + uri])

    def test_probe_bounds_and_environment(self):
        with patch.dict(os.environ, {'SUPERVISOR_TOKEN': 'SECRET', 'OTHER_SECRET': 'SECRET'}):
            status, output = usb.probe([sys.executable, '-c',
                'import os,sys; assert "SUPERVISOR_TOKEN" not in os.environ; '
                'assert "OTHER_SECRET" not in os.environ; '
                'sys.stderr.write("SECRET"); print("ok")'])
        self.assertEqual((status, output), ('ok', 'ok\n'))
        status, output = usb.probe([sys.executable, '-c', 'print("x"*100000)'])
        self.assertEqual(status, 'output-limit')
        self.assertLessEqual(len(output), usb.LIMIT)
        status, _ = usb.probe([sys.executable, '-c', 'import time; time.sleep(3)'], timeout=0.1)
        self.assertEqual(status, 'timeout')
        self.assertEqual(usb.probe(['/nonexistent'])[0], 'unavailable')
        self.assertEqual(usb.probe([sys.executable, '-c', 'raise SystemExit(1)'])[0], 'failed')

    def test_numeric_enumeration_and_sysfs_fallback(self):
        out = io.StringIO()
        record = 'Bus 001 Device 002: ID 03f0:1234 SECRET\n'
        with patch.object(usb, 'probe', return_value=('ok', record * 40)), contextlib.redirect_stdout(out):
            usb.enumerate_usb()
        self.assertNotIn('SECRET', out.getvalue())
        self.assertEqual(len(out.getvalue().splitlines()), 33)
        self.assertIn('capped=True', out.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            device = Path(tmp) / '1-2'
            device.mkdir()
            for name, value in {'busnum': '1', 'devnum': '2', 'idVendor': '03f0', 'idProduct': '1234',
                                'serial': 'SECRET', 'product': 'SECRET'}.items():
                (device / name).write_text(value)
            out = io.StringIO()
            with patch.object(usb, 'probe', return_value=('unavailable', 'SECRET')), contextlib.redirect_stdout(out):
                usb.enumerate_usb(Path(tmp))
            self.assertIn('id=03f0:1234', out.getvalue())
            self.assertNotIn('SECRET', out.getvalue())

    def test_sanitized_backend_evidence(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            usb.cups_summary('DEBUG: libusb_get_device_list=15\n'
                'DEBUG: Failed to open device, code: -3\n'
                'DEBUG: Failed to detach "usblp" module from 03f0:ea2a\n'
                'DEBUG: Failed to claim interface 1 for 03f0:ea2a: SECRET\n'
                'DEBUG2: iSerialNumber="SECRET"\nSECRET')
        self.assertNotIn('SECRET', out.getvalue())
        self.assertIn('evidence=open-error value=-3', out.getvalue())
        self.assertIn('evidence=detach-failed', out.getvalue())
        self.assertIn('evidence=claim-failed', out.getvalue())

    def test_node_access_errno_and_no_device_io(self):
        out = io.StringIO()
        info = os.stat('/dev/null')
        with patch.object(Path, 'stat', return_value=info), patch.object(usb.os, 'open',
                side_effect=PermissionError(13, 'SECRET')), contextlib.redirect_stdout(out):
            usb.hp_node_access(Path('/dev/bus/usb/001/002'))
        self.assertIn('errno=EACCES', out.getvalue())
        self.assertNotIn('SECRET', out.getvalue())
        with patch.object(Path, 'stat', return_value=info), patch.object(usb.os, 'open',
                return_value=123) as opened, patch.object(usb.os, 'close') as closed, contextlib.redirect_stdout(io.StringIO()):
            usb.hp_node_access(Path('/dev/bus/usb/001/002'))
        self.assertEqual(opened.call_args.args[1], os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        closed.assert_called_once_with(123)

    def test_stderr_collection_is_bounded_and_optional(self):
        argv = [sys.executable, '-c', 'import sys; sys.stderr.write("x"*100000)']
        self.assertEqual(usb.probe(argv), ('ok', ''))
        status, output = usb.probe(argv, include_stderr=True)
        self.assertEqual(status, 'output-limit')
        self.assertLessEqual(len(output), usb.LIMIT)

    def test_target_interface_numeric_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            device = root / '1-2'
            device.mkdir()
            (device / 'idVendor').write_text('03f0')
            (device / 'idProduct').write_text('ea2a')
            interface = root / '1-2:1.0'
            interface.mkdir()
            for name, value in {'bInterfaceNumber': '00', 'bInterfaceClass': '07',
                                'bInterfaceSubClass': '01', 'bInterfaceProtocol': '02'}.items():
                (interface / name).write_text(value)
            (interface / 'driver').symlink_to('/SECRET/usblp')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                usb.hp_interfaces(root)
            self.assertIn('class=07 subclass=01 protocol=02 driver=usblp', out.getvalue())
            self.assertNotIn('SECRET', out.getvalue())

    def test_main_does_not_forward_raw_discovery(self):
        out = io.StringIO()
        uri = 'usb://HP/Color%20Laser%20150a?serial=ABC'
        with patch.object(usb, 'enumerate_usb'), patch.object(usb, 'probe', side_effect=[
                ('ok', 'SECRET\ndirect ' + uri + ' "SECRET"'), ('ok', 'cups:capture:/hp150 SECRET\ndirect cups:usb://HP/Color%20Laser%20150?serial=CNB2N32ZJ4 "SECRET"')]) as probe, contextlib.redirect_stdout(out):
            usb.main()
        self.assertNotIn('SECRET', out.getvalue())
        self.assertIn('device-uri=' + uri, out.getvalue())
        self.assertIn('discovery=pappl-capture-usb status=ok HP-Color-Laser-150a=visible', out.getvalue())
        self.assertIn('device-uri=cups:usb://HP/Color%20Laser%20150?serial=CNB2N32ZJ4', out.getvalue())
        self.assertEqual(probe.call_args_list[0].args[0], ['/opt/poc/diagnostics/usb'])
        self.assertIn('devices', probe.call_args_list[1].args[0])
        self.assertIn('PAPPL allowlist=capture,usb', out.getvalue())
