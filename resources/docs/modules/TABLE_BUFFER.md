# Table Buffer Module

## Purpose

`Table Buffer` accumulates JSON rows into a bounded in-memory table for analytics and export workflows. It supports optional deduplication by key and deterministic eviction behavior.

- Module type: `table_buffer`
- Family: `Research`
- Capabilities: `transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `row` | `json` | `data` | no | Pending row candidate object. |
| `append` | `trigger` | `control` | no | Commits pending row into buffer. |
| `emit` | `trigger` | `control` | no | Re-emits current rows/state without append. |
| `clear` | `trigger` | `control` | no | Resets rows, pending row, and eviction counter. |
| `max_rows` | `integer` | `data` | yes | Capacity; clamped to minimum `1`. |
| `dedupe_key` | `string` | `data` | yes | If set and present in new row, removes existing matches before append. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `rows` | `table` | `data` | Full buffered rows in insertion/trim order. |
| `row_count` | `integer` | `data` | Current number of buffered rows. |
| `appended` | `trigger` | `control` | Pulses when append succeeds. |
| `evicted_count` | `integer` | `data` | Total rows removed due to dedupe/capacity trims. |
| `text` | `string` | `data` | Status summary or error text. |
| `error` | `string` | `data` | Deterministic error (`""` when clear). |

## Operational Semantics

### Row Intake

- `row` must be an object (`dict`); otherwise emit `error="row must be an object"`.
- Valid rows are deep-copied into a pending slot and not appended until `append`.

### Append Behavior

On truthy `append`:

1. If no pending row exists, append is ignored with `error="no pending row"`.
2. If `dedupe_key` is non-empty and present in incoming row, existing rows with the same key value are removed.
3. Incoming row is appended.
4. Capacity trimming removes oldest overflow rows when `len(rows) > max_rows`.

### Emit and Clear

- `emit` publishes current state without mutation.
- `clear` empties rows, clears pending row, resets `evicted_count`.

## Persistence

Persisted keys:

- `max_rows`
- `dedupe_key`

Non-persisted runtime state:

- buffered rows
- pending row
- eviction counters/status text

## Recommended Bind Chains

### Provider Record Accumulation

1. `JSON Project.record` -> `Table Buffer.row`
2. provider completion trigger -> `Table Buffer.append`
3. `Table Buffer.rows` -> analytics/export modules

### Sliding Snapshot Buffer

- Set `max_rows` to desired rolling window size.
- Optional `dedupe_key` keeps only latest row per entity.

## Operational Guidance

- Use stable, low-cardinality `dedupe_key` values for predictable replacement behavior.
- For large buffers, tune runtime queue settings and downstream export cadence.
- `evicted_count` is cumulative and intended for observability, not row indexing.
