# HTTP Request Module

## Purpose

`HTTP Request` is a built-in `Providers` module in Qt Modula.

- Module type: `http_request`
- Family: `Providers`
- Capabilities: `provider, source`

## Typical Use Cases

- Fetch structured JSON/text payloads from external APIs.
- Drive provider-normalization pipelines with retry-aware async I/O.
- Integrate custom internal services into deterministic workflows.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `url` | `string` | `data` | yes | Default: `"https://httpbin.org/get"` |
| `method` | `string` | `data` | yes | Default: `"GET"` |
| `params` | `json` | `data` | yes | Default: `{}` |
| `headers` | `json` | `data` | yes | Default: `{}` |
| `body` | `json` | `data` | yes | Default: `{}` |
| `timeout_s` | `number` | `data` | yes | Default: `10.0` |
| `retries` | `integer` | `data` | yes | Default: `2` |
| `fetch` | `trigger` | `control` | no | Default: `0` |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `status_code` | `integer` | `data` | Default: `0` |
| `elapsed_ms` | `integer` | `data` | Default: `0` |
| `text` | `string` | `data` | Default: `""` |
| `json` | `json` | `data` | Default: `{}` |
| `busy` | `boolean` | `control` | Default: `false` |
| `fetched` | `trigger` | `control` | Default: `0` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Use `error` and `text` outputs as primary observability lanes where provided.

## Example Bind Chain

1. `Trigger Mapper.fetch` -> `HTTP Request.fetch`
2. `HTTP Request.json` -> `JSON Project.json`
3. `HTTP Request.fetched` -> `JSON Project.emit`
