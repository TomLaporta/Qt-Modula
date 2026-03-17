# Text Import Module

## Purpose

`Text Import` stages or imports one local UTF-8 / UTF-8-SIG text file.

- Module type: `text_import`
- Family: `Import`
- Capabilities: `source`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `path` | `string` | `data` | yes | Absolute staged file path. |
| `auto_import` | `boolean` | `data` | yes | If true, path changes trigger an import immediately. |
| `import` | `trigger` | `control` | no | Starts one import using the staged path. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `content` | `string` | `data` | Imported text payload. |
| `char_count` | `integer` | `data` | Imported character count. |
| `line_count` | `integer` | `data` | Imported line count. |
| `path` | `string` | `data` | Path from the last successful import. |
| `imported` | `trigger` | `control` | Pulses on successful import. |
| `busy` | `boolean` | `control` | True while the async file read is running. |
| `text` | `string` | `data` | Status summary. |
| `error` | `string` | `data` | Import failure or selection error. |

## Behavior

- Browse, drag-and-drop, and manual path entry all stage the same `path` input.
- Manual path edits commit on `editingFinished`.
- Project restore rehydrates staged state but does not auto-read the file.
- Failures clear stale success outputs deterministically.
