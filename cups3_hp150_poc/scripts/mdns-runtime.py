#!/usr/bin/env python3
"""Private unprivileged DNS-SD lifecycle; never submits jobs or edits queues."""
import os
import ipaddress
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

BUS = 'unix:path=/work/mdns/system_bus_socket'
LIMIT = 32768


def log(message):
    print('mDNS: ' + message, flush=True)


def probe(argv, timeout=2):
    """Bound both time and output; never publish raw D-Bus/browse output."""
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as child:
        data = bytearray()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline and len(data) < LIMIT:
                events = selector.select(max(0, deadline - time.monotonic()))
                if not events:
                    break
                block = os.read(child.stdout.fileno(), min(4096, LIMIT - len(data)))
                if not block:
                    break
                data.extend(block)
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        return bytes(data).decode('utf-8', 'replace')


def avahi(method):
    return probe(['dbus-send', '--system', '--print-reply', '--reply-timeout=1000',
                  '--dest=org.freedesktop.Avahi', '/', 'org.freedesktop.Avahi.Server.' + method])


def hostname():
    match = re.search(r'^\s*string "([a-zA-Z0-9.-]{1,253})"\s*$', avahi('GetHostNameFqdn'), re.M)
    return match.group(1) if match else None


def services(output, host, port):
    """Only resolved local PAPPL endpoints with the AirPrint subtype/TXT essentials."""
    found = set()
    for line in output.splitlines()[:256]:
        fields = line.split(';', 9)
        if len(fields) != 10 or fields[0] != '=':
            continue
        _, interface, protocol, name, kind, domain, target, address, service_port, txt = fields
        if kind != '_ipp._tcp' or target.lower() != host.lower() or service_port != str(port):
            continue
        try:
            ip = ipaddress.ip_address(address)
            if interface == 'lo' or ip.is_loopback or ip.is_unspecified:
                continue
        except ValueError:
            continue
        # Avahi escapes special bytes in parsable names. Keep those escapes, no controls.
        if not re.fullmatch(r'[\x20-\x7e]{1,256}', name):
            continue
        values = dict(re.findall(r'"(rp|pdl|URF)=([^"\r\n]*)"', txt))
        if not values.get('rp') or not values.get('URF') or 'image/urf' not in values.get('pdl', '').split(','):
            continue
        found.add(name)
    return sorted(found)[:16]


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def main(argv):
    for key in ('SUPERVISOR_TOKEN', 'HASSIO_TOKEN'):
        os.environ.pop(key, None)
    os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = BUS
    if argv == ['--diagnose']:
        try:
            host = hostname()
        except OSError:
            log('avahi=failed registration=unconfirmed port=8631')
            return 1
        if not host:
            log('avahi=failed registration=unconfirmed port=8631')
            return 1
        try:
            names = services(probe(['avahi-browse', '--parsable', '--resolve', '--terminate',
                                '_universal._sub._ipp._tcp'], timeout=5), host, 8631)
        except OSError:
            log('registration=unconfirmed; browse tool unavailable')
            return 1
        for name in names:
            log(f'registration=success service={name} hostname={host} port=8631 type=_ipp._tcp subtype=_universal pdl=image/urf URF=present')
        if not names:
            log(f'registration=unconfirmed hostname={host} port=8631; no resolved LAN AirPrint queue')
        return 0 if names else 1
    children = []
    stopping = False

    def shutdown(signum, frame):
        nonlocal stopping
        stopping = True
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        bus = daemon = None
        host = None
        try:
            Path('/work/mdns').mkdir(exist_ok=True)
            # Stale private socket can remain after an abrupt container stop.
            Path('/work/mdns/system_bus_socket').unlink(missing_ok=True)
            bus = subprocess.Popen(['dbus-daemon', '--nofork', '--nopidfile',
                                    '--config-file=/opt/poc/mdns/dbus.conf'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(bus)
            deadline = time.monotonic() + 5
            while not Path('/work/mdns/system_bus_socket').exists() and bus.poll() is None and not stopping and time.monotonic() < deadline:
                time.sleep(0.1)
            bus_ready = Path('/work/mdns/system_bus_socket').exists() and bus.poll() is None
            log('private-dbus=' + ('running' if bus_ready else 'failed'))
            if bus_ready and not stopping:
                daemon = subprocess.Popen(['avahi-daemon', '--no-drop-root', '--no-chroot',
                                           '--no-rlimits', '--file=/opt/poc/mdns/avahi.conf'],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                children.append(daemon)
                deadline = time.monotonic() + 10
                while daemon.poll() is None and not stopping and time.monotonic() < deadline:
                    if re.search(r'\bint32 2\b', avahi('GetState')):
                        host = hostname()
                        if host:
                            break
                    time.sleep(0.2)
        except OSError:
            log("private-daemon=failed; continuing manual USB runtime")
        log(f'avahi={"running" if host else "failed"} hostname={host or "unavailable"} port=8631 uid={os.getuid()}')
        if stopping:
            return 0
        # mDNS failure must not take the proven USB printing path down.
        app = subprocess.Popen(argv)
        children.append(app)
        deadline = time.monotonic() + 30
        reported = False
        if host:
            while app.poll() is None and not stopping and time.monotonic() < deadline:
                try:
                    names = services(probe(['avahi-browse', '--parsable', '--resolve', '--terminate',
                                            '_universal._sub._ipp._tcp'], timeout=3), host, 8631)
                except OSError:
                    log('registration=unconfirmed; browse tool unavailable')
                    break
                if names:
                    for name in names:
                        log(f'registration=success service={name} hostname={host} port=8631 type=_ipp._tcp subtype=_universal pdl=image/urf URF=present')
                    reported = True
                    break
                time.sleep(0.5)
        if not reported:
            log('registration=unconfirmed port=8631; daemon failure, no manual queue, or missing AirPrint records; no job submitted')
        # Supervise without restarting PAPPL or altering queues/jobs.
        failed = False
        while app.poll() is None and not stopping:
            if not failed and ((bus is not None and bus.poll() is not None) or (daemon is not None and daemon.poll() is not None)):
                log('daemon=exited registration=unavailable; PAPPL continues for manual USB use')
                failed = True
            time.sleep(0.5)
        return app.wait() if not stopping else 0
    except (OSError, ValueError):
        log('startup=failed; private daemon or application launch unavailable')
        return 1
    finally:
        for child in reversed(children):
            stop(child)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
