# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""clarkbrowser CLI entry point.

Usage:
    python -m clarkbrowser info       # binary install status
    python -m clarkbrowser fetch      # pre-download binary
    python -m clarkbrowser clear      # delete cached binary
"""
from __future__ import annotations

import json
import sys

from .download import binary_info, clear_cache, ensure_binary


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0

    cmd = argv[0]
    if cmd == "info":
        print(json.dumps(binary_info(), indent=2))
        return 0
    if cmd == "fetch":
        path = ensure_binary()
        print(f"binary at {path}")
        return 0
    if cmd == "clear":
        clear_cache()
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
