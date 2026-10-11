#!/usr/bin/env python3
"""Bounded startup discovery only; no queue creation or print invocation."""
import importlib.util
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location('usb_diagnostics', Path(__file__).with_name('usb-diagnostics.py'))
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)

BACKOFF = (2, 4, 8, 16, 16)
PROBE_TIMEOUT = 8
ATTEMPTS = len(BACKOFF) + 1


def settle(probe=diagnostics.probe, sleep=time.sleep):
    for attempt in range(1, ATTEMPTS + 1):
        # Exercise the same wrapped backend used by retrofit; discard raw output.
        cups_status, cups_output = probe(['/opt/poc/backend/usb'], timeout=PROBE_TIMEOUT)
        app_status, app_output = probe(['/usr/bin/legacy-printer-app', 'devices',
                                       '-o', 'log-level=error', '-o', 'log-file=-'],
                                      timeout=PROBE_TIMEOUT)
        # Only a successful retrofit enumeration establishes application readiness.
        ready = app_status == 'ok' and bool(diagnostics.hp_uris(app_output))
        backend = cups_status == 'ok' and bool(diagnostics.hp_uris(cups_output))
        print(f'INFO: usb-settle attempt={attempt} backend={"visible" if backend else "unconfirmed"} '
              f'application={"visible" if ready else "unconfirmed"}', flush=True)
        if ready:
            print(f'INFO: usb-settle result=ready attempts={attempt}', flush=True)
            return True
        if attempt < ATTEMPTS:
            delay = BACKOFF[attempt - 1]
            print(f'INFO: usb-settle backoff-seconds={delay}', flush=True)
            sleep(delay)
    print(f'INFO: usb-settle result=exhausted attempts={ATTEMPTS}', flush=True)
    return False


if __name__ == '__main__':
    try:
        settle()
    except Exception:
        # USB failure must not disable capture or the web service; no raw exceptions.
        print('INFO: usb-settle result=failed', flush=True)
