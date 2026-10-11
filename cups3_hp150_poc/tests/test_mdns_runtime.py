import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mdns', ROOT / 'scripts/mdns-runtime.py')
mdns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mdns)

RECORD = '=;eth0;IPv4;hp150-usb-test;_ipp._tcp;local;hp150-poc.local;192.168.0.3;8631;"rp=ipp/print/hp150" "pdl=application/pdf,image/urf" "URF=W8,SRGB24,RS600"'


class MDNSTests(unittest.TestCase):
    def test_transport_rejects_tls_and_ipps_without_logging_raw_records(self):
        for record, expected in (
            (RECORD, True),
            (RECORD + ' "TLS=1.2"', False),
            (RECORD + '\n' + RECORD.replace('_ipp._tcp', '_ipps._tcp'), False),
            (RECORD + '\n' + RECORD.replace('_ipp._tcp', '_ipps-system._tcp'), False),
            ('', False),
            (RECORD + '\n' + 'x' * mdns.LIMIT, False),
            (RECORD.replace('hp150-poc.local', 'other.local'), False),
        ):
            output = io.StringIO()
            with patch.object(mdns, 'probe', return_value=record + '\nSECRET'), contextlib.redirect_stdout(output):
                self.assertEqual(mdns.transport('hp150-poc.local'), expected)
            self.assertNotIn('SECRET', output.getvalue())
            self.assertNotIn('192.168.0.3', output.getvalue())
            self.assertIn('uri-policy=ipp-only security-policy=none', output.getvalue())

    def test_only_resolved_airprint_local_endpoint(self):
        self.assertEqual(mdns.services(RECORD + '\n' + RECORD, 'hp150-poc.local', 8631), ['hp150-usb-test'])
        for bad in (RECORD.replace('8631;', '631;'), RECORD.replace('hp150-poc.local', 'other.local'),
                    RECORD.replace('image/urf', 'image/pwg-raster'), RECORD.replace('URF=', 'X='),
                    RECORD.replace('rp=', 'X='), RECORD.replace('_ipp._tcp', '_http._tcp'),
                    RECORD.replace('=;', '+;', 1), RECORD.replace('hp150-usb-test', 'evil\x1b[2J')):
            self.assertEqual(mdns.services(bad, 'hp150-poc.local', 8631), [])

    def test_probe_caps_output_and_time_and_hides_stderr(self):
        data = mdns.probe([sys.executable, '-c', 'import sys; sys.stderr.write("SECRET"); print("x"*100000)'])
        self.assertLessEqual(len(data), mdns.LIMIT)
        self.assertNotIn('SECRET', data)
        start = time.monotonic()
        self.assertEqual(mdns.probe([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=0.1), '')
        self.assertLess(time.monotonic() - start, 2)

    def test_start_order_credentials_registration_and_cleanup(self):
        bus = Mock(poll=Mock(return_value=None))
        daemon = Mock(poll=Mock(return_value=None), stderr=io.BytesIO())
        app = Mock(poll=Mock(side_effect=[None, 0]), wait=Mock(return_value=0))
        launches = []
        def launch(argv, **kwargs):
            self.assertNotIn('SUPERVISOR_TOKEN', os.environ)
            self.assertNotIn('HASSIO_TOKEN', os.environ)
            self.assertEqual(os.environ['DBUS_SYSTEM_BUS_ADDRESS'], mdns.BUS)
            launches.append(argv)
            return [bus, daemon, app][len(launches)-1]
        output = io.StringIO()
        with patch.dict(os.environ, {'SUPERVISOR_TOKEN': 'SECRET', 'HASSIO_TOKEN': 'SECRET'}), \
             patch.object(mdns, 'Path') as paths, patch.object(mdns.subprocess, 'Popen', side_effect=launch), \
             patch.object(mdns, 'avahi', return_value='int32 2'), \
             patch.object(mdns, 'hostname', return_value='hp150-poc.local'), \
             patch.object(mdns, 'probe', return_value=RECORD), patch.object(mdns.signal, 'signal'), \
             patch.object(mdns, 'stop') as stop, contextlib.redirect_stdout(output):
            paths.return_value.exists.return_value = True
            self.assertEqual(mdns.main(['legacy-printer-app', 'server']), 0)
        self.assertEqual([x[0] for x in launches], ['dbus-daemon', 'avahi-daemon', 'legacy-printer-app'])
        self.assertIn('--no-drop-root', launches[1])
        self.assertEqual([call.args[0] for call in stop.call_args_list], [app, daemon, bus])
        self.assertIn('registration=success service=hp150-usb-test', output.getvalue())
        self.assertNotIn('SECRET', output.getvalue())
        self.assertNotIn('192.168.0.3', output.getvalue())

    def test_missing_daemon_does_not_block_usb_application(self):
        app = Mock(poll=Mock(return_value=0), wait=Mock(return_value=7))
        output = io.StringIO()
        with patch.object(mdns, 'Path'), patch.object(mdns.subprocess, 'Popen', side_effect=[OSError('SECRET'), app]) as launch, \
             patch.object(mdns.signal, 'signal'), patch.object(mdns, 'stop'), contextlib.redirect_stdout(output):
            self.assertEqual(mdns.main(['legacy-printer-app', 'server']), 7)
        self.assertEqual(launch.call_args_list[-1].args[0], ['legacy-printer-app', 'server'])
        self.assertIn('registration=unconfirmed', output.getvalue())
        self.assertNotIn('SECRET', output.getvalue())

    def test_crashed_avahi_reports_reason_and_keeps_usb_running(self):
        bus = Mock(poll=Mock(return_value=None))
        daemon = Mock(poll=Mock(return_value=1), stderr=io.BytesIO(
            b'Failed to create runtime directory /run/avahi-daemon. SECRET'))
        app = Mock(poll=Mock(return_value=0), wait=Mock(return_value=0))
        output = io.StringIO()
        with patch.object(mdns, 'Path') as paths, \
             patch.object(mdns.subprocess, 'Popen', side_effect=[bus, daemon, app]), \
             patch.object(mdns.signal, 'signal'), patch.object(mdns, 'stop'), \
             patch.object(mdns, 'probe') as probe, contextlib.redirect_stdout(output):
            paths.return_value.exists.return_value = True
            self.assertEqual(mdns.main(['legacy-printer-app', 'server']), 0)
        probe.assert_not_called()
        self.assertIn('avahi=failed', output.getvalue())
        self.assertIn('reason=runtime-owner-mismatch', output.getvalue())
        self.assertIn('registration=unconfirmed', output.getvalue())
        self.assertNotIn('registration=success', output.getvalue())
        self.assertNotIn('SECRET', output.getvalue())

    def test_cleanup_kills_unresponsive_child(self):
        child = Mock(poll=Mock(return_value=None), wait=Mock(side_effect=[subprocess.TimeoutExpired('fixture', 3), 0]))
        mdns.stop(child)
        child.terminate.assert_called_once()
        child.kill.assert_called_once()

    def test_diagnose_uses_existing_bus_without_daemon_or_queue_changes(self):
        with patch.dict(os.environ, {}), patch.object(mdns, 'hostname', return_value='hp150-poc.local'), \
             patch.object(mdns, 'probe', return_value=RECORD), patch.object(mdns.subprocess, 'Popen') as launch, \
             patch.object(mdns, 'Path') as paths, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mdns.main(['--diagnose']), 0)
        launch.assert_not_called()
        paths.assert_not_called()
        for record in (RECORD.replace('eth0;', 'lo;'), RECORD.replace('192.168.0.3', '127.0.0.1')):
            self.assertEqual(mdns.services(record, 'hp150-poc.local', 8631), [])

    def test_explicit_hostname_and_avahi_account_match_runtime(self):
        import configparser
        config = configparser.ConfigParser()
        config.read(ROOT / 'mdns/avahi.conf')
        self.assertEqual(config['server']['host-name'], 'hp150-poc')
        self.assertEqual(config['server']['host-name-from-machine-id'], 'no')
        self.assertEqual(config['server']['disallow-other-stacks'], 'no')
        docker = (ROOT / 'Dockerfile').read_text()
        self.assertIn('usermod --non-unique --uid 10001 --gid poc avahi', docker)
        self.assertIn('groupmod --non-unique --gid 10001 avahi', docker)

    def test_daemon_reason_is_bounded_and_sanitized(self):
        diagnostics = mdns.DaemonDiagnostics()
        child = subprocess.Popen([sys.executable, '-c',
            'import sys; sys.stderr.write("Failed to create runtime directory SECRET\\n" + "x"*100000)'],
            stderr=subprocess.PIPE)
        diagnostics.attach(child)
        child.wait(timeout=3)
        deadline = time.monotonic() + 2
        while len(diagnostics.data) < mdns.LIMIT and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertLessEqual(len(diagnostics.data), mdns.LIMIT)
        self.assertEqual(diagnostics.reason(child), 'runtime-owner-mismatch')
        self.assertNotIn('SECRET', diagnostics.reason(child))

    def test_private_bus_has_reply_signal_and_connection_policy(self):
        import xml.etree.ElementTree as ET
        config = ET.fromstring((ROOT / 'mdns/dbus.conf').read_text())
        self.assertEqual(config.find('listen').text, mdns.BUS)
        self.assertIsNotNone(config.find('./policy/allow[@user="poc"]'))
        self.assertIsNotNone(config.find('./policy/allow[@send_requested_reply="true"]'))
        self.assertIsNotNone(config.find('./policy/allow[@send_type="signal"]'))


if __name__ == '__main__':
    unittest.main()
