# Trigger Delay Module

## Purpose

`Trigger Delay` schedules one trigger pulse after a configurable delay and supports cancel/clear control.

- Module type: `trigger_delay`
- Family: `Control`
- Capabilities: `transform`, `scheduler`

## Typical Use Cases

- Delay write/export operations after user input settles.
- Build deterministic cooldown flows before expensive operations.
- Add explicit defer timing to control lanes.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `trigger` | `trigger` | `control` | no | Schedules a delayed pulse. |
| `delay_ms` | `integer` | `data` | yes | Delay duration (`>= 0`). |
| `restart_on_trigger` | `boolean` | `data` | yes | If true, a trigger during pending delay restarts the timer. |
| `cancel` | `trigger` | `control` | no | Cancels active pending delay. |
| `clear` | `trigger` | `control` | no | Clears pending state and counters. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `pulse` | `trigger` | `control` | Delayed pulse output. |
| `pending` | `boolean` | `data` | True while waiting for timeout. |
| `delayed_count` | `integer` | `data` | Total emitted delayed pulses since clear/start. |
| `canceled_count` | `integer` | `data` | Total canceled pending delays since clear/start. |
| `text` | `string` | `data` | Deterministic status summary. |
| `error` | `string` | `data` | Validation warning (`""` when clear). |

## Runtime Notes

- `delay_ms=0` emits immediately.
- `restart_on_trigger=false` ignores triggers while a delay is already pending.
- `cancel` on idle is a no-op with status-only update.

## Persistence

Persisted keys:

- `delay_ms`
- `restart_on_trigger`

Non-persisted runtime state:

- pending timer
- pulse/cancel counters

## Example Bind Chain

1. `Trigger Button.pulse` -> `Trigger Delay.trigger`
2. `Trigger Delay.pulse` -> `Table Export.write`
3. `Trigger Delay.canceled_count` -> `Value View.value`
