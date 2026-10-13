#!/usr/bin/env python3
"""Resolve HP usbfs group once, then permanently enter the capture runtime."""
import ctypes
import os
from itertools import islice
from pathlib import Path
import re
import runpy
import stat
import sys

UID = GID = 10001


def hp_groups(sysfs=Path('/sys/bus/usb/devices'), usbfs=Path('/dev/bus/usb')):
    groups = set()
    try:
        entries = list(islice(sysfs.iterdir(), 256))
    except OSError:
        return []
    for device in entries:
        try:
            values = []
            for name in ('idVendor', 'idProduct', 'busnum', 'devnum'):
                with (device / name).open() as stream:
                    values.append(stream.read(16).strip().lower())
            if values[:2] != ['03f0', 'ea2a']:
                continue
            if not all(re.fullmatch(r'[0-9]{1,3}', v) and 1 <= int(v) <= 999
                       for v in values[2:]):
                continue
            node = usbfs / f'{int(values[2]):03d}' / f'{int(values[3]):03d}'
            info = node.lstat()
            if stat.S_ISCHR(info.st_mode) and os.major(info.st_rdev) == 189:
                # Never grant root-group membership or change host node permissions.
                if info.st_gid != 0:
                    groups.add(info.st_gid)
        except (OSError, ValueError):
            continue
    return sorted(groups)


def drop_privileges(groups):
    os.setgroups(groups)
    os.setresgid(GID, GID, GID)
    os.setresuid(UID, UID, UID)
    # Prevent exec from gaining privileges through setuid binaries/file caps.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), 'privilege restriction failed')
    if os.getresuid() != (UID,) * 3 or os.getresgid() != (GID,) * 3:
        raise RuntimeError('identity restriction failed')


def prepare_mdns_runtime():
    # /run can be a fresh tmpfs on HAOS. Prepare only this private path.
    try:
        runtime = Path('/run/avahi-daemon')
        runtime.mkdir(mode=0o755, exist_ok=True)
        if runtime.is_symlink() or not runtime.is_dir():
            raise RuntimeError('invalid Avahi runtime directory')
        os.chown(runtime, UID, GID)
    except (OSError, RuntimeError):
        # A discovery setup failure must not disable USB printing.
        print('mDNS: runtime=failed reason=directory-setup-failed', flush=True)


def prepare_state_runtime():
    # HAOS mounts /data freshly; own only our directory, never the mount or contents.
    data = Path('/data')
    if data.is_symlink() or not data.is_dir():
        raise RuntimeError('persistent storage unavailable')
    state = data / 'state'
    state.mkdir(mode=0o700, exist_ok=True)
    if state.is_symlink() or not state.is_dir():
        raise RuntimeError('invalid persistent directory')
    info = state.stat()
    if (info.st_uid, info.st_gid) != (UID, GID):
        os.chown(state, UID, GID)
    if stat.S_IMODE(info.st_mode) != 0o700:
        os.chmod(state, 0o700)


def main():
    for key in ('SUPERVISOR_TOKEN', 'HASSIO_TOKEN'):
        os.environ.pop(key, None)
    os.environ.pop('POC_LOG_LEVEL', None)
    if len(sys.argv) == 1 or sys.argv[1] in ('', 'server'):
        try:
            # Read Supervisor-owned options while privileged; carry only the allowlist.
            read_level = runpy.run_path(str(Path(__file__).with_name('log-level.py')))['read_level']
            os.environ['POC_LOG_LEVEL'] = read_level()
        except (OSError, ValueError, UnicodeError):
            print('ERROR: invalid add-on log_level options; refusing server startup', file=sys.stderr)
            return 1
    try:
        prepare_state_runtime()
        groups = hp_groups()
        prepare_mdns_runtime()
        drop_privileges(groups)
    except Exception:
        print('USB runtime: identity setup failed; refusing launch', flush=True)
        return 1
    print(f'USB runtime: uid={UID} gid={GID} HP supplementary-gids={groups}', flush=True)
    os.execv('/opt/poc/scripts/entrypoint.sh', ['entrypoint.sh', *sys.argv[1:]])


if __name__ == '__main__':
    sys.exit(main())
