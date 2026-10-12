#!/usr/bin/env python3
"""Read only the allowlisted PAPPL server log level from HA add-on options."""
import json
from pathlib import Path
import sys

# PAPPL 1.3.1 mainloop-subcommands.c, _papplMainloopSystem: exact spellings.
LEVELS = ('fatal', 'error', 'warn', 'info', 'debug')
DEFAULT = 'info'


def read_level(path=Path('/data/options.json')):
    try:
        with Path(path).open(encoding='utf-8') as stream:
            options = json.load(stream)
    except FileNotFoundError:
        return DEFAULT  # Standalone container, without Supervisor options.
    if not isinstance(options, dict):
        raise ValueError('Invalid options object')
    level = options.get('log_level', DEFAULT)
    if not isinstance(level, str) or level not in LEVELS:
        raise ValueError('Invalid log level')
    return level


def main():
    try:
        level = read_level()
    except (OSError, ValueError, UnicodeError):
        # Never disclose unvalidated values, file contents or loader errors.
        print('ERROR: invalid add-on log_level options; refusing server startup', file=sys.stderr)
        return 1
    print(level)
    return 0


if __name__ == '__main__':
    sys.exit(main())
