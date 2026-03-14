# Value Change Gate Module

## Purpose

`Value Change Gate` suppresses unchanged values and emits control signals only when a value changes materially. It is useful for reducing redundant downstream work in high-frequency lanes.

- Module type: `value_change_gate`
- Family: `Logic`
- Capabilities: `gate`, `transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `value` | `any` | `data` | no | Candidate input value to compare. |
| `epsilon` | `number` | `data` | yes | Numeric tolerance for number-to-number comparisons. |
| `emit_initial` | `boolean` | `data` | yes | Controls whether first observed value emits `changed`. |
| `auto` | `boolean` | `data` | yes | If true, evaluate automatically on `value` updates. |
| `emit` | `trigger` | `control` | no | Manual evaluation trigger when `auto=false`. |
| `clear` | `trigger` | `control` | no | Resets baseline, candidate, and counters. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `value` | `any` | `data` | Last emitted changed value. |
| `changed` | `trigger` | `control` | Pulses when change criteria are satisfied. |
| `unchanged` | `trigger` | `control` | Pulses when no effective change is detected. |
| `change_count` | `integer` | `data` | Total number of emitted changes since clear/start. |
| `text` | `string` | `data` | Evaluation state summary and reason. |
| `error` | `string` | `data` | Validation warning lane (`""` on clean state). |

## Comparison Semantics

### Numeric Values

If both baseline and candidate coerce to finite numbers, change is:

`abs(current - previous) > epsilon`

### Non-Numeric Values

Uses direct inequality (`previous != current`).

## Evaluation Flow

- `value` input caches a deep-copied candidate.
- If `auto=true`, evaluation runs immediately.
- If `auto=false`, evaluation runs on truthy `emit`.

Baseline behavior:

- First candidate establishes baseline.
- If `emit_initial=true`, first candidate also emits `changed` and `value`.
- If `emit_initial=false`, first candidate is stored but treated as `unchanged`.

## Reset Behavior

`clear` performs a full runtime reset:

- clears candidate and baseline
- resets `change_count` to `0`
- emits `value=None`
- emits status with reason `cleared`

## Persistence

Persisted keys:

- `epsilon`
- `emit_initial`
- `auto`

Non-persisted runtime state:

- candidate and baseline payloads
- `change_count`

## Recommended Bind Chains

### High-Frequency Provider Dampening

1. provider value output -> `Value Change Gate.value`
2. `Value Change Gate.changed` -> expensive transforms/exports
3. `Value Change Gate.value` -> payload input of downstream stage

### Manual Sampling

- Set `auto=false`.
- Feed source updates into `value`.
- Use separate scheduler pulses into `emit` for sampled evaluation.

## Operational Guidance

- Keep `epsilon` domain-appropriate; too small can create noise, too large can hide real drift.
- Non-finite `epsilon` values are normalized to `0` and surfaced on `error`.
- Use upstream type-normalization if mixed payload types are expected.
- Deep-copy behavior protects against mutable-object aliasing between modules.
