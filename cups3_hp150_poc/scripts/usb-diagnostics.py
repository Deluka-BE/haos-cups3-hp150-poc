#!/usr/bin/env python3
"""Bounded discovery only: never submit jobs, open printers or log raw output."""
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time
from urllib.parse import unquote, urlsplit, parse_qsl

LIMIT = 32768
TIMEOUT = 8
MAX_DEVICES = 32


def probe(argv, timeout=TIMEOUT):
    # Explicit environment prevents discovery debug messages inheriting credentials.
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'HOME': '/nonexistent'}
    for key in ('LD_LIBRARY_PATH', 'PPD_DIRS', 'USER_PPD_DIR', 'FILTER_DIR',
                'BACKEND_DIR', 'STATE_DIR', 'SPOOL_DIR', 'CAPTURE_DIR'):
        if key in os.environ:
            env[key] = os.environ[key]
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, env=env, start_new_session=True)
    except OSError:
        return 'unavailable', ''
    data = bytearray()
    status = 'ok'
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + timeout
            while sel.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = 'timeout'
                    break
                for key, _ in sel.select(min(remaining, 0.1)):
                    chunk = os.read(key.fd, min(4096, LIMIT + 1 - len(data)))
                    if not chunk:
                        sel.unregister(key.fileobj)
                    else:
                        data.extend(chunk)
                    if len(data) > LIMIT:
                        status = 'output-limit'
                        break
                if status != 'ok':
                    break
            if status == 'ok':
                try:
                    if p.wait(timeout=max(0.01, deadline - time.monotonic())):
                        status = 'failed'
                except subprocess.TimeoutExpired:
                    status = 'timeout'
    finally:
        # Also stop any discovery descendants which retained the output pipe.
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()
        p.stdout.close()
    return status, bytes(data[:LIMIT]).decode('ascii', 'replace')


def hp_uris(output):
    found = set()
    for uri in re.findall(r'(?:cups:)?usb://[^\s"<>]+', output):
        if len(uri) > 512 or not re.fullmatch(r'[A-Za-z0-9%:/?&=._+~-]+', uri):
            continue
        parsed = urlsplit(uri.removeprefix('cups:'))
        model = unquote(parsed.path).lower()
        if parsed.netloc.lower() != 'hp' or not re.search(r'color[ _-]*laser[ _-]*150a?(?:$|[ /_-])', model):
            continue
        # Only known USB identity parameters; never echo arbitrary query data.
        if any(k not in ('serial', 'interface') or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}', v)
               for k, v in parse_qsl(parsed.query, keep_blank_values=True)):
            continue
        found.add(uri)
    return sorted(found)[:MAX_DEVICES]


def enumerate_usb(sysfs=Path('/sys/bus/usb/devices')):
    status, output = probe(['/usr/bin/lsusb'])
    records = re.findall(r'^Bus (\d{3}) Device (\d{3}): ID ([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\b', output, re.M)
    if status == 'ok':
        source = 'lsusb'
    else:
        source = 'sysfs'
        records = []
        try:
            for index, path in enumerate(sysfs.iterdir()):
                if index >= 256:
                    break
                try:
                    values = []
                    for name in ('busnum', 'devnum', 'idVendor', 'idProduct'):
                        with (path / name).open('r') as stream:
                            values.append(stream.read(16).strip())
                    if all(re.fullmatch(pattern, value) for pattern, value in zip(
                            (r'\d{1,3}', r'\d{1,3}', r'[0-9a-fA-F]{4}', r'[0-9a-fA-F]{4}'), values)):
                        records.append(tuple(values))
                except OSError:
                    continue
        except OSError:
            print('USB diagnostics: enumeration=unavailable')
            return
    print(f'USB diagnostics: enumeration={source} records={min(len(records), MAX_DEVICES)} capped={len(records) > MAX_DEVICES}')
    for bus, device, vendor, product in records[:MAX_DEVICES]:
        print(f'USB diagnostics: bus={int(bus):03d} device={int(device):03d} id={vendor.lower()}:{product.lower()}')


def main():
    usb = Path('/dev/bus/usb')
    print(f'USB diagnostics: /dev/bus/usb exists={usb.exists()} directory={usb.is_dir()} readable={os.access(usb, os.R_OK)} searchable={os.access(usb, os.X_OK)}')
    print('USB diagnostics: permissions are current-UID checks; enumeration does not prove device-node access')
    enumerate_usb()
    for label, argv in (
            ('cups-usb', ['/opt/poc/diagnostics/usb']),
            ('pappl-capture-only', ['/usr/bin/legacy-printer-app', 'devices', '-o', 'log-level=error', '-o', 'log-file=-'])):
        status, output = probe(argv)
        uris = hp_uris(output)
        visibility = 'visible' if uris else ('not-reported' if status == 'ok' else 'inconclusive')
        print(f'USB diagnostics: discovery={label} status={status} HP-Color-Laser-150a={visibility}')
        for uri in uris:
            print(f'USB diagnostics: discovery={label} device-uri={uri}')
    print('USB diagnostics: USB printing disabled; PAPPL allowlist=capture')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Diagnostics must never prevent the validated capture service starting.
        print('USB diagnostics: unavailable (details suppressed)')
