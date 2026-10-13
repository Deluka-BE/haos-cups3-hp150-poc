#!/usr/bin/python3
"""Supervise one transport/filter invocation; never echo vendor stderr or argv."""
import os
import re
import selectors
import signal
import subprocess
import sys
import time


RASTER_SHIM = '/opt/poc/lib/raster-header-diagnostics.so'
RASTER_FIELDS = ('width', 'height', 'xdpi', 'ydpi', 'cupsBitsPerColor',
                 'cupsBitsPerPixel', 'cupsNumColors', 'cupsBytesPerLine',
                 'cupsColorSpace', 'cupsColorOrder', 'cupsCompression',
                 'cupsRowCount', 'cupsRowFeed', 'cupsRowStep')
RASTER_RECORD = re.compile(rb'HP150_RASTER_HEADER 1' + rb' ([0-9]{1,10})' * 14)


def raster_header_message(line):
    """Accept only a fixed numeric record; no vendor text is ever forwarded."""
    match = RASTER_RECORD.fullmatch(line)
    if not match:
        return None
    values = tuple(int(value) for value in match.groups())
    if any(value > 0xffffffff for value in values):
        return None
    width, bits, actual = values[0], values[5], values[7]
    expected = (width * bits + 7) // 8
    relation = 'equal' if actual == expected else 'above' if actual > expected else 'below'
    return ('raster-header page=first ' +
            ' '.join(f'{key}={value}' for key, value in zip(RASTER_FIELDS, values)) +
            f' expected_bytes_per_line={expected} packed_relation={relation}'
            ' comparison_scope=packed-reference')


def supervise(stage, command, job, timeout=180):
    env = dict(os.environ)
    for key in ('SUPERVISOR_TOKEN', 'HASSIO_TOKEN'):
        env.pop(key, None)
    # Scope the shim to the proprietary raster child, never Python/USB.
    if stage == 'rastertospl':
        env['LD_PRELOAD'] = RASTER_SHIM + (' ' + env['LD_PRELOAD'] if env.get('LD_PRELOAD') else '')
    def report(message):
        print(f'INFO: path job={job} stage={stage} {message}', file=sys.stderr, flush=True)
    report('started deadline-seconds=' + str(timeout))
    try:
        child = subprocess.Popen(command, env=env, close_fds=False,
                                 stderr=subprocess.PIPE, start_new_session=True)
    except OSError as error:
        report(f'failed errno={error.errno}')
        return 1
    # Drain continuously with bounded storage; report only fixed failure categories.
    categories = set()
    tail = b''
    line = b''
    dropping = False
    control_count = 0
    raster_reported = False
    selector = selectors.DefaultSelector()
    selector.register(child.stderr, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    timed_out = False
    cancelled = False
    def cancel(signum, frame):
        nonlocal cancelled, deadline
        cancelled = True
        deadline = min(deadline, time.monotonic() + 2)
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass
    old_handlers = {sig: signal.signal(sig, cancel) for sig in (signal.SIGTERM, signal.SIGINT)}
    while child.poll() is None or selector.get_map():
        if time.monotonic() >= deadline:
            timed_out = True
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            break
        for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
            chunk = os.read(key.fd, 4096)
            if not chunk:
                selector.unregister(key.fileobj)
                continue
            # Preserve CUPS transport state protocol, only known fixed keywords.
            # Overlong or unknown lines are discarded, never echoed.
            for byte in chunk:
                if byte == 10:
                    match = re.fullmatch(rb'STATE: ([+-]?)(connecting-to-device|connected-to-device|offline-report|media-empty-warning|media-needed|marker-supply-low-warning|marker-supply-empty-warning|door-open-report)', line)
                    if not dropping and match and control_count < 64:
                        print(line.decode('ascii'), file=sys.stderr, flush=True)
                        control_count += 1
                    if stage == 'rastertospl' and not dropping and not raster_reported:
                        message = raster_header_message(line)
                        if message is not None:
                            report(message)
                            raster_reported = True
                    line = b''
                    dropping = False
                elif len(line) < 256 and not dropping:
                    line += bytes((byte,))
                else:
                    dropping = True
            tail = (tail + chunk).lower()
            for category, needle in (('open', b'unable to open'), ('claim', b'claim'),
                                     ('write', b'write'), ('timeout', b'timeout'),
                                     ('permission', b'permission denied'), ('busy', b'busy'),
                                     ('disconnected', b'no device'), ('cms', b'cms')):
                if needle in tail and category not in categories:
                    categories.add(category)
                    report('vendor-marker=' + category)
            for pattern in (rb'libusb error (-?[0-9]{1,8})', rb'libusb write operation returned ([0-9a-f]{1,8})'):
                match = re.search(pattern, tail)
                if match and 'libusb-code' not in categories:
                    categories.add('libusb-code')
                    report('libusb-code=' + match.group(1).decode('ascii'))
            tail = tail[-256:]
    result = child.wait()
    for sig, handler in old_handlers.items():
        signal.signal(sig, handler)
    selector.close()
    child.stderr.close()
    report(f'finished exit={result} timeout={str(timed_out).lower()} cancelled={str(cancelled).lower()} retry=none')
    return 1 if timed_out or result < 0 else result


def valid_usb_uri(uri):
    # Classification only: no parsing result or input is ever printed.
    return (uri.startswith('usb://') and len(uri) > 6
            and not any(ord(char) <= 32 or ord(char) == 127 for char in uri))


def main():
    stage = sys.argv[1]
    args = sys.argv[2:]
    executable = {'usb': '/opt/poc/backend/usb.real',
                  'rastertospl': '/work/filter/rastertospl.real'}[stage]
    # Discovery must retain unmodified stdout; no job or document is involved.
    if stage == 'usb' and not args:
        os.environ.pop('SUPERVISOR_TOKEN', None)
        os.environ.pop('HASSIO_TOKEN', None)
        os.execv(executable, ['usb', *args])
    job = args[0] if args and args[0].isascii() and args[0].isdigit() and len(args[0]) <= 10 else 'unknown'
    if stage == 'usb':
        valid_uri = valid_usb_uri(os.environ.get('DEVICE_URI', ''))
        print(f'INFO: path job={job} stage=usb launch path=/opt/poc/backend/usb.real '
              f'class=usb argc={len(args)} device-uri={"usb" if valid_uri else "invalid"} '
              f'normalized-usb={str(valid_uri).lower()}', file=sys.stderr, flush=True)
        if len(args) not in (5, 6) or job == 'unknown' or not valid_uri:
            print(f'ERROR: path job={job} stage=usb rejected reason=invalid-usb-invocation retry=none',
                  file=sys.stderr, flush=True)
            return 1
    return supervise(stage, [executable, *args], job)


if __name__ == '__main__':
    sys.exit(main())
