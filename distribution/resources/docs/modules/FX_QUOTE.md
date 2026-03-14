# FX Quote Module

## Purpose

`FX Quote` is a built-in `Providers` module in Qt Modula.

- Module type: `fx_quote`
- Family: `Providers`
- Capabilities: `provider, source`

## Typical Use Cases

- Periodic FX polling for currency conversion dashboards.
- Real-time pricing lanes feeding analytics and table export paths.
- Reference rates for downstream valuation formulas.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `from_currency` | `string` | `data` | yes | Default: `"USD"` |
| `to_currency` | `string` | `data` | yes | Default: `"EUR"` |
| `fetch` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `rate` | `number` | `data` | Default: `0.0` |
| `inverse_rate` | `number` | `data` | Default: `0.0` |
| `from_currency` | `string` | `data` | Default: `""` |
| `to_currency` | `string` | `data` | Default: `""` |
| `pair` | `string` | `data` | Default: `""` |
| `change` | `number` | `data` | Default: `0.0` |
| `change_pct` | `number` | `data` | Default: `0.0` |
| `as_of` | `string` | `data` | Default: `""` |
| `source_symbol` | `string` | `data` | Default: `""` |
| `quote` | `json` | `data` | Row payload for plotting/buffering (`x`, `y`, `series`, and quote fields). |
| `provider` | `string` | `data` | Default: `""` |
| `text` | `string` | `data` | Default: `""` |
| `busy` | `boolean` | `control` | Default: `false` |
| `fetched` | `trigger` | `control` | Default: `0` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Quote source is Yahoo Finance via `yfinance`; `source_symbol` exposes the resolved ticker.
- `quote.x` is fetch-time (`sampled_at`) so live plots advance each poll; provider timestamp remains in `quote.as_of`.
- `quote` output is bind-ready for `Line Plotter.row` and `Table Buffer.row`.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Interval Pulse.pulse` -> `FX Quote.fetch`
2. `FX Quote.quote` -> `Line Plotter.row`
3. `FX Quote.fetched` -> `Line Plotter.append`
4. Set `Line Plotter.x_key=x`, `y_key=y`, `series_key=series`, `x_mode=datetime`
5. `FX Quote.error` -> `Log Notes.append`
