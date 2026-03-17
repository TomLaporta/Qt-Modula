# JSON Import Module

## Purpose

`JSON Import` stages or imports one local `.json` file and emits its top-level payload.

- Module type: `json_import`
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
| `json` | `json` | `data` | Imported top-level JSON payload. |
| `keys` | `json` | `data` | Sorted top-level keys for object roots, otherwise `[]`. |
| `item_count` | `integer` | `data` | Top-level key count, array length, or `1` for scalar roots. |
| `path` | `string` | `data` | Path from the last successful import. |
| `imported` | `trigger` | `control` | Pulses on successful import. |
| `busy` | `boolean` | `control` | True while the async file read is running. |
| `text` | `string` | `data` | Status summary. |
| `error` | `string` | `data` | Import failure or selection error. |

## Behavior

- Only `.json` files are accepted by the service layer.
- Parsing uses `orjson`.
- Project restore rehydrates staged state but does not auto-read the file.
- Failures clear stale success outputs deterministically.
