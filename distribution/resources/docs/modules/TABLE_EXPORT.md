# Table Export Module

## Purpose

`Table Export` writes table payloads to disk in `csv`, `jsonl`, or `xlsx` formats using deterministic overwrite/append semantics and shared async error handling.

- Module type: `table_export`
- Family: `Export`
- Capabilities: `sink`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `rows` | `table` | `data` | no | Source rows to write. Non-object rows are coerced to `{"value": ...}`. |
| `file_name` | `string` | `data` | yes | Export stem; sanitized and defaulted to `output`. |
| `export_folder` | `string` | `data` | yes | Optional subfolder under `saves/exports`. |
| `format` | `string` | `data` | yes | Normalized to `csv`, `jsonl`, or `xlsx`; invalid values fallback with warning. |
| `mode` | `string` | `data` | yes | Normalized to `overwrite` or `append`; invalid values fallback with warning. |
| `write` | `trigger` | `control` | no | Starts export using configured mode. |
| `overwrite` | `trigger` | `control` | no | One-shot mode override. |
| `append` | `trigger` | `control` | no | One-shot mode override. |
| `refresh` | `trigger` | `control` | no | Recomputes status preview only. |
| `clear` | `trigger` | `control` | no | Clears transient status outputs; normalization warnings remain until corrected inputs are set. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `path` | `string` | `data` | Final resolved export path. |
| `row_count` | `integer` | `data` | Number of rows written in current operation. |
| `total_row_count` | `integer` | `data` | Total rows in target after operation. |
| `wrote` | `trigger` | `control` | Pulses when write succeeds. |
| `busy` | `boolean` | `control` | True while async export is running. |
| `text` | `string` | `data` | Status summary or deterministic error summary. |
| `error` | `string` | `data` | Export failure or deterministic input-normalization warning (`""` when clean). |

## Input Normalization Warnings

- Invalid `format` falls back to `csv` and emits `error="invalid format '<value>'; using 'csv'"`.
- Invalid `mode` falls back to `overwrite` and emits `error="invalid mode '<value>'; using 'overwrite'"`.
- Multiple warnings are joined deterministically with `;`.

## Format and Mode Semantics

### CSV

- `overwrite`: write current rows only.
- `append`: read existing CSV, merge by concatenation, rewrite with sorted header union.

### JSONL

- `overwrite`: rewrite full file with one JSON object per line.
- `append`: append newline-delimited JSON rows and update total by line count.

### XLSX

- `overwrite`: write workbook with `Sheet1` containing current rows.
- `append`: read existing workbook rows, concatenate, and rewrite workbook.

## Path and Sanitization Rules

Path is built as:

`saves/exports[/<export_folder>]/<file_name>.<format>`

Sanitization details:

- disallowed characters become `_`
- leading/trailing separators are trimmed
- reserved Windows stems are suffixed
- empty values fall back to deterministic defaults

## Async and Failure Policy

`Table Export` uses the shared async framework:

- `AsyncServiceRunner`
- `capture_service_result(...)`
- `apply_async_error_policy(...)`

On failure, stale success outputs are cleared deterministically:

- `path=""`
- `row_count=0`
- `total_row_count=0`
- `wrote=0`

`busy` is always returned to `False` on completion or failure.

## Persistence

Persisted keys:

- `file_name`
- `export_folder`
- `format`
- `mode`

Non-persisted:

- `rows`
- trigger inputs
- runtime status outputs

## Recommended Bind Chains

### Snapshot Export

1. `Table Buffer.rows` -> `Table Export.rows`
2. `Trigger source` -> `Table Export.overwrite`

### Log-Style Export

1. `Table Buffer.rows` -> `Table Export.rows`
2. periodic trigger -> `Table Export.append`

### Quality Monitoring

- Route `error` or `text` to `Log Notes` for operator visibility.

## Operational Guidance

- Prefer `jsonl` append for high-volume incremental logs.
- Use `overwrite` for reproducible point-in-time artifacts.
- Keep file naming stable for downstream automation and post-processing.
