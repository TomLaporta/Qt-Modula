# Value Latch Module

## Purpose

`Value Latch` is a built-in `Logic` module in Qt Modula.

- Module type: `value_latch`
- Family: `Logic`
- Capabilities: `gate, transform`

## Typical Use Cases

- Hold transient values until explicit release control.
- Decouple noisy inputs from downstream compute cadence.
- Switch between transparent and latched flow during operations.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `value` | `any` | `data` | no | Default: `null` |
| `release` | `trigger` | `control` | no | Default: `0` |
| `transparent` | `boolean` | `data` | yes | Default: `true` |
| `clear` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `value` | `any` | `data` | Default: `null` |
| `held` | `any` | `data` | Default: `null` |
| `released` | `trigger` | `control` | Default: `0` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.
- `release` with no held value emits `error=\"release ignored (no held value)\"` for deterministic diagnostics.

## Example Bind Chain

1. source payload -> `Value Latch.value`
2. release trigger -> `Value Latch.release`
3. `Value Latch.value` -> expensive downstream compute/export lane
