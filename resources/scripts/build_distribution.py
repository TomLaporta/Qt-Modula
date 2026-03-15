#!/usr/bin/env python3
"""Build the desktop distribution for the current platform."""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from _bootstrap import REPO_ROOT

APP_NAME = "qt-modula"
PYINSTALLER_BUILD_ROOT = REPO_ROOT / "build" / "pyinstaller"
PYINSTALLER_DIST_ROOT = REPO_ROOT / "build" / "pyinstaller-dist"
MACOS_DEPLOY_BUILD_ROOT = REPO_ROOT / "build" / "pyside6-deploy"
MACOS_DEPLOY_OUTPUT_DIRECTORY = MACOS_DEPLOY_BUILD_ROOT / "output"
MACOS_DEPLOY_SOURCE_DIRECTORY = MACOS_DEPLOY_BUILD_ROOT / "source"
PYINSTALLER_SPEC_TEMPLATE = REPO_ROOT / "packaging" / "pyinstaller.spec.in"
PYINSTALLER_RENDERED_SPEC = PYINSTALLER_BUILD_ROOT / "spec" / f"{APP_NAME}.spec"
MACOS_DEPLOY_SPEC_TEMPLATE = REPO_ROOT / "packaging" / "pyside6-deploy.spec.in"
MACOS_DEPLOY_RENDERED_SPEC = REPO_ROOT / "pysidedeploy.spec"
INPUT_FILE = REPO_ROOT / "main.py"
MACOS_STAGED_INPUT_FILE = MACOS_DEPLOY_SOURCE_DIRECTORY / "main.py"
MACOS_STAGED_PROJECT_FILE = MACOS_DEPLOY_SOURCE_DIRECTORY / "pyproject.toml"
SOURCE_IGNORE_PATTERNS = ("__pycache__", "*.pyc", "*.pyo", ".DS_Store")
MACOS_DEPLOY_EXTRA_QT_MODULES = ("OpenGL",)
MACOS_NUITKA_BASE_ARGS = (
    "--quiet",
    "--noinclude-qt-translations",
    "--include-package-data=qt_modula",
    "--disable-cache=ccache",
    "--include-module=PySide6.QtOpenGL",
)
# Force-include runtime packages the app imports directly plus dependency roots that those
# packages resolve through lazily or behind optional imports at freeze time.
MACOS_NUITKA_REQUIRED_PACKAGES = (
    "docx",
    "httpx",
    "numpy",
    "openpyxl",
    "orjson",
    "pydantic",
    "pyqtgraph",
    "xlsxwriter",
)
MACOS_NUITKA_OPTIONAL_PACKAGES = (
    "yfinance",
)
MACOS_NUITKA_DEPENDENCY_PACKAGES = (
    "annotated_types",
    "anyio",
    "bs4",
    "certifi",
    "curl_cffi",
    "et_xmlfile",
    "frozendict",
    "httpcore",
    "idna",
    "mpmath",
    "multitasking",
    "platformdirs",
    "pydantic_core",
    "sniffio",
    "typing_inspection",
    "websockets",
)
MACOS_NUITKA_OPTIONAL_MODULES = (
    "google.protobuf.json_format",
    "peewee",
    "sympy",
    "sympy.parsing.sympy_parser",
    "typing_extensions",
)
ASSETS_ROOT = REPO_ROOT / "resources" / "assets"
ICON_PATHS = {
    "darwin": ASSETS_ROOT / "macos" / "app_icon.icns",
    "win32": ASSETS_ROOT / "windows" / "app_icon.ico",
    "linux": ASSETS_ROOT / "linux" / "app_icon.png",
}


def _uses_macos_deploy_backend() -> bool:
    return sys.platform == "darwin"


def _reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _generate_icon_assets() -> None:
    generator = REPO_ROOT / "resources" / "scripts" / "generate_app_icons.py"
    result = subprocess.run(
        [sys.executable, str(generator)],
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit("App icon generation failed.")


def _icon_path() -> Path:
    icon_path = ICON_PATHS.get(sys.platform)
    if icon_path is None:
        raise SystemExit(f"Unsupported packaging platform for icon selection: {sys.platform}")
    if not icon_path.is_file():
        raise SystemExit(f"App icon asset not found: {icon_path}")
    return icon_path


def _ensure_supported_python(*, dry_run: bool) -> None:
    if dry_run or not _uses_macos_deploy_backend():
        return
    if sys.version_info >= (3, 14):
        version = ".".join(str(part) for part in sys.version_info[:3])
        raise SystemExit(
            "pyside6-deploy currently uses Nuitka 2.7.11, which does not support "
            f"Python {version}. Use Python 3.11, 3.12, or 3.13 for release builds."
        )


def _deploy_executable() -> str:
    sibling = Path(sys.executable).resolve().parent / "pyside6-deploy"
    if sibling.is_file():
        return str(sibling)
    command = shutil.which("pyside6-deploy")
    if command:
        return command
    raise SystemExit("pyside6-deploy is not installed or not on PATH.")


def _stage_macos_source_tree() -> None:
    MACOS_DEPLOY_BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    _reset_directory(MACOS_DEPLOY_SOURCE_DIRECTORY)
    shutil.copy2(INPUT_FILE, MACOS_STAGED_INPUT_FILE)
    MACOS_STAGED_PROJECT_FILE.write_text(
        '[project]\n'
        'name = "qt-modula"\n\n'
        '[tool.pyside6-project]\n'
        'files = ["main.py"]\n',
        encoding="utf-8",
    )
    shutil.copytree(
        REPO_ROOT / "src",
        MACOS_DEPLOY_SOURCE_DIRECTORY / "src",
        ignore=shutil.ignore_patterns(*SOURCE_IGNORE_PATTERNS),
        dirs_exist_ok=True,
    )


def _render_macos_deploy_spec() -> Path:
    _stage_macos_source_tree()
    MACOS_DEPLOY_BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    MACOS_DEPLOY_OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    rendered = MACOS_DEPLOY_SPEC_TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "__PROJECT_DIR__": MACOS_DEPLOY_SOURCE_DIRECTORY.resolve().as_posix(),
        "__INPUT_FILE__": MACOS_STAGED_INPUT_FILE.resolve().as_posix(),
        "__EXEC_DIRECTORY__": MACOS_DEPLOY_OUTPUT_DIRECTORY.resolve().as_posix(),
        "__PROJECT_FILE__": MACOS_STAGED_PROJECT_FILE.name,
        "__ICON_PATH__": _icon_path().resolve().as_posix(),
        "__NUITKA_EXTRA_ARGS__": _macos_nuitka_extra_args(),
        "__PYTHON_PATH__": Path(sys.executable).resolve().as_posix(),
    }
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    MACOS_DEPLOY_RENDERED_SPEC.write_text(rendered, encoding="utf-8")
    return MACOS_DEPLOY_RENDERED_SPEC


def _find_module_spec(name: str) -> importlib.machinery.ModuleSpec | None:
    try:
        return importlib.util.find_spec(name)
    except (ImportError, ModuleNotFoundError, ValueError):
        return None


def _is_package_available(name: str) -> bool:
    spec = _find_module_spec(name)
    return bool(spec and spec.submodule_search_locations is not None)


def _is_module_available(name: str) -> bool:
    return _find_module_spec(name) is not None


def _available_packages(names: tuple[str, ...]) -> list[str]:
    return [name for name in names if _is_package_available(name)]


def _missing_required_packages(names: tuple[str, ...]) -> list[str]:
    return [name for name in names if not _is_package_available(name)]


def _available_modules(names: tuple[str, ...]) -> list[str]:
    return [name for name in names if _is_module_available(name)]


def _macos_nuitka_extra_args() -> str:
    args = list(MACOS_NUITKA_BASE_ARGS)
    missing_required = _missing_required_packages(MACOS_NUITKA_REQUIRED_PACKAGES)
    if missing_required:
        missing_text = ", ".join(missing_required)
        raise SystemExit(
            "Required runtime packages are missing from the packaging Python environment: "
            f"{missing_text}."
        )

    packages = list(MACOS_NUITKA_REQUIRED_PACKAGES)
    packages.extend(_available_packages(MACOS_NUITKA_OPTIONAL_PACKAGES))
    packages.extend(_available_packages(MACOS_NUITKA_DEPENDENCY_PACKAGES))
    args.extend(f"--include-package={package}" for package in packages)
    args.extend(
        f"--include-module={module}"
        for module in _available_modules(MACOS_NUITKA_OPTIONAL_MODULES)
    )
    return " ".join(args)


def _render_pyinstaller_spec() -> Path:
    spec_dir = PYINSTALLER_RENDERED_SPEC.parent
    spec_dir.mkdir(parents=True, exist_ok=True)
    rendered = PYINSTALLER_SPEC_TEMPLATE.read_text(encoding="utf-8")
    icon_arg = ""
    if sys.platform == "win32":
        icon_arg = f"    icon=[{_icon_path().resolve().as_posix()!r}],\n"
    replacements = {
        "__APP_NAME__": APP_NAME,
        "__INPUT_FILE__": INPUT_FILE.resolve().as_posix(),
        "__SRC_PATH__": (REPO_ROOT / "src").resolve().as_posix(),
        "__ICON_ARG__": icon_arg,
    }
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    PYINSTALLER_RENDERED_SPEC.write_text(rendered, encoding="utf-8")
    return PYINSTALLER_RENDERED_SPEC


def _macos_build_command(*, dry_run: bool, verbose: bool) -> list[str]:
    command = [
        _deploy_executable(),
        "--force",
        "--config-file",
        str(_render_macos_deploy_spec()),
        "--name",
        APP_NAME,
        "--mode",
        "standalone",
        "--extra-modules",
        ",".join(MACOS_DEPLOY_EXTRA_QT_MODULES),
    ]
    if verbose:
        command.append("--verbose")
    if dry_run:
        command.append("--dry-run")
    return command


def _pyinstaller_build_command(*, dry_run: bool, verbose: bool) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(PYINSTALLER_DIST_ROOT),
        "--workpath",
        str(PYINSTALLER_BUILD_ROOT / "work"),
        str(_render_pyinstaller_spec()),
    ]
    if verbose:
        cmd.append("--log-level=DEBUG")
    if dry_run:
        print(" ".join(shlex.quote(part) for part in cmd))
        return []
    return cmd


def _cleanup_macos_transient_artifacts() -> None:
    _remove_tree(MACOS_DEPLOY_SOURCE_DIRECTORY)


def _build_pyinstaller(*, dry_run: bool, verbose: bool) -> int:
    command = _pyinstaller_build_command(dry_run=dry_run, verbose=verbose)
    if dry_run:
        return 0
    return subprocess.run(command, cwd=REPO_ROOT, check=False).returncode


def _build_macos(*, dry_run: bool, verbose: bool) -> int:
    try:
        return subprocess.run(
            _macos_build_command(dry_run=dry_run, verbose=verbose),
            cwd=REPO_ROOT,
            check=False,
        ).returncode
    finally:
        _cleanup_macos_transient_artifacts()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the build command only.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose build output.")
    args = parser.parse_args()

    _generate_icon_assets()
    _ensure_supported_python(dry_run=args.dry_run)

    if _uses_macos_deploy_backend():
        return _build_macos(dry_run=args.dry_run, verbose=args.verbose)
    return _build_pyinstaller(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
