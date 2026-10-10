#!/usr/bin/env python3
"""CUPS backend scaffold: accept only capture:/hp150, never interpret a file URI."""
import os
import pathlib
import shutil
import sys
import tempfile


def main(argv):
    if len(argv) == 1:
        print('direct capture:/hp150 "HP Color Laser 150 capture" "HP150 file capture"')
        return 0
    if len(argv) not in (6, 7) or os.environ.get('DEVICE_URI') != 'capture:/hp150':
        print('ERROR: invalid capture invocation/URI', file=sys.stderr)
        return 1
    directory = pathlib.Path(os.environ.get('CAPTURE_DIR', '/work/capture'))
    directory.mkdir(parents=True, exist_ok=True)
    # A unique file for every invocation; spool retries cannot overwrite earlier evidence.
    fd, filename = tempfile.mkstemp(prefix='job-', suffix='.spl.part', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as output:
            if len(argv) == 7:
                with open(argv[6], 'rb') as source:
                    shutil.copyfileobj(source, output)
            else:
                shutil.copyfileobj(sys.stdin.buffer, output)
            output.flush()
            os.fsync(output.fileno())
        final = filename[:-5]
        os.rename(filename, final)
        print(f'INFO: Captured {os.path.getsize(final)} bytes to {final}', file=sys.stderr)
        return 0
    except Exception:
        pathlib.Path(filename).unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    sys.exit(main(sys.argv))
