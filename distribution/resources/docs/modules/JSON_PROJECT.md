# JSON Project Module

## Purpose

`JSON Project` transforms nested JSON payloads into deterministic flat records using explicit path-mapping clauses. It is typically used between provider modules and table/export stages.

- Module type: `json_project`
- Family: `Transform`
- Capabilities: `transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `json` | `json` | `data` | no | Source payload object/array tree. |
| `mapping` | `string` | `data` | yes | Mapping clauses (`output=$.path`). |
| `auto` | `boolean` | `data` | yes | Reproject automatically on relevant input changes. |
| `emit` | `trigger` | `control` | no | Manual projection trigger. |
| `strict` | `boolean` | `data` | yes | Missing-path behavior control. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `record` | `json` | `data` | Flat projected key/value object. |
| `keys` | `json` | `data` | Ordered list of emitted keys. |
| `projected` | `trigger` | `control` | Pulses on successful projection. |
| `text` | `string` | `data` | Projection summary or deterministic error text. |
| `error` | `string` | `data` | Projection error string (`""` on success). |

## Mapping Language

Each clause uses:

`<output_key>=<json_path>`

Example:

```text
symbol=$.quote.symbol
price=$.quote.prices[0]
timestamp=$.meta.generated_at
```

Clause separators:

- newline
- semicolon (`;`)
- comma (`,`)

### Supported Path Syntax

- Root: `$`
- Object segment: `.name`
- Array segment: `[index]`

Unsupported by design:

- wildcards
- filters
- functions
- recursive descent

## Strict vs Non-Strict Behavior

- `strict=false`: missing paths are skipped, projection continues.
- `strict=true`: first missing path fails the projection with explicit error.

## Projection Lifecycle

- When `auto=true`, updates to `json`, `mapping`, or `strict` re-run projection.
- When `auto=false`, those inputs update state but do not project until `emit`.
- On success, `projected=1` and downstream control-plane binds can append or write explicitly.
- On parsing/projection errors, `record={}`, `keys=[]`, `projected=0`, and `error` is emitted.

## Persistence

Persisted keys:

- `mapping`
- `auto`
- `strict`

Non-persisted runtime state:

- source payload
- last projected output
- status/error text

## Recommended Bind Chains

### Provider Normalization

1. `HTTP Request.json` -> `JSON Project.json`
2. `Trigger source` -> `JSON Project.emit` (or enable `auto`)
3. `JSON Project.record` -> `Table Buffer.row`
4. `JSON Project.projected` -> `Table Buffer.append`

### Strict Data Contracts

- Enable `strict=true` where downstream schemas require all mapped fields.
- Route `error` into `Log Notes` for operational observability.

## Operational Guidance

- Keep mappings explicit and narrowly scoped; avoid overloading one module with many unrelated keys.
- Use one `JSON Project` per logical payload shape when providers differ.
- Prefer deterministic, fixed-path mappings over ad hoc dynamic extraction.
