# Getting Started

This guide is for people who are new to Qt Modula.

It focuses on practical skills:

- understanding how modules, ports, and bindings work
- practicing standard workflow patterns
- learning to debug common mistakes
- building confidence through repeatable, hands-on exercises

By the end, you should be able to build and troubleshoot small-to-medium workflows without guessing.

## Before You Start

- Make sure this distribution folder still contains `qt-modula.app`, `modules/`, `saves/`, and `resources/`.
- Launch the app from the distribution root:

```bash
open qt-modula.app
```

- Start with a fresh canvas (`Canvas 1` is created by default).
- Keep the `Bind Chains` panel visible while practicing.
- Leave `Show Advanced Ports` disabled while learning core workflows (enable it later when needed).

## What You Are Building

A Qt Modula workflow is a directed graph:

- modules are the nodes
- bindings are the edges
- outputs feed inputs
- control-plane pulses tell modules when to act

A useful mental model:

- data ports carry values (`number`, `string`, `json`, `table`)
- control ports carry intent (`trigger`, `pulse`)

Most robust workflows separate these lanes:

- data lane: what to process
- control lane: when to process

## UI Orientation (Quick)

### Module Palette

Use this panel to add modules to the active canvas.

### Canvas

This is where module cards live. You can open multiple canvases for separate workflows.

### Bind Chains Panel

Use this panel to create and inspect bindings:

1. choose source module and source port
2. choose destination module and destination port
3. click `Inspect Candidate` (recommended)
4. click `Create Binding`

If a binding is invalid (for example, would create a cycle), the runtime rejects it.

## Core Terms You Will Use

- `Module`: a unit of behavior (for example `Arithmetic`, `JSON Project`, `Table Export`).
- `Port`: named input/output lane on a module.
- `Binding`: one directed connection from output port to input port.
- `Bind chain`: multiple bindings that form an end-to-end workflow.
- `Data plane`: payload values.
- `Control plane`: triggers/pulses for coordination.

## Learning Path

Work through the exercises in order. Each one introduces one new concept and reuses earlier concepts.

Estimated time: 60-120 minutes.

## Exercise 1: Your First Binding (Live Data)

Goal: see immediate value propagation.

### Modules to Add

- `Text Input`
- `Value View`

### Bindings

1. `Text Input.text` -> `Value View.value`
2. `Text Input.text` -> `Value View.text`

### What to Do

- Type into `Text Input`.
- Observe `Value View` reflect the value.

### What You Learn

- a binding is directional
- data ports can fan out to multiple destinations
- simple workflows can be live-updating without explicit triggers

### Common Issues

- No output changes: verify source/destination module selection in bind panel.
- Wrong destination port: check that destination input exists.

## Exercise 2: Data Lane + Control Lane (Triggered Math)

Goal: separate values from execution timing.

### Modules to Add

- `Number Input` (rename mentally as `A`)
- `Number Input` (rename mentally as `B`)
- `Arithmetic`
- `Trigger Button`
- `Trigger Mapper`
- `Value View`

### Configure Modules

- `Arithmetic.auto = false`
- `Arithmetic.op = add` (or any operator you want to test)
- `Trigger Mapper.channel = evaluate`
- optional: `Trigger Button.label = Run`

### Bindings

1. `Number Input (A).value` -> `Arithmetic.a`
2. `Number Input (B).value` -> `Arithmetic.b`
3. `Trigger Button.pulse` -> `Trigger Mapper.trigger`
4. `Trigger Mapper.evaluate` -> `Arithmetic.evaluate`
5. `Arithmetic.result` -> `Value View.value`
6. `Arithmetic.text` -> `Value View.text`

### What to Do

- change `A` and `B` values
- click the trigger button
- observe result updates only when triggered

### What You Learn

- data inputs can change without recomputing
- control lane decides evaluation timing
- `Trigger Mapper` makes control intent explicit (`evaluate`, `fetch`, `run`, etc.)

## Exercise 3: Scheduled Workflows (Timer-Driven Chain)

Goal: replace manual triggers with a deterministic schedule.

### Modules to Add

- `Interval Pulse`
- `Trigger Mapper`
- reuse `Arithmetic` from Exercise 2 (or create a new one)

### Configure Modules

- `Interval Pulse.interval_ms = 1000`
- `Interval Pulse.fire_immediately = true` (optional)
- `Trigger Mapper.channel = evaluate`

### Bindings

1. `Interval Pulse.pulse` -> `Trigger Mapper.trigger`
2. `Trigger Mapper.evaluate` -> `Arithmetic.evaluate`

### What to Do

- enable/start `Interval Pulse`
- watch `Arithmetic` recompute every interval
- change input values while running

### What You Learn

- scheduler modules drive repeatable periodic behavior
- timing logic belongs in explicit modules, not hidden side effects

### Practical Tip

For fast intervals, keep workflows lightweight and consider runtime coalescing settings.

## Exercise 4: Change Detection (Reduce Noise)

Goal: avoid expensive downstream work when values are effectively unchanged.

### Modules to Add

- `Number Input`
- `Value Change Gate`
- `Value View`

### Configure Modules

- `Value Change Gate.epsilon = 0.5`
- `Value Change Gate.auto = true`
- `Value Change Gate.emit_initial = true`

### Bindings

1. `Number Input.value` -> `Value Change Gate.value`
2. `Value Change Gate.value` -> `Value View.value`
3. `Value Change Gate.text` -> `Value View.text`

### What to Do

- adjust the number by small increments (for example `+0.1`)
- then large increments (for example `+1.0`)
- observe `change_count` and status text behavior

### What You Learn

- epsilon-aware gating can suppress noisy updates
- change filtering is a standard pattern before expensive modules

## Exercise 5: Offline JSON Shaping Pipeline

Goal: build a realistic transform chain without external services.

### Modules to Add

- `Text Input` (JSON source)
- `JSON Project`
- `Table Buffer`
- `Table Metrics`
- `Trigger Button` (append control)
- `Value View`

### Configure Modules

In `Text Input.text`, enter valid JSON:

```json
{"symbol":"AAPL","price":198.52,"time":"2026-03-09T10:00:00Z"}
```

In `JSON Project.mapping`, enter:

```text
symbol=$.symbol
price=$.price
time=$.time
```

Other settings:

- `JSON Project.auto = true`
- `JSON Project.strict = true` (recommended while learning)
- `Table Buffer.max_rows = 100`

### Bindings

1. `Text Input.text` -> `JSON Project.json`
2. `JSON Project.record` -> `Table Buffer.row`
3. `Trigger Button.pulse` -> `Table Buffer.append`
4. `Table Buffer.rows` -> `Table Metrics.rows`
5. `Table Metrics.row_count` -> `Value View.value`
6. `Table Metrics.text` -> `Value View.text`

### What to Do

- edit JSON payload values in `Text Input`
- click append trigger each time you want to commit a row
- observe row counts and metric summaries

### What You Learn

- JSON strings can feed JSON ports
- projection and buffering are separate responsibilities
- explicit append triggers prevent accidental row growth

### Common Issues

- `JSON Project.error` populated: check JSON validity and mapping paths.
- append does nothing: ensure `Table Buffer.row` is receiving a valid object.

## Exercise 6: Export a Workflow Result

Goal: write your buffered data to disk.

### Modules to Add

- `Table Export`
- `Trigger Button` (write control)
- optional `Value View` or `Log Notes` for status

### Configure Modules

- `Table Export.file_name = beginner_rows`
- `Table Export.format = jsonl`
- `Table Export.mode = overwrite` (start simple)

### Bindings

1. `Table Buffer.rows` -> `Table Export.rows`
2. `Trigger Button.pulse` -> `Table Export.write`
3. `Table Export.text` -> `Value View.text` (or `Log Notes.append`)
4. `Table Export.path` -> `Value View.value`

### What to Do

- append a few rows in Exercise 5
- trigger write
- verify status text and output path

### What You Learn

- sink modules are usually controlled by explicit triggers
- export status should be treated as part of your workflow observability

## Optional Exercise 7: Online Provider Pipeline

Goal: practice a standard provider chain.

Requires internet connectivity.

### Modules to Add

- `Trigger Button`
- `Trigger Mapper`
- `HTTP Request`
- `JSON Project`
- `Table Buffer`

### Configure Modules

- `Trigger Mapper.channel = fetch`
- `HTTP Request.url = https://httpbin.org/get`
- `JSON Project.mapping` example:

```text
url=$.url
origin=$.origin
```

- `JSON Project.auto = true`

### Bindings

1. `Trigger Button.pulse` -> `Trigger Mapper.trigger`
2. `Trigger Mapper.fetch` -> `HTTP Request.fetch`
3. `HTTP Request.json` -> `JSON Project.json`
4. `JSON Project.record` -> `Table Buffer.row`
5. `HTTP Request.fetched` -> `Table Buffer.append`

### What You Learn

- provider modules are usually driven by control pulses
- transform + buffer pattern makes downstream usage predictable

## Debugging Checklist (Beginner-Friendly)

When a chain does not behave as expected:

1. inspect candidate bindings before creating them
2. verify source and destination ports are correct
3. check plane intent (`data` vs `control`)
4. check destination module `text` and `error` outputs
5. verify trigger path actually fires
6. verify payload path actually updates

A strong workflow has both:

- clear data path
- clear trigger path

## Common Beginner Mistakes

### Mistake: Binding only data, no trigger

Symptom: values update but computation/action never runs.

Fix: add explicit control binding (for example `Trigger Mapper.evaluate` -> `Arithmetic.evaluate`).

### Mistake: Triggering append/write too often

Symptom: duplicate rows/files or unexpected churn.

Fix: make trigger sources intentional; use manual trigger while learning.

### Mistake: Ignoring module status outputs

Symptom: uncertain why chain failed.

Fix: bind `text`/`error` outputs into `Value View` or `Log Notes` during development.

### Mistake: Overbuilding on one canvas

Symptom: hard-to-read and hard-to-debug graph.

Fix: split workflows by purpose across canvases.

## Practice Challenges

After finishing the core exercises, try these:

1. Replace manual append with `Interval Pulse` at 2s cadence.
2. Insert `Value Change Gate` before export to reduce write noise.
3. Add `Text Export` to write a human-readable run summary after each table export.
4. Build two separate canvases: one for ingestion, one for reporting.

## What to Learn Next

- workflow patterns and operational discipline:
  - `resources/docs/guides/WORKFLOW_ENGINEERING.md`
- module contract details:
  - `resources/docs/modules/MODULE_CATALOG.md`
- runtime and typing model:
  - `resources/docs/platform/RUNTIME_CONTRACTS.md`

## Final Notes

- Start with explicit, simple chains.
- Keep data and control lanes separate.
- Build in observability (`text` / `error`) while developing.
- Once behavior is stable, then optimize for speed and scale.

That approach produces workflows that are easy to understand, easier to debug, and safer to extend.
