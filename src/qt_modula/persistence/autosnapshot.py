"""Debounced autosnapshot support for crash recovery."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import orjson
from PySide6.QtCore import QObject, QTimer

from qt_modula.persistence.io import load_project, save_project
from qt_modula.persistence.schemas import AutosnapshotPolicy, Project


class AutosnapshotManager(QObject):
    """Debounced autosnapshot writer with bounded retention."""

    _STATE_FILE = "_autosnapshot_state.json"

    def __init__(
        self,
        *,
        root: Path,
        policy: AutosnapshotPolicy,
        snapshot_factory: Callable[[], Project],
    ) -> None:
        super().__init__()
        self._root = root
        self._policy = policy
        self._snapshot_factory = snapshot_factory
        self._project_id = "workspace"
        self._dirty = False
        self._counter = 0

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

        self._root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_project_id(project_id: str) -> str:
        token = re.sub(r"[^a-zA-Z0-9_.-]+", "_", project_id.strip())
        return token or "workspace"

    def set_project_id(self, project_id: str) -> None:
        self._project_id = self._sanitize_project_id(project_id)

    def mark_dirty(self) -> None:
        if not self._policy.enabled:
            return
        self._dirty = True
        self._timer.start(self._policy.debounce_ms)

    def flush(self) -> Path | None:
        if not self._policy.enabled or not self._dirty:
            return None

        project = self._snapshot_factory()
        if not isinstance(project, Project):
            raise RuntimeError("Autosnapshot factory must return Project.")
        if not self._project_has_modules(project):
            self.clear_project_snapshots(self._project_id)
            return None

        self._counter += 1
        stamp = time.time_ns()
        folder = self._root / self._project_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stamp}_{self._counter:04d}.json"

        save_project(path, project)
        self._trim_history(folder)

        self._dirty = False
        return path

    def record_manual_save(self, project_id: str) -> None:
        sanitized = self._sanitize_project_id(project_id)
        state_path = self._root / self._STATE_FILE
        now_ns = time.time_ns()

        state: dict[str, int] = self._read_state()

        state[sanitized] = now_ns

        blob = orjson.dumps(state, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
        state_path.write_bytes(blob)

    def has_unsaved_snapshot(self, project_id: str) -> bool:
        sanitized = self._sanitize_project_id(project_id)
        latest = self.latest_snapshot_path(sanitized)
        if latest is None:
            return False

        saved_ns = self._last_saved_ns(sanitized)
        return latest.stat().st_mtime_ns > saved_ns

    def latest_snapshot_path(self, project_id: str | None = None) -> Path | None:
        token = self._sanitize_project_id(project_id or self._project_id)
        folder = self._root / token
        if not folder.exists():
            return None

        snapshots = sorted(
            (path for path in folder.glob("*.json") if path.is_file()),
            key=lambda path: path.name,
        )
        if not snapshots:
            return None
        return snapshots[-1]

    def load_latest_snapshot(self, project_id: str | None = None) -> Project | None:
        path = self.latest_snapshot_path(project_id)
        if path is None:
            return None
        return load_project(path)

    def clear_project_snapshots(self, project_id: str | None = None) -> None:
        token = self._sanitize_project_id(project_id or self._project_id)
        if token == self._project_id:
            self._timer.stop()
            self._dirty = False

        folder = self._root / token
        if not folder.exists():
            return

        for path in folder.glob("*.json"):
            if path.is_file():
                path.unlink(missing_ok=True)
        with suppress(OSError):
            folder.rmdir()

    def _trim_history(self, folder: Path) -> None:
        snapshots = sorted(path for path in folder.glob("*.json") if path.is_file())
        excess = len(snapshots) - self._policy.max_history
        if excess <= 0:
            return
        for path in snapshots[:excess]:
            path.unlink(missing_ok=True)

    def _last_saved_ns(self, project_id: str) -> int:
        state = self._read_state()
        return state.get(project_id, 0)

    def _read_state(self) -> dict[str, int]:
        state_path = self._root / self._STATE_FILE
        if not state_path.exists():
            return {}

        try:
            payload = orjson.loads(state_path.read_bytes())
        except Exception:
            return {}

        if not isinstance(payload, dict):
            return {}

        state: dict[str, int] = {}
        for raw_key, raw_value in payload.items():
            key = str(raw_key)
            if isinstance(raw_value, int):
                state[key] = raw_value
        return state

    @staticmethod
    def _project_has_modules(project: Project) -> bool:
        return any(canvas.modules for canvas in project.canvases)
