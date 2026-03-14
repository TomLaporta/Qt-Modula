# Module Authoring Guide

This guide defines the canonical workflow for implementing first-party Qt Modula modules.

It is based on a scan of all current first-party module implementations.

## Baseline Observations from Current Modules

Across all registered first-party modules (`40` total), the shared baseline is consistent:

- every module subclasses `BaseModule`
- every module defines a class-level `descriptor: ModuleDescriptor`
- every module implements `__init__(module_id)`, `widget()`, and `on_input(port, value)`
- every module publishes `text` and `error` outputs
- most modules declare `persistent_inputs`; sink-only modules may omit it
- modules with external/background resources implement `on_close()` cleanup
- modules that must republish state after project load implement `replay_state()`

Use this as the minimum engineering contract.

## Start from the Template

Use:

- `resources/module_template.py`

Copy it, rename the class/module identity fields, then iterate from there.

Template guarantees you start with:

- strict descriptor contract
- persistence baseline
- deterministic UI/input synchronization
- clear state publication pattern
- replay and cleanup hooks

## Authoring Progression

Implement modules in this order.

### 1. Define Contract First

Populate descriptor fields before writing behavior:

- `module_type`: stable persisted id
- `display_name`: operator-facing name
- `family`: functional grouping used in palette/catalog
- `description`: concise behavior statement
- `inputs` and `outputs`: full `PortSpec` tuples

Port-level standards:

- use `control_plane=True` for trigger/pulse lanes
- keep defaults deterministic and explicit
- use `bind_visibility="advanced"` only for expert knobs
- use `bind_visibility="hidden"` sparingly for non-bindable internals

### Contract Naming Conventions

Keep contracts predictable across module families:

- prefer concise lowercase snake_case port keys
- use verbs for control inputs (`emit`, `fetch`, `clear`, `reset`, `write`)
- use nouns for data outputs (`rows`, `record`, `value`, `path`)
- keep summary/diagnostic ports standardized (`text`, `error`)

### 2. Choose Persistence Intentionally

`persistent_inputs` should contain only stable user intent.

Persist:

- operator configuration values
- deterministic options that define behavior

Do not persist:

- transient status strings
- derived outputs
- ephemeral runtime counters

Remember: `BaseModule.restore_inputs(...)` enforces exact key match with `persistent_inputs`.

### 3. Build UI as a Projection of Inputs

In `widget()`:

- initialize controls from `self.inputs`
- connect controls to `receive_binding(...)` (not direct mutation-only paths)
- use shared UI helpers (`apply_layout_defaults`, `set_control_height`, `set_expand`)
- include a status label for operator diagnostics

UI consistency rules:

- block signals when synchronizing controls from runtime updates
- keep core controls visible
- place advanced tuning controls in collapsed/segmented UI regions when needed

### 4. Implement Deterministic Input Handling

In `on_input(...)`:

- branch by port name explicitly
- update `self.inputs` first
- synchronize affected controls with signal blocking
- publish outputs through a single helper (for example `_publish_state(...)`)

Trigger-port handling pattern:

- check with `is_truthy(value)`
- avoid side effects when trigger input is falsey

Validation pattern:

- clamp/reject invalid operational configuration deterministically
- publish actionable errors to `error` output

### 5. Centralize Output Publication

Use one internal method to emit coherent state:

- payload outputs (domain values)
- pulse outputs (`changed`, `fetched`, `wrote`, etc.)
- `text` summary
- `error` message

Benefits:

- deterministic output ordering
- easier replay implementation
- easier test assertions

### 6. Implement Replay and Cleanup Hooks

#### `replay_state()`

Implement when downstream chains need the module to republish current outputs after project load.

Use it to emit current state only; do not perform uncontrolled side effects.

#### `on_close()`

Implement when the module owns resources (threads, timers, clients, files).

Examples:

- `AsyncServiceRunner.shutdown()`
- timer stop/disconnect
- provider client cleanup

### 7. Extend for Async Work (When Needed)

For provider/export/network modules:

- run background work via `AsyncServiceRunner`
- wrap service calls with `capture_service_result(...)`
- normalize failures with `apply_async_error_policy(...)`
- expose deterministic `busy` state
- clear stale success outputs on failure

Required async invariants:

- no concurrent duplicate run if already busy
- all exit paths clear busy
- success and failure outputs are deterministic

### 8. Extend for Dynamic Ports (When Needed)

Use dynamic ports only when static contracts cannot model operator workflow cleanly.

Requirements:

- generated port keys are deterministic from persisted inputs
- descriptor updates preserve existing inputs where keys still exist
- runtime contract is refreshed after descriptor mutation (`refresh_module_contract`)
- removed dynamic ports produce deterministic outcomes (pruned bindings or validation failure)

Never generate dynamic keys from randomness, timestamps, or external non-persisted state.

### Error and Status Language Standards

Keep operator-facing language deterministic and actionable:

- use short status summaries (`reason=...`, `rows=...`, `mode=...`)
- avoid noisy text churn when state has not materially changed
- keep `error` empty (`""`) on healthy state
- include fallback behavior in warnings (`invalid mode 'x'; using 'overwrite'`)

### Performance and Memory Baseline

For high-rate modules:

- avoid unnecessary object churn in hot paths
- emit only when outputs meaningfully change
- keep retained state bounded (for example max rows, max points)
- avoid blocking calls in `on_input(...)`; use async runner for I/O

### Minimal Test Skeleton

Use this test structure for new modules:

1. descriptor contract test (port keys, kinds, planes, defaults)
2. input coercion/validation test (happy + invalid cases)
3. state publication test (`text`, `error`, data outputs)
4. persistence roundtrip test (`snapshot_inputs`/`restore_inputs`)
5. replay/cleanup tests when implemented

## Mandatory Baseline Checklist

Before registering a module:

1. descriptor is complete and accurate
2. `persistent_inputs` contains only stable intent
3. `widget()` initializes from `self.inputs`
4. `on_input(...)` handles each declared input intentionally
5. module emits `text` and `error` consistently
6. replay/close hooks are implemented when needed
7. deterministic behavior is validated by tests

## Testing Matrix

At minimum, add tests for:

1. descriptor contract correctness
2. coercion/validation behavior on inputs
3. success-path output publication
4. failure-path output publication
5. persistence round trip (`snapshot_inputs` + `restore_inputs`)
6. replay behavior if `replay_state()` is implemented
7. resource cleanup if `on_close()` is implemented
8. dynamic port regeneration + project-load behavior (if applicable)

## Registration and Documentation Workflow

After implementation:

1. register built-in modules in `src/qt_modula/modules_builtin/registry.py` (or expose plugins through the `src/qt_modula/modules` compatibility/plugin surface as appropriate)
2. update `resources/docs/modules/MODULE_CATALOG.md`
3. add/update module-specific doc in `resources/docs/modules/`
4. update platform docs for contract changes:
   - `resources/docs/platform/ARCHITECTURE.md`
   - `resources/docs/platform/RUNTIME_CONTRACTS.md`
   - `resources/docs/platform/SCHEMA_REFERENCE.md`

## Quality Gate Before PR

Run:

```bash
QT_QPA_PLATFORM=offscreen python3 resources/scripts/run_quality_gate.py
```

If your change affects module behavior, include exact command outputs in the PR summary.

## Anti-Patterns to Avoid

- implicit behavior not represented in descriptor ports
- non-deterministic output wording or ordering
- persistence of transient/derived state
- UI-only state that can diverge from `self.inputs`
- async work that can remain busy forever on exception paths
- dynamic ports that cannot be rebuilt deterministically on load
