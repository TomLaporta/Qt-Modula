#!/usr/bin/env python3
"""Run full quality gate sequence for Qt Modula."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _bootstrap import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "resources" / "scripts"
TESTS_DIR = REPO_ROOT / "tests"


def _steps() -> list[list[str]]:
    steps: list[list[str]] = [
        [
            sys.executable,
            "-c",
            (
                "import importlib.util\n"
                "required=(\n"
                "    'numpy','pyqtgraph','httpx','yfinance',\n"
                "    'xlsxwriter','openpyxl','docx','sympy',\n"
                ")\n"
                "missing=[name for name in required if importlib.util.find_spec(name) is None]\n"
                "if missing:\n"
                "    raise SystemExit(f'Missing required dependency imports: {missing}')\n"
                "print('required dependency imports passed')\n"
            ),
        ],
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(REPO_ROOT / "src" / "qt_modula"),
            str(SCRIPTS_DIR),
        ],
        [sys.executable, "-m", "mypy", str(REPO_ROOT / "src" / "qt_modula")],
        [sys.executable, str(SCRIPTS_DIR / "run_workflow_sim.py")],
        [sys.executable, str(SCRIPTS_DIR / "run_benchmarks.py")],
    ]

    if TESTS_DIR.is_dir():
        steps.insert(3, [sys.executable, "-m", "pytest", str(TESTS_DIR)])

    return steps


def main() -> int:
    if not TESTS_DIR.is_dir():
        print(f"tests directory not found at {TESTS_DIR}; skipping pytest step")

    for step in _steps():
        print(f"\n>>> {' '.join(step)}")
        result = subprocess.run(step, check=False, cwd=REPO_ROOT)
        if result.returncode != 0:
            return result.returncode
    print("\nQuality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
