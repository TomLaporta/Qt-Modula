"""Persistence I/O helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import orjson

from qt_modula.persistence.schemas import AppConfig, Project


class PersistenceError(RuntimeError):
    """Persistence-level failure with deterministic messages."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = orjson.loads(path.read_bytes())
    except FileNotFoundError as exc:
        raise PersistenceError(f"File not found: {path}") from exc
    except orjson.JSONDecodeError as exc:
        raise PersistenceError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise PersistenceError(f"Root payload in {path} must be an object.")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def load_app_config(path: Path) -> AppConfig:
    """Load app settings with strict version validation."""
    if not path.exists():
        return AppConfig()

    raw = _read_json(path)
    if raw.get("version") != "AppConfig":
        raise PersistenceError("Unsupported app config version. Expected AppConfig.")

    try:
        return AppConfig.model_validate(raw)
    except Exception as exc:
        raise PersistenceError(f"Invalid app config: {exc}") from exc


def save_app_config(path: Path, config: AppConfig) -> None:
    """Save app settings deterministically."""
    _write_json(path, config.model_dump(mode="json"))


def load_project(path: Path) -> Project:
    """Load project with strict current-contract validation."""
    raw = _read_json(path)
    if raw.get("version") != "ProjectV2":
        raise PersistenceError("Unsupported project format. Only ProjectV2 is accepted.")

    try:
        return Project.model_validate(raw)
    except Exception as exc:
        raise PersistenceError(f"Invalid Project payload: {exc}") from exc


def save_project(path: Path, project: Project) -> None:
    """Save project deterministically."""
    _write_json(path, project.model_dump(mode="json"))
