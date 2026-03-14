# Trigger Rate Limit Module

## Purpose

`Trigger Rate Limit` enforces a fixed-window trigger budget (`max_events` per `window_ms`).

- Module type: `trigger_rate_limit`
- Family: `Control`
- Capabilities: `gate`, `transform`

## Typical Use Cases

- Protect providers/exports from trigger floods.
- Cap high-frequency scheduler lanes.
- Emit explicit blocked signals for observability.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `trigger` | `trigger` | `control` | no | Candidate trigger to evaluate. |
| `max_events` | `integer` | `data` | yes | Allowed events per window (`>= 1`). |
| `window_ms` | `integer` | `data` | yes | Fixed window size in milliseconds (`>= 1`). |
| `reset` | `trigger` | `control` | no | Clears window and counters. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `pulse` | `trigger` | `control` | Pulses when trigger is allowed. |
| `blocked` | `trigger` | `control` | Pulses when trigger is denied. |
| `window_count` | `integer` | `data` | Number of allowed events in the current window. |
| `allowed_count` | `integer` | `data` | Cumulative allowed events since reset/start. |
| `blocked_count` | `integer` | `data` | Cumulative blocked events since reset/start. |
| `text` | `string` | `data` | Deterministic state summary. |
| `error` | `string` | `data` | Validation warning (`""` when clear). |

## Runtime Notes

- Window is anchored to the first trigger in each window period.
- Once `window_count == max_events`, further triggers are blocked until window rollover.
- `reset` clears both current-window and cumulative counters.

## Persistence

Persisted keys:

- `max_events`
- `window_ms`

Non-persisted runtime state:

- active window start time
- window and cumulative counters

## Example Bind Chain

1. scheduler pulse -> `Trigger Rate Limit.trigger`
2. `Trigger Rate Limit.pulse` -> provider `fetch`
3. `Trigger Rate Limit.blocked` -> `Log Notes.append`
