#!/usr/bin/env python3
"""Fail closed on source drift; honor NO_TLS in both PAPPL DNS-SD TXT paths."""
from pathlib import Path
import sys


def patch(path):
    source = path.read_text()
    statements = (
        'TXTRecordSetValue(&txt, "TLS", 3, "1.2");',
        'txt = avahi_string_list_add_printf(txt, "TLS=1.2");',
    )
    for statement in statements:
        old = '  ' + statement
        if source.splitlines().count(old) != 1:
            raise ValueError('PAPPL TLS TXT source changed; review required')
        source = source.replace(old, '  if (!(printer->system->options & PAPPL_SOPTIONS_NO_TLS))\n    ' + statement)
    path.write_text(source)


if __name__ == '__main__':
    patch(Path(sys.argv[1]))
