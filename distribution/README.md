# Qt Modula

Qt Modula is a desktop application for building visual workflows from connected modules.

At a high level:

- modules are the building blocks
- ports define what each module accepts and emits
- bindings connect outputs to inputs
- the runtime keeps delivery order predictable so the same graph behaves the same way

## Distribution Layout

All paths below are relative to this folder. Keep this layout intact:

- `qt-modula.app/` is the packaged macOS application bundle
- `modules/` for optional local plugins
- `saves/` for your settings, projects, exports, and autosnapshots
- `resources/docs/` for user and technical documentation
- `resources/module_template.py` for plugin authoring

Qt Modula keeps runtime data under `saves/` so your work stays separate from the packaged application.

## Start Here

1. Open a terminal in this folder.
2. Launch Qt Modula:

```bash
open qt-modula.app
```

3. Read `resources/docs/guides/GETTING_STARTED.md`.
4. Build your first workflow on the default canvas.

## Plugin Folder

`modules/` is the local plugin discovery folder.

Qt Modula looks for plugins in these forms:

- `modules/<name>.py`
- `modules/<name>/plugin.py`

Plugin contract:

```python
API_VERSION = "1"

def register(registry):
    registry.register_module(MyModule)
```

Plugins are trusted local code and run inside the application process. Only install plugins you trust.

If you want Qt Modula to use a different workspace location, set `QT_MODULA_HOME=/absolute/path` before launch.

## Documentation

The main references shipped with this distribution are:

- `resources/docs/guides/GETTING_STARTED.md`: first-run guide
- `resources/docs/guides/WORKFLOW_ENGINEERING.md`: workflow design guide
- `resources/docs/modules/MODULE_CATALOG.md`: built-in module reference
- `resources/docs/platform/PLUGIN_INTERFACE.md`: local plugin contract
- `resources/docs/platform/SCHEMA_REFERENCE.md`: settings and project schema reference

If you need help understanding workflow design, start with the getting started guide before you experiment with larger graphs.
