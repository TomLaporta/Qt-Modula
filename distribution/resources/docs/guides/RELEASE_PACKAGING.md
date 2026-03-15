# Release Packaging

This guide covers the production packaging path for Qt Modula.

Qt Modula uses the backend that best fits each platform:

- macOS and Linux: `pyside6-deploy` in `standalone` mode
- Windows: PyInstaller in `--onefile` mode

For the Qt Modula-specific packaging guide, including the Windows split and macOS/Linux Nuitka notes, see `resources/docs/guides/PYSIDE6_DEPLOY_NUITKA.md`.

## Why This Path

- macOS/Linux stay on the Qt-for-Python deployment tool
- Windows gets a cleaner end-user folder with one top-level `.exe`
- the staged release layout still preserves `modules/`, `saves/`, and `resources/`
- generated packaging icons live under `resources/assets/`

## Local Build

Install build dependencies:

```bash
python3.11 -m pip install -e '.[build]'
```

macOS helper:

```bash
chmod +x build_macos.command
./build_macos.command
```

This helper auto-selects Python `3.11` to `3.13`, runs the macOS packaging path, stages
`distribution/`, and pauses before closing so packaging errors stay visible.

Linux helper:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

This helper auto-selects Python `3.11` to `3.13`, runs the Linux packaging path, stages
`distribution/`, and pauses before closing so packaging errors stay visible.

Build the packaged application:

```bash
python3.11 resources/scripts/build_distribution.py
```

Stage the end-user distribution layout:

```bash
python3.11 resources/scripts/stage_distribution.py
```

Output:

- macOS/Linux build output: `build/pyside6-deploy/output/`
- Windows build output: `build/pyinstaller-dist/`
- staged distribution: `distribution/`

## What The Build Scripts Do

`resources/scripts/build_distribution.py`

- renders a temporary `pyside6-deploy` config from `packaging/pyside6-deploy.spec.in`
- stamps in the current Python executable so the checked-in template stays portable
- runs `pyside6-deploy` in `standalone` mode on macOS/Linux
- runs PyInstaller in `--onefile` mode on Windows
- refreshes the generated platform icon set in `resources/assets/`

`build_macos.command`

- finds `python3.13`, `python3.12`, or `python3.11`
- runs `resources/scripts/build_distribution.py`
- runs `resources/scripts/stage_distribution.py`
- pauses before exit so build output remains readable from Finder launches

`build_linux.sh`

- finds `python3.13`, `python3.12`, or `python3.11`
- runs `resources/scripts/build_distribution.py`
- runs `resources/scripts/stage_distribution.py`
- pauses before exit so build output remains readable from terminal launches

## Python Version

Use Python `3.11`, `3.12`, or `3.13` for release packaging.

Current limitation:

- Nuitka `2.7.11`, which is the version used by `pyside6-deploy`, does not currently support Python `3.14` on macOS/Linux

`resources/scripts/stage_distribution.py`

- copies the packaged app into a clean distribution folder
- adds the end-user `README.md`
- adds curated end-user docs under `resources/docs/`
- creates empty `saves/` folders
- copies `modules/` without shipping a separate plugin README

## Automation

This checkout does not include a checked-in `.github/workflows/release.yml`. If you automate
releases, use the same native commands documented above on each target OS so your automated builds
match the local packaging path.

## Windows Note

Windows release builds now use PyInstaller, so the local developer path no longer depends on the Visual Studio C++ toolchain just to produce a portable `.exe`.

## Linux Note

Linux portability still needs real-world validation on your target distributions. Automate builds if
you want, but test on the oldest Linux environment you plan to support before you publish.
