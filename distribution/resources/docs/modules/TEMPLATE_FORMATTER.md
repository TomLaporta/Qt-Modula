# Template Formatter Module

## Purpose

`Template Formatter` renders text templates from structured context and a bound `value` lane.

- Module type: `template_formatter`
- Family: `Transform`
- Capabilities: `transform`

## Typical Use Cases

- Build log lines and operator notes from multiple fields.
- Format hover/readout strings from structured payloads.
- Render deterministic status text for export/report lanes.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `template` | `string` | `data` | yes | Template using `{field}` placeholders. |
| `context` | `json` | `data` | no | Source object/list for field resolution. |
| `value` | `any` | `data` | no | Convenience lane exposed as `{value}`. |
| `auto` | `boolean` | `data` | yes | Auto-render on updates when true. |
| `emit` | `trigger` | `control` | no | Manual render trigger when `auto=false`. |
| `strict` | `boolean` | `data` | yes | Missing-field behavior control. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `value` | `string` | `data` | Rendered template output. |
| `fields` | `json` | `data` | Ordered placeholder field list discovered in template. |
| `rendered` | `trigger` | `control` | Pulses on successful render. |
| `text` | `string` | `data` | Deterministic render summary. |
| `error` | `string` | `data` | Missing-field/validation warnings (`""` when clear). |

## Placeholder Syntax

- Placeholders use `{field}` notation.
- Nested paths support dot and index traversal (`{quote.items[0].symbol}`).
- Field resolution is deterministic and order-preserving.

## Strict vs Non-Strict

- `strict=false`: missing fields render as empty text and are reported on `error`.
- `strict=true`: missing fields fail render (`value=""`, `rendered=0`, error populated).

## Persistence

Persisted keys:

- `template`
- `auto`
- `strict`

Non-persisted runtime state:

- context/value payloads
- rendered outputs and status text

## Example Bind Chain

1. payload object -> `Template Formatter.context`
2. auxiliary scalar -> `Template Formatter.value`
3. `Template Formatter.value` -> `Log Notes.append`
