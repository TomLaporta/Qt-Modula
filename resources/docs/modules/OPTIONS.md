# Options Module

## Purpose

`Options` is a built-in `Control` module in Qt Modula.

- Module type: `options`
- Family: `Control`
- Capabilities: `source, scheduler`

## Typical Use Cases

- Build and maintain a runtime-selectable list from operator-entered values.
- Route the selected option to downstream modules through an explicit emit lane.
- Check whether an incoming value currently exists in the maintained option list.

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `entry` | `string` | `data` | yes | Default: `""` |
| `add` | `trigger` | `control` | no | Default: `0` |
| `options` | `json` | `data` | yes | Default: `[]` |
| `selected` | `string` | `data` | yes | Default: `""` |
| `auto` | `boolean` | `data` | yes | Default: `true`; auto-emits on selected option changes |
| `value` | `string` | `data` | yes | Default: `""` |
| `emit` | `trigger` | `control` | no | Default: `0` |
| `select_<slug>` | `trigger` | `control` | no | Dynamic: one trigger input is generated for each option value |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `selected` | `string` | `data` | Default: `""` |
| `options` | `json` | `data` | Default: `[]` |
| `in_list` | `boolean` | `data` | Default: `false` |
| `changed` | `trigger` | `control` | Default: `0` |
| `text` | `string` | `data` | Default: `""` |
| `error` | `string` | `data` | Default: `""` |

## Runtime Notes

- Control-plane inputs react to truthy trigger values.
- Persisted inputs are restored from project snapshots.
- Added options are normalized by trimming whitespace and removing empty/duplicate entries, then sorted alphabetically (case-insensitive).
- `selected` accepts option text; values not present in the list emit deterministic errors.
- `auto` defaults to `true`; when enabled, selection changes from `selected`, `select_<slug>`, or `add` trigger `changed`.
- Right-clicking the dropdown selection exposes a delete action for the current option.
- Each option generates a bindable trigger input (`select_<slug>`). Triggering that input selects the matching option.
- Dynamic option input ports are rebuilt during project load before bindings are applied.
- Dynamic input key generation is deterministic from the normalized `options` list.
- Deleting an option removes its `select_<slug>` input and runtime contract refresh drops bindings targeting that removed input.
- `value` is checked against the normalized option list and published through `in_list`.

## Project Binding Persistence

- Bindings to dynamic option inputs persist as ordinary `BindingSnapshot.dst_port` keys.
- On load, restoring `options` reconstructs the same `select_<slug>` ports before binding replay.
- If an option is removed at runtime and its dynamic input port disappears, runtime contract refresh
  removes bindings targeting that removed port.

## Example Bind Chain

1. `Text Input.text` -> `Options.entry`
2. `Trigger Button.pulse` -> `Options.add`
3. `Options.selected` -> downstream consumer input
4. `Text Input.text` -> `Options.value`
5. `Options.in_list` -> `Value View.value`
