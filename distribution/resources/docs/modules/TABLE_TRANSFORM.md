# Table Transform Module

## Purpose

`Table Transform` applies deterministic table operations (filter, sort, project, and limit) in one module.

- Module type: `table_transform`
- Family: `Transform`
- Capabilities: `transform`

## Typical Use Cases

- Filter provider tables before export.
- Project a stable output schema for downstream modules.
- Apply deterministic sorting and limit windows for reporting workflows.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `rows` | `table` | `data` | no | Source rows (non-object rows normalize to `{ "value": ... }`). |
| `filter_key` | `string` | `data` | yes | Optional equality filter key. |
| `filter_value` | `any` | `data` | yes | Equality filter value (`row[filter_key] == filter_value`). |
| `sort_key` | `string` | `data` | yes | Optional sort key. |
| `descending` | `boolean` | `data` | yes | Sort direction toggle. |
| `limit` | `integer` | `data` | yes | Max output rows (`0` means no cap; negative clamps to `0`). |
| `columns` | `json` | `data` | yes | Optional projection list of output columns. |
| `auto` | `boolean` | `data` | yes | Transform on updates when true. |
| `emit` | `trigger` | `control` | no | Manual transform trigger. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `rows` | `table` | `data` | Transformed rows. |
| `row_count` | `integer` | `data` | Number of output rows. |
| `transformed` | `trigger` | `control` | Pulses on transform execution. |
| `text` | `string` | `data` | Deterministic transform summary. |
| `error` | `string` | `data` | Input-normalization warnings (`""` when clean). |

## Transform Order

Operations are applied in this order:

1. normalize row payloads
2. equality filter (`filter_key`/`filter_value`)
3. sort (`sort_key`, `descending`)
4. project columns (`columns`)
5. limit (`limit`)

## Persistence

Persisted keys:

- `filter_key`
- `filter_value`
- `sort_key`
- `descending`
- `limit`
- `columns`
- `auto`

Non-persisted runtime state:

- source rows
- transient outputs/status

## Example Bind Chain

1. `Table Buffer.rows` -> `Table Transform.rows`
2. configure `filter_key=symbol`, `filter_value=AAPL`, `columns=["timestamp","close"]`
3. `Table Transform.rows` -> `Table Export.rows`
4. trigger `Table Export.write`
