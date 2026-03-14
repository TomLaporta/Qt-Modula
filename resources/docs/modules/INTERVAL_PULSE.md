# Interval Pulse Module

## Purpose

`Interval Pulse` is a deterministic scheduler module that emits control-plane pulses at a configured cadence. It is typically used as a reusable time base for fetch, evaluate, export, or maintenance bind chains.

- Module type: `interval_pulse`
- Family: `Control`
- Capabilities: `source`, `scheduler`

## Typical Use Cases

- Polling providers at fixed intervals.
- Periodic recompute triggers for analytics modules.
- Time-based append/export workflows.
- Synthetic load generation for coalescing and queue-policy testing.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `enabled` | `boolean` | `data` | yes | Starts/stops the repeating timer when toggled. |
| `interval_ms` | `integer` | `data` | yes | Timer period in milliseconds; clamped to `>= 1`. |
| `fire_immediately` | `boolean` | `data` | yes | If true, emits one pulse immediately when started. |
| `start` | `trigger` | `control` | no | One-shot start command; also forces `enabled=true`. |
| `stop` | `trigger` | `control` | no | One-shot stop command; also forces `enabled=false`. |
| `pulse` | `trigger` | `control` | no | Manual one-shot pulse independent of timer cadence. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `pulse` | `trigger` | `control` | Emitted for interval ticks and manual pulses. |
| `running` | `boolean` | `control` | Reflects whether the internal timer is active. |
| `tick_count` | `integer` | `data` | Monotonic count of emitted pulses since module creation. |
| `text` | `string` | `data` | Operational summary including reason and interval. |
| `error` | `string` | `data` | Validation/status error (`""` on normal operation). |

## Runtime Semantics

### Start/Stop Behavior

- `enabled=true` starts the timer using `interval_ms`.
- `start` behaves as an explicit start command and sets `enabled=true`.
- `stop` always halts the timer and sets `enabled=false`.

### Immediate Fire

When `fire_immediately=true`, starting the timer emits one pulse before regular cadence continues.

### Manual Pulse

A truthy `pulse` input emits one pulse and increments `tick_count` without requiring the timer to run.

### Interval Validation

`interval_ms < 1` is clamped to `1` and surfaces `error="interval_ms clamped to 1"`.

## State and Persistence

Persisted keys:

- `enabled`
- `interval_ms`
- `fire_immediately`

Non-persisted runtime state:

- timer active flag (reconstructed from `enabled` at widget init)
- `tick_count`
- transient status/error text

## Bind-Chain Patterns

### Provider Polling Loop

1. `Interval Pulse.pulse` -> `HTTP Request.fetch`
2. `HTTP Request.fetched` -> downstream transform/export

### Controlled Periodic Recompute

1. `Interval Pulse.pulse` -> `Trigger Mapper.trigger`
2. `Trigger Mapper.evaluate` -> `Formula Calculator.evaluate`

### Manual + Scheduled Hybrid

- Keep timer running for baseline cadence.
- Inject ad hoc pulses with manual `pulse` for on-demand refresh.

## Operational Notes

- `running` is emitted on every state publication for reliable UI/chain observability.
- `on_close()` stops the timer to avoid background emissions after module unload.
- High-frequency settings should be paired with runtime queue/coalescing policy controls.
