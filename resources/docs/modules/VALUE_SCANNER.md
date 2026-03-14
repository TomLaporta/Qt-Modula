# Value Scanner Module

## Purpose

`Value Scanner` checks whether a text `entry` is present in the current `value` payload after string conversion.

- Module type: `value_scanner`
- Family: `Transform`
- Capabilities: `transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `value` | `any` | `data` | no | Candidate payload converted with `str(value)` during evaluation. |
| `entry` | `string` | `data` | yes | Case-sensitive substring to scan for. |
| `auto` | `boolean` | `data` | yes | Evaluate automatically on relevant input changes. |
| `emit` | `trigger` | `control` | no | Manual evaluate trigger when `auto=false`. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `in_value` | `boolean` | `data` | `true` when `entry` is present in `str(value)`. |
| `text` | `string` | `data` | Deterministic evaluation summary. |
| `error` | `string` | `data` | Warning text (`""` on healthy state). |

## Evaluation Rules

- Match mode is case-sensitive substring search: `entry in str(value)`.
- Empty `entry` always yields `in_value=false` and warning: `entry must be non-empty`.
- Warnings do not block output publication.

## Auto and Manual Execution

- `auto=true`: recompute on `value`, `entry`, and `auto` updates.
- `auto=false`: cache input changes and keep previous outputs until `emit`.
- `replay_state()` always recomputes from current inputs.

## Persistence

Persisted keys:

- `entry`
- `auto`

Non-persisted runtime fields:

- current `value` payload
- status text and warning state
