# Runtime Contracts

This document defines canonical contracts between modules, runtime scheduling, and async service workflows.

## Module Identity Contract

`ModuleDescriptor` is the authoritative runtime identity and I/O contract.

```python
ModuleDescriptor(
  module_type: str,
  display_name: str,
  family: str,
  description: str,
  inputs: tuple[PortSpec, ...],
  outputs: tuple[PortSpec, ...],
  capabilities: tuple[CapabilityTag, ...] = (),
)
```

### Capability Tags

Supported tags:

- `source`
- `gate`
- `transform`
- `sink`
- `provider`
- `scheduler`

## Port Contract

`PortSpec` declares typed lane behavior and bind-surface metadata.

```python
PortSpec(
  key: str,
  kind: PayloadKind = "any",
  default: Any = None,
  required: bool = False,
  description: str = "",
  display_name: str = "",
  plane: "data" | "control" = "data",
  control_plane: bool = False,
  bind_visibility: "normal" | "advanced" | "hidden" = "normal",
  ui_group: "basic" | "advanced" = "basic",
)
```

Rule: if `control_plane=True`, effective `plane` is forced to `control`.

### Payload Kinds

- `any`
- `number`
- `integer`
- `string`
- `boolean`
- `json`
- `table`
- `pulse`
- `trigger`

### Coercion Semantics

`BaseModule.receive_binding(...)` applies strict coercion before `on_input(...)`:

- `trigger` / `pulse`: normalized to `0` or `1`
- `boolean`: deterministic truthy parsing (`"1"`, `"true"`, `"yes"`, `"on"` are true)
- `number`: finite float required
- `integer`: finite float required, then rounded to nearest integer
- `string`: `None` maps to `""`, otherwise `str(value)`
- `json`: accepts `dict/list`; string payload must parse to object/list; empty string -> `{}`
- `table`: accepts list; string payload must parse to list; empty string -> `[]`

Invalid values are rejected and published as module errors.

## Runtime Interaction Contract

Modules interact with runtime only through `ExecutionContext`:

```python
emit(module_id: str, port: str, value: Any) -> EmitResult
list_bindings() -> list[BindingEdge]
refresh_module_contract(module_id: str) -> None
notify_persistent_input_changed(module_id: str, key: str, value: Any) -> None
```

`EmitResult` fields:

- `ok: bool`
- `delivered_events: int`
- `dropped_events: int`
- `error: RuntimeFailure | None`

## Binding Contract

`BindingEdge` is one directed edge:

- `src_module_id`
- `src_port`
- `dst_module_id`
- `dst_port`
- `order`

Candidate diagnostics (`diagnostics_for_edge`) return deterministic records:

- `level`: `error` | `warning` | `info`
- `message`: stable human-readable text

`warning` diagnostics (plane/kind mismatch) do not block binding creation. `error` diagnostics do.

## Scheduling Contract

Runtime enqueues deliveries with deterministic ordering by:

1. destination rank
2. source emission sequence
3. edge order
4. delivery serial

Queue behavior:

- coalescing replaces pending deliveries per destination input key
- overflow raises `queue_overflow`
- delivery budget overflow raises `cycle_detected` (`probable cycle or runaway pulse`)

Last drain telemetry is exposed as `RuntimeBatch`.

## Dynamic Contract Extension

`RuntimeEngine` supports runtime contract synchronization:

- `refresh_module_contract(module_id)`
  - re-indexes current input/output specs
  - removes bindings targeting removed ports
  - removes pending deliveries for removed destination inputs
- `add_module_contract_listener(...)` / `remove_module_contract_listener(...)`
  - allows UI to refresh bind selectors after module contract changes

## Runtime Failure Contract

`RuntimeFailure` payload:

- `code: RuntimeErrorCode`
- `message: str`
- `details: dict[str, Any]`

`RuntimeErrorCode` values:

- `unknown_module`
- `unknown_port`
- `invalid_binding`
- `cycle_detected`
- `queue_overflow`
- `module_failure`
- `internal_error`

`RuntimeFailureInfo` wraps `RuntimeFailure` for exception surfaces.

## Module Lifecycle Contract

Modules implement `ModuleLifecycle` (typically via `BaseModule`):

- `attach_execution_context(context)`
- `widget()`
- `receive_binding(port, value)`
- `snapshot_inputs()`
- `restore_inputs(inputs)`
- `replay_state()`
- `on_close()`

`BaseModule` provides:

- descriptor-based port indexing
- typed input/output storage
- strict snapshot/restore key matching for `persistent_inputs`
- normalized emit behavior with runtime failure propagation

Runtime/UI lifecycle rule:

- `on_close()` must be safe to call exactly once during module removal, project replacement, workspace reset, or app shutdown

## Async Service Contract

Async modules standardize on result envelopes:

- `ServiceSuccess[T](value)`
- `ServiceFailure(message, kind, provider, retryable, details)`

`capture_service_result(...)` converts exceptions into deterministic envelopes.

`apply_async_error_policy(...)` enforces:

- stale-success output clearing
- deterministic `error`/`text` publication
- optional UI status sink synchronization

## Contract Change Checklist

When changing contracts:

1. update descriptor/spec source of truth in code
2. update runtime/persistence/module tests for invariant impact
3. update `RUNTIME_CONTRACTS`, `SCHEMA_REFERENCE`, and module docs
4. preserve deterministic behavior under replay
