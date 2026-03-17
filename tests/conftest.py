from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable

import pytest
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def wait_for(qapp: QApplication) -> Callable[[Callable[[], bool], float], None]:
    def _wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            qapp.processEvents()
            if predicate():
                qapp.processEvents()
                return
            time.sleep(0.01)
        qapp.processEvents()
        assert predicate()

    return _wait_for
