# Value View Module

## Purpose

`Value View` is a built-in `Control` module in Qt Modula.

- Module type: `value_view`
- Family: `Control`
- Capabilities: `sink`

## Typical Use Cases

- Inspect payloads at critical workflow points.
- Expose bindable readout sinks for debugging and audits.
- Mirror transformed values without side effects.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `value` | `any` | `data` | no | Default: `null` |
| `text` | `string` | `data` | no | Default: `""` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `value` | `any` | `data` | Default: `null` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. any upstream payload -> `Value View.value`
2. `Value View.text` -> `Log Notes.append` (optional trace)
3. use multiple viewers to audit branch outputs side-by-side
