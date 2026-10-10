#!/usr/bin/env python3
"""Check capture integrity and declared format, without logging document bytes.

A PJL QPDL declaration is signature evidence only, not QPDL page validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def verify(path):
    path = Path(path)
    result = {'job': 'unknown', 'bytes': 0, 'sha256': 'unavailable',
              'format': 'unknown', 'signature': 'none', 'passed': False}
    match = re.fullmatch(r'job-([0-9]+)-[^/]+\.spl', path.name, flags=re.ASCII)
    if match:
        result['job'] = int(match[1])
    try:
        digest = hashlib.sha256()
        with path.open('rb') as source:
            header = source.read(65536)
            digest.update(header)
            result['bytes'] = len(header)
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                result['bytes'] += len(chunk)
        result['sha256'] = digest.hexdigest()
        # Anchor at the stream start and require a complete PJL command line.
        # Do not recognize declarations buried in PDF/document/page payloads.
        pjl = re.match(rb'\x1b%-12345X((?:@PJL[^\r\n]*\r?\n)+)', header)
        if pjl and re.search(rb'(?:^|\n)@PJL ENTER LANGUAGE[ \t]*=[ \t]*QPDL[ \t]*\r?\n', pjl[1]):
            result.update(format='QPDL-declared', signature='PJL-QPDL')
        elif header.startswith(b'%PDF-'):
            result.update(format='PDF', signature='PDF-header')
        elif header[:4] in (b'RaSt', b'tSaR', b'RaS2', b'2SaR', b'RaS3', b'3SaR'):
            result.update(format='CUPS-raster', signature='CUPS-raster-magic')
        metadata = json.loads(Path(str(path) + '.json').read_text())
        result['passed'] = bool(
            match and isinstance(metadata, dict)
            and type(metadata.get('job_id')) is int and metadata['job_id'] == result['job']
            and type(metadata.get('size_bytes')) is int and metadata['size_bytes'] == result['bytes']
            and metadata.get('file') == path.name
            and metadata.get('sha256') == result['sha256']
            and result['bytes'] and result['signature'] == 'PJL-QPDL')
    except (OSError, ValueError, TypeError):
        pass
    return result


def report(result, stream=None):
    print(f'{"PASS" if result["passed"] else "FAIL"}: capture job={result["job"]} '
          f'bytes={result["bytes"]} sha256={result["sha256"]} '
          f'format={result["format"]} signature={result["signature"]}',
          file=stream if stream is not None else sys.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path, help='exact /work/capture/job-<id>-<unique>.spl path')
    args = parser.parse_args()
    result = verify(args.capture)
    report(result)
    sys.exit(0 if result['passed'] else 1)
