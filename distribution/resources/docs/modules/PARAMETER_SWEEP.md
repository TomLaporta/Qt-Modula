# Parameter Sweep Module

## Purpose

`Parameter Sweep` is a built-in `Research` module in Qt Modula.

- Module type: `parameter_sweep`
- Family: `Research`
- Capabilities: `transform, source`

## Typical Use Cases

- Run deterministic parameter ranges for scientific or financial studies.
- Produce reproducible result tables for analytics and export.
- Benchmark formula behavior over bounded domains.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `start` | `number` | `data` | yes | Default: `0.0` |
| `stop` | `number` | `data` | yes | Default: `10.0` |
| `step` | `number` | `data` | yes | Default: `1.0` |
| `variable` | `string` | `data` | yes | Default: `"x"` |
| `formula` | `string` | `data` | yes | Default: `"x"` |
| `run` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `rows` | `table` | `data` | Default: `[]` |
| `count` | `integer` | `data` | Default: `0` |
| `text` | `string` | `data` | Default: `""` |
| `done` | `trigger` | `control` | Default: `0` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Trigger Mapper.run` -> `Parameter Sweep.run`
2. `Parameter Sweep.rows` -> `Line Plotter.rows`
3. `Parameter Sweep.rows` -> `Table Export.rows`
