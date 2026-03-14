# Rolling Stats Module

## Purpose

`Rolling Stats` is a built-in `Analytics` module in Qt Modula.

- Module type: `rolling_stats`
- Family: `Analytics`
- Capabilities: `transform, sink`

## Typical Use Cases

- Compute rolling aggregate statistics on value streams.
- Feed smoothed metrics into alerts, gates, and plot overlays.
- Monitor central tendency/dispersion trends in real time.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `value` | `number` | `data` | no | Default: `0.0` |
| `window` | `integer` | `data` | yes | Default: `32` |
| `reset` | `trigger` | `control` | no | Default: `0` |
| `emit` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `mean` | `number` | `data` | Default: `0.0` |
| `stddev` | `number` | `data` | Default: `0.0` |
| `min` | `number` | `data` | Default: `0.0` |
| `max` | `number` | `data` | Default: `0.0` |
| `count` | `integer` | `data` | Default: `0` |
| `ready` | `trigger` | `control` | Default: `0` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Market Fetcher.latest_close` -> `Rolling Stats.value`
2. `Rolling Stats.mean` -> `Line Plotter.row` (via projection/buffer)
3. `Rolling Stats.error` -> `Log Notes.append`
