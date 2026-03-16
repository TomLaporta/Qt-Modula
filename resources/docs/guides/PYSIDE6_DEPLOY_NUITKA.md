# Qt Modula Packaging with PySide6-Deploy and Nuitka

This guide is for packaging Qt Modula specifically.

It is not a generic Qt-for-Python guide. It documents the release path this repository actually uses, the files that control it, and the packaging problems already found in this codebase.

## Packaging Rule

For Qt Modula:

- use `pyside6-deploy` on macOS
- use PyInstaller `--onefile` on Windows and Linux
- build natively on each target OS
- use raw Nuitka only for debugging or when `pyside6-deploy` needs help on macOS

Do not use `onefile` for macOS production builds of this app. Linux and Windows use the repository
PyInstaller wrapper because it avoids the extra standalone tree copy performed by
`pyside6-deploy`.

## Runtime Layout

Packaged Qt Modula expects this portable layout:

- packaged app or executable
- `modules/`
- `saves/`
- `resources/`

The app keeps user-facing data outside the bundle itself.

## Files That Control Packaging

- entrypoint: `main.py`
- deploy spec template: `packaging/pyside6-deploy.spec.in`
- PyInstaller spec template: `packaging/pyinstaller.spec.in`
- generated local spec: `build/pyside6-deploy/pysidedeploy.spec`
- build wrapper: `resources/scripts/build_distribution.py`
- staging wrapper: `resources/scripts/stage_distribution.py`
- generated icon assets: `resources/assets/`

The checked-in source of truth is `packaging/pyside6-deploy.spec.in`. The rendered
`build/pyside6-deploy/pysidedeploy.spec` is generated at build time and should stay out of version
control.

## Default Build Path

Use Python `3.11`, `3.12`, or `3.13` for release packaging.

Current limitation:

- Nuitka `2.7.11`, which is the version used by `pyside6-deploy`, does not currently support Python `3.14` on macOS

Install build dependencies:

```bash
python3.11 -m pip install -e '.[build]'
```

Preview the generated build command:

```bash
python3.11 resources/scripts/build_distribution.py --dry-run
```

Build the packaged app:

```bash
python3.11 resources/scripts/build_distribution.py
```

Stage the distribution folder:

```bash
python3.11 resources/scripts/stage_distribution.py
```

Output paths:

- macOS deploy output: `build/pyside6-deploy/output/`
- Windows/Linux build output: `build/pyinstaller-dist/`
- staged release root: `distribution/`

## What The Build Wrapper Does

`resources/scripts/build_distribution.py` is the normal entry point for this repo.

It does two different packaging jobs depending on platform:

1. on macOS, it renders `build/pyside6-deploy/pysidedeploy.spec` from `packaging/pyside6-deploy.spec.in`, injects the current Python executable path, forces `standalone` mode, and passes repo-specific Nuitka flags
2. on Windows/Linux, it runs the repo's PyInstaller `--onefile` build with the required hidden imports and package data collection

Current repo-specific flags:

- `--extra-modules OpenGL`
- generated spec `extra_args` include `--include-module=PySide6.QtOpenGL`
- macOS build output is written under `build/pyside6-deploy/output/`
- Windows/Linux build output is written under `build/pyinstaller-dist/`
- generated packaging icons are written under `resources/assets/`

On Windows and Linux, `resources/scripts/build_distribution.py` writes the intermediate executable
under `build/pyinstaller-dist/`.

Those flags are not cosmetic. Qt Modula uses `pyqtgraph`, and `pyqtgraph` imports `PySide6.QtOpenGL` dynamically. Without that explicit include, the packaged app can boot into a `ModuleNotFoundError`.

## When To Use Raw Nuitka

Use raw Nuitka only when:

- the packaged app fails and you need to isolate the failure
- you need to test an explicit hidden import
- you need to compare macOS `pyside6-deploy` output with a direct Nuitka invocation

For Qt Modula, the minimum useful direct command is:

```bash
python3.11 -m nuitka \
  --standalone \
  --enable-plugin=pyside6 \
  --include-package-data=qt_modula \
  --include-module=PySide6.QtOpenGL \
  main.py
```

On macOS, use:

```bash
python3.11 -m nuitka \
  --standalone \
  --macos-create-app-bundle \
  --enable-plugin=pyside6 \
  --include-package-data=qt_modula \
  --include-module=PySide6.QtOpenGL \
  main.py
```

If a direct Nuitka build works and the wrapped macOS build does not, the problem is usually in the
rendered `build/pyside6-deploy/pysidedeploy.spec` or in `pyside6-deploy` argument handling.

## Do Not Use `pyside6-deploy --init` For Normal Repo Builds

`pyside6-deploy --init` is useful for experiments, but it is not the normal path for this repository.

Qt Modula already has:

- a spec template
- a build wrapper
- a staging wrapper
- generated packaging icon assets under `resources/assets/`

If you run `pyside6-deploy --init`, treat the result as scratch material, not as the new source of truth.

## Platform Notes

### macOS

Requirements:

- Xcode Command Line Tools or full Xcode
- `dyld_info`
- Python `3.11`, `3.12`, or `3.13`

Repository build:

```bash
python3.11 -m pip install -e '.[build]'
python3.11 resources/scripts/build_distribution.py
python3.11 resources/scripts/stage_distribution.py
```

Finder-friendly helper:

```bash
chmod +x build_macos.command
./build_macos.command
```

This helper finds a supported Python automatically, runs the same macOS packaging flow, stages
`distribution/`, and pauses before closing so failures are easy to read.

Expected output:

- `build/pyside6-deploy/output/qt-modula.app`
- `distribution/qt-modula.app`

Direct `pyside6-deploy` debugging command:

```bash
pyside6-deploy -c build/pyside6-deploy/pysidedeploy.spec --mode standalone --name qt-modula
```

Important Qt Modula note:

- the packaged `.app` must still resolve `modules/`, `saves/`, and `resources/` beside the app bundle, not inside it

### Windows

Requirements:

- CPython from python.org
- PyInstaller installed via `pip install -e ".[build]"`
- Python `3.11`, `3.12`, or `3.13`

Repository build:

```powershell
py -3.11 -m pip install -e ".[build]"
py -3.11 resources/scripts/build_distribution.py
py -3.11 resources/scripts/stage_distribution.py
```

Expected output:

- `build/pyinstaller-dist/qt-modula.exe`
- `distribution/`

Important Qt Modula note:

- the staged Windows distribution keeps the app as `distribution/Qt Modula.exe` beside `modules/`, `saves/`, and `resources/`

### Linux

Requirements:

- a supported PyInstaller runtime toolchain for your target distro
- Python `3.11`, `3.12`, or `3.13`

Typical Debian or Ubuntu baseline:

```bash
sudo apt install build-essential
```

Repository build:

```bash
python3.11 -m pip install -e '.[build]'
python3.11 resources/scripts/build_distribution.py
python3.11 resources/scripts/stage_distribution.py
```

Terminal helper:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

This helper finds a supported Python automatically, runs the same Linux packaging flow, stages
`distribution/`, and pauses before closing so failures are easy to read.

Expected output:

- `build/pyinstaller-dist/qt-modula`
- `distribution/`

Important Qt Modula note:

- validate on the oldest Linux environment you intend to support, not just on your build host
- prefer the repository build wrapper over raw `pyside6-deploy`; the Qt wrapper duplicates the
  standalone payload during finalize and can fail with `No space left on device`

## Automation Note

This checkout does not include a checked-in release workflow. If you automate packaging, run
`resources/scripts/build_distribution.py` and `resources/scripts/stage_distribution.py` natively
on each target OS so the automated path matches the local release path.

## Known Qt Modula Packaging Problems

### `ModuleNotFoundError: No module named 'PySide6.QtOpenGL'`

Cause:

- `pyqtgraph` imports `PySide6.QtOpenGL` dynamically
- automatic dependency discovery may miss it

Fix:

- keep `--include-module=PySide6.QtOpenGL` in the rendered spec
- keep `--extra-modules OpenGL` in `resources/scripts/build_distribution.py`

### App is slow to boot

Cause:

- using a single-file bundle instead of `standalone` on macOS

Fix:

- stay on the current macOS `pyside6-deploy` standalone path

### `No space left on device` during Linux packaging

Cause:

- `pyside6-deploy` builds a standalone payload and then copies that entire tree again during its
  finalize step
- large dependency sets can exhaust the working drive during that second copy

Fix:

- use `resources/scripts/build_distribution.py` so Linux goes through the repository PyInstaller path
- stage the final folder with `resources/scripts/stage_distribution.py`

### Built app starts but cannot find user folders

Cause:

- app launched from a layout that does not include the external runtime folders

Fix:

- ship the app beside `modules/`, `saves/`, and `resources/`
- verify using the staged distribution folder, not the intermediate build output alone

## Recommended Release Loop

For this repo, use this order:

1. edit `packaging/pyside6-deploy.spec.in` or `resources/scripts/build_distribution.py`
2. run `python3.11 resources/scripts/build_distribution.py --dry-run`
3. run `python3.11 resources/scripts/build_distribution.py`
4. run `python3.11 resources/scripts/stage_distribution.py`
5. launch the staged app from `distribution/`
6. verify:
   - startup
   - local plugin loading from `modules/`
   - save/load under `saves/`
   - exports under `saves/exports/`

## Official References

- Qt for Python deployment overview: <https://doc.qt.io/qtforpython-6/deployment/index.html>
- `pyside6-deploy`: <https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html>
- Qt for Python and Nuitka: <https://doc.qt.io/qtforpython-6/deployment/deployment-nuitka.html>
- Nuitka user manual: <https://nuitka.net/user-documentation/user-manual.html>
