# Log Notes Module

## Purpose

`Log Notes` is a built-in `Control` module in Qt Modula.

- Module type: `log_notes`
- Family: `Control`
- Capabilities: `sink`

## Typical Use Cases

- Centralize status/error lanes from multiple modules for operator audit.
- Accumulate timeline notes during research and incident workflows.
- Expose a bindable textual log sink for dashboards.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `append` | `string` | `data` | no | Default: `""` |
| `text` | `string` | `data` | no | Default: `""` |
| `clear` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `text` | `string` | `data` | Default: `""` |
| `line_count` | `integer` | `data` | Default: `0` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `HTTP Request.error` -> `Log Notes.append`
2. `Table Export.text` -> `Log Notes.append`
3. `Log Notes.text` -> `Text Export.text` (optional archive lane)
