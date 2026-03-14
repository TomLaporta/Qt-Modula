# Retry Controller Module

## Purpose

`Retry Controller` provides deterministic retry orchestration for trigger-driven operations. It tracks active request state, emits attempt pulses, applies optional backoff, and publishes explicit exhausted/done signals.

- Module type: `retry_controller`
- Family: `Logic`
- Capabilities: `gate`, `transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `request` | `trigger` | `control` | no | Starts a retry run if idle. |
| `success` | `trigger` | `control` | no | Completes current run successfully. |
| `failure` | `trigger` | `control` | no | Advances retry logic for current run. |
| `max_attempts` | `integer` | `data` | yes | Minimum effective value is `1`. |
| `backoff_ms` | `integer` | `data` | yes | Delay before next attempt; clamped to `>= 0`. |
| `reset` | `trigger` | `control` | no | Stops timers and returns to idle baseline. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `attempt` | `trigger` | `control` | Pulses when a new attempt should be executed. |
| `attempt_index` | `integer` | `data` | Current 1-based attempt index; `0` when idle. |
| `active` | `boolean` | `control` | True while a retry run is in progress. |
| `exhausted` | `trigger` | `control` | Pulses when retries are fully consumed. |
| `done` | `trigger` | `control` | Pulses on terminal success or exhaustion. |
| `text` | `string` | `data` | Summary of current state and decision reason. |
| `error` | `string` | `data` | Config validation error (`""` when clear). |

## Retry State Machine

### Start

- `request` while idle sets `active=true`, `attempt_index=1`, and emits `attempt=1`.
- `request` while already active is ignored and logged in `text`.

### Success

- `success` while active stops any pending backoff timer.
- Emits `done=1`, clears `active`, keeps `attempt_index` at last attempt value.

### Failure

- If idle, failure is ignored.
- If `attempt_index >= max_attempts`, emits `exhausted=1` and `done=1`, then returns idle.
- Otherwise:
  - `backoff_ms == 0`: increments attempt immediately and emits `attempt=1`.
  - `backoff_ms > 0`: schedules timer; attempt pulse fires on timeout.

### Reset

- Stops timer, clears active state, resets `attempt_index=0`, clears `error`.

## Validation and Clamping

- `max_attempts < 1` is clamped to `1` with `error="max_attempts clamped to 1"`.
- `backoff_ms < 0` is clamped to `0` with `error="backoff_ms clamped to 0"`.

## Persistence

Persisted keys:

- `max_attempts`
- `backoff_ms`

Non-persisted runtime state:

- active flag
- current attempt index
- pending retry timer

## Recommended Bind Chains

### Provider with Feedback

1. `Retry Controller.attempt` -> `HTTP Request.fetch`
2. `HTTP Request.fetched` -> `Retry Controller.success`
3. `HTTP Request.error` (via gate/mapper) -> `Retry Controller.failure`

### Exhaustion Alerting

- `Retry Controller.exhausted` -> logging/notification sink.
- `Retry Controller.done` -> downstream cleanup or finalization branch.

## Operational Guidance

- Keep `max_attempts` modest in UI workflows to avoid long failure loops.
- Use `Circuit Breaker` upstream when failures are prolonged across many runs.
- `on_close()` stops backoff timer to prevent late pulses after unload.
