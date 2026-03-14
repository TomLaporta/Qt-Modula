# Trigger Mapper Module

## Purpose

`Trigger Mapper` is a built-in `Control` module in Qt Modula.

- Module type: `trigger_mapper`
- Family: `Control`
- Capabilities: `transform, scheduler`

## Typical Use Cases

- Convert generic trigger pulses into explicit action channels.
- Standardize trigger routing for fetch/run/evaluate semantics.
- Simplify workflow readability by naming trigger intent.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `trigger` | `trigger` | `control` | no | Default: `0` |
| `channel` | `string` | `data` | yes | Default: `"evaluate"` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `pulse` | `trigger` | `control` | Default: `0` |
| `evaluate` | `trigger` | `control` | Default: `0` |
| `refresh` | `trigger` | `control` | Default: `0` |
| `fetch` | `trigger` | `control` | Default: `0` |
| `run` | `trigger` | `control` | Default: `0` |
| `flush` | `trigger` | `control` | Default: `0` |
| `emit` | `trigger` | `control` | Default: `0` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.
- Invalid `channel` values are normalized to `evaluate` and surfaced on `error`.

## Example Bind Chain

1. `Trigger Button.pulse` -> `Trigger Mapper.trigger`
2. `Trigger Mapper.evaluate` -> calculator evaluate lane
3. `Trigger Mapper.fetch` -> provider fetch lane
