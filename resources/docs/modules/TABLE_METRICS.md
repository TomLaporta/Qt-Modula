# Table Metrics Module

## Purpose

`Table Metrics` is a built-in `Analytics` module in Qt Modula.

- Module type: `table_metrics`
- Family: `Analytics`
- Capabilities: `transform`

## Typical Use Cases

- Inspect tabular payload health (row/column/shape metrics).
- Validate upstream schema consistency before export.
- Attach lightweight QA checks to ingestion pipelines.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `rows` | `table` | `data` | no | Default: `[]` |
| `emit` | `trigger` | `control` | no | Default: `1` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `row_count` | `integer` | `data` | Default: `0` |
| `column_count` | `integer` | `data` | Default: `0` |
| `columns` | `json` | `data` | Default: `[]` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Table Buffer.rows` -> `Table Metrics.rows`
2. `Table Metrics.text` -> `Log Notes.append`
3. `Table Metrics.row_count` -> downstream gate/threshold lane
