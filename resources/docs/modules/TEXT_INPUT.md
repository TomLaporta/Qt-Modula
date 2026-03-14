# Text Input Module

## Purpose

`Text Input` is a built-in `Control` module in Qt Modula.

- Module type: `text_input`
- Family: `Control`
- Capabilities: `source, scheduler`

## Typical Use Cases

- Operator-entered textual payload source for dynamic workflows.
- Manual variable or note injection into transform/export modules.
- Editable control-plane emit lane for reproducible triggers.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `text` | `string` | `data` | yes | Default: `""` |
| `append` | `string` | `data` | no | Default: `""` |
| `emit` | `trigger` | `control` | no | Default: `0` |
| `clear` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `text` | `string` | `data` | Default: `""` |
| `changed` | `trigger` | `control` | Default: `0` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Editor height starts at one visible line and grows with wrapped content up to ten lines.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Text Input.text` -> `Text Export.text`
2. `Text Input.changed` -> `Text Export.write`
3. `Text Export.error` -> `Log Notes.append`
