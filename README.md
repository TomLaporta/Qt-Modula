# Qt Modula

Qt Modula is a deterministic desktop workflow runtime for modular bind chains. Built with Qt/PySide6.

Version `1.0.0` is a platform-first release focused on a stable core architecture:

- strict contracts and current-version-only persistence
- deterministic linear runtime scheduling
- compact cards + bind-panel UX for professional workflows
- local plugin loading from `modules/`
- debounced autosnapshots for crash recovery
- portable runtime layout for packaged desktop builds

## Why Qt Modula

Qt Modula is designed for workflows where reproducibility and explicit contracts matter more than permissive behavior. The runtime guarantees stable delivery ordering under identical graph and input state.

## Buy Me a Coffee

Qt Modula is an independent project built to a professional standard: deterministic behavior, explicit contracts, and careful long-term maintenance. If you value software shaped by rigor, clarity, and stewardship, you can support its continued development here:

[Support Qt Modula on Buy Me a Coffee](https://buymeacoffee.com/thomaslaporta)

Your support helps fund disciplined releases, documentation, packaging, and the steady polish that makes a tool trustworthy.

## Built-In Module Pack (v1)

The first-party module set includes `40` built-ins across the platform families:

- Control (`11`): `interval_pulse`, `log_notes`, `number_input`, `options`, `text_input`, `trigger_button`, `trigger_debounce`, `trigger_delay`, `trigger_mapper`, `trigger_rate_limit`, `value_view`
- Providers (`3`): `fx_quote`, `http_request`, `market_fetcher`
- Transform (`7`): `datetime_convert`, `json_project`, `json_transform`, `table_transform`, `template_formatter`, `value_scanner`, `value_wrapper`
- Logic (`10`): `circuit_breaker`, `condition_gate`, `logic_combinator`, `retry_controller`, `trigger_join`, `trigger_join_n`, `value_change_gate`, `value_latch`, `value_router`, `value_selector`
- Math (`2`): `arithmetic`, `formula_calculator`
- Research (`2`): `parameter_sweep`, `table_buffer`
- Analytics (`3`): `line_plotter`, `rolling_stats`, `table_metrics`
- Export (`2`): `table_export`, `text_export`

## Runtime Guarantees

- deterministic scheduling order
  - destination rank
  - source emit sequence
  - binding insertion order
  - delivery serial
- strict cycle rejection at bind creation
- bounded queue and delivery budget controls
- explicit runtime diagnostics for invalid bindings

## Persistence Policy

Qt Modula uses strict current-contract loading only:

- settings payload version must be `AppConfig`
- project payload version must be `ProjectV1`
- persisted module input keys must match each module's current `persistent_inputs`
- unknown modules and invalid bindings are rejected
- no migration layer and no legacy compatibility fallback

## Autosnapshots

Crash recovery snapshots are built in:

- trigger: structural changes and persistent input updates
- write model: debounced snapshots
- location: `saves/main/autosnapshots/<project_id>/`
- retention: bounded rolling history (default `50`)
- startup behavior: prompt to recover unsaved snapshot when available

## Plugin Model

Plugins are auto-loaded from the root `modules/` directory.

Supported layout:

- `modules/<name>.py`
- `modules/<name>/plugin.py`

Required plugin contract:

- `API_VERSION = "1"`
- `register(registry)` function

Invalid plugins are isolated and reported without blocking app startup.

Packaged builds resolve plugins from the external `modules/` directory beside the executable.

## Quick Start

macOS/Linux:

```bash
python3 -m pip install -e ".[dev]"
python3 main.py
```

Windows PowerShell:

```powershell
py -3.11 -m pip install -e ".[dev]"
py -3.11 main.py
```

Alternative entrypoint:

```bash
python3 -m qt_modula.app
```

```powershell
py -3.11 -m qt_modula.app
```

## Production Packaging

Production packaging uses the platform-specific backend:

- macOS: `pyside6-deploy` in `standalone` mode
- Windows/Linux: PyInstaller in `--onefile` mode

Local build prerequisites:

macOS/Linux:

```bash
python3.11 -m pip install -e ".[build]"
```

Windows PowerShell:

```powershell
py -3.11 -m pip install -e ".[build]"
```

macOS developer helper:

```bash
chmod +x build_macos.command
./build_macos.command
```

This helper auto-selects Python `3.11` to `3.13`, runs the macOS Nuitka packaging path, stages the
final `distribution/` folder, and keeps the terminal window open if the build fails.

Linux developer helper:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

This helper auto-selects Python `3.11` to `3.13`, runs the Linux PyInstaller packaging path, stages the final
`distribution/` folder, and pauses so build output stays visible.

Windows developer helper:

```cmd
build_windows.bat
```

This helper auto-selects a supported Python, builds the `.exe`, and stages the final
`distribution/` layout in one step.

Manual build commands:

macOS/Linux:

```bash
python3.11 resources/scripts/build_distribution.py
python3.11 resources/scripts/stage_distribution.py
```

Windows PowerShell:

```powershell
py -3.11 resources/scripts/build_distribution.py
py -3.11 resources/scripts/stage_distribution.py
```

Output:

- macOS build output: `build/pyside6-deploy/output/`
- Windows/Linux build output: `build/pyinstaller-dist/`
- staged distribution: `distribution/`

Linux note:

- use the repository build wrapper instead of calling raw `pyside6-deploy`; the Qt wrapper duplicates the standalone payload during finalize and can fail with `No space left on device`

The build step refreshes the generated platform icon assets under `resources/assets/` from
`src/qt_modula/assets/app_icon.svg`.

Windows staged layout:

- single-file app: `distribution/Qt Modula.exe`
- external runtime folders: `distribution/resources/`, `distribution/modules/`, `distribution/saves/`

Packaged runtime layout:

- app bundle or executable payload
- `modules/`
- `saves/`
- `resources/`

Runtime behavior in packaged builds:

- settings: `saves/main/settings.json`
- theme presets: `saves/main/theme_presets.json`
- autosnapshots: `saves/main/autosnapshots/`
- projects: `saves/projects/`
- exports: `saves/exports/`
- plugins: `modules/`
- each export target folder is capped at `100 MB`; writes that would grow past the cap are rejected with a user-visible warning

Release process guide:

- `resources/docs/guides/RELEASE_PACKAGING.md`
- use Python `3.11`, `3.12`, or `3.13` for macOS release packaging; the current macOS Nuitka path does not yet support `3.14`

## Quality Gate

Run the full gate:

macOS/Linux:

```bash
QT_QPA_PLATFORM=offscreen python3 resources/scripts/run_quality_gate.py
```

Windows PowerShell:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
py -3.11 resources/scripts/run_quality_gate.py
```

Equivalent sequence:

```bash
python3 -m ruff check src/qt_modula resources/scripts
python3 -m mypy src/qt_modula
QT_QPA_PLATFORM=offscreen python3 -m pytest tests
QT_QPA_PLATFORM=offscreen python3 resources/scripts/run_workflow_sim.py
QT_QPA_PLATFORM=offscreen python3 resources/scripts/run_benchmarks.py
```

If `tests/` is not present in your checkout, `resources/scripts/run_quality_gate.py` skips the pytest step automatically.

## Production Notes

Before pushing to production, verify the desktop app under a normal interactive launch path, not only from the repository root.

- project, export, and autosnapshot paths are app-configurable and default to absolute paths under the local `saves/` workspace
- packaged builds resolve the external app root from the deployed app location; source runs use the repository root
- project/settings writes use atomic replace semantics so interrupted writes do not leave partial JSON payloads behind
- module `on_close()` cleanup now runs on module removal, project replacement, workspace reset, and window shutdown
- provider and export modules run their blocking work off the UI thread and report normalized failure payloads back into the runtime
- export writers enforce a `100 MB` per-folder quota and still allow overwrites that reduce an already-over-limit folder

## Repository Layout

- `src/qt_modula/sdk`
  - contracts, coercion, base module class
- `src/qt_modula/runtime`
  - deterministic scheduler and binding validation
- `src/qt_modula/persistence`
  - strict schemas, deterministic JSON I/O, autosnapshots
- `src/qt_modula/modules_builtin`
  - first-party module pack
- `src/qt_modula/plugins`
  - local plugin discovery and loading
- `src/qt_modula/ui`
  - app shell, canvas cards, bind panel
- `modules`
  - user-facing plugin directory
- `resources/assets`
  - generated packaging icons for Linux, macOS, and Windows
- `resources/docs`
  - platform and user/developer documentation
- `resources/scripts`
  - quality gate, simulation, benchmarks

## Documentation

Start here: `resources/docs/guides/CONTRIBUTING.md`

Key references:

- platform architecture: `resources/docs/platform/ARCHITECTURE.md`
- runtime contracts: `resources/docs/platform/RUNTIME_CONTRACTS.md`
- persistence schema: `resources/docs/platform/SCHEMA_REFERENCE.md`
- plugin API: `resources/docs/platform/PLUGIN_INTERFACE.md`
- module authoring: `resources/docs/guides/MODULE_AUTHORING.md`
- release packaging: `resources/docs/guides/RELEASE_PACKAGING.md`
- module-specific docs: `resources/docs/modules`
