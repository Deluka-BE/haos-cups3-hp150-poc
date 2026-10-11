#!/usr/bin/python3
"""Supervise one transport/filter invocation; never echo vendor stderr or argv."""
import os
import re
import selectors
import signal
import subprocess
import sys
import time


def supervise(stage, command, job, timeout=180):
    env = dict(os.environ)
    for key in ('SUPERVISOR_TOKEN', 'HASSIO_TOKEN'):
        env.pop(key, None)
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
    return supervise(stage, [executable, *args], job)


if __name__ == '__main__':
    sys.exit(main())
