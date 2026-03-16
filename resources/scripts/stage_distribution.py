#!/usr/bin/env python3
"""Stage a clean end-user distribution folder for the current platform."""

from __future__ import annotations

import re
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
DIST_STAGING_ROOT = REPO_ROOT / ".distribution-staging"
DIST_BACKUP_ROOT = REPO_ROOT / ".distribution-backup"
README_SOURCE = REPO_ROOT / "README.md"
PERSONAL_PATH_MARKERS = tuple(
    sorted(
        {
            REPO_ROOT.resolve().as_posix(),
            str(REPO_ROOT.resolve()),
            Path.home().resolve().as_posix(),
            str(Path.home().resolve()),
        },
        key=len,
        reverse=True,
    )
)
TEXT_SANITIZE_SUFFIXES = {
    ".cfg",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".plist",
    ".py",
    ".qml",
    ".svg",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
SVG_EXPORT_FILENAME_RE = re.compile(r'\s+inkscape:export-filename="[^"]+"')


def _reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return
    path.unlink()


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


def _stage_pyinstaller_distribution(stage_root: Path, payload: Path) -> None:
    display_name = WINDOWS_DISPLAY_NAME if sys.platform == "win32" else LINUX_DISPLAY_NAME
    shutil.copy2(payload, stage_root / display_name)


def _stage_non_windows_distribution(stage_root: Path, payload: Path) -> None:
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


def _sanitize_svg_export_metadata(stage_root: Path) -> None:
    for path in stage_root.rglob("*.svg"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        sanitized = SVG_EXPORT_FILENAME_RE.sub("", text)
        if sanitized != text:
            path.write_text(sanitized, encoding="utf-8")


def _iter_text_files(stage_root: Path):
    for path in stage_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SANITIZE_SUFFIXES:
            yield path


def _assert_no_personal_paths(stage_root: Path) -> None:
    hits: list[str] = []
    for path in _iter_text_files(stage_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in PERSONAL_PATH_MARKERS):
                relative_path = path.relative_to(stage_root)
                hits.append(f"{relative_path}:{line_number}")
                if len(hits) == 10:
                    break
        if len(hits) == 10:
            break
    if hits:
        joined_hits = "\n".join(f"  - {hit}" for hit in hits)
        raise SystemExit(
            "Staged distribution still contains personal path references:\n"
            f"{joined_hits}"
        )


def _commit_staged_distribution() -> None:
    _remove_path(DIST_BACKUP_ROOT)
    try:
        if DIST_ROOT.exists() or DIST_ROOT.is_symlink():
            DIST_ROOT.rename(DIST_BACKUP_ROOT)
        DIST_STAGING_ROOT.rename(DIST_ROOT)
    except Exception:
        if not DIST_ROOT.exists() and DIST_BACKUP_ROOT.exists():
            DIST_BACKUP_ROOT.rename(DIST_ROOT)
        raise
    else:
        _remove_path(DIST_BACKUP_ROOT)


def main() -> int:
    payload = (
        _non_windows_payload_path()
        if sys.platform == "darwin"
        else _pyinstaller_payload_path()
    )
    _reset_directory(DIST_STAGING_ROOT)
    try:
        if sys.platform == "darwin":
            _stage_non_windows_distribution(DIST_STAGING_ROOT, payload)
        else:
            _stage_pyinstaller_distribution(DIST_STAGING_ROOT, payload)
        _stage_common_files(DIST_STAGING_ROOT)
        _sanitize_svg_export_metadata(DIST_STAGING_ROOT)
        _assert_no_personal_paths(DIST_STAGING_ROOT)
        _commit_staged_distribution()
    except Exception:
        _remove_path(DIST_STAGING_ROOT)
        raise
    _cleanup_build_artifacts()
    print(f"Distribution staged at {DIST_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
