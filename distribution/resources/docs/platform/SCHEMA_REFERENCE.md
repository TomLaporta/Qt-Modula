# Schema Reference

This reference covers the settings and project files that Qt Modula reads and writes.

Schemas use `extra="forbid"`, so unknown fields are rejected.

## App Settings Schema

`AppConfig` stores application settings.

```text
AppConfig
  version: "AppConfig"
  runtime: RuntimePolicy
  ui: UiPolicy
  autosnapshot: AutosnapshotPolicy
  provider_network: ProviderNetworkPolicy
  paths: PathPolicy
  safety_prompts: SafetyPromptPolicy
```

### RuntimePolicy

- `max_queue_size: int` (`1 .. 5_000_000`, default `100_000`)
- `coalesce_pending_inputs: bool` (default `true`)
- `max_deliveries_per_batch: int` (`1 .. 10_000_000`, default `250_000`)

### UiPolicy

- `theme: str` (default `"default"`)
  - stores selected theme preset token (for example `"default"` or a user preset name)
- `custom_theme: CustomThemePolicy`
  - `primary_color: str` (`#RRGGBB`)
  - `secondary_color: str` (`#RRGGBB`)
  - `highlight_color: str` (`#RRGGBB`)
  - `canvas_color: str` (`#RRGGBB`)

Theme preset definitions are stored separately in `saves/main/theme_presets.json`.
Preset names are unique (case-insensitive) and `Default` is reserved.

### AutosnapshotPolicy

- `enabled: bool` (default `true`)
- `debounce_ms: int` (`100 .. 30_000`, default `800`)
- `max_history: int` (`1 .. 500`, default `50`)

### ProviderNetworkPolicy

- `http: HttpNetworkPolicy`
  - `timeout_s: float` (`0.1 .. 300.0`, default `10.0`)
  - `retries: int` (`0 .. 20`, default `2`)
  - `backoff_s: float` (`0.0 .. 60.0`, default `0.15`)
  - `min_gap_s: float` (`0.0 .. 60.0`, default `0.0`)
  - `proxy_url: str` (default `""`)
- `yfinance: YFinanceNetworkPolicy`
  - `retries: int` (`0 .. 20`, default `2`)
  - `backoff_s: float` (`0.0 .. 60.0`, default `0.25`)

### PathPolicy

- `project_directory: str` (absolute path)
- `autosnapshot_directory: str` (absolute path)
- `export_directory: str` (absolute path)

Export writes are bounded by a runtime quota:

- each concrete export target folder under `export_directory` is capped at `100 MB`
- writes that would push a folder past the cap are rejected with an export warning
- overwrites that reduce an already-over-limit folder are still allowed

### SafetyPromptPolicy

- `confirm_module_remove: bool` (default `true`)
- `confirm_binding_remove: bool` (default `true`)
- `confirm_canvas_delete: bool` (default `true`)
- `confirm_workspace_reset: bool` (default `true`)
- `confirm_load_over_unsaved: bool` (default `true`)

### Loader Rules (`load_app_config`)

- Missing file: returns defaults.
- Existing file: `version` must be exactly `"AppConfig"`.
- Any other `version` value (including missing) is rejected.

### Storage Path

Desktop entrypoint resolves settings path as:

- `<app_root>/saves/main/settings.json`

`app_root` resolution policy:

- override: `QT_MODULA_HOME=/absolute/path`
- default distribution root: folder containing `qt-modula.app`, `modules/`, `saves/`, and `resources/`

## Project Schema

`ProjectV1` is the only accepted workflow snapshot payload.

```text
Project
  version: "ProjectV1"
  runtime: RuntimePolicy
  canvases: list[CanvasSnapshot]
  bindings: list[BindingSnapshot]
```

### CanvasSnapshot

- `canvas_id: str` (non-empty)
- `name: str` (non-empty)
- `modules: list[ModuleSnapshot]`

### ModuleSnapshot

- `module_id: str` (non-empty)
- `module_type: str` (non-empty)
- `name: str` (non-empty, max length `32`)
- `inputs: dict[str, Any]`

### BindingSnapshot

- `src_module_id: str` (non-empty)
- `src_port: str` (non-empty)
- `dst_module_id: str` (non-empty)
- `dst_port: str` (non-empty)

### Loader Rules (`load_project`)

- Root payload must be an object.
- `version` must be exactly `"ProjectV1"`.
- Schema violations raise deterministic `PersistenceError`.

### Writer Rules (`save_project`, `save_app_config`)

- parent directories are created automatically
- JSON output is deterministic (`sorted keys`, `2-space indentation`)

## Apply-Time Semantic Validation

Schema validation guarantees payload shape. Project apply adds semantic checks:

- at least one canvas must exist
- `canvas_id` values must be unique
- `module_id` values must be unique
- module custom names must be non-empty and globally unique (case-insensitive)
- `module_type` must exist in live registry
- bindings must reference existing source/destination modules
- bindings must satisfy live module port contracts
- cycle policy is enforced during binding creation

## Dynamic Port Persistence Rules

For modules with dynamic bind ports:

- bindings persist exact source/destination port keys
- dynamic keys must be rebuilt from persisted module inputs before binding replay
- if a key no longer exists in live descriptor, binding application fails

## Example Minimal Project

```json
{
  "version": "ProjectV1",
  "runtime": {
    "max_queue_size": 100000,
    "coalesce_pending_inputs": true,
    "max_deliveries_per_batch": 250000
  },
  "canvases": [
    {
      "canvas_id": "c_0001",
      "name": "Canvas 1",
      "modules": []
    }
  ],
  "bindings": []
}
```

## Compatibility Policy

Qt Modula currently has no schema migration layer.

- payloads matching current schema versions load
- non-current versions are rejected with explicit persistence errors
