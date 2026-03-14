# JSON Transform Module

## Purpose

`JSON Transform` applies deterministic JSON operations (`identity`, `flatten`, `pluck`, `filter_eq`) over a selected path.

- Module type: `json_transform`
- Family: `Transform`
- Capabilities: `transform`

## Typical Use Cases

- Flatten nested array payloads before buffering/export.
- Map arrays of objects to one key list (`pluck`).
- Filter records from provider payloads with simple equality conditions.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `json` | `json` | `data` | no | Source payload object/list. |
| `mode` | `string` | `data` | yes | `identity`, `flatten`, `pluck`, `filter_eq`. |
| `path` | `string` | `data` | yes | Source path (`$`, `.field`, `[index]` syntax). |
| `key` | `string` | `data` | yes | Key argument for `pluck` / `filter_eq`. |
| `match` | `any` | `data` | yes | Equality target for `filter_eq`. |
| `auto` | `boolean` | `data` | yes | Transform on updates when true. |
| `emit` | `trigger` | `control` | no | Manual transform trigger. |
| `strict` | `boolean` | `data` | yes | Type/key/path mismatch behavior (`error` vs tolerant fallback). |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `json` | `json` | `data` | Transformed payload result. |
| `count` | `integer` | `data` | `len(result)` for list/dict outputs. |
| `transformed` | `trigger` | `control` | Pulses on successful transform. |
| `text` | `string` | `data` | Deterministic mode/path/count summary. |
| `error` | `string` | `data` | Parse/validation errors (`""` on clean state). |

## Supported Path Syntax

- Root: `$`
- Object segment: `.name`
- Array segment: `[index]`

Unsupported path operators intentionally remain out of scope (`*`, filters, functions, recursive descent).

## Mode Semantics

- `identity`: returns selected source payload (non-JSON scalars wrap as `{ "value": ... }`).
- `flatten`: flattens nested lists recursively; object source becomes `[{"key": ..., "value": ...}]`.
- `pluck`: extracts one key from object rows.
- `filter_eq`: keeps object rows where `row[key] == match`.

## Persistence

Persisted keys:

- `mode`
- `path`
- `key`
- `match`
- `auto`
- `strict`

Non-persisted runtime state:

- source payload
- transient outputs/status

## Example Bind Chain

1. `HTTP Request.json` -> `JSON Transform.json`
2. set `mode=filter_eq`, `path=$.items`, `key=symbol`, `match=AAPL`
3. `JSON Transform.json` -> `Table Buffer.row` (through downstream mapping as needed)
