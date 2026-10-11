#!/usr/bin/env python3
"""Migrate only bounded PAPPL configuration, after the permanent privilege drop."""
from itertools import islice
import os
from pathlib import Path
import re
import stat
import tempfile

STATE = 'legacy-printer-app.state'
MAX_FILE = 1024 * 1024
MAX_TOTAL = 8 * MAX_FILE


def migrate(old=Path('/work/state'), new=Path('/data/state')):
    if new.is_symlink() or not new.is_dir():
        raise RuntimeError('invalid state directory')
    # Persistent state is authoritative, including an intentionally empty file.
    if os.path.lexists(new / STATE):
        if not stat.S_ISREG((new / STATE).lstat().st_mode):
            raise RuntimeError('invalid state file')
        return 'retained'
    if not os.path.lexists(old / STATE):
        return 'fresh'
    if old.is_symlink() or not old.is_dir():
        raise RuntimeError('invalid legacy directory')
    entries = sorted(islice(old.iterdir(), 257))
    if len(entries) > 256:
        raise RuntimeError('entry limit')
    names = [p.name for p in entries if re.fullmatch(r'p[0-9]{5,10}-inst-opt\.conf', p.name)]
    if len(names) > 63:
        raise RuntimeError('file limit')
    names.append(STATE)  # Publish the app state last; interrupted copies can retry.
    payloads = []
    total = 0
    for name in names:
        fd = os.open(old / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise RuntimeError('invalid legacy file')
            data = stream.read(MAX_FILE + 1)
        total += len(data)
        if len(data) > MAX_FILE or total > MAX_TOTAL:
            raise RuntimeError('size limit')
        payloads.append((name, data))
    for name, data in payloads:
        # Atomic publication without replacing any destination. No old data is deleted.
        with tempfile.NamedTemporaryFile(dir=new, prefix='.migration-', delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                try:
                    os.link(temporary, new / name)
                except FileExistsError:
                    if not stat.S_ISREG((new / name).lstat().st_mode):
                        raise RuntimeError('invalid destination')
            finally:
                temporary.unlink()
    directory = os.open(new, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return 'migrated'


if __name__ == '__main__':
    try:
        result = migrate()
    except (OSError, RuntimeError):
        raise SystemExit('ERROR: persistence status=failed')
    print(f'INFO: persistence status={result}', flush=True)
