# Logic Combinator Module

## Purpose

`Logic Combinator` evaluates boolean logic across an input list and emits deterministic true/false control pulses.

- Module type: `logic_combinator`
- Family: `Logic`
- Capabilities: `gate`, `transform`

## Typical Use Cases

- Gate execution based on multiple readiness flags.
- Replace chained comparator modules for simple boolean fan-in.
- Drive `run`/`fetch` lanes only when composite conditions are met.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `values` | `json` | `data` | no | Boolean candidate list (truthy semantics applied). |
| `operator` | `string` | `data` | yes | `and`, `or`, `xor`, or `not` (invalid values normalize to `and`). |
| `auto` | `boolean` | `data` | yes | Evaluate on input updates when true. |
| `emit` | `trigger` | `control` | no | Manual evaluation trigger. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `matched` | `boolean` | `data` | Final boolean result. |
| `on_true` | `trigger` | `control` | Pulses when evaluation result is true. |
| `on_false` | `trigger` | `control` | Pulses when evaluation result is false. |
| `true_count` | `integer` | `data` | Number of truthy inputs in current evaluation. |
| `false_count` | `integer` | `data` | Number of falsey inputs in current evaluation. |
| `text` | `string` | `data` | Deterministic evaluation summary. |
| `error` | `string` | `data` | Validation warnings (`""` when clean). |

## Operator Semantics

- `and`: true only when input list is non-empty and all entries are truthy.
- `or`: true when any entry is truthy.
- `xor`: true when the number of truthy entries is odd.
- `not`: negates only the first entry (empty list treated as false before negation).

## Persistence

Persisted keys:

- `operator`
- `auto`

Non-persisted runtime state:

- current `values` payload
- transient output pulses

## Example Bind Chain

1. readiness signal list -> `Logic Combinator.values`
2. `Logic Combinator.on_true` -> provider `fetch`
3. `Logic Combinator.on_false` -> `Log Notes.append`
