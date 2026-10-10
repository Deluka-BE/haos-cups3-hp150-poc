#!/usr/bin/env python3
"""CUPS backend scaffold: accept only capture:/hp150, never interpret a file URI."""
import datetime
import hashlib
import json
import os
import pathlib
import select
import runpy
import stat
import struct
import threading
import sys
import tempfile


def side_channel(stop, fd=4):
    """CUPS fd 4 protocol; virtual sink status, no physical printer claims."""
    pending = b''
    try:
        if not stat.S_ISSOCK(os.fstat(fd).st_mode):
            return
        while not stop.is_set():
            if not select.select([fd], [], [], 0.1)[0]:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                return
            pending += chunk
            while len(pending) >= 4:
                command, _, length = struct.unpack('!BBH', pending[:4])
                if len(pending) < 4 + length:
                    break
                pending = pending[4 + length:]
                # GET_BIDI=no, GET_STATE=online virtual sink, GET_CONNECTED=yes.
                replies = {3: b'\x00', 4: b'MFG:HP;MDL:HP Color Laser 15x Series;CMD:SPLC;',
                           5: b'\x01', 8: b'\x01'}
                data = replies.get(command, b'')
                status = 1 if command in replies else 7  # OK / NOT_IMPLEMENTED
                packet = struct.pack('!BBH', command, status, len(data)) + data
                while packet:
                    written = os.write(fd, packet)
                    packet = packet[written:]
    except (OSError, ValueError):
        return  # fd 4 is optional in direct backend tests


def main(argv):
    if len(argv) == 1:
        print('direct capture:/hp150 "HP Color Laser 150 capture" "HP150 file capture" '
              '"MFG:HP;MDL:HP Color Laser 15x Series;CMD:SPLC;"')
        return 0
    if (len(argv) not in (6, 7) or os.environ.get('DEVICE_URI') != 'capture:/hp150'
            or not argv[1].isascii() or not argv[1].isdigit()):
        print('ERROR: invalid capture invocation/URI/job id', file=sys.stderr)
        return 1
    directory = pathlib.Path(os.environ.get('CAPTURE_DIR', '/work/capture'))
    stop = threading.Event()
    channel = threading.Thread(target=side_channel, args=(stop,), daemon=True)
    channel.start()
    filename = None
    final = None
    metadata_part = None
    try:
        verifier = runpy.run_path(str(pathlib.Path(__file__).resolve().with_name('verify-capture.py')))
        directory.mkdir(parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix=f'job-{argv[1]}-', suffix='.spl.part', dir=directory)
        digest = hashlib.sha256()
        size = 0
        source = open(argv[6], 'rb') if len(argv) == 7 else sys.stdin.buffer
        try:
            with os.fdopen(fd, 'wb') as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
        finally:
            if len(argv) == 7:
                source.close()
        if size == 0:
            pathlib.Path(filename).unlink()
            return 0  # Administrative status opens are not print evidence.
        final = filename[:-5]
        metadata_part = final + '.json.part'
        with open(metadata_part, 'x', encoding='utf-8') as output:
            os.chmod(metadata_part, 0o600)
            json.dump({'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'job_id': int(argv[1]), 'size_bytes': size,
                       'sha256': digest.hexdigest(), 'file': pathlib.Path(final).name}, output)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.rename(filename, final)
        os.rename(metadata_part, final + '.json')
        result = verifier['verify'](pathlib.Path(final))
        verifier['report'](result, stream=sys.stderr)
        return 0 if result['passed'] else 1
    except Exception:
        if final and pathlib.Path(final + '.json').is_file():
            print(f'FAIL: capture job={int(argv[1])} bytes={size} sha256={digest.hexdigest()} '
                  'format=unknown signature=none', file=sys.stderr)
            return 1  # Retain completed evidence even if verification itself fails.
        for path in (filename, final, metadata_part):
            if path:
                pathlib.Path(path).unlink(missing_ok=True)
        print('ERROR: capture failed (input/read/write); no completed capture retained', file=sys.stderr)
        return 1
    finally:
        stop.set()
        channel.join(timeout=0.5)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
