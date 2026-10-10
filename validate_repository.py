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
    assert config['stage'] == 'experimental'
    assert config['boot'] == 'manual_only'
    assert config['ports'] == {'8631/tcp': 8631}
    assert config['webui'] == 'http://[HOST]:[PORT:8631]/'
    assert config['watchdog'] == 'tcp://[HOST]:[PORT:8631]'
    for key in ('usb', 'uart', 'udev', 'devices', 'privileged', 'full_access',
                'host_network', 'host_pid', 'host_dbus', 'gpio', 'video',
                'docker_api', 'hassio_api', 'homeassistant_api', 'ingress'):
        assert not config.get(key), f'Forbidden access: {key}'
    assert config['map'] == [
        {'type': 'app_config', 'read_only': True, 'path': '/hp-driver'}]
    dockerfile = (app / 'Dockerfile').read_text()
    assert 'FROM debian:trixie-slim' in dockerfile
    assert 'USER 10001:10001' in dockerfile
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
    print('PASS: YAML, app structure, build inputs, non-USB isolation and HP exclusions')


if __name__ == '__main__':
    main()
