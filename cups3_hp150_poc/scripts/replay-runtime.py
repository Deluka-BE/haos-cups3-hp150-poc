#!/usr/bin/python3
"""Offline HP replay: bubblewrap by default; explicit unsandboxed diagnostic opt-in."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import shutil
import subprocess
import sys

FILTER = '/work/filter/rastertospl.real'
ALLOWED_ENV = set(('PPD LD_LIBRARY_PATH CUPS_DATADIR CUPS_SERVERBIN CUPS_SERVERROOT '
                   'CUPS_FONTPATH CUPS_CACHEDIR CONTENT_TYPE FINAL_CONTENT_TYPE PRINTER '
                   'PRINTER_INFO LANG LC_ALL CHARSET RIP_MAX_CACHE HOME TMPDIR PATH').split())


def identity(path):
    p = Path(path)
    result = {'path': str(p), 'resolved': str(p.resolve())}
    try:
        h = hashlib.sha256()
        with p.open('rb') as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        result.update(bytes=p.stat().st_size, sha256=h.hexdigest())
    except OSError as error:
        result['error'] = error.__class__.__name__
    return result


def probe(argv, env):
    try:
        p = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors='replace', timeout=30, close_fds=True)
        return {'exit': p.returncode, 'text': p.stdout}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'error': error.__class__.__name__}


def sandbox_command(output, raster, ppd, argv):
    # Hide host /dev (including USB), /sys and sockets under /run and /tmp.
    # No host CUPS channels survive; network and all other namespaces are private.
    return ['/usr/bin/bwrap', '--unshare-all', '--die-with-parent', '--new-session',
            '--cap-drop', 'ALL', '--ro-bind', '/', '/', '--dev', '/dev',
            '--proc', '/proc', '--tmpfs', '/sys', '--tmpfs', '/run', '--tmpfs', '/tmp',
            '--bind', str(output), '/tmp/replay',
            '--ro-bind', str(raster), '/tmp/input.raster',
            '--ro-bind', str(ppd), '/tmp/input.ppd', '--chdir', '/tmp/replay',
            '--', *argv]


def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def replay(boundary, output, timeout, raster=Path('/tmp/input.raster'),
           ppd=Path('/tmp/input.ppd'), mode='bwrap'):
    env = {k: v for k, v in boundary['environment'].items() if k in ALLOWED_ENV}
    env['PPD'] = str(ppd)
    argv = boundary['argv']
    if len(argv) not in (6, 7) or argv[0] != FILTER or not all(isinstance(v, str) for v in argv):
        raise ValueError('expected captured rastertospl argv with five CUPS arguments')
    command = [FILTER, *argv[1:6]]  # saved filename, if any, replaced by captured stdin
    report = {'schema': 1, 'argv': command, 'environment': env,
              'mode': mode, 'input': identity(raster), 'ppd': identity(env['PPD']),
              'boundary': boundary,
              'limitations': ['allowlisted snapshot only; PPD and input paths remapped',
                              'LD_DEBUG=libs,files,versions added for this offline replay',
                              'loader trace proves library resolution, not CMS file reads',
                              ('sandbox changes devices/network/cwd/tmp; not a live-job trace'
                               if mode == 'bwrap' else
                               'UNSANDBOXED: host devices/network/files remain accessible; diagnostic filter only')]}
    report['elf'] = probe(['/usr/bin/readelf', '-l', '-d', '-V', FILTER], env)
    report['ldd'] = probe(['/usr/bin/ldd', '-v', FILTER], env)
    report['glibc'] = probe(['/usr/bin/getconf', 'GNU_LIBC_VERSION'], env)
    report['packages'] = probe(['/usr/bin/dpkg-query', '-W',
                                '-f=${binary:Package}\t${Version}\t${Architecture}\n'], env)
    trace_env = dict(env, LD_DEBUG='libs,files,versions')
    with open(raster, 'rb') as source, (output / 'replay.spl').open('xb') as spl, (output / 'loader-stderr.txt').open('xb') as err:
        try:
            child = subprocess.Popen(command, env=trace_env, stdin=source, stdout=spl,
                                     stderr=err, close_fds=True, cwd=output, start_new_session=True,
                                     preexec_fn=limits)
            try:
                report['filter_exit'] = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                report.update(filter_exit=child.wait(), timed_out=True)
        except OSError as error:
            report.update(filter_exit=None, launch_error=error.__class__.__name__,
                          launch_errno=error.errno)
    trace = (output / 'loader-stderr.txt').read_text(errors='replace')
    # Canonical report excludes loader PIDs and timestamps. Keep raw evidence separately.
    report['loader_trace'] = re.sub(r'(?m)^\s*\d+:\s?', '', trace)
    for key in ('elf', 'ldd'):
        if 'text' in report[key]:
            report[key]['text'] = re.sub(r'0x[0-9a-fA-F]{8,}', '<address>', report[key]['text'])
    report['loader_trace'] = re.sub(r'0x[0-9a-fA-F]{8,}', '<address>', report['loader_trace'])
    if 'text' in report['packages']:
        report['packages']['text'] = '\n'.join(sorted(report['packages']['text'].splitlines())) + '\n'
    paths = set(re.findall(r'(?:=>\s*|calling init:\s*|file=)(/[^\s;\[()]+)',
                           report['ldd'].get('text', '') + '\n' + trace))
    paths.update((FILTER, '/work/lib/libscmssc.so'))
    paths.update(re.findall(r'Requesting program interpreter:\s*([^\]]+)', report['elf'].get('text', '')))
    cms = Path(env.get('CUPS_DATADIR', '/usr/share/cups')) / 'model/uld-hp/cms'
    paths.update(str(p) for p in sorted(cms.glob('*')) if p.is_file())
    report['runtime_files'] = [identity(p) for p in sorted(paths)]
    report['output'] = identity(output / 'replay.spl')
    (output / 'report.json').write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + '\n')
    return 0 if report['filter_exit'] == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boundary', type=Path, required=True)
    parser.add_argument('--raster', type=Path, required=True)
    parser.add_argument('--ppd', type=Path, help='override embedded PPD; recorded by hash')
    parser.add_argument('--output-dir', type=Path, required=True, help='must not exist')
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--offline-unsandboxed-ok', action='store_true',
                        help='explicitly run diagnostic filter without bwrap isolation (host access remains)')
    args = parser.parse_args()
    os.umask(0o077)
    boundary = json.loads(args.boundary.read_text())
    if not 1 <= args.timeout <= 1800:
        parser.error('timeout must be 1..1800 seconds')
    raster = args.raster.resolve(strict=True)
    if not raster.is_file() or raster.stat().st_size > 512 * 1024 * 1024:
        parser.error('raster must be a regular file <=512 MiB')
    with raster.open('rb') as stream:
        if stream.read(4) not in (b'RaSt', b'tSaR', b'RaS2', b'2SaR', b'RaS3', b'3SaR'):
            parser.error('input is not CUPS raster')
    output = args.output_dir.resolve()
    output.mkdir(mode=0o700)  # never overwrite capture or earlier diagnostics
    # Copy while the caller can read the protected capture directory. Bubblewrap
    # only receives private diagnostic sources, never the original capture path.
    staged_raster = output / 'input.raster'
    with raster.open('rb') as source, staged_raster.open('xb') as target:
        shutil.copyfileobj(source, target)
    ppd = output / 'snapshot.ppd'
    ppd.write_bytes(args.ppd.read_bytes() if args.ppd else boundary['ppd']['text'].encode('latin1'))
    (output / 'boundary.json').write_text(json.dumps(boundary, sort_keys=True, indent=2) + '\n')
    mode = 'offline-unsandboxed' if args.offline_unsandboxed_ok else 'bwrap'
    worker_output = output if args.offline_unsandboxed_ok else Path('/tmp/replay')
    worker_raster = staged_raster if args.offline_unsandboxed_ok else Path('/tmp/input.raster')
    worker_ppd = ppd if args.offline_unsandboxed_ok else Path('/tmp/input.ppd')
    worker = ('import runpy,json,pathlib; m=runpy.run_path(' + repr(str(Path(__file__).resolve())) + '); '
              'raise SystemExit(m["replay"](json.loads(pathlib.Path(' +
              repr(str(worker_output / 'boundary.json')) + ').read_text()),pathlib.Path(' +
              repr(str(worker_output)) + '),' + str(args.timeout) + ',pathlib.Path(' +
              repr(str(worker_raster)) + '),pathlib.Path(' + repr(str(worker_ppd)) + '),' +
              repr(mode) + '))')
    command = ['/usr/bin/python3', '-c', worker]
    if not args.offline_unsandboxed_ok:
        command = sandbox_command(output, staged_raster, ppd, command)
    with (output / 'sandbox-stderr.txt').open('xb') as errors:
        try:
            return subprocess.run(command, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=errors, close_fds=True, timeout=args.timeout + 150).returncode
        except (OSError, subprocess.TimeoutExpired):
            print('Replay sandbox unavailable/failed; no unsandboxed fallback.', file=sys.stderr)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
