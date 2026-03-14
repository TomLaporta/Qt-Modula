# Value Wrapper Module

## Purpose

`Value Wrapper` replaces key text inside an entry template using the current `value` payload.

- Module type: `value_wrapper`
- Family: `Transform`
- Capabilities: `transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `value` | `any` | `data` | no | Replacement payload converted with `str(value)`. |
| `key` | `string` | `data` | yes | Case-sensitive token to replace in `entry`. |
| `entry` | `string` | `data` | yes | Source template text. |
| `auto` | `boolean` | `data` | yes | Evaluate automatically on relevant input changes. |
| `emit` | `trigger` | `control` | no | Manual evaluate trigger when `auto=false`. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `value` | `string` | `data` | Wrapped output text after replacement. |
| `text` | `string` | `data` | Deterministic evaluation summary. |
| `error` | `string` | `data` | Warning text (`""` on healthy state). |

## Replacement Rules

- Replacement mode is raw case-sensitive text replacement: `entry.replace(key, str(value))`.
- All occurrences are replaced.
- Example: `value="value"`, `key="example"`, `entry="{example}"` -> `"{value}"`.
- Empty `key`: output passes through unchanged and warning is emitted.
- Missing `key` in `entry`: output passes through unchanged and warning is emitted.

## Auto and Manual Execution

- `auto=true`: recompute on `value`, `key`, `entry`, and `auto` updates.
- `auto=false`: cache input changes and keep previous outputs until `emit`.
- `replay_state()` always recomputes from current inputs.

## Persistence

Persisted keys:

- `key`
- `entry`
- `auto`

Non-persisted runtime fields:

- current `value` payload
- status text and warning state
