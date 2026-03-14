"""Runtime path policy for source and packaged builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_HOME_ENV = "QT_MODULA_HOME"


def _is_packaged_runtime() -> bool:
    return bool(getattr(sys, "frozen", False) or globals().get("__compiled__"))


def _frozen_app_root() -> Path:
    executable = Path(sys.executable).resolve()
    if (
        executable.parent.name == "MacOS"
        and executable.parent.parent.name == "Contents"
        and executable.parent.parent.parent.suffix == ".app"
    ):
        return executable.parent.parent.parent.parent.resolve()
    return executable.parent.resolve()


def app_root() -> Path:
    """Return the external runtime home for the app."""
    override = os.getenv(_APP_HOME_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if _is_packaged_runtime():
        return _frozen_app_root()
    return Path(__file__).resolve().parents[2]


def package_root() -> Path:
    return Path(__file__).resolve().parent


def saves_root() -> Path:
    return (app_root() / "saves").resolve()


def saves_main_root() -> Path:
    return (saves_root() / "main").resolve()


def projects_root() -> Path:
    return (saves_root() / "projects").resolve()


def autosnapshots_root() -> Path:
    return (saves_main_root() / "autosnapshots").resolve()


def exports_root() -> Path:
    return (saves_root() / "exports").resolve()


def modules_root() -> Path:
    return (app_root() / "modules").resolve()


def docs_root() -> Path:
    return (app_root() / "resources" / "docs").resolve()


def settings_path() -> Path:
    return (saves_main_root() / "settings.json").resolve()


def theme_presets_path() -> Path:
    return (saves_main_root() / "theme_presets.json").resolve()


def resolve_app_relative(path: Path | str) -> Path:
    normalized = Path(path).expanduser()
    if normalized.is_absolute():
        return normalized.resolve()
    return (app_root() / normalized).resolve()


def app_icon_path() -> Path:
    candidates = (
        package_root() / "assets" / "app_icon.png",
        package_root() / "assets" / "app_icon.svg",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0].resolve()
