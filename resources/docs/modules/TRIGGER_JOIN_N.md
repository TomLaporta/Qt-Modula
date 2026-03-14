# Trigger Join N Module

## Purpose

`Trigger Join N` synchronizes multiple trigger lanes and emits one joined pulse when all configured inputs have been seen.

- Module type: `trigger_join_n`
- Family: `Logic`
- Capabilities: `gate`, `transform`

## Typical Use Cases

- Coordinate 3+ readiness signals before downstream execution.
- Replace chains of pairwise joins with one deterministic barrier.
- Track multi-signal arrival state using `seen_mask` and `seen_count`.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `in_0` .. `in_7` | `trigger` | `control` | no | Trigger lanes participating in the barrier. |
| `input_count` | `integer` | `data` | yes | Number of active inputs (`2..8`). |
| `auto_reset` | `boolean` | `data` | yes | If true, clears seen state immediately after each join. |
| `clear` | `trigger` | `control` | no | Clears seen state and join count. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `joined` | `trigger` | `control` | Pulses once when all active inputs are seen. |
| `seen_count` | `integer` | `data` | Count of seen active inputs. |
| `seen_mask` | `json` | `data` | Boolean list of active seen flags. |
| `count` | `integer` | `data` | Number of joins since clear/start. |
| `text` | `string` | `data` | Deterministic status summary. |
| `error` | `string` | `data` | Validation warning (`""` when clear). |

## Runtime Notes

- `input_count` clamps to `2..8`.
- With `auto_reset=false`, one join is emitted per clear cycle.
- With `auto_reset=true`, module is immediately ready for the next cycle after each join.

## Persistence

Persisted keys:

- `input_count`
- `auto_reset`

Non-persisted runtime state:

- seen flags
- join count

## Example Bind Chain

1. `Trigger Mapper.fetch` -> `Trigger Join N.in_0`
2. readiness trigger A -> `Trigger Join N.in_1`
3. readiness trigger B -> `Trigger Join N.in_2`
4. `Trigger Join N.joined` -> downstream `run` / `write`
