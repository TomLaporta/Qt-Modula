# Table Import Module

## Purpose

`Table Import` stages or imports one local `csv`, `jsonl`, or `xlsx` table file.

- Module type: `table_import`
- Family: `Import`
- Capabilities: `source`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `path` | `string` | `data` | yes | Absolute staged file path. |
| `auto_import` | `boolean` | `data` | yes | If true, path changes trigger an import immediately. |
| `format` | `string` | `data` | yes | `auto`, `csv`, `jsonl`, or `xlsx`. Invalid values normalize to `auto` with a warning. |
| `sheet_name` | `string` | `data` | yes | Optional XLSX sheet override; ignored for non-XLSX formats. |
| `import` | `trigger` | `control` | no | Starts one import using the staged path. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `rows` | `table` | `data` | Imported rows. |
| `row_count` | `integer` | `data` | Imported row count. |
| `column_count` | `integer` | `data` | Imported column count. |
| `columns` | `json` | `data` | Column names in import order. |
| `path` | `string` | `data` | Path from the last successful import. |
| `imported` | `trigger` | `control` | Pulses on successful import. |
| `busy` | `boolean` | `control` | True while the async file read is running. |
| `text` | `string` | `data` | Status summary. |
| `error` | `string` | `data` | Import failure, selection error, or format warning. |

## Behavior

- `auto` format infers from the file extension.
- CSV/XLSX use the first row as headers.
- JSONL non-object rows are coerced to `{"value": ...}`.
- If `sheet_name` is empty, XLSX imports use the active sheet.
- Project restore rehydrates staged state but does not auto-read the file.
