# Text Export Module

## Purpose

`Text Export` writes textual payloads to `.txt`, `.docx`, or `.json` targets with workflow-friendly trigger controls, append/overwrite modes, and deterministic async failure behavior.

- Module type: `text_export`
- Family: `Export`
- Capabilities: `sink`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `text` | `string` | `data` | no | Primary payload buffer. |
| `append_text` | `string` | `data` | no | Concatenates into `text` buffer, then clears itself. |
| `file_name` | `string` | `data` | yes | Export stem; sanitized and defaulted to `notes`. |
| `export_folder` | `string` | `data` | yes | Optional subfolder under `saves/exports`. |
| `extension` | `string` | `data` | yes | Normalized to `txt`, `docx`, or `json`; invalid values fallback with warning. |
| `mode` | `string` | `data` | yes | Normalized to `overwrite` or `append`; invalid values fallback with warning. |
| `tag` | `string` | `data` | no | Optional suffix in output filename stem (`_<tag>`). |
| `section_title` | `string` | `data` | no | Section heading for append flows and unbound JSON mode. |
| `auto_write` | `boolean` | `data` | no | If true, text updates immediately trigger writes. |
| `json_dictionary_bound` | `boolean` | `data` | yes | JSON mode: treat `text` as full object payload. |
| `json_key_conflict` | `string` | `data` | yes | JSON append conflict policy: `overwrite`, `error`, `skip` (invalid values warn + fallback). |
| `json_duplicate_keys` | `string` | `data` | yes | Bound JSON duplicate policy: `error`, `last_wins` (invalid values warn + fallback). |
| `write` | `trigger` | `control` | no | Start export with configured mode. |
| `export` | `trigger` | `control` | no | Alias for `write`. |
| `overwrite` | `trigger` | `control` | no | One-shot mode override. |
| `append` | `trigger` | `control` | no | One-shot mode override. |
| `refresh` | `trigger` | `control` | no | Recompute status preview only. |
| `clear` | `trigger` | `control` | no | Clears transient text/tag/section fields and status outputs; normalization warnings remain until corrected inputs are set. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `path` | `string` | `data` | Final resolved file path. |
| `wrote` | `trigger` | `control` | Pulses when write occurs; `0` for no-op writes. |
| `busy` | `boolean` | `control` | True while async writer is executing. |
| `text` | `string` | `data` | Status summary or deterministic error summary. |
| `error` | `string` | `data` | Failure message or deterministic input-normalization warning (`""` when clean). |
| `char_count` | `integer` | `data` | Total chars in resulting stored content. |
| `line_count` | `integer` | `data` | Total line count in resulting stored content. |

## Input Normalization Warnings

- Invalid `extension` falls back to `txt`.
- Invalid `mode` falls back to `overwrite`.
- Invalid `json_key_conflict` falls back to `overwrite`.
- Invalid `json_duplicate_keys` falls back to `error`.
- Multiple warnings are joined deterministically with `;`.

## Path Resolution

Target path format:

`saves/exports[/<export_folder>]/<file_name>[_<tag>].<extension>`

`file_name`, `export_folder`, and `tag` are sanitized by shared path utilities.

## Text and DOCX Behavior

### Overwrite

- Replaces target content with normalized payload.

### Append

- Appends payload to existing content.
- If `section_title` is present:
  - inserts a blank separation and heading before appended text.
- Newline policy for text payloads is normalized to LF (`\n`).

## JSON Behavior

### Dictionary-Bound Mode (`json_dictionary_bound=true`)

- `text` must parse as a JSON object.
- Duplicate key handling:
  - `error`: reject duplicates.
  - `last_wins`: parser accepts last occurrence.

### Unbound Mode (`json_dictionary_bound=false`)

- Incoming payload is `{section_title: text}`.
- `section_title` is required. If absent, module performs a deterministic no-op and reports it.

### JSON Append Conflict Policies

- `overwrite`: incoming keys replace existing keys.
- `error`: fail if any incoming key exists.
- `skip`: keep existing keys, only add new keys.

Writer returns no-op (`wrote=0`) when append result does not change file content.

## Async and Error Policy

Uses shared async framework and applies deterministic stale-output clearing on failures:

- `path=""`
- `char_count=0`
- `line_count=0`
- `wrote=0`

`busy` is guaranteed to return `False` after completion/failure.

## Persistence

Persisted keys:

- `file_name`
- `export_folder`
- `extension`
- `mode`
- `json_dictionary_bound`
- `json_key_conflict`
- `json_duplicate_keys`

Non-persisted:

- `text`
- `append_text`
- `tag`
- `section_title`
- `auto_write`
- transient status outputs

## Recommended Bind Chains

### Operational Notes Stream

1. diagnostic text -> `Text Export.text`
2. periodic/manual trigger -> `Text Export.append`

### Structured JSON Log

1. set `extension=json`
2. choose bound/unbound mode by workflow contract
3. trigger append/overwrite lanes explicitly

### Immediate Mirror Mode

- Enable `auto_write=true` only when high write frequency is acceptable.

## Operational Guidance

- Keep JSON mode explicit; route `error` to observability sinks.
- Use `clear` to reset transient UI text/section/tag state between runs.
- Prefer append mode for cumulative operator logs and overwrite for canonical artifacts.
