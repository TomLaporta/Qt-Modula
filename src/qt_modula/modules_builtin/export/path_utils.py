"""Shared export path sanitization utilities."""

from __future__ import annotations

import re
from pathlib import Path

from qt_modula.paths import exports_root
from qt_modula.services.settings_state import current_export_root

DEFAULT_EXPORT_ROOT = exports_root()
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_WINDOWS_RESERVED_STEMS = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def sanitize_export_segment(value: str, *, fallback: str) -> str:
    token = _SANITIZE_RE.sub("_", value.strip()).strip("._-") or fallback
    stem = token.rstrip(" .").split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_STEMS:
        return f"{token}_"
    return token


def build_export_path(
    *,
    file_name: str,
    export_folder: str,
    extension: str,
    default_stem: str,
    root: Path | None = None,
    tag: str = "",
) -> Path:
    stem = sanitize_export_segment(file_name, fallback=default_stem)

    tag_token = tag.strip()
    if tag_token:
        normalized_tag = sanitize_export_segment(tag_token, fallback="")
        if normalized_tag:
            stem = f"{stem}_{normalized_tag}"

    parent = root if root is not None else current_export_root()
    folder_token = export_folder.strip()
    if folder_token:
        normalized_folder = sanitize_export_segment(folder_token, fallback="")
        if normalized_folder:
            parent = parent / normalized_folder

    return parent / f"{stem}.{extension}"
