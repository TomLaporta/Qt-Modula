# Circuit Breaker Module

## Purpose

`Circuit Breaker` protects trigger-driven request lanes from repeated failures. It blocks requests during open-state cooldowns and allows controlled half-open probing before returning to normal flow.

- Module type: `circuit_breaker`
- Family: `Logic`
- Capabilities: `gate`, `transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `request` | `trigger` | `control` | no | Candidate operation request to gate. |
| `success` | `trigger` | `control` | no | Positive feedback from guarded operation. |
| `failure` | `trigger` | `control` | no | Negative feedback from guarded operation. |
| `failure_threshold` | `integer` | `data` | yes | Consecutive failures required to open. |
| `cooldown_ms` | `integer` | `data` | yes | Open-state hold time before half-open. |
| `half_open_budget` | `integer` | `data` | yes | Allowed requests during half-open. |
| `reset` | `trigger` | `control` | no | Forces transition back to closed state. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `allow` | `trigger` | `control` | Pulses when a request is permitted. |
| `blocked` | `trigger` | `control` | Pulses when a request is denied. |
| `state` | `string` | `data` | One of `closed`, `open`, `half_open`. |
| `failure_count` | `integer` | `data` | Closed-state failure counter. |
| `text` | `string` | `data` | Current state summary and transition reason. |
| `error` | `string` | `data` | Config validation error (`""` when clear). |

## State Model

### Closed

- `request` emits `allow=1`.
- `failure` increments `failure_count`.
- When `failure_count >= failure_threshold`, transitions to `open`.

### Open

- `request` emits `blocked=1`.
- `success` is ignored for reopening logic.
- Cooldown timer runs for `cooldown_ms`.
- If `cooldown_ms == 0`, transitions immediately to `half_open`.

### Half-Open

- Allows up to `half_open_budget` request pulses.
- Exceeding budget emits `blocked=1`.
- `success` transitions to `closed` and resets counters.
- `failure` transitions back to `open`.

## Validation and Clamping

- `failure_threshold < 1` -> clamped to `1`.
- `cooldown_ms < 0` -> clamped to `0`.
- `half_open_budget < 1` -> clamped to `1`.

Each clamp updates `error` with a deterministic message.

## Persistence

Persisted keys:

- `failure_threshold`
- `cooldown_ms`
- `half_open_budget`

Non-persisted runtime state:

- current breaker state
- cooldown timer status
- half-open remaining budget

## Recommended Bind Chains

### Resilient Provider Lane

1. `Trigger source` -> `Circuit Breaker.request`
2. `Circuit Breaker.allow` -> provider `fetch`
3. provider success -> `Circuit Breaker.success`
4. provider failure -> `Circuit Breaker.failure`

### Combined with Retry

- Use `Retry Controller` inside allowed windows.
- Feed terminal retry failure into `Circuit Breaker.failure`.
- Feed successful fetch completion into `Circuit Breaker.success`.

## Operational Guidance

- Keep `failure_threshold` and `half_open_budget` small for fast recovery feedback.
- Choose `cooldown_ms` based on provider rate limits and downstream pressure.
- `on_close()` stops cooldown timer to prevent post-unload transitions.
