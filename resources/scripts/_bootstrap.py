"""Bootstrap helpers for script entry points."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
_SRC_TOKEN = str(SRC_DIR)

if SRC_DIR.is_dir() and _SRC_TOKEN not in sys.path:
    sys.path.insert(0, _SRC_TOKEN)
