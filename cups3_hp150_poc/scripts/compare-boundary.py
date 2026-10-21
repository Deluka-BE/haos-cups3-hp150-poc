#!/usr/bin/env python3
"""Compare private rastertospl boundary JSON; output can contain print metadata."""
import argparse
import difflib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cups24', type=Path)
    parser.add_argument('cups3', type=Path)
    args = parser.parse_args()
    # Sorting normalizes dictionary ordering only: argv/options remain exact.
    documents = [json.dumps(json.loads(p.read_text()), sort_keys=True,
                            indent=2, ensure_ascii=True).splitlines(keepends=True)
                 for p in (args.cups24, args.cups3)]
    print(''.join(difflib.unified_diff(*documents, fromfile='CUPS2.4',
                                      tofile='CUPS3')), end='')
    return 0 if documents[0] == documents[1] else 1


if __name__ == '__main__':
    raise SystemExit(main())
