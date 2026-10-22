#!/usr/bin/python3
"""Supervise one transport/filter invocation; never echo vendor stderr or argv."""
import os
import re
import selectors
import signal
import subprocess
import sys
import time
import hashlib
import json
import pathlib
import shutil
import threading


RASTER_FIELDS = ('width', 'height', 'xdpi', 'ydpi', 'cupsBitsPerColor',
                 'cupsBitsPerPixel', 'cupsNumColors', 'cupsBytesPerLine',
                 'cupsColorSpace', 'cupsColorOrder', 'cupsCompression',
                 'cupsRowCount', 'cupsRowFeed', 'cupsRowStep')
RASTER_RECORD = re.compile(rb'HP150_RASTER_HEADER 1' + rb' ([0-9]{1,10})' * 14)
CAPTURE_STATE = pathlib.Path('/run/hp150-raster-capture')
CAPTURE_DIR = pathlib.Path('/share/cups3-capture')
CAPTURE_MAX_STREAM = 512 * 1024 * 1024
CAPTURE_MIN_FREE = 1152 * 1024 * 1024
CAPTURE_CHUNK = 1024 * 1024


def raster_header_message(line):
    """Accept only a fixed numeric record; no vendor text is ever forwarded."""
    match = RASTER_RECORD.fullmatch(line)
    if not match:
        return None
    values = tuple(int(value) for value in match.groups())
    if any(value > 0xffffffff for value in values):
        return None
    width, bits, actual = values[0], values[5], values[7]
    expected = (width * bits + 7) // 8
    relation = 'equal' if actual == expected else 'above' if actual > expected else 'below'
    return ('raster-header page=first ' +
            ' '.join(f'{key}={value}' for key, value in zip(RASTER_FIELDS, values)) +
            f' expected_bytes_per_line={expected} packed_relation={relation}'
            ' comparison_scope=packed-reference')


def _safe_unlink(path):
    try:
        pathlib.Path(path).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _claim_capture(stage, job):
    """Atomically claim the one-shot. Any setup failure disables capture, never printing."""
    if stage != 'rastertospl' or os.environ.get('POC_CAPTURE_RASTER_ONCE') != '1':
        return None
    try:
        os.replace(CAPTURE_STATE / 'armed', CAPTURE_STATE / 'claimed')
    except OSError:
        return None
    try:
        if CAPTURE_DIR.is_symlink() or not CAPTURE_DIR.is_dir():
            raise OSError('capture directory unavailable')
        if shutil.disk_usage(CAPTURE_DIR).free < CAPTURE_MIN_FREE:
            raise OSError('insufficient capture storage')
        parts = {
            'in': CAPTURE_DIR / 'cups3-reference.in.raster.part',
            'out': CAPTURE_DIR / 'cups3-reference.out.spl.part',
        }
        for path in parts.values():
            _safe_unlink(path)
        inf = parts['in'].open('xb', buffering=0)
        outf = parts['out'].open('xb', buffering=0)
        for path in parts.values():
            os.chmod(path, 0o600)
        return {
            'job': job, 'parts': parts, 'in_file': inf, 'out_file': outf,
            'in_hash': hashlib.sha256(), 'out_hash': hashlib.sha256(),
            'in_bytes': 0, 'out_bytes': 0, 'bad': threading.Event(),
            'lock': threading.Lock(), 'reason': None, 'raster_header': None,
        }
    except OSError:
        try:
            inf.close()
        except (NameError, OSError):
            pass
        try:
            outf.close()
        except (NameError, OSError):
            pass
        for suffix in ('cups3-reference.in.raster.part', 'cups3-reference.out.spl.part'):
            _safe_unlink(CAPTURE_DIR / suffix)
        print(f'INFO: path job={job} stage=rastertospl capture status=skipped reason=storage',
              file=sys.stderr, flush=True)
        return None


# Deliberate allowlist: never serialize service credentials or the whole environment.
BOUNDARY_ENV = ('PPD', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'CUPS_DATADIR',
                'CUPS_SERVERBIN', 'CUPS_SERVERROOT', 'CUPS_FONTPATH',
                'CUPS_CACHEDIR', 'CONTENT_TYPE', 'FINAL_CONTENT_TYPE',
                'PRINTER', 'PRINTER_INFO', 'LANG', 'LC_ALL', 'CHARSET',
                'RIP_MAX_CACHE', 'HOME', 'TMPDIR', 'PATH')


def _boundary_file(path, content=False):
    result = {'path': str(path)}
    try:
        # Bounded diagnostics, including accidental oversized/non-regular PPDs.
        path = pathlib.Path(path)
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            return dict(result, status='unavailable')
        data = path.read_bytes()
        result.update(status='readable', bytes=len(data),
                      sha256=hashlib.sha256(data).hexdigest())
        if content:
            result['text'] = data.decode('latin1')
    except OSError:
        result['status'] = 'unavailable'
    return result


def capture_boundary(command, env):
    """Private evidence of the actual Popen boundary; no values go to logs.

    IPP attributes are upstream of this boundary; argv[5] is the exact mapped
    option string, not proof of the original IPP request or resolved PPD marks.
    File readability/hash proves presence, not that the vendor opened a file.
    """
    resources = ['/work/filter/rastertospl.real', '/work/lib/libscmssc.so']
    cms = pathlib.Path(env.get('CUPS_DATADIR', '/usr/share/cups')) / 'model/uld-hp/cms'
    if cms.is_dir():
        resources.extend(str(p) for p in sorted(cms.glob('*'))[:128] if p.is_file())
    return {'schema': 1, 'argv': list(command),
            'environment': {k: env[k] for k in BOUNDARY_ENV if k in env},
            'ppd': _boundary_file(env.get('PPD', ''), content=True),
            'resources': [_boundary_file(p) for p in resources],
            'limitations': ['environment is allowlisted', 'IPP request not captured',
                            'resource presence does not prove vendor lookup']}


def _save_boundary(command, env):
    target = CAPTURE_DIR / 'cups3-reference.boundary.json'
    part = target.with_suffix('.json.part')
    try:
        _safe_unlink(part)
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='ascii') as stream:
            json.dump(capture_boundary(command, env), stream, ensure_ascii=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(part, target)
        return hashlib.sha256(target.read_bytes()).hexdigest()
    except (OSError, ValueError):
        _safe_unlink(part)
        _safe_unlink(target)
        return False


def _capture_bad(session, reason):
    with session['lock']:
        if session['reason'] is None:
            session['reason'] = reason
            session['bad'].set()


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        try:
            count = os.write(fd, view)
        except InterruptedError:
            continue
        if count <= 0:
            raise BrokenPipeError('short write')
        view = view[count:]


def _tee_input(child, session):
    try:
        while True:
            chunk = os.read(0, CAPTURE_CHUNK)
            if not chunk:
                break
            view = memoryview(chunk)
            while view:
                try:
                    count = os.write(child.stdin.fileno(), view)
                except InterruptedError:
                    continue
                if count <= 0:
                    raise BrokenPipeError('short write')
                forwarded = bytes(view[:count])
                session['in_bytes'] += count
                session['in_hash'].update(forwarded)
                if not session['bad'].is_set():
                    if session['in_bytes'] > CAPTURE_MAX_STREAM:
                        _capture_bad(session, 'limit')
                    else:
                        try:
                            _write_all(session['in_file'].fileno(), forwarded)
                        except OSError:
                            _capture_bad(session, 'write')
                view = view[count:]
    except OSError:
        # The capture now contains only bytes successfully presented to the child.
        pass
    finally:
        try:
            child.stdin.close()
        except OSError:
            pass
        try:
            if not session['bad'].is_set():
                os.fsync(session['in_file'].fileno())
            session['in_file'].close()
        except OSError:
            _capture_bad(session, 'write')


def _tee_output(child, session):
    try:
        while True:
            chunk = os.read(child.stdout.fileno(), CAPTURE_CHUNK)
            if not chunk:
                break
            session['out_bytes'] += len(chunk)
            session['out_hash'].update(chunk)
            if not session['bad'].is_set():
                if session['out_bytes'] > CAPTURE_MAX_STREAM:
                    _capture_bad(session, 'limit')
                else:
                    try:
                        _write_all(session['out_file'].fileno(), chunk)
                    except OSError:
                        _capture_bad(session, 'write')
            _write_all(1, chunk)
    except OSError:
        try:
            child.stdout.close()
        except OSError:
            pass
    finally:
        try:
            if not session['bad'].is_set():
                os.fsync(session['out_file'].fileno())
            session['out_file'].close()
        except OSError:
            _capture_bad(session, 'write')


def _capture_formats(input_path, output_path):
    """Bounded signature inspection; never emit arbitrary document bytes."""
    with input_path.open('rb') as stream:
        magic = stream.read(4)
    raster = magic in (b'RaSt', b'tSaR', b'RaS2', b'2SaR', b'RaS3', b'3SaR')
    with output_path.open('rb') as stream:
        header = stream.read(65536)
    pjl = re.match(rb'\x1b%-12345X((?:@PJL[^\r\n]*\r?\n)+)', header)
    qpdl = bool(pjl and re.search(
        rb'(?:^|\n)@PJL ENTER LANGUAGE[ \t]*=[ \t]*QPDL[ \t]*\r?\n', pjl[1]))
    return (f'in_format={"CUPS-raster" if raster else "unknown"}\n'
            f'in_magic_hex={magic.hex()}\n'
            f'out_format={"QPDL-declared" if qpdl else "unknown"}\n'
            f'out_signature={"PJL-QPDL" if qpdl else "none"}\n')


def _finish_capture(session):
    parts = session['parts']
    if session['bad'].is_set():
        for path in parts.values():
            _safe_unlink(path)
        reason = session['reason'] if session['reason'] in ('limit', 'write') else 'capture'
        print(f'INFO: path job={session["job"]} stage=rastertospl capture status=failed reason={reason}',
              file=sys.stderr, flush=True)
        return
    final_in = CAPTURE_DIR / 'cups3-reference.in.raster'
    final_out = CAPTURE_DIR / 'cups3-reference.out.spl'
    meta_part = CAPTURE_DIR / 'cups3-reference.meta.txt.part'
    meta = CAPTURE_DIR / 'cups3-reference.meta.txt'
    try:
        os.replace(parts['in'], final_in)
        os.replace(parts['out'], final_out)
        os.chmod(final_in, 0o600)
        os.chmod(final_out, 0o600)
        text = (f'job={session["job"]}\n'
                f'filter_exit={session.get("filter_exit", "unknown")}\n'
                f'boundary_sha256={session.get("boundary_sha256", "unavailable")}\n'
                + _capture_formats(final_in, final_out)
                + f'raster_header={session["raster_header"] or "unavailable"}\n'
                + 'in_file=cups3-reference.in.raster\n'
                f'in_bytes={session["in_bytes"]}\n'
                f'in_sha256={session["in_hash"].hexdigest()}\n'
                'out_file=cups3-reference.out.spl\n'
                f'out_bytes={session["out_bytes"]}\n'
                f'out_sha256={session["out_hash"].hexdigest()}\n')
        _safe_unlink(meta_part)
        with meta_part.open('x', encoding='ascii') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(meta_part, 0o600)
        os.replace(meta_part, meta)
        print(f'INFO: path job={session["job"]} stage=rastertospl capture status=complete '
              f'in_bytes={session["in_bytes"]} in_sha256={session["in_hash"].hexdigest()} '
              f'out_bytes={session["out_bytes"]} out_sha256={session["out_hash"].hexdigest()} '
              'path=/share/cups3-capture', file=sys.stderr, flush=True)
    except OSError:
        for path in (parts['in'], parts['out'], final_in, final_out, meta_part, meta):
            _safe_unlink(path)
        print(f'INFO: path job={session["job"]} stage=rastertospl capture status=failed reason=publish',
              file=sys.stderr, flush=True)


def supervise(stage, command, job, timeout=180):
    env = dict(os.environ)
    for key in ('SUPERVISOR_TOKEN', 'HASSIO_TOKEN'):
        env.pop(key, None)
    # A/B diagnostic: run the proprietary filter without any preload.
    if stage == 'rastertospl':
        env.pop('LD_PRELOAD', None)
    def report(message):
        print(f'INFO: path job={job} stage={stage} {message}', file=sys.stderr, flush=True)
    report('started deadline-seconds=' + str(timeout))
    capture = _claim_capture(stage, job)
    if capture is not None:
        saved = _save_boundary(command, env)
        capture['boundary_sha256'] = saved or 'unavailable'
        report('boundary status=' + ('complete' if saved else 'unavailable'))
    popen_kwargs = dict(env=env, close_fds=False, stderr=subprocess.PIPE, start_new_session=True)
    if capture is not None:
        popen_kwargs.update(stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        child = subprocess.Popen(command, **popen_kwargs)
    except OSError as error:
        if capture is not None:
            _capture_bad(capture, 'capture')
            try:
                capture['in_file'].close(); capture['out_file'].close()
            except OSError:
                pass
            _finish_capture(capture)
        report(f'failed errno={error.errno}')
        return 1
    in_thread = out_thread = None
    if capture is not None:
        in_thread = threading.Thread(target=_tee_input, args=(child, capture), daemon=True)
        out_thread = threading.Thread(target=_tee_output, args=(child, capture), daemon=True)
        in_thread.start(); out_thread.start()
    # Drain continuously with bounded storage; report only fixed failure categories.
    categories = set()
    tail = b''
    line = b''
    dropping = False
    control_count = 0
    raster_reported = False
    selector = selectors.DefaultSelector()
    selector.register(child.stderr, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    timed_out = False
    cancelled = False
    def cancel(signum, frame):
        nonlocal cancelled, deadline
        cancelled = True
        deadline = min(deadline, time.monotonic() + 2)
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass
    old_handlers = {sig: signal.signal(sig, cancel) for sig in (signal.SIGTERM, signal.SIGINT)}
    while child.poll() is None or selector.get_map():
        if time.monotonic() >= deadline:
            timed_out = True
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            break
        for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
            chunk = os.read(key.fd, 4096)
            if not chunk:
                selector.unregister(key.fileobj)
                continue
            for byte in chunk:
                if byte == 10:
                    match = re.fullmatch(rb'STATE: ([+-]?)(connecting-to-device|connected-to-device|offline-report|media-empty-warning|media-needed|marker-supply-low-warning|marker-supply-empty-warning|door-open-report)', line)
                    if not dropping and match and control_count < 64:
                        print(line.decode('ascii'), file=sys.stderr, flush=True)
                        control_count += 1
                    if stage == 'rastertospl' and not dropping and not raster_reported:
                        message = raster_header_message(line)
                        if message is not None:
                            report(message)
                            if capture is not None:
                                capture['raster_header'] = message
                            raster_reported = True
                    line = b''
                    dropping = False
                elif len(line) < 256 and not dropping:
                    line += bytes((byte,))
                else:
                    dropping = True
            tail = (tail + chunk).lower()
            for category, needle in (('open', b'unable to open'), ('claim', b'claim'),
                                     ('write', b'write'), ('timeout', b'timeout'),
                                     ('permission', b'permission denied'), ('busy', b'busy'),
                                     ('disconnected', b'no device'), ('cms', b'cms')):
                if needle in tail and category not in categories:
                    categories.add(category)
                    report('vendor-marker=' + category)
            for pattern in (rb'libusb error (-?[0-9]{1,8})', rb'libusb write operation returned ([0-9a-f]{1,8})'):
                match = re.search(pattern, tail)
                if match and 'libusb-code' not in categories:
                    categories.add('libusb-code')
                    report('libusb-code=' + match.group(1).decode('ascii'))
            tail = tail[-256:]
    result = child.wait()
    if capture is not None:
        capture['filter_exit'] = result
        in_thread.join(timeout=5)
        out_thread.join(timeout=5)
        if in_thread.is_alive() or out_thread.is_alive():
            _capture_bad(capture, 'capture')
        _finish_capture(capture)
    for sig, handler in old_handlers.items():
        signal.signal(sig, handler)
    selector.close()
    child.stderr.close()
    report(f'finished exit={result} timeout={str(timed_out).lower()} cancelled={str(cancelled).lower()} retry=none')
    return 1 if timed_out or result < 0 else result

def valid_usb_uri(uri):
    # Classification only: no parsing result or input is ever printed.
    return (uri.startswith('usb://') and len(uri) > 6
            and not any(ord(char) <= 32 or ord(char) == 127 for char in uri))


# Only image-quality controls verified in the pinned HP 15x PPD. Never infer
# defaults for absent controls or change raster/media/transport options.
HP_QUALITY_DEFAULTS = {'Screen': 'Enhanced', 'secBrightness': '50',
                       'secContrast': '50', 'secSaturation': '50',
                       'CyanRed': '50', 'MagentaGreen': '50', 'YellowBlue': '50'}
CUPS_OPTION_TOKEN = re.compile(r"""(?:[^\s'"\\]|\\.|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')+""")


def normalize_hp_quality(options, ppd):
    """Replace all occurrences, preserving unrelated CUPS tokens verbatim.

    Gate each key on its explicit active-PPD default; this experiment must not
    invent defaults for another PPD. Quoting/escapes remain CUPS syntax, never
    shell syntax or shlex serialization.
    """
    text = pathlib.Path(ppd).read_text(encoding='latin1')
    defaults = {key: value for key, value in HP_QUALITY_DEFAULTS.items()
                if re.search(r'^\*Default' + key + r':[ \t]*' + value +
                             r'[ \t]*\r?$', text, re.MULTILINE)}
    if not defaults:
        return options
    tokens = []
    end = 0
    for match in CUPS_OPTION_TOKEN.finditer(options):
        if options[end:match.start()].strip():
            raise ValueError('invalid CUPS option syntax')
        tokens.append(match.group())
        end = match.end()
    if options[end:].strip():
        raise ValueError('invalid CUPS option syntax')
    keys = {key.lower() for key in defaults}
    retained = [token for token in tokens
                if token.split('=', 1)[0].lower() not in keys]
    return ' '.join(retained + [f'{key}={value}' for key, value in defaults.items()])


def main():
    stage = sys.argv[1]
    args = sys.argv[2:]
    executable = {'usb': '/opt/poc/backend/usb.real',
                  'rastertospl': '/work/filter/rastertospl.real'}[stage]
    # Discovery must retain unmodified stdout; no job or document is involved.
    if stage == 'usb' and not args:
        os.environ.pop('SUPERVISOR_TOKEN', None)
        os.environ.pop('HASSIO_TOKEN', None)
        os.execv(executable, ['usb', *args])
    job = args[0] if args and args[0].isascii() and args[0].isdigit() and len(args[0]) <= 10 else 'unknown'
    if stage == 'usb':
        valid_uri = valid_usb_uri(os.environ.get('DEVICE_URI', ''))
        print(f'INFO: path job={job} stage=usb launch path=/opt/poc/backend/usb.real '
              f'class=usb argc={len(args)} device-uri={"usb" if valid_uri else "invalid"} '
              f'normalized-usb={str(valid_uri).lower()}', file=sys.stderr, flush=True)
        if len(args) not in (5, 6) or job == 'unknown' or not valid_uri:
            print(f'ERROR: path job={job} stage=usb rejected reason=invalid-usb-invocation retry=none',
                  file=sys.stderr, flush=True)
            return 1
    if stage == 'rastertospl':
        try:
            if len(args) not in (5, 6):
                raise ValueError('invalid filter argument count')
            args[4] = normalize_hp_quality(args[4], os.environ['PPD'])
        except (OSError, KeyError, ValueError):
            print(f'ERROR: path job={job} stage=rastertospl rejected reason=quality-options retry=none',
                  file=sys.stderr, flush=True)
            return 1
    return supervise(stage, [executable, *args], job)


if __name__ == '__main__':
    sys.exit(main())
