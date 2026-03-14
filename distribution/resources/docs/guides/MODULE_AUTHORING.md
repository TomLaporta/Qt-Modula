# Module Authoring Guide

Use this guide when you are adding a Qt Modula module to this distribution as a local plugin.

It is not meant to be a spec for every possible module. It is the practical path that matches how the shipped modules already work.

## What Existing Modules Have In Common

Most shipped modules follow the same shape:

- every module subclasses `ModuleBase`
- every module defines a class-level `descriptor: ModuleDescriptor`
- every module implements `__init__(module_id)`, `widget()`, and `on_input(port, value)`
- every module publishes `text` and `error` outputs
- most modules declare `persistent_inputs`; sink-only modules may omit it
- modules with external/background resources implement `on_close()` cleanup
- modules that must republish state after project load implement `replay_state()`

If you stay close to this pattern, the module will fit the runtime, persistence layer, and UI without surprises.

## Start from the Template

Start with:

- `resources/module_template.py`

Copy it, rename the class and module metadata, then remove anything you do not need.

The template already handles the parts that are easy to get wrong:

- strict descriptor contract
- persistence baseline
- deterministic UI/input synchronization
- clear state publication pattern
- replay and cleanup hooks

## Choose the Extension Path

If you are extending the shipped distribution, prefer a local plugin in `modules/`.

Keep custom work outside of the executable. If you maintain the application's internals in a separate development repository, make those changes there and then rebuild the distribution.

## Build In This Order

This order keeps the work simple and avoids UI/runtime drift.

### 1. Define Contract First

Write the descriptor before you write behavior:

- `module_type`: stable persisted id
- `display_name`: operator-facing name
- `family`: functional grouping used in palette/catalog
- `description`: concise behavior statement
- `inputs` and `outputs`: full `PortSpec` tuples

A few contract rules help:

- use `control_plane=True` for trigger/pulse lanes
- keep defaults deterministic and explicit
- use `bind_visibility="advanced"` only for expert knobs
- use `bind_visibility="hidden"` sparingly for non-bindable internals

### Naming Conventions

Keep port names predictable:

- prefer concise lowercase snake_case port keys
- use verbs for control inputs (`emit`, `fetch`, `clear`, `reset`, `write`)
- use nouns for data outputs (`rows`, `record`, `value`, `path`)
- keep summary/diagnostic ports standardized (`text`, `error`)

### 2. Decide What To Persist

`persistent_inputs` should contain only stable user intent.

Persist:

- operator configuration values
- deterministic options that define behavior

Do not persist:

- transient status strings
- derived outputs
- ephemeral runtime counters

`ModuleBase.restore_inputs(...)` expects an exact key match with `persistent_inputs`, so loose persistence rules will break reload behavior.

### 3. Build UI as a Projection of Inputs

In `widget()`:

- initialize controls from `self.inputs`
- connect controls to `receive_binding(...)` (not direct mutation-only paths)
- use shared UI helpers (`apply_layout_defaults`, `set_control_height`, `set_expand`)
- include a status label for operator diagnostics

Keep the widget in sync with runtime state:

- block signals when synchronizing controls from runtime updates
- keep core controls visible
- place advanced tuning controls in collapsed/segmented UI regions when needed

### 4. Implement Deterministic Input Handling

In `on_input(...)`:

- branch by port name explicitly
- update `self.inputs` first
- synchronize affected controls with signal blocking
- publish outputs through a single helper (for example `_publish_state(...)`)

For trigger-style inputs:

- check with `is_truthy(value)`
- avoid side effects when trigger input is falsey

For validation:

- clamp/reject invalid operational configuration deterministically
- publish actionable errors to `error` output

### 5. Centralize Output Publication

Use one internal helper to publish state:

- payload outputs (domain values)
- pulse outputs (`changed`, `fetched`, `wrote`, etc.)
- `text` summary
- `error` message

That gives you:

- deterministic output ordering
- easier replay implementation
- easier test assertions

### 6. Implement Replay and Cleanup Hooks

#### `replay_state()`

Implement this when downstream modules need the current state to be republished after a project loads.

It should republish state, not perform fresh side effects.

#### `on_close()`

Implement this when the module owns anything that must be shut down cleanly, such as timers, worker threads, clients, or files.

Examples:

- `AsyncServiceRunner.shutdown()`
- timer stop/disconnect
- provider client cleanup

### 7. Extend for Async Work (When Needed)

For provider, export, or network modules:

- run background work via `AsyncServiceRunner`
- wrap service calls with `capture_service_result(...)`
- normalize failures with `apply_async_error_policy(...)`
- expose deterministic `busy` state
- clear stale success outputs on failure

Keep these rules in place:

- no concurrent duplicate run if already busy
- all exit paths clear busy
- success and failure outputs are deterministic

### 8. Extend for Dynamic Ports (When Needed)

Use dynamic ports only when a fixed port list would make the workflow clumsy or misleading.

Requirements:

- generated port keys are deterministic from persisted inputs
- descriptor updates preserve existing inputs where keys still exist
- runtime contract is refreshed after descriptor mutation (`refresh_module_contract`)
- removed dynamic ports produce deterministic outcomes (pruned bindings or validation failure)

Never generate dynamic keys from randomness, timestamps, or external non-persisted state.

### Status And Error Text

Operator-facing text should stay short, stable, and useful:

- use short status summaries (`reason=...`, `rows=...`, `mode=...`)
- avoid noisy text churn when state has not materially changed
- keep `error` empty (`""`) on healthy state
- include fallback behavior in warnings (`invalid mode 'x'; using 'overwrite'`)

### Performance And Memory

For high-rate modules:

- avoid unnecessary object churn in hot paths
- emit only when outputs meaningfully change
- keep retained state bounded (for example max rows, max points)
- avoid blocking calls in `on_input(...)`; use async runner for I/O

### Test Shape

If you also maintain a development workspace, this is a good minimum test shape:

1. descriptor contract test (port keys, kinds, planes, defaults)
2. input coercion/validation test (happy + invalid cases)
3. state publication test (`text`, `error`, data outputs)
4. persistence roundtrip test (`snapshot_inputs`/`restore_inputs`)
5. replay/cleanup tests when implemented

## Shipping Checklist

Before shipping a module:

1. descriptor is complete and accurate
2. `persistent_inputs` contains only stable intent
3. `widget()` initializes from `self.inputs`
4. `on_input(...)` handles each declared input intentionally
5. module emits `text` and `error` consistently
6. replay/close hooks are implemented when needed
7. deterministic behavior is validated before packaging

## Additional Test Coverage

If you keep an automated test suite, cover at minimum:

1. descriptor contract correctness
2. coercion/validation behavior on inputs
3. success-path output publication
4. failure-path output publication
5. persistence round trip (`snapshot_inputs` + `restore_inputs`)
6. replay behavior if `replay_state()` is implemented
7. resource cleanup if `on_close()` is implemented
8. dynamic port regeneration + project-load behavior (if applicable)

## Wire It Into The Distribution

After implementation:

1. If this is a local plugin, place it in `modules/<name>.py` or `modules/<name>/plugin.py` and expose `API_VERSION = "1"` plus `register(registry)`.
2. Update `resources/docs/modules/MODULE_CATALOG.md` if the module is part of the package you are redistributing.
3. Add or update the module-specific doc in `resources/docs/modules/` when recipients need a reference for it.
4. Update platform docs for contract or persistence changes that affect recipients:
   - `resources/docs/platform/ARCHITECTURE.md`
   - `resources/docs/platform/RUNTIME_CONTRACTS.md`
   - `resources/docs/platform/SCHEMA_REFERENCE.md`

This package does not expose an editable built-in module registry. If you need to change bundled internals, do that work in your development repository and ship a new package.

## Final Validation

Before you redistribute the package, confirm the following in the app itself:

1. the module appears in the palette or plugin load succeeds cleanly
2. persisted inputs save and restore correctly
3. `text` and `error` outputs stay deterministic and useful
4. replay does not trigger uncontrolled side effects
5. cleanup logic releases timers, workers, and external resources

If you maintain the full development tree elsewhere, run your normal test and lint pipeline there before packaging the updated distribution.

## Common Mistakes

- implicit behavior not represented in descriptor ports
- non-deterministic output wording or ordering
- persistence of transient/derived state
- UI-only state that can diverge from `self.inputs`
- async work that can remain busy forever on exception paths
- dynamic ports that cannot be rebuilt deterministically on load
