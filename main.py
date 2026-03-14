"""Qt Modula desktop entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

src_dir = Path(__file__).resolve().parent / "src"
src_token = str(src_dir)
if src_dir.is_dir() and src_token not in sys.path:
    sys.path.insert(0, src_token)

from qt_modula.app import main

if __name__ == "__main__":
    raise SystemExit(main())
