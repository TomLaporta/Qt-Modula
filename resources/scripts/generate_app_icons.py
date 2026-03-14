#!/usr/bin/env python3
"""Generate platform app icon assets from the master SVG."""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from _bootstrap import REPO_ROOT

SOURCE_SVG = REPO_ROOT / "src" / "qt_modula" / "assets" / "app_icon.svg"
PACKAGE_PNG = REPO_ROOT / "src" / "qt_modula" / "assets" / "app_icon.png"
ASSETS_ROOT = REPO_ROOT / "resources" / "assets"
LINUX_PNG = ASSETS_ROOT / "linux" / "app_icon.png"
WINDOWS_ICO = ASSETS_ROOT / "windows" / "app_icon.ico"
MACOS_ICNS = ASSETS_ROOT / "macos" / "app_icon.icns"

_ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
_ICONSET_FILES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def _renderer() -> QSvgRenderer:
    renderer = QSvgRenderer(str(SOURCE_SVG))
    if not renderer.isValid():
        raise SystemExit(f"Invalid SVG source: {SOURCE_SVG}")
    return renderer


def _render_png_bytes(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    array = QByteArray()
    buffer = QBuffer(array)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise SystemExit("Unable to open in-memory PNG buffer.")
    if not image.save(buffer, "PNG"):
        raise SystemExit(f"Unable to render {size}px PNG.")
    return bytes(array)


def _write_png(path: Path, png_bytes: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes)


def _write_ico(path: Path, png_payloads: list[tuple[int, bytes]]) -> None:
    header = struct.pack("<HHH", 0, 1, len(png_payloads))
    entries: list[bytes] = []
    offset = len(header) + (16 * len(png_payloads))
    data_chunks: list[bytes] = []

    for size, png_bytes in png_payloads:
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                width,
                height,
                0,
                0,
                1,
                32,
                len(png_bytes),
                offset,
            )
        )
        data_chunks.append(png_bytes)
        offset += len(png_bytes)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + b"".join(entries) + b"".join(data_chunks))


def _write_icns(renderer: QSvgRenderer, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        iconset_dir = Path(tmp_dir) / "app_icon.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)
        for filename, size in _ICONSET_FILES.items():
            _write_png(iconset_dir / filename, _render_png_bytes(renderer, size))
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(path)],
            check=True,
        )


def main() -> int:
    renderer = _renderer()

    package_png = _render_png_bytes(renderer, 1024)
    linux_png = _render_png_bytes(renderer, 512)
    ico_payloads = [(size, _render_png_bytes(renderer, size)) for size in _ICO_SIZES]

    _write_png(PACKAGE_PNG, package_png)
    _write_png(LINUX_PNG, linux_png)
    _write_ico(WINDOWS_ICO, ico_payloads)

    print(PACKAGE_PNG)
    print(LINUX_PNG)
    print(WINDOWS_ICO)
    if sys.platform == "darwin":
        _write_icns(renderer, MACOS_ICNS)
        print(MACOS_ICNS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
