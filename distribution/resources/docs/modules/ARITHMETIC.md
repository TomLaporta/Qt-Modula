# Arithmetic Module

## Purpose

`Arithmetic` is a built-in `Math` module in Qt Modula.

- Module type: `arithmetic`
- Family: `Math`
- Capabilities: `transform`

## Typical Use Cases

- Fast scalar arithmetic for runtime parameter tuning and derived values.
- Lightweight computation blocks before gates, selectors, or exports.
- Operator-checking in workflows where formulas are unnecessary.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `a` | `number` | `data` | yes | Default: `0.0` |
| `b` | `number` | `data` | yes | Default: `0.0` |
| `op` | `string` | `data` | yes | Default: `"add"` |
| `auto` | `boolean` | `data` | yes | Default: `true` |
| `evaluate` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `result` | `number` | `data` | Default: `0.0` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |
| `evaluated` | `trigger` | `control` | Default: `0` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Number Input.value` -> `Arithmetic.a`
2. `Number Input.value` (second input) -> `Arithmetic.b`
3. `Arithmetic.result` -> `Value View.value`
