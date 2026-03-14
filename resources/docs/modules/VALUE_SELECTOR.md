# Value Selector Module

## Purpose

`Value Selector` is a built-in `Logic` module in Qt Modula.

- Module type: `value_selector`
- Family: `Logic`
- Capabilities: `gate, transform`

## Typical Use Cases

- Select primary/fallback payloads using explicit mode control.
- Route alternative value lanes in robust failover workflows.
- Implement deterministic data precedence in bind chains.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `a` | `any` | `data` | no | Default: `null` |
| `b` | `any` | `data` | no | Default: `null` |
| `selector` | `integer` | `data` | yes | Default: `0` |
| `auto` | `boolean` | `data` | yes | Default: `true` |
| `emit` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `value` | `any` | `data` | Default: `null` |
| `selected` | `integer` | `data` | Default: `0` |
| `changed` | `trigger` | `control` | Default: `0` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. primary source -> `Value Selector.a`
2. fallback source -> `Value Selector.b`
3. `Value Selector.value` -> downstream consumer
