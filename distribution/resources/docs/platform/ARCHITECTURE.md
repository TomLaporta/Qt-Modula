# Architecture

Qt Modula is organized in a small set of layers, each with a clear job.

This document describes the shipped application conceptually rather than as a source-tree map.

## Layer Model

### SDK

- canonical contracts (`ModuleDescriptor`, `PortSpec`, `BindingEdge`, runtime failure/result types)
- `ModuleBase` typed input/output handling, persistence snapshot discipline
- shared async helpers (`AsyncServiceRunner`, background runner, async error policy)

### Runtime

- module registration and contract indexing
- binding diagnostics (`error` + `warning` + `info`) and strict cycle rejection
- deterministic delivery scheduling with queue/coalescing/batch controls
- dynamic contract refresh (`refresh_module_contract`) and listener notifications

### Modules

- built-in workflow modules grouped by family
- module-local behavior only (no persistence I/O, no scheduler mutation internals)

### Services

- HTTP/provider/export side-effect implementations
- normalized service error taxonomy and result envelopes

### Persistence

- strict Pydantic schemas (`extra="forbid"`)
- deterministic JSON read/write (`sorted keys`, `indented`, atomic replace)
- current-contract-only version validation

### UI

- desktop shell, module palette, multi-canvas workspace
- bind inspection and strict candidate diagnostics before edge creation
- staged project load/apply flow with replay after binding installation

## Runtime Execution Flow

1. A module emits `emit(output_port, value)`.
2. Runtime validates source identity and output port.
3. Runtime resolves outbound bindings and enqueues deliveries with stable ordering keys.
4. Scheduler drains queue in deterministic order and calls `receive_binding(...)`.
5. Destination module coerces payload by declared `PortSpec.kind` and runs `on_input(...)`.

Ordering keys are deterministic and rank-aware:

1. destination topological rank
2. source emission sequence
3. binding insertion order
4. delivery serial

## Binding Safety Model

Before `add_binding(...)`, runtime computes candidate diagnostics:

- unknown source/destination module errors
- unknown source/destination port errors
- plane mismatch warning
- payload kind mismatch warning
- cycle-creation error (hard rejection)

Only candidates without `error` diagnostics are admitted.

## Runtime Policy Knobs

`RuntimePolicy` controls bounded scheduling behavior:

- `max_queue_size`: hard pending-delivery cap
- `coalesce_pending_inputs`: optional latest-value replacement per destination input
- `max_deliveries_per_batch`: deterministic delivery budget per drain

These settings are persisted and applied when projects are loaded.

Runtime precedence:

- project load uses the project's `RuntimePolicy` for active execution
- app settings runtime values remain default values for new/unspecified workspaces
- saving runtime settings from the Settings dialog updates both active runtime and app defaults

Runtime presets in Settings (`Runtime` tab):

- `Safe`: `max_queue_size=50_000`, `coalesce_pending_inputs=true`, `max_deliveries_per_batch=75_000`
- `Balanced` (default): `max_queue_size=100_000`, `coalesce_pending_inputs=true`, `max_deliveries_per_batch=250_000`
- `Fast`: `max_queue_size=500_000`, `coalesce_pending_inputs=true`, `max_deliveries_per_batch=1_000_000`

## Project Load/Apply Lifecycle

The UI applies projects through a staged process:

1. validate schema + semantic constraints (module ids, names, module types, binding endpoints)
2. build a staged runtime with project runtime policy
3. construct modules and restore persisted inputs (strict key match)
4. register modules so live contracts exist
5. apply bindings against live contracts
6. swap staged runtime/workspace into the active UI
7. replay module state in deterministic runtime order (`module_ids_in_order`)

If staging fails, staged modules/widgets are cleaned up and active workspace remains unchanged.

## Dynamic Port Rehydration

Dynamic modules (for example `Options`) must rebuild generated port keys from restored persisted inputs before binding replay.

When a module changes dynamic ports at runtime:

1. module updates descriptor
2. runtime `refresh_module_contract(module_id)` updates input/output indexes
3. bindings referencing removed ports are pruned
4. pending deliveries to removed ports are cleared
5. UI bind selectors refresh through contract-change listeners

## Async Service Architecture

Async modules share one model:

- task execution: `BackgroundTaskRunner` (single-flight worker thread)
- envelope normalization: `ServiceSuccess` / `ServiceFailure`
- result capture: `capture_service_result(...)`
- deterministic failure policy: `apply_async_error_policy(...)`

This enforces consistent `busy` semantics and stale-success output clearing.

Shutdown behavior is part of the contract:

- module `on_close()` is invoked for module removal, staged-load rollback, workspace reset, and window shutdown
- async provider/export modules use `on_close()` to stop accepting late completions and release worker-thread ownership
- autosnapshots are flushed on window shutdown before module teardown begins

## Persistence Boundary

Accepted payload identities:

- app settings: `AppConfig`
- project snapshots: `ProjectV1`

No compatibility fallback loader is used. Version mismatches are rejected explicitly.

## Design Priorities

- deterministic behavior under identical graph + input conditions
- strict contracts over implicit compatibility behavior
- explicit, testable failure lanes
- minimal cross-layer coupling
