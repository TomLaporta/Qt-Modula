# Plugin Interface

Qt Modula v1 loads local plugins from the `modules/` directory in the current distribution folder.

Qt Modula resolves that root in the following order:

- override: `QT_MODULA_HOME=/absolute/path`
- default distribution root: folder containing `qt-modula.app`, `modules/`, `saves/`, and `resources/`

## Discovery

Qt Modula checks these locations in order:

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

Start from `resources/module_template.py` if you want a working baseline that matches the shipped plugin contract.

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

Plugins run in-process and are trusted code. Review plugin code before placing it in `modules/`.
