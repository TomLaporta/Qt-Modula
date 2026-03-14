# Line Plotter Module

## Purpose

`Line Plotter` is a professional visualization sink for scientific and financial workflows. It renders line series from table data, supports deterministic batch + live ingestion, and exposes exact point-snapped hover coordinates for downstream bind chains.

- Module type: `line_plotter`
- Family: `Analytics`
- Capabilities: `sink, transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `rows` | `table` | `data` | no | Replaces full dataset. |
| `row` | `json` | `data` | no | Caches one pending live row object. |
| `append` | `trigger` | `control` | no | Appends cached row into dataset. |
| `clear` | `trigger` | `control` | no | Clears dataset, hover state, and readout. |
| `x_key` | `string` | `data` | yes | X column key. |
| `y_key` | `string` | `data` | yes | Y column key. |
| `series_key` | `string` | `data` | yes | Grouping key for multi-series rendering. |
| `x_mode` | `string` | `data` | yes | `auto`, `number`, `datetime`, or `index`. |
| `epoch_unit` | `string` | `data` | yes | `auto`, `s`, or `ms` for datetime epoch parsing. |
| `max_points` | `integer` | `data` | yes | Retention cap (`1..1000000`, default `200000`). |
| `range_mode` | `string` | `data` | yes | `all`, `last_n`, `last_seconds`, `x_between`. |
| `range_points` | `integer` | `data` | yes | Used by `last_n` (`1..1000000`). |
| `range_seconds` | `number` | `data` | yes | Used by `last_seconds` (non-negative). |
| `range_seconds_iso` | `string` | `data` | no | ISO-8601 duration mirror for datetime X workflows (`PT1H`, `P1D`). |
| `range_x_min` | `number` | `data` | yes | Lower bound for `x_between`. |
| `range_x_min_iso` | `string` | `data` | no | ISO-8601 timestamp mirror for datetime X workflows. |
| `x_compression_threshold` | `number` | `data` | yes | Compress qualifying X gaps when consecutive visible values differ by at least this amount. |
| `x_compression_span` | `number` | `data` | yes | Retained display span for compressed X gaps; clamped to `0..x_compression_threshold`. |
| `x_compression_threshold_iso` | `string` | `data` | no | ISO-8601 duration mirror for datetime X compression threshold. |
| `x_compression_span_iso` | `string` | `data` | no | ISO-8601 duration mirror for datetime X compression span. |
| `y_compression_threshold` | `number` | `data` | yes | Compress qualifying Y gaps when consecutive visible values differ by at least this amount. |
| `y_compression_span` | `number` | `data` | yes | Retained display span for compressed Y gaps; clamped to `0..y_compression_threshold`. |
| `follow_latest` | `boolean` | `data` | yes | For live append lanes, keep viewport anchored to newest data. |
| `show_points` | `boolean` | `data` | yes | Show/hide point markers. |
| `antialias` | `boolean` | `data` | yes | Toggle antialiasing for curves. |
| `lock_on_click` | `boolean` | `data` | yes | Click toggles hover lock state. |
| `show_legend` | `boolean` | `data` | yes | Show/hide the legend. |
| `show_grid` | `boolean` | `data` | yes | Show/hide plot grid lines. |
| `local_time` | `boolean` | `data` | yes | Datetime X-axis display mode (`true` = local timezone, `false` = UTC). |
| `reset_view` | `trigger` | `control` | no | Reapplies the configured range window and data-bounded Y view. |
| `export_folder` | `string` | `data` | yes | Export folder under `saves/exports`. |
| `file_name` | `string` | `data` | yes | Export file stem. |
| `tag` | `string` | `data` | no | Optional suffix in export filename stem (`_<tag>`). |
| `export_png` | `trigger` | `control` | no | Exports plot snapshot as PNG. |
| `export_svg` | `trigger` | `control` | no | Exports plot snapshot as SVG. |

`range_x_max` is UI-only. It is not part of the bind or persistence contract.

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `point_count` | `integer` | `data` | Count of currently visible points after range filtering. |
| `source_point_count` | `integer` | `data` | Count of valid retained points before range filtering. |
| `series_count` | `integer` | `data` | Number of rendered series. |
| `invalid_count` | `integer` | `data` | Rows skipped due to invalid/missing coordinates. |
| `visible_x_min` | `number` | `data` | Minimum X value in current visible range. |
| `visible_x_max` | `number` | `data` | Maximum X value in current visible range. |
| `range_mode` | `string` | `data` | Effective normalized range mode token. |
| `range_applied` | `string` | `data` | Human-readable applied range expression. |
| `hover_active` | `boolean` | `data` | True when a hover/locked point is active. |
| `hover_series` | `string` | `data` | Active series label. |
| `hover_index` | `integer` | `data` | Row index for active point; for interpolated lock points this is the nearest source row endpoint. |
| `hover_x` | `number` | `data` | Exact snapped X value (UTC epoch seconds for datetime points). |
| `hover_y` | `number` | `data` | Exact snapped Y value. |
| `hover_x_text` | `string` | `data` | Display-formatted X (timezone follows `local_time` for datetime points). |
| `hover_y_text` | `string` | `data` | Adaptive formatted Y text. |
| `path` | `string` | `data` | Last export path. |
| `exported` | `trigger` | `control` | Pulses on successful export. |
| `text` | `string` | `data` | Deterministic status summary. |
| `error` | `string` | `data` | Deterministic error/warning text (`""` on clean state). |

## Data Handling Semantics

- Invalid rows are skipped, not fatal.
- `x_mode=datetime` accepts ISO-8601 or epoch (`epoch_unit` controls seconds/ms, `auto` infers from magnitude).
- `x_mode=auto` treats ISO-like strings as datetime and numeric values as numeric.
- When datetime mode is active (or auto mode resolves fully datetime data), x-axis ticks render as datetime intervals instead of raw epoch/scientific notation.
- Datetime display timezone is controlled by `local_time`:
  - `true` (default): local timezone rendering
  - `false`: UTC rendering
- Datetime axis labels include timezone text as `(<x_key> (time <TZ>))`, for example `x (time EDT)` or `x (time UTC)`.
- Datetime X controls expose ISO mirror inputs. Numeric and ISO updates are normalized immediately and the sibling representation is re-synced with last-write-wins behavior.
- `x_mode=index` ignores `x_key` and uses retained row index.
- Invalid `x_mode` / `epoch_unit` values are normalized to `auto` with deterministic warnings on `error`.
- Retention is bounded by `max_points`; oldest rows are trimmed first.
- Range filtering is non-destructive: source rows stay in memory, visible rows are filtered by `range_mode`.
- `range_mode=last_n` keeps the latest N points per series (sorted by X).
- `range_mode=last_seconds` keeps points in `[max_x - range_seconds, max_x]`.
- `range_mode=x_between` keeps points with `x` between `range_x_min` and latest source-data `x` (inclusive). The upper bound is auto-derived and displayed read-only in the UI.
- For datetime-style `x_between`, default `range_x_min=0` is auto-anchored to the first visible sample to avoid `0..epoch` collapse.
- Compression is display-only. Hover outputs, visible bounds, exports, and lock readouts stay in raw source coordinates.
- Compression is computed from the currently visible, range-filtered dataset. When a consecutive visible gap is `>= threshold`, that raw interval is rendered using the configured retained `span`.
- `threshold <= 0` disables compression on that axis. `span > threshold` is clamped deterministically and reported on `error`.
- Plot viewport X-range is always exact to the active configured range window, including `range_mode=all` (full visible-data extent).
- Y viewport is clamped to visible-data bounds with slight headroom to prevent top/bottom stroke clipping.
- For live appends with `follow_latest=false`, if the current Y view already matches full data bounds, new extrema auto-expand the Y view; manual Y zoom windows are preserved.

## Hover and Lock Behavior

- Hover snapping prioritizes nearest X-aligned point first, then nearest Y among X ties.
- Lock-on-click always chooses between a vertical-axis candidate and a horizontal-axis candidate.
- Axis candidates are projected onto the plotted line in source data space (segment interpolation when needed), so snap stays on one crosshair axis and does not jump diagonally.
- Axis comparison uses scene/view-space distances so the chosen axis matches on-screen crosshair proximity.
- Lock snapping does not use pyqtgraph display-reduced points.
- Hover outputs are sample-snapped; lock outputs may use segment interpolation to stay on the chosen crosshair axis.
- Hover outputs emit only when active snapped point changes or lock toggles.
- Crosshair follows cursor position in live mode.
- With `lock_on_click=true`, click freezes/unfreezes the current snapped point.
- Locked coordinate readout is rendered on the bottom-left axis bar (where pyqtgraph’s `A` button appears) and shown only while locked.
- The lock readout is an anchored graphics badge (not a layout column item), so it does not compress plot width.
- Lock readout badge uses an opaque background for maximum legibility.
- X dragging is disabled to preserve strict X-range constraints; Y zoom/pan remains enabled.
- Single-point or same-X series automatically render point markers even when `show_points=false` so data stays visible.

## UI Layout

- Core workflow controls are grouped under a collapsed `Options` section by default.
- Expert tuning is grouped under a collapsed `Advanced` section by default.
- `Show Legend`, `Show Grid`, and `Local Time` are advanced persisted display settings, so saved projects reopen with the same presentation state.
- Range rows are context-sensitive:
  - `last_n` shows `Range Points`
  - `last_seconds` shows `Range Duration` / numeric span
  - `x_between` shows `Range X Min` and derived `Range X Max (Auto)`
- `Epoch Unit` is only shown when the X mode can parse datetime/epoch values.
- Range and compression editors switch automatically between numeric widgets and datetime/duration widgets when the X axis is operating in datetime mode.
- `Range X Max (Auto)` is visible in the UI as derived state only; it is not a bind target.
- `File Name`, inline `Tag`, `Export Folder`, and export action buttons remain always visible for quick export workflows.

## Bind Panel Defaults

- The bind panel shows only normal `Line Plotter` ports by default.
- Bind labels use canonical port keys such as `x_key` and `range_mode`, consistent with the rest of the application.
- Expert/runtime tuning ports such as compression controls, `Epoch Unit`, `Max Points`, and detailed telemetry outputs are hidden until `Show Advanced Ports` is enabled.
- The full contract still exists; the default UI is intentionally narrower than the implementation surface.

## Export Behavior

- PNG and SVG exports are deterministic and use sanitized file/folder segments.
- PNG export uses high-resolution width scaling with antialiasing for improved quality.
- For PNG export only: if hover is not locked, crosshair is hidden during render and restored immediately after.
- Exports resolve under `saves/exports/<export_folder>/<file_name>[_<tag>].<ext>`.
- Successful export sets `path`, pulses `exported=1`, and clears `error`.

## Professional Workflow Recipes

### 1. Historical Market Visualization

Use this for deterministic history pulls with exact hover readout.

1. `Trigger Button.pulse` -> `Market Fetcher.commit`
2. `Trigger Button.pulse` -> `Market Fetcher.fetch`
3. `Market Fetcher.rows` -> `Line Plotter.rows`

Recommended module settings:

- `Line Plotter.x_key`: `x`
- `Line Plotter.y_key`: `y`
- `Line Plotter.series_key`: `series`
- `Line Plotter.x_mode`: `datetime`
- `Line Plotter.epoch_unit`: `auto`
- `Line Plotter.range_mode`: `all` (or `x_between` for focused windows)
- Optional session-gap compression:
  - `Line Plotter.x_compression_threshold_iso`: `PT1H`
  - `Line Plotter.x_compression_span_iso`: `PT5M`
- `Line Plotter.follow_latest`: `false`

### 2. Scientific Sweep Visualization

Use this for deterministic parameter studies.

1. `Trigger Button.pulse` -> `Trigger Mapper.trigger` (`channel=run`)
2. `Trigger Mapper.run` -> `Parameter Sweep.run`
3. `Parameter Sweep.rows` -> `Line Plotter.rows`

Recommended module settings:

- `Line Plotter.x_key`: `x` (or configured sweep variable)
- `Line Plotter.y_key`: `result`
- `Line Plotter.series_key`: empty for single-series
- `Line Plotter.x_mode`: `number`

### 3. Hover-to-Inspection Lane

Use this when analysts need explicit value auditing in bind chains.

1. `Line Plotter.hover_x` -> `Value View.value`
2. `Line Plotter.hover_y` -> second `Value View.value` (or downstream logic lane)
3. `Line Plotter.hover_series` / `hover_index` -> `Log Notes.append` (through formatter/mapper if used)

## Troubleshooting

- `error` contains `skipped N invalid row(s)`:
  - check `x_key`/`y_key` against row schema
  - ensure Y values are finite numbers
  - ensure datetime inputs match ISO-8601 or epoch policy
- Hover values look unexpected:
  - confirm `x_mode` and `epoch_unit`
  - remember hover is snapped to nearest real point, not interpolated
- Datetime range or compression input was rejected:
  - use ISO-8601 timestamps for `range_x_min_iso`
  - use ISO-8601 durations for `range_seconds_iso` / X compression ISO ports
  - if `span > threshold`, the span is clamped and reported on `error`
- No data visible:
  - verify `point_count > 0`
  - use `reset_view` to restore viewport
  - check upstream `Table Buffer.row_count` and `error` lanes
