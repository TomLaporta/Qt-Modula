#!/usr/bin/env python3
"""Stage a clean end-user distribution folder for the current platform."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from _bootstrap import REPO_ROOT

APP_NAME = "qt-modula"
WINDOWS_DISPLAY_NAME = "Qt Modula.exe"
LINUX_DISPLAY_NAME = APP_NAME
PYSIDE_BUILD_ROOT = REPO_ROOT / "build" / "pyside6-deploy"
PYSIDE_BUILD_OUTPUT = PYSIDE_BUILD_ROOT / "output"
PYINSTALLER_BUILD_ROOT = REPO_ROOT / "build" / "pyinstaller"
PYINSTALLER_DIST_ROOT = REPO_ROOT / "build" / "pyinstaller-dist"
DIST_ROOT = REPO_ROOT / "distribution"
README_SOURCE = REPO_ROOT / "README.md"


def _reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _copy_tree_if_exists(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def _copy_file_if_exists(src: Path, dst: Path) -> None:
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _copy_dir_contents(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def _pyinstaller_payload_path() -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    candidate = PYINSTALLER_DIST_ROOT / f"{APP_NAME}{suffix}"
    if candidate.is_file():
        return candidate
    raise SystemExit(
        "PyInstaller output not found. Run resources/scripts/build_distribution.py first."
    )


def _non_windows_payload_path() -> Path:
    candidates = (
        PYSIDE_BUILD_OUTPUT / f"{APP_NAME}.app",
        PYSIDE_BUILD_OUTPUT / f"{APP_NAME}.dist",
        PYSIDE_BUILD_OUTPUT / f"{APP_NAME}.bin",
        REPO_ROOT / f"{APP_NAME}.app",
        REPO_ROOT / f"{APP_NAME}.dist",
        REPO_ROOT / f"{APP_NAME}.bin",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(
        "Deploy output not found. Run resources/scripts/build_distribution.py first."
    )


def _stage_common_files(stage_root: Path) -> None:
    _copy_file_if_exists(README_SOURCE, stage_root / "README.md")
    _copy_tree_if_exists(REPO_ROOT / "modules", stage_root / "modules")
    _copy_tree_if_exists(REPO_ROOT / "saves", stage_root / "saves")
    _copy_file_if_exists(
        REPO_ROOT / "resources" / "module_template.py",
        stage_root / "resources" / "module_template.py",
    )
    _copy_tree_if_exists(REPO_ROOT / "resources" / "docs", stage_root / "resources" / "docs")

    for path in (
        stage_root / "saves" / "main" / "autosnapshots",
        stage_root / "saves" / "projects",
        stage_root / "saves" / "exports",
    ):
        path.mkdir(parents=True, exist_ok=True)


def _stage_pyinstaller_distribution(stage_root: Path) -> None:
    display_name = WINDOWS_DISPLAY_NAME if sys.platform == "win32" else LINUX_DISPLAY_NAME
    shutil.copy2(_pyinstaller_payload_path(), stage_root / display_name)


def _stage_non_windows_distribution(stage_root: Path) -> None:
    payload = _non_windows_payload_path()
    if payload.suffix == ".app":
        shutil.copytree(payload, stage_root / payload.name, dirs_exist_ok=True)
        return
    if payload.suffix == ".dist":
        _copy_dir_contents(payload, stage_root)
        return
    shutil.copy2(payload, stage_root / payload.name)


def _cleanup_build_artifacts() -> None:
    for artifact_root in (PYSIDE_BUILD_ROOT, PYINSTALLER_BUILD_ROOT, PYINSTALLER_DIST_ROOT):
        if artifact_root.exists():
            shutil.rmtree(artifact_root)


def main() -> int:
    _reset_directory(DIST_ROOT)
    if sys.platform == "darwin":
        _stage_non_windows_distribution(DIST_ROOT)
    else:
        _stage_pyinstaller_distribution(DIST_ROOT)
    _stage_common_files(DIST_ROOT)
    _cleanup_build_artifacts()
    print(f"Distribution staged at {DIST_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
