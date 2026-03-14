# Condition Gate Module

## Purpose

`Condition Gate` is a built-in `Logic` module in Qt Modula.

- Module type: `condition_gate`
- Family: `Logic`
- Capabilities: `gate, transform`

## Typical Use Cases

- Branch payloads into pass/block lanes from numeric or truthy comparisons.
- Guard expensive downstream requests behind explicit predicates.
- Emit deterministic control triggers for true/false branches.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `a` | `any` | `data` | no | Default: `null` |
| `b` | `any` | `data` | yes | Default: `0.0` |
| `value` | `any` | `data` | no | Default: `null` |
| `operator` | `string` | `data` | yes | Default: `"truthy"` |
| `auto` | `boolean` | `data` | yes | Default: `true` |
| `evaluate` | `trigger` | `control` | no | Default: `0` |
| `epsilon` | `number` | `data` | yes | Default: `1e-09` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `matched` | `boolean` | `data` | Default: `false` |
| `on_true` | `trigger` | `control` | Default: `0` |
| `on_false` | `trigger` | `control` | Default: `0` |
| `passed` | `any` | `data` | Default: `null` |
| `blocked` | `any` | `data` | Default: `null` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.
- Invalid `operator` values are normalized to `truthy` with deterministic warning text on `error`.

## Example Bind Chain

1. `Number Input.value` -> `Condition Gate.a`
2. `Condition Gate.on_true` -> downstream `fetch`/`run` trigger
3. `Condition Gate.blocked` -> `Log Notes.append`
