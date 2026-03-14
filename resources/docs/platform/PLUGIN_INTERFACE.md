# Plugin Interface

Qt Modula v1 supports local plugins loaded from the external `modules/` directory under the active app root.

App root resolution:

- packaged build: external directory containing the deployed app payload
- source run: repository root
- override: `QT_MODULA_HOME=/absolute/path`

## Discovery

Loader checks in deterministic order:

- `modules/*.py`
- `modules/*/plugin.py`

Ignored:

- names starting with `_`

## Required Contract

Each plugin must define:

```python
API_VERSION = "1"

def register(registry):
    registry.register_module(MyModule)
```

`MyModule` requirements:

- subclasses `ModuleBase`
- has class-level `descriptor: ModuleDescriptor`
- implements `widget()` and `on_input(...)`
- follows persistence and error/output conventions

## Loader Behavior

- API version mismatch -> plugin skipped with issue
- missing `register(registry)` -> plugin skipped with issue
- import failure -> plugin skipped with issue
- register failure -> plugin skipped with issue

Startup continues even if plugin issues exist.

## Registry Surface

`register(registry)` receives an active registry object with:

- `register_module(module_cls)`

Modules registered by plugins are treated exactly like built-in modules at runtime.

## Stability Policy

Plugin API major version is strict.

- v1 loader accepts only `API_VERSION = "1"`
- future breaking changes increment API version

## Security

Plugins run in-process and are trusted code. Use source review and controlled distribution practices.
