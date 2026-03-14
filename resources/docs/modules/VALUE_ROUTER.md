# Value Router Module

## Purpose

`Value Router` selects one of up to eight value lanes using a clamped selector and emits deterministic route outputs.

- Module type: `value_router`
- Family: `Logic`
- Capabilities: `gate`, `transform`

## Typical Use Cases

- Replace chained two-lane selectors with one N-way router.
- Route primary/fallback/override payload sets.
- Keep route decisions explicit via `selected` and `in_range` outputs.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `v0` .. `v7` | `any` | `data` | no | Candidate value lanes. |
| `selector` | `integer` | `data` | yes | Selected lane index (clamped to active range). |
| `input_count` | `integer` | `data` | yes | Number of active lanes (`2..8`). |
| `auto` | `boolean` | `data` | yes | Auto-emit on input updates when true. |
| `emit` | `trigger` | `control` | no | Manual emit trigger when `auto=false`. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `value` | `any` | `data` | Currently routed value. |
| `selected` | `integer` | `data` | Effective selector after clamping. |
| `in_range` | `boolean` | `data` | True when requested selector was in active range. |
| `changed` | `trigger` | `control` | Pulses on route emission. |
| `text` | `string` | `data` | Deterministic route summary. |
| `error` | `string` | `data` | Validation warning (`""` when clear). |

## Runtime Notes

- `input_count` clamps to `2..8`.
- Selector values outside active range are clamped and surfaced on `error`.
- With `auto=false`, lane updates are cached until `emit`.

## Persistence

Persisted keys:

- `input_count`
- `selector`
- `auto`

Non-persisted runtime state:

- lane payload values
- transient trigger outputs

## Example Bind Chain

1. primary -> `Value Router.v0`
2. fallback -> `Value Router.v1`
3. override -> `Value Router.v2`
4. `Value Router.value` -> downstream module
