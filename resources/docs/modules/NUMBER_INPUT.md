# Number Input Module

## Purpose

`Number Input` is a built-in `Control` module in Qt Modula.

- Module type: `number_input`
- Family: `Control`
- Capabilities: `source, scheduler`

## Typical Use Cases

- Manual numeric parameter entry for formulas and gates.
- Operator-controlled threshold updates in live sessions.
- Inject finite numbers into deterministic compute chains.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `value` | `number` | `data` | yes | Default: `0.0` |
| `min` | `number` | `data` | yes | Default: `-1000000.0` |
| `max` | `number` | `data` | yes | Default: `1000000.0` |
| `emit` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `value` | `number` | `data` | Default: `0.0` |
| `text` | `string` | `data` | Default: `""` |
| `changed` | `trigger` | `control` | Default: `0` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Number Input.value` -> `Arithmetic.a`
2. `Number Input.changed` -> `Arithmetic.evaluate`
3. `Arithmetic.result` -> `Value View.value`
