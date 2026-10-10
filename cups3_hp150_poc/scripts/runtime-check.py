#!/usr/bin/env python3
"""Check fixed runtime paths and dynamic library lookup without printing environment."""
import ctypes
import os
from pathlib import Path
import tempfile


def check(root=Path('/work'), load=True):
    for name in ('filter/rastertospl', 'filter/rastertospl.real',
                 'lib/libscmssc.so', 'share/cups/model/uld-hp/cms/15xsc.cts',
                 'state/ppd/HP_Color_Laser_15x_Series.ppd'):
        path = root / name
        if not path.is_file() or not path.stat().st_size or not os.access(path, os.R_OK):
            raise RuntimeError(f'Missing/unreadable runtime component: {name}')
        if name.startswith('filter/') and not os.access(path, os.X_OK):
            raise RuntimeError(f'Non-executable runtime filter: {name}')
        print(f'Runtime component OK: {path}')
    for name in ('capture', 'spool', 'state'):
        with tempfile.TemporaryFile(dir=root / name):
            pass
        print(f'Runtime directory writable: {root / name}')
    if load:
        # dlopen checks the actual ULD library and its transitive dependencies.
        # The vendor raster filter also requires these two CUPS 2 ABI libraries.
        for name in ('libcups.so.2', 'libcupsimage.so.2', 'libscmssc.so'):
            ctypes.CDLL(name)
            print(f'Runtime library lookup OK: {name}')


if __name__ == '__main__':
    try:
        check()
    except (OSError, RuntimeError):
        # Loader errors can include arbitrary inherited search paths; keep logs fixed.
        raise SystemExit('ERROR: runtime path/library check failed; inspect fixed component paths')
