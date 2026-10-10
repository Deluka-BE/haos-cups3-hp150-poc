#!/usr/bin/env python3
"""Inspect local ULD files without executing proprietary binaries (no ldd)."""
import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys

REQUIRED = ('HP_Color_Laser_15x_Series.ppd', 'rastertospl',
            'libscmssc.so', 'cms/15xsc.cts')


def validate(root, expected='AArch64'):
    errors = []
    for name in REQUIRED:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            errors.append(f'MISSING/INVALID: {name} (nonempty regular file required)')
            continue
        print(f'{name}: sha256={hashlib.sha256(path.read_bytes()).hexdigest()}')
        if name.endswith('.ppd'):
            text = path.read_text(errors='replace')
            if not text.startswith('*PPD-Adobe:') or 'rastertospl' not in text:
                errors.append('PPD must have a PPD-Adobe header and reference rastertospl')
            for line in text.splitlines():
                if line.startswith(('*cupsFilter:', '*cupsFilter2:', '*NickName:')):
                    print(line)
        if name in ('rastertospl', 'libscmssc.so'):
            if shutil.which('file'):
                subprocess.run(['file', str(path)], check=True)
            if not shutil.which('readelf'):
                errors.append('readelf unavailable: cannot validate ELF architecture')
                continue
            header = subprocess.run(['readelf', '-h', str(path)], capture_output=True, text=True)
            machine = next((line.strip() for line in header.stdout.splitlines()
                            if 'Machine:' in line), 'not ELF')
            print(f'{name}: {machine}')
            if header.returncode or expected not in machine:
                errors.append(f'{name}: expected {expected}, got {machine}')
            deps = subprocess.run(['readelf', '-d', str(path)], capture_output=True, text=True)
            print('\n'.join(line.strip() for line in deps.stdout.splitlines()
                            if any(key in line for key in ('NEEDED', 'RPATH', 'RUNPATH')))
                  or 'No dynamic dependencies reported')
    for error in errors:
        print(error, file=sys.stderr)
    return bool(errors)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=pathlib.Path, default=pathlib.Path('hp-driver'))
    parser.add_argument('--expected-machine', default='AArch64')
    args = parser.parse_args()
    sys.exit(validate(args.directory, args.expected_machine))
