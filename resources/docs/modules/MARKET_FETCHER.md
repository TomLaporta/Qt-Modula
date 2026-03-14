# Market Fetcher Module

## Purpose

`Market Fetcher` is a built-in `Providers` module for historical market-data workflows in Qt Modula.

- Module type: `market_fetcher`
- Family: `Providers`
- Capabilities: `provider, source`

## Typical Use Cases

- Fetch OHLCV history windows for quantitative analysis.
- Feed historical close series directly into `Line Plotter`.
- Export normalized market history rows for research pipelines.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `symbol` | `string` | `data` | yes | Default: `"AAPL"` |
| `years` | `integer` | `data` | yes | Default: `0` |
| `months` | `integer` | `data` | yes | Default: `0` |
| `weeks` | `integer` | `data` | yes | Default: `0` |
| `days` | `integer` | `data` | yes | Default: `0` |
| `interval` | `string` | `data` | yes | `auto`, `1m`, `2m`, `5m`, `15m`, `30m`, `1h`, `1d` (`60m` aliases to `1h`). |
| `extended_hours` | `boolean` | `data` | yes | Default: `true`; includes pre/post-market bars for intraday fetches. |
| `filter_zero_volume_outliers` | `boolean` | `data` | yes | Default: `false`; when enabled with extended-hours intraday fetches, removes zero-volume quote-only spikes. |
| `auto_fetch` | `boolean` | `data` | yes | Default: `false`; automatically queues `fetch` after successful `commit`. |
| `commit` | `trigger` | `control` | no | Resolves max available range for symbol and updates range controls. |
| `fetch` | `trigger` | `control` | no | Fetches history for selected range (requires successful `commit`). |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `history` | `json` | `data` | JSON array of normalized OHLCV rows. |
| `rows` | `table` | `data` | Same payload as `history`, table lane for bind chains. |
| `row_count` | `integer` | `data` | Number of rows emitted in last successful fetch. |
| `symbol` | `string` | `data` | Resolved symbol. |
| `provider` | `string` | `data` | Provider identifier. |
| `source_symbol` | `string` | `data` | Source ticker used by provider. |
| `extended_trading` | `boolean` | `data` | Mirrors `extended_hours` toggle state for bind chains. |
| `outliers` | `boolean` | `data` | Mirrors `filter_zero_volume_outliers` toggle state for bind chains. |
| `auto_fetch` | `boolean` | `data` | Mirrors `auto_fetch` toggle state for bind chains. |
| `range_ready` | `boolean` | `data` | True after successful commit. |
| `max_years` | `integer` | `data` | Maximum available years for symbol history. |
| `available_start` | `string` | `data` | Earliest available timestamp (ISO UTC). |
| `available_end` | `string` | `data` | Latest timestamp in committed availability profile (ISO UTC). |
| `selected_start` | `string` | `data` | Applied fetch start timestamp (ISO UTC). |
| `selected_end` | `string` | `data` | Applied fetch end timestamp (ISO UTC); for non-`full_max`, resolved at fetch time as `max(available_end, now_utc)`. |
| `effective_interval` | `string` | `data` | Actual interval used by provider after auto selection/downgrade. |
| `latest_timestamp` | `string` | `data` | Last row timestamp (ISO UTC). |
| `latest_open` | `number` | `data` | Last row open value. |
| `latest_high` | `number` | `data` | Last row high value. |
| `latest_low` | `number` | `data` | Last row low value. |
| `latest_close` | `number` | `data` | Last row close value. |
| `latest_adj_close` | `number` | `data` | Last row adjusted close value. |
| `latest_volume` | `integer` | `data` | Last row volume. |
| `busy` | `boolean` | `control` | True while provider call is running. |
| `committed` | `trigger` | `control` | Pulses on successful commit. |
| `fetched` | `trigger` | `control` | Pulses on successful fetch. |
| `text` | `string` | `data` | Deterministic status text. |
| `error` | `string` | `data` | Deterministic error text. |

## History Row Schema

Each emitted row contains:

- `timestamp` (ISO UTC)
- `epoch_s`
- `symbol`
- `open`
- `high`
- `low`
- `close`
- `adj_close`
- `volume`
- `x`, `y`, `series` for direct plotting (`x=timestamp`, `y=close`, `series=symbol`)

## Runtime Notes

- `commit` is required before fetching.
- `auto_fetch=true` queues fetch immediately after successful commit completes.
- If `fetch` and `commit` arrive in the same pulse lane, the module executes deterministically as `commit -> fetch`.
- In the module widget, range controls are exposed as two dropdowns: `Range` (`Years/Months/Weeks/Days`) and `Value` (values for the selected category).
- In `Range=Days`, value `0` is displayed as `Today`.
- Commit defaults range selection to today (`days=0`, `years=months=weeks=0`, `Range=Days`).
- Range selection is exclusive: when a category is selected/edited, all other range categories are reset to `0`.
- `Extended Hours` defaults to on and maps to yfinance pre/post-market history (`prepost=true`) for intraday effective intervals.
- `Extended Hours` is ignored/forced off for daily effective interval (`1d`), including `full_max`.
- `Filter Outliers` defaults to off so raw extended-hours bars are preserved; when enabled, zero-volume quote-only spikes are removed.
- If selected `years` equals `max_years`, `months`, `weeks`, and `days` are forced to `0`.
- Non-`full_max` fetches resolve `selected_end` at fetch time as `max(available_end, now_utc)`, so same-day bars can be included without re-committing.
- Default `interval=auto` uses adaptive granularity:
  - `Today (days=0) -> 1m`
  - `<= 7d -> 2m`, `<= 30d -> 5m`, `<= 60d -> 15m`, `<= 730d -> 1h`, `> 730d -> 1d`.
- Fixed intervals are allowed and auto-downgraded when over yfinance intraday caps:
  - `1m<=7d`, `2m/5m/15m/30m<=60d`, `1h<=730d`, `1d` unlimited.
- For `full_max` ranges, provider forces `1d`.
- All timestamps are emitted in UTC.

## Example Bind Chains

### 1. Historical Plot Workflow

1. `Trigger Button.pulse` -> `Market Fetcher.commit`
2. `Trigger Button.pulse` -> `Market Fetcher.fetch`
3. `Market Fetcher.rows` -> `Line Plotter.rows`
4. Set `Line Plotter.x_key=x`, `y_key=y`, `series_key=series`, `x_mode=datetime`
5. Optional: set `Market Fetcher.interval=auto` (adaptive default) or fixed interval.

### 2. Research Export Workflow

1. `Market Fetcher.rows` -> `Table Export.rows`
2. `Market Fetcher.fetched` -> `Table Export.write`
3. `Market Fetcher.error` -> `Log Notes.append`

### 3. Rolling Metric Workflow

1. `Market Fetcher.latest_close` -> `Rolling Stats.value`
2. `Market Fetcher.fetched` -> `Rolling Stats.emit`
3. `Rolling Stats.mean` -> downstream analytics lane
