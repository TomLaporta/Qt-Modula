# Trigger Button Module

## Purpose

`Trigger Button` is a built-in `Control` module in Qt Modula.

- Module type: `trigger_button`
- Family: `Control`
- Capabilities: `source, scheduler`

## Typical Use Cases

- Manual one-shot pulse generation for workflow control.
- Human-in-the-loop execution of fetch, evaluate, or export lanes.
- Ad hoc testing and debugging of trigger pathways.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `trigger` | `trigger` | `control` | no | Default: `0` |
| `label` | `string` | `data` | yes | Default: `"Trigger"` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `pulse` | `trigger` | `control` | Default: `0` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Trigger Button.pulse` -> `Trigger Mapper.trigger`
2. `Trigger Mapper.fetch` -> provider module trigger
3. `Trigger Mapper.run` -> research module trigger
