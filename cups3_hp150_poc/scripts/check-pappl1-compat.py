#!/usr/bin/env python3
"""Build-only PAPPL1 gate; use retrofit's configured compiler and flags."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def check_source(root):
    config = (root / 'config.h').read_text()
    if not re.search(r'^\s*#\s*define\s+HAVE_PAPPL1\s+1\s*$', config, re.M):
        raise ValueError('Configured retrofit must select HAVE_PAPPL1=1')
    header = (root / 'pappl-retrofit/pappl1-private.h').read_text()
    for suffix, target in [('Format', 'Format'), ('Filename', 'Filename')]:
        pattern = (r'^\s*#\s*define\s+papplJobGetDocument' + suffix
                   + r'\(job,\s*doc\)\s+papplJobGet' + target + r'\(job\)\s*$')
        if len(re.findall(pattern, header, re.M)) != 1:
            raise ValueError('PAPPL1 getter mapping changed; source review required')


PROBE = '''#include "pappl-retrofit/pappl1-private.h"
#ifndef HAVE_PAPPL1
# error "PAPPL1 configuration required"
#endif
const char *poc_compat_format(pappl_job_t *job)
{
  return papplJobGetDocumentFormat(job, 1);
}
const char *poc_compat_filename(pappl_job_t *job)
{
  return papplJobGetDocumentFilename(job, 1);
}
int main(void) { return 0; }
'''

# Read the generated Makefile, so CC and dependency flags match retrofit.
# No recipe invokes the linked executable; no job is created or submitted.
MAKE_GATE = '''.PHONY: poc-pappl1-compat
poc-pappl1-compat:
\t$(CC) $(CPPFLAGS) $(CFLAGS) $(CUPS_CFLAGS) $(PAPPL_CFLAGS) -I. -Werror=implicit-function-declaration -Werror=incompatible-pointer-types $(LDFLAGS) "$(POC_COMPAT_SOURCE)" -o "$(POC_COMPAT_BINARY)" $(PAPPL_LIBS) $(CUPS_LIBS) $(LIBS)
'''


def main(root):
    root = Path(root).resolve()
    check_source(root)
    with tempfile.TemporaryDirectory(prefix='poc-pappl1-compat-') as directory:
        stage = Path(directory)
        (stage / 'probe.c').write_text(PROBE)
        (stage / 'gate.mk').write_text(MAKE_GATE)
        subprocess.run(['make', '-f', 'Makefile', '-f', str(stage / 'gate.mk'),
                        'poc-pappl1-compat', 'POC_COMPAT_SOURCE=' + str(stage / 'probe.c'),
                        'POC_COMPAT_BINARY=' + str(stage / 'probe')], cwd=root, check=True)
    print('PAPPL1 compatibility gate: compile/link passed (probe not executed)')


if __name__ == '__main__':
    main(sys.argv[1])
