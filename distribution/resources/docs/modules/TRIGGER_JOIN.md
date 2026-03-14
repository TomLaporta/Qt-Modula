# Trigger Join Module

## Purpose

`Trigger Join` is a built-in `Logic` module in Qt Modula.

- Module type: `trigger_join`
- Family: `Logic`
- Capabilities: `gate, transform`

## Typical Use Cases

- Synchronize two trigger sources before downstream execution.
- Create deterministic barrier semantics for multi-signal workflows.
- Enforce left/right readiness before expensive operations.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `left` | `trigger` | `control` | no | Default: `0` |
| `right` | `trigger` | `control` | no | Default: `0` |
| `auto_reset` | `boolean` | `data` | yes | Default: `true` |
| `clear` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `joined` | `trigger` | `control` | Default: `0` |
| `left_seen` | `boolean` | `data` | Default: `false` |
| `right_seen` | `boolean` | `data` | Default: `false` |
| `count` | `integer` | `data` | Default: `0` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Trigger Mapper.fetch` -> `Trigger Join.left`
2. secondary readiness signal -> `Trigger Join.right`
3. `Trigger Join.joined` -> downstream `write`/`run` trigger
