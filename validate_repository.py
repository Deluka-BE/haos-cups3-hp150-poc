"""Static repository/safety checks; requires PyYAML, not a Supervisor install."""
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parent


def main():
    repository = yaml.safe_load((ROOT / 'repository.yaml').read_text())
    assert isinstance(repository['name'], str) and repository['name']
    assert repository['url'] == 'https://github.com/Deluka-BE/haos-cups3-hp150-poc'
    configs = list(ROOT.rglob('config.yaml'))
    assert len(configs) == 1, 'Exactly one isolated app expected'
    app = configs[0].parent
    config = yaml.safe_load(configs[0].read_text())
    for key in ('name', 'version', 'slug', 'description'):
        assert isinstance(config[key], str) and config[key], key
    assert re.fullmatch(r'[a-z0-9_]+', config['slug'])
    assert config['slug'] == app.name
    assert config['arch'] == ['aarch64']
    assert config['options'] == {'log_level': 'info'}
    assert config['schema'] == {'log_level': 'list(fatal|error|warn|info|debug)'}
    assert config['stage'] == 'experimental'
    assert config['boot'] == 'manual_only'
    assert config.get('host_network') is True
    assert config['ports'] == {'8631/tcp': 8631}
    assert config['webui'] == 'http://[HOST]:[PORT:8631]/'
    assert config['watchdog'] == 'tcp://[HOST]:[PORT:8631]'
    for key in ('uart', 'udev', 'devices', 'privileged', 'full_access',
                'host_pid', 'host_uts', 'host_ipc', 'host_dbus', 'gpio', 'video',
                'docker_api', 'hassio_api', 'homeassistant_api', 'ingress'):
        assert not config.get(key), f'Forbidden access: {key}'
    assert not config.get('map'), 'The baked-in HP files must not be hidden by mounts'
    dockerfile = (app / 'Dockerfile').read_text()
    assert 'FROM debian:trixie-slim' in dockerfile
    assert config.get('usb') is True
    assert 'USER 0:0' in dockerfile
    assert 'ENTRYPOINT ["python3", "/opt/poc/scripts/usb-runtime.py"]' in dockerfile
    bootstrap = (app / 'scripts/usb-runtime.py').read_text()
    assert 'os.setgroups(groups)' in bootstrap
    assert 'os.setresuid(UID, UID, UID)' in bootstrap
    assert 'libc.prctl(38, 1, 0, 0, 0)' in bootstrap
    assert 'cp /opt/poc/scripts/verify-capture.py /opt/poc/backend/verify-capture.py' in dockerfile
    assert 'avahi-daemon avahi-utils dbus dbus-bin' in dockerfile
    assert 'COPY mdns/ /opt/poc/mdns/' in dockerfile
    assert 'chown poc:poc /run/avahi-daemon' in dockerfile
    assert 'ENV POC_PORT=8631\n' in dockerfile
    assert 'EXPOSE 8631\n' in dockerfile
    entrypoint = (app / 'scripts/entrypoint.sh').read_text()
    assert 'server-port=${POC_PORT:-8631}' in entrypoint
    assert 'exec python3 /opt/poc/scripts/mdns-runtime.py "$@"' in entrypoint
    assert 'server) python3 /opt/poc/scripts/usb-diagnostics.py' in entrypoint
    assert 'python3 /opt/poc/scripts/usb-settle.py' in entrypoint
    assert 'export STATE_DIR=/data/state SPOOL_DIR=/work/spool CAPTURE_DIR=/work/capture' in entrypoint
    assert 'python3 /opt/poc/scripts/state-runtime.py' in entrypoint
    assert '"capture,usb", // PoC: capture and real CUPS USB backend' in dockerfile
    assert 'cp extracted/usr/lib/cups/backend-available/usb /opt/poc/backend/usb' in dockerfile
    assert 'chmod 755 /opt/poc/backend/usb' in dockerfile
    assert 'ln -s /opt/poc/backend/usb /opt/poc/diagnostics/usb' in dockerfile
    assert f'ARG BUILD_VERSION={config["version"]}' in dockerfile
    assert 'RUN sh /opt/poc/scripts/stage-hp-uld.sh "$BUILD_ARCH"' in dockerfile
    for label in ('version', 'type', 'arch'):
        assert f'io.hass.{label}=' in dockerfile
    for source in re.findall(r'^COPY (\S+) ', dockerfile, re.MULTILINE):
        assert (app / source).exists(), f'Missing build input: {source}'
    tracked = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
        cwd=ROOT, text=True).splitlines()
    proprietary = {'HP_Color_Laser_15x_Series.ppd', 'rastertospl',
                   'libscmssc.so', '15xsc.cts'}
    assert not any(Path(p).name in proprietary for p in tracked)
    for name in proprietary:
        candidate = f'{app.name}/hp-driver/{name}'
        subprocess.run(['git', 'check-ignore', '-q', candidate], cwd=ROOT, check=True)
        assert name in (app / '.dockerignore').read_text().splitlines()
    print('PASS: YAML, app structure, build inputs, capture/USB isolation and HP exclusions')


if __name__ == '__main__':
    main()
