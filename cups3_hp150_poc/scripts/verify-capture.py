#!/usr/bin/env python3
"""Verify captured bytes/metadata and HP QPDL framing; never print document bytes."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(path):
    metadata = json.loads(Path(str(path) + '.json').read_text())
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as source:
        header = source.read(65536)
        digest.update(header)
        size += len(header)
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    if (metadata['file'] != path.name or metadata['size_bytes'] != size
            or metadata['sha256'] != digest.hexdigest() or not size):
        raise ValueError('capture metadata mismatch')
    # The pinned HP SPL-C filter emits this PJL language declaration.
    if b'@PJL ENTER LANGUAGE = QPDL' not in header:
        raise ValueError('HP QPDL framing absent; extension alone is not SPL evidence')
    print(f'PASS: {path.name} job={metadata["job_id"]} bytes={size} sha256={digest.hexdigest()}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path, help='exact /work/capture/job-<id>-<unique>.spl path')
    args = parser.parse_args()
    try:
        verify(args.capture)
    except (OSError, ValueError, KeyError):
        raise SystemExit('FAIL: unreadable capture, metadata mismatch or missing HP QPDL framing')
