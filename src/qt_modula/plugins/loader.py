"""Local plugin loader for `./modules` directory."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

PLUGIN_API_VERSION = "1"


@dataclass(frozen=True, slots=True)
class PluginLoadIssue:
    """Plugin load diagnostic."""

    path: Path
    message: str


def _discover_plugin_targets(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []

    candidates: list[Path] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.name.startswith("_"):
            continue
        if path.is_file() and path.suffix == ".py":
            candidates.append(path)
            continue
        if path.is_dir():
            plugin_py = path / "plugin.py"
            if plugin_py.is_file():
                candidates.append(plugin_py)
    return candidates


def _load_module(path: Path, token: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(token, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to create import spec.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_plugins(
    *,
    root: Path,
    registry: object,
) -> list[PluginLoadIssue]:
    """Auto-load all valid plugins from `root` in deterministic order."""
    issues: list[PluginLoadIssue] = []

    for index, path in enumerate(_discover_plugin_targets(root), start=1):
        token = f"qt_modula_plugin_{index:04d}_{path.stem}"
        try:
            module = _load_module(path, token)
        except Exception as exc:
            issues.append(PluginLoadIssue(path=path, message=f"Import failed: {exc}"))
            continue

        api_version = str(getattr(module, "API_VERSION", ""))
        if api_version != PLUGIN_API_VERSION:
            issues.append(
                PluginLoadIssue(
                    path=path,
                    message=(
                        f"Unsupported API_VERSION '{api_version}'. "
                        f"Expected '{PLUGIN_API_VERSION}'."
                    ),
                )
            )
            continue

        register_fn = getattr(module, "register", None)
        if not callable(register_fn):
            issues.append(
                PluginLoadIssue(
                    path=path,
                    message="Plugin is missing register(registry).",
                )
            )
            continue

        try:
            register_fn(registry)
        except Exception as exc:
            issues.append(PluginLoadIssue(path=path, message=f"register() failed: {exc}"))

    return issues
