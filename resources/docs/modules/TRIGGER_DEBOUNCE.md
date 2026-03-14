# Trigger Debounce Module

## Purpose

`Trigger Debounce` suppresses bursty trigger inputs and emits deterministic leading/trailing pulses inside a bounded time window.

- Module type: `trigger_debounce`
- Family: `Control`
- Capabilities: `transform`, `scheduler`

## Typical Use Cases

- Prevent duplicate `write`/`fetch` operations when operators click rapidly.
- Collapse noisy trigger bursts into one trailing pulse.
- Allow immediate leading execution while still suppressing repeated bursts.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `trigger` | `trigger` | `control` | no | Candidate pulse to debounce. |
| `window_ms` | `integer` | `data` | yes | Debounce window; clamped to minimum `1`. |
| `leading` | `boolean` | `data` | yes | Emit immediately on first pulse in a window. |
| `trailing` | `boolean` | `data` | yes | Emit at window end when pending pulses exist. |
| `flush` | `trigger` | `control` | no | Immediately emits pending trailing pulse (if any). |
| `clear` | `trigger` | `control` | no | Resets counters and pending state. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `pulse` | `trigger` | `control` | Debounced trigger output. |
| `dropped_count` | `integer` | `data` | Number of suppressed pulses since clear/start. |
| `pending` | `boolean` | `data` | True when a trailing pulse is queued. |
| `text` | `string` | `data` | Deterministic state summary and reason. |
| `error` | `string` | `data` | Config warnings (`""` when clean). |

## Runtime Semantics

- First pulse in an idle window starts the timer.
- If `leading=true`, that first pulse emits immediately.
- Additional pulses inside the active window are suppressed and increment `dropped_count`.
- If `trailing=true`, suppressed pulses queue one trailing emit at timeout.
- If both `leading` and `trailing` are set false, module enforces `trailing=true` with warning.

## Persistence

Persisted keys:

- `window_ms`
- `leading`
- `trailing`

Non-persisted runtime state:

- active timer window
- pending trailing pulse
- `dropped_count`

## Example Bind Chain

1. noisy trigger source -> `Trigger Debounce.trigger`
2. `Trigger Debounce.pulse` -> `Table Export.write`
3. `Trigger Debounce.dropped_count` -> `Value View.value`
