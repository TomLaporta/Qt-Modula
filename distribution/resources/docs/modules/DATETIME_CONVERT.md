# Datetime Convert Module

## Purpose

`Datetime Convert` parses common date/time input formats and emits normalized bind-friendly outputs.

- Module type: `datetime_convert`
- Family: `Transform`
- Capabilities: `transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `value` | `any` | `data` | yes | Source value to parse (`string` or numeric epoch seconds). |
| `auto` | `boolean` | `data` | yes | Convert on every `value`/option update. |
| `day_first` | `boolean` | `data` | yes | Slash-date input mode (`DD/MM/YYYY` when true; `MM/DD/YYYY` when false). |
| `input_timezone` | `string` | `data` | yes | How timezone-naive values are interpreted (`utc` or `local`). |
| `output_timezone` | `string` | `data` | yes | How rendered outputs are formatted (`utc` or `local`). |
| `emit` | `trigger` | `control` | no | Manual conversion trigger. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `datetime` | `string` | `data` | Normalized datetime (`YYYY-MM-DD HH:MM:SS`) when a date is available. |
| `date` | `string` | `data` | Normalized date (`YYYY-MM-DD`) when a date is available. |
| `time` | `string` | `data` | Normalized time (`HH:MM:SS`) when a time is available. |
| `iso` | `string` | `data` | ISO output (`YYYY-MM-DDTHH:MM:SSZ` for UTC datetime, local offset form for local datetime, `YYYY-MM-DD` for date-only). |
| `epoch_seconds` | `number` | `data` | Absolute epoch-seconds instant (`0.0` on clear/error). |
| `date_mdy` | `string` | `data` | Date rendered as `MM/DD/YYYY` when a date is available. |
| `date_dmy` | `string` | `data` | Date rendered as `DD/MM/YYYY` when a date is available. |
| `time_12h` | `string` | `data` | Time rendered as `HH:MM:SS AM/PM` when a time is available. |
| `datetime_mdy` | `string` | `data` | Datetime rendered as `MM/DD/YYYY HH:MM:SS AM/PM` (or date-only `MM/DD/YYYY`). |
| `datetime_dmy` | `string` | `data` | Datetime rendered as `DD/MM/YYYY HH:MM:SS AM/PM` (or date-only `DD/MM/YYYY`). |
| `month_name` | `string` | `data` | Full month name (`March`) when a date is available. |
| `named_date` | `string` | `data` | Human-readable date (`March 10, 2026`) when a date is available. |
| `named_datetime` | `string` | `data` | Human-readable 12-hour datetime (`March 10, 2026 06:30:00 PM`) or date-only fallback. |
| `year` | `integer` | `data` | Year component (`0` when no date component is present). |
| `month` | `integer` | `data` | Month component (`0` when no date component is present). |
| `day` | `integer` | `data` | Day-of-month component (`0` when no date component is present). |
| `hours` | `integer` | `data` | Hour component in selected output timezone (`0` when no time component is present). |
| `minutes` | `integer` | `data` | Minute component (`0` when no time component is present). |
| `seconds` | `number` | `data` | Second component (`0.0` when no time component is present). |
| `converted` | `trigger` | `control` | Pulses on successful conversion. |
| `text` | `string` | `data` | Deterministic conversion status text. |
| `error` | `string` | `data` | Parse error text (`""` on success). |

## Supported Input Formats

- ISO datetime/date, including `Z` and explicit offsets
  - Examples: `2026-03-10T18:30:00Z`, `2026-03-10 18:30:00`, `2026-03-10`
- Epoch seconds (numeric input or numeric string)
  - Examples: `1704067200`, `1704067200.5`
- Slash dates (`MM/DD/YYYY` and `DD/MM/YYYY`)
  - Examples: `12/31/2026`, `31/12/2026`
- Date + time using slash dates
  - Examples: `03/10/2026 6:30 PM`, `31/12/2026 23:10`
- 12-hour clock time-only values
  - Examples: `6:30 PM`, `11:59:30 PM`

## Normalization Rules

- All parsed values are reduced to a canonical UTC instant internally.
- Timezone-aware ISO values use their explicit offset first, then normalize to UTC.
- Timezone-naive datetime/date/time inputs are interpreted using `input_timezone`:
  - `utc`: treat naive values as UTC wall time
  - `local`: treat naive values as local wall time
- Rendered outputs (`datetime`, `time`, named variants, numeric components) follow `output_timezone`:
  - `utc`: UTC wall time formatting
  - `local`: local wall time formatting
- `epoch_seconds` is always the absolute UTC epoch for the resolved instant.
- `iso` behavior for datetime outputs:
  - `output_timezone=utc`: `YYYY-MM-DDTHH:MM:SSZ`
  - `output_timezone=local`: ISO datetime with local offset (for example, `-04:00`)
- Outputs are grouped in this order for bind-panel clarity:
  - canonical (`datetime`, `date`, `time`, `iso`, `epoch_seconds`)
  - alternate formats (`date_mdy`, `date_dmy`, `time_12h`, `datetime_mdy`, `datetime_dmy`)
  - named formats (`month_name`, `named_date`, `named_datetime`)
  - numeric components (`year`, `month`, `day`, `hours`, `minutes`, `seconds`)
- Date-only inputs emit:
  - `date=YYYY-MM-DD`
  - `datetime=YYYY-MM-DD 00:00:00`
  - `time=""`
- Time-only inputs emit:
  - `time=HH:MM:SS`
  - `date=""`
  - `datetime=""`
- Empty input clears outputs and does not emit an error.

## Ambiguous Slash Dates

For values where both month/day and day/month are valid (for example, `03/04/2026`):

- `day_first=false` (default): interpret as `MM/DD/YYYY`
- `day_first=true`: interpret as `DD/MM/YYYY`

Widget control:

- `Date Input` radio buttons expose both input-entry modes directly:
  - `MM/DD/YYYY`
  - `DD/MM/YYYY`

When only one interpretation is valid (for example, `31/12/2026`), that valid interpretation is used regardless of preference.

## Timezone Controls

- `Input` radio group controls how timezone-naive values are interpreted (`UTC` or `Local`).
- `Output` radio group controls how output values are rendered (`UTC` or `Local`).
- Timezone-aware ISO input (`Z`/`+/-HH:MM`) remains absolute regardless of `Input` mode.

## Persistence

Persisted keys:

- `value`
- `auto`
- `day_first`
- `input_timezone`
- `output_timezone`

Non-persisted runtime state:

- conversion outputs
- status/error outputs
