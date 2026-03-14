# Workflow Engineering

This guide explains how modules, ports, bindings, scheduling, persistence, and runtime diagnostics fit together so you can design workflows that stay understandable and reliable.

If you are completely new to the app, start with `resources/docs/guides/GETTING_STARTED.md`. Come back here when you want the broader mental model.

## 1. Core Model

Qt Modula is a typed directed graph runtime.

- modules are the nodes
- bindings are the edges
- outputs feed inputs
- each edge is checked against the live module contracts
- identical graph + identical input state produce deterministic scheduling behavior

Important scope rule:

- canvases are for visual organization, not runtime isolation
- one project contains one runtime graph across all canvases
- bindings can connect modules on different canvases

Operationally, a workflow succeeds when four things stay aligned:

1. the module contract is correct
2. the bind chain is explicit
3. the runtime policy matches the event rate
4. the saved project can restore and replay the same intent

## 2. The Port System

The port system is the center of Qt Modula. If you understand ports well, the rest of the program becomes predictable.

### 2.1 Ports Are Contracts

Every module publishes a `ModuleDescriptor`. Each input and output is a `PortSpec`.

Each port has a few properties that matter to workflow builders:

| Property | Meaning | Why it matters |
| --- | --- | --- |
| `key` | Stable port identifier such as `value`, `fetch`, `rows`, `error` | Bindings persist this exact key. |
| `kind` | Payload type such as `number`, `json`, `table`, `trigger` | Destination coercion and bind warnings depend on it. |
| `plane` | `data` or `control` | Tells you whether the lane carries payload or coordination intent. |
| `default` | Initial runtime value | Useful for understanding replay and idle state. |
| `bind_visibility` | `normal`, `advanced`, or `hidden` | Controls whether the bind panel shows the port by default. |

Ports are not loose UI hints. They are the canonical runtime contract used by:

- the bind panel
- binding diagnostics
- runtime delivery
- persistence replay
- dynamic contract refresh

### 2.2 Kind And Plane Are Different Things

`kind` answers "what value shape is this?"

`plane` answers "what role does this lane play?"

Most control-plane ports are `trigger` or `pulse`, but not all. For example, async modules often publish `busy` as a `boolean` control-plane output. That is still a coordination lane.

Practical rule:

- `data` answers "what should be processed?"
- `control` answers "when should something happen?"

### 2.3 Payload Kinds

Qt Modula supports these payload kinds:

- `any`
- `number`
- `integer`
- `string`
- `boolean`
- `json`
- `table`
- `trigger`
- `pulse`

Use them intentionally:

- `any` is flexible, but it gives up type clarity. Use it only when a module genuinely needs multiple payload shapes.
- `json` is for `dict`/`list` style structured payloads.
- `table` is for list-shaped row collections.
- `trigger` and `pulse` are normalized control values. In practice both coerce to `0` or `1`; the naming communicates intent.

### 2.4 Coercion Rules

Bindings are validated at creation time, but actual payload coercion happens at the destination input when a delivery arrives.

Important coercion behavior:

- `trigger` and `pulse` become `0` or `1`
- `boolean` uses deterministic truthy parsing (`"1"`, `"true"`, `"yes"`, `"on"` are true)
- `number` requires a finite float
- `integer` requires a finite float, then rounds to the nearest integer
- `string` maps `None` to `""`
- `json` accepts `dict`/`list`, or parses a JSON string; empty string becomes `{}`
- `table` accepts a `list`, or parses a JSON string list; empty string becomes `[]`

If coercion fails, the destination module rejects the input update and publishes an error. The runtime does not silently guess.

This is why a bind warning is not always wrong. A real example:

```text
Text Input.text -> JSON Project.json
```

That is a `string -> json` kind mismatch, so `Inspect Candidate` warns. But it is still a valid design when the text contains JSON, because `json` inputs are allowed to parse strings.

### 2.5 Port Visibility

Bind visibility is a UI concern, not a runtime existence concern.

- `normal`: shown in the bind panel by default
- `advanced`: hidden until `Show Advanced Ports` is enabled
- `hidden`: not offered in the bind panel

Important consequence:

- an advanced port is still a real contract port
- hiding a port does not remove the runtime behavior
- persistence still uses the real port keys, not what the UI currently shows
- some widget fields are intentionally UI-only and are not part of the bind contract at all

The default bind panel intentionally narrows the visible surface for common workflows. Expert tuning ports remain available when you need them.

Example:

- `Line Plotter.range_x_max` is shown in the widget as derived state, but it is not a bind target and is not persisted as a workflow port

### 2.6 Persistent And Transient Inputs

Modules persist only declared user-intent inputs.

That means:

- saved projects store `persistent_inputs`, not arbitrary runtime outputs
- outputs such as `result`, `rows`, `busy`, `error`, `wrote`, or `fetched` are not persisted
- on load, persisted input keys must match the current module contract exactly

This is a strict system. There is no compatibility fallback layer for old input shapes.

Design rule:

- persist stable intent
- do not design workflows that depend on transient status outputs being restored from disk

### 2.7 Dynamic Ports

Some modules can change their port contract at runtime. The canonical built-in example is `Options`.

`Options` can generate trigger inputs such as:

- `select_alpha`
- `select_beta`
- `select_alpha_beta`

These ports are derived from the normalized option list and are generated deterministically. That matters because project bindings persist exact port keys.

Dynamic-port lifecycle:

1. module state changes
2. module rebuilds its descriptor
3. runtime refreshes the live contract
4. UI bind selectors refresh
5. bindings targeting removed ports are pruned
6. pending deliveries to removed ports are cleared

Project-load rule:

- dynamic ports must be reconstructable from persisted inputs before binding replay happens

If a dynamic port no longer exists, the project cannot replay that binding.

### 2.8 Fan-Out And Fan-In

One output can feed many destinations. This is normal and often desirable.

Example:

```text
Parameter Sweep.rows -> Line Plotter.rows
Parameter Sweep.rows -> Table Export.rows
```

Many outputs can also target the same input, but this should be a deliberate design choice.

Important nuance:

- destination inputs are single slots
- deliveries arrive in runtime order
- with coalescing enabled, pending deliveries are collapsed per destination input key

So if multiple upstream sources race into the same input, "last pending value wins" may be the effective behavior. If you need explicit arbitration, use modules such as `Value Selector`, `Value Router`, `Trigger Join`, `Trigger Join N`, or `Condition Gate` instead of relying on accidental timing.

## 3. How Everything Interacts

The cleanest way to understand Qt Modula is to follow one payload through the system.

### 3.1 Binding Creation

When you create a binding in the bind panel:

1. you pick a live source module and output port
2. you pick a live destination module and input port
3. `Inspect Candidate` asks the runtime for deterministic diagnostics
4. the runtime checks:
   - unknown source or destination module
   - unknown source or destination port
   - plane mismatch
   - payload kind mismatch
   - cycle creation
5. only diagnostics with `level=error` block the binding

Meaning of diagnostics:

- `error`: the edge is invalid and cannot be created
- `warning`: the edge is allowed, but the design may be risky or coercion-dependent
- `info`: the edge is valid

Warnings are important. They are not noise. A warning means "the runtime will allow this, but you should understand exactly why."

### 3.2 Delivery Execution

When a module emits an output:

1. the module coerces the emitted value to the output port kind
2. the runtime validates the source module and output port
3. all outbound bindings for that source port are resolved
4. deliveries are enqueued with deterministic ordering keys
5. the scheduler drains the queue
6. each destination input is coerced to the destination kind
7. the destination module runs its `on_input(...)` logic
8. that module may emit more outputs and continue the chain

Deterministic ordering is based on:

1. destination topological rank
2. source emission sequence
3. binding insertion order
4. delivery serial

This is why Qt Modula can be reasoned about precisely. The scheduler is not "best effort". It is ordered by contract.

### 3.3 Queue Policy

Runtime policy controls bounded behavior under load.

Default project policy:

- `max_queue_size = 100000`
- `coalesce_pending_inputs = true`
- `max_deliveries_per_batch = 250000`

What each knob means:

- `coalesce_pending_inputs=true`: if several deliveries are waiting for the same destination input, only the latest pending value is kept
- `max_queue_size`: hard upper bound on pending deliveries
- `max_deliveries_per_batch`: hard upper bound on one drain cycle

Use coalescing when latest value wins. Disable it when every intermediate event matters.

### 3.4 Failure Surfaces

Failures can appear in three places:

1. bind time
   - invalid edge, unknown port, cycle rejection
2. delivery time
   - queue overflow, module failure, internal runtime failure
3. module logic
   - coercion errors, provider failures, export failures, validation warnings

In practical workflow design, you usually observe failures through module outputs:

- `error`
- `text`
- `busy`
- `blocked`
- `exhausted`
- `done`
- `wrote`
- `exported`

Treat these as first-class ports, not cosmetic add-ons.

### 3.5 Persistence And Replay

Project load is staged, strict, and deterministic.

High-level load flow:

1. validate project schema and semantic constraints
2. build a staged runtime with the saved runtime policy
3. construct modules
4. restore persisted inputs
5. register modules so their live contracts exist
6. apply bindings against those live contracts
7. swap the staged runtime into the UI
8. replay module state in deterministic runtime order

This has a major design consequence:

- project saves must describe reusable intent, not incidental temporary state

If you need a workflow to come back exactly after load, make sure the important behavior is implied by persisted inputs plus deterministic replay.

### 3.6 UI, Runtime, And Autosnapshots

The UI is not a separate execution model. Widget edits and bound deliveries both go through the same module input machinery.

Also:

- persistent input changes notify runtime listeners
- the main window uses those notifications to mark the project dirty
- autosnapshots capture the updated project state

This is why stable persistent inputs matter so much. They are the bridge between live editing and durable project state.

## 4. Beginner Workflow Engineering

Beginner workflow engineering is about discipline, not complexity. Small clean graphs beat clever dense graphs.

### 4.1 Beginner Rules

1. Separate data lanes from control lanes.
2. Use explicit trigger modules when timing matters.
3. Connect `error` and `text` early so you can see what the graph is doing.
4. Prefer one clear writer per destination input.
5. Leave `Show Advanced Ports` off unless you know exactly why you need a hidden surface.
6. Save and reload early. Do not wait until the workflow is large.

### 4.2 Beginner Pattern: Live Mirror

Use this to understand direct value propagation.

```text
Text Input.text -> Value View.value
Text Input.text -> Value View.text
```

What it teaches:

- bindings are directional
- one output can fan out to multiple destinations
- simple data-only lanes do not need explicit triggers

### 4.3 Beginner Pattern: Triggered Arithmetic

Use this when values should change freely, but computation should happen only on demand.

Configuration:

- `Arithmetic.auto = false`
- `Trigger Mapper.channel = evaluate`

Bind chain:

```text
Number Input A.value -> Arithmetic.a
Number Input B.value -> Arithmetic.b
Trigger Button.pulse -> Trigger Mapper.trigger
Trigger Mapper.evaluate -> Arithmetic.evaluate
Arithmetic.result -> Value View.value
Arithmetic.text -> Value View.text
```

Why this matters:

- the data lane (`a`, `b`) is separate from the control lane (`evaluate`)
- the workflow stays readable because the trigger intent is named
- changing inputs does not immediately recompute the result

### 4.4 Beginner Pattern: JSON To Table Pipeline

Use this to learn structured payload flow.

Configuration:

- put valid JSON into `Text Input.text`
- set `JSON Project.mapping` to explicit paths
- leave `JSON Project.auto = true` while learning

Bind chain:

```text
Text Input.text -> JSON Project.json
JSON Project.record -> Table Buffer.row
JSON Project.projected -> Table Buffer.append
Table Buffer.rows -> Table Metrics.rows
Table Metrics.text -> Log Notes.append
```

This pattern is important because it shows three real rules at once:

- warning diagnostics can still represent intentional designs (`string -> json`)
- a buffer creates a stable state boundary
- analytics modules are useful as observability, not just final outputs

### 4.5 Beginner Pattern: Operator-Managed Options

Use this to understand dynamic ports.

Configuration:

- create options such as `Alpha` and `Beta`
- enable `Show Advanced Ports` to see generated `select_<slug>` inputs

Bind chain:

```text
Trigger Button (Select Alpha).pulse -> Options.select_alpha
Trigger Button (Select Beta).pulse -> Options.select_beta
Options.selected -> Value View.text
Options.changed -> Value View.value
```

What it teaches:

- some bindable ports do not exist until module state creates them
- advanced ports are still real contract ports
- removing an option removes its generated port and prunes bindings to it

You can watch this behavior directly in the app: add or remove options, then reopen the bind surface and confirm the generated ports appear or disappear with the saved option list.

## 5. Professional Workflow Engineering

Professional workflow engineering is mostly about making the graph predictable under stress, change, and replay.

### 5.1 Design In Three Lanes

Most production workflows are easiest to reason about when split into three lane types:

1. data lane
   - values, JSON, tables, selected records
2. control lane
   - fetch, run, evaluate, append, write, done, blocked
3. observability lane
   - text, error, busy, counts, status metrics

If a workflow is hard to debug, it is usually because one of these lanes is hidden or overloaded.

### 5.2 Choose Between Auto And Explicit Control

Many modules offer both:

- automatic behavior on data updates
- explicit control-plane triggers such as `emit`, `evaluate`, `run`, `append`, or `write`

Choose intentionally:

- use `auto=true` for simple low-rate transformations
- use explicit triggers when batching, gating, retrying, or exporting
- do not mix auto and explicit control casually in the same stage unless you want both behaviors

### 5.3 Put State Boundaries In Obvious Places

Useful state-boundary modules include:

- `Table Buffer`
- `Value Latch`
- `Options`
- provider modules with explicit `commit`/`fetch`

State boundaries help because they make it clear:

- what is cached
- what is merely passing through
- what will be replayed from persisted intent

### 5.4 Use Gates Before Side Effects

Never put a write, export, or external request behind an ambiguous trigger path.

Preferred pattern:

```text
upstream data -> transform/buffer
upstream readiness -> gate/join/rate-limit
gate output -> write/fetch/export trigger
```

Modules that make this explicit:

- `Condition Gate`
- `Trigger Join`
- `Trigger Join N`
- `Trigger Debounce`
- `Trigger Rate Limit`
- `Circuit Breaker`
- `Retry Controller`

### 5.5 Understand Coalescing Before You Tune It

With coalescing enabled, the runtime keeps only the latest pending value per destination input.

This is excellent for:

- live UI mirrors
- latest-value indicators
- rapidly updating numeric lanes
- redraw-style sinks

It is dangerous for:

- event logs where every event matters
- append-style workflows
- retry accounting
- workflows that intentionally depend on intermediate pulses

Professional rule:

- if the workflow represents a stream of distinct events, validate behavior with coalescing both on and off

The key question is simple: does the workflow need every event, or only the latest pending state?

### 5.6 Avoid Implicit Fan-In

Feeding several upstream outputs into the same destination input is legal, but usually not readable enough for production.

Prefer explicit arbiters:

- `Value Selector` for two-lane value choice
- `Value Router` for N-way value choice
- `Trigger Join` or `Trigger Join N` for readiness barriers
- `Condition Gate` for predicate-controlled branching

If you cannot explain which source should win and why, you do not yet have a production-safe fan-in design.

### 5.7 Treat Async Modules As Contracts

Providers and export modules are not special exceptions to workflow discipline. They are contract-driven stages with:

- trigger inputs
- `busy` coordination outputs
- success outputs such as `fetched`, `wrote`, or `exported`
- failure outputs such as `error`
- status summaries in `text`

Professional rule:

- always wire at least one observability sink into async lanes during development

Common choices:

- `Log Notes`
- `Value View`
- downstream status dashboards

### 5.8 Do Not Stack Retry Systems Blindly

Some providers already support internal retries. Qt Modula also gives you external workflow-level retry tools.

Be deliberate:

- provider-local retries are useful for small transient transport failures
- `Retry Controller` is useful when you want the graph to own retry timing and observability
- `Circuit Breaker` is useful when repeated failures should temporarily stop new requests

If you use external retry orchestration, consider reducing the provider's own retry count so the graph remains the authoritative control path.

### 5.9 Design For Replay

Professional replay discipline means:

- persistent inputs describe the workflow's intended configuration
- dynamic ports can be rebuilt deterministically from saved inputs
- important outputs can be recomputed from replayed state
- transient errors and busy flags are not required for correctness

Replay is easiest to reason about when you can point to the exact persisted inputs that reconstruct the workflow's operating state.

### 5.10 Use Canvases For Separation Of Concerns

Because canvases are organizational only, use them to separate concerns visually:

- ingest
- transform
- analytics
- export
- operations

Do not assume a second canvas means a second runtime. It does not.

## 6. Real Bind Chain Examples

The following chains use real modules and real port names from the built-in module set. They are meant to be built directly.

### 6.1 Triggered Math With Post-Compute Gate

Use this pattern when one manual trigger should coordinate both computation and a downstream decision.

Configuration:

- `Arithmetic.op = mul`
- `Condition Gate.operator = gte`
- `Condition Gate.b = 8`

Bind chain:

```text
Number Input.value -> Arithmetic.a
Number Input.value -> Arithmetic.b
Trigger Button.pulse -> Arithmetic.evaluate
Arithmetic.result -> Condition Gate.a
Trigger Button.pulse -> Condition Gate.evaluate
Condition Gate.passed -> Value View.value
```

Why it is useful:

- one trigger can coordinate multiple downstream stages
- a compute stage and a decision stage stay separate
- only passing values reach the sink

### 6.2 Table Buffer -> Transform -> Metrics

Use this pattern when you want a stable table state before analytics or export.

Configuration:

- `Table Transform.filter_key = kind`
- `Table Transform.filter_value = keep`

Bind chain:

```text
Table Buffer.rows -> Table Transform.rows
Table Transform.rows -> Table Metrics.rows
```

Typical upstream row intake:

```text
JSON Project.record -> Table Buffer.row
JSON Project.projected -> Table Buffer.append
```

Why it is useful:

- the buffer owns mutable table state
- the transform owns deterministic shape changes
- metrics give you a cheap validation lane before export

### 6.3 Parameter Sweep -> Plot -> Export

Use this chain when one research run should feed both analysis and artifact generation.

Configuration:

- `Trigger Mapper.channel = run`
- `Line Plotter.x_key = x`
- `Line Plotter.y_key = result`
- `Table Export.mode = overwrite`

Bind chain:

```text
Trigger Button.pulse -> Trigger Mapper.trigger
Trigger Mapper.run -> Parameter Sweep.run
Parameter Sweep.rows -> Line Plotter.rows
Parameter Sweep.rows -> Table Export.rows
Parameter Sweep.done -> Table Export.overwrite
Line Plotter.hover_x -> Value View (X).value
Line Plotter.hover_y -> Value View (Y).value
```

Why it is useful:

- one research run feeds both analytics and export
- the export is explicitly tied to sweep completion
- hover outputs create a second inspection workflow without modifying the primary plot lane

### 6.4 Dynamic Option Selection -> Market Fetcher

This example shows how dynamic ports interact with a provider lane.

Configuration:

- populate `Options` with symbols such as `AAPL`, `MSFT`, `NVDA`
- `Market Fetcher.auto_fetch = true`
- `Line Plotter.x_key = x`
- `Line Plotter.y_key = y`
- `Line Plotter.series_key = series`
- `Line Plotter.x_mode = datetime`

Bind chain:

```text
Trigger Button (AAPL).pulse -> Options.select_aapl
Trigger Button (MSFT).pulse -> Options.select_msft
Options.selected -> Market Fetcher.symbol
Options.changed -> Market Fetcher.commit
Market Fetcher.rows -> Line Plotter.rows
Market Fetcher.error -> Log Notes.append
```

Why it is useful:

- operator selection is explicit and bindable
- dynamic option ports drive a real provider workflow
- `commit` stays visible as the control boundary before fetch

### 6.5 Resilient HTTP Ingest Lane

This is a production-style request design using explicit retry and breaker control.

Recommended settings:

- set `HTTP Request.retries` low, or to `0`, if `Retry Controller` is the main retry owner
- set `Condition Gate.operator = truthy`
- leave `Condition Gate.auto = true`

Bind chain:

```text
Trigger Button.pulse -> Circuit Breaker.request
Circuit Breaker.allow -> Retry Controller.request
Retry Controller.attempt -> HTTP Request.fetch
HTTP Request.fetched -> Retry Controller.success
HTTP Request.fetched -> Circuit Breaker.success
HTTP Request.error -> Condition Gate.value
Condition Gate.on_true -> Retry Controller.failure
Retry Controller.exhausted -> Circuit Breaker.failure
HTTP Request.json -> JSON Project.json
HTTP Request.fetched -> JSON Project.emit
JSON Project.record -> Table Buffer.row
JSON Project.projected -> Table Buffer.append
Circuit Breaker.text -> Log Notes.append
Retry Controller.text -> Log Notes.append
HTTP Request.error -> Log Notes.append
```

Why it is useful:

- request permission, retry policy, and provider execution are separate stages
- terminal retry exhaustion feeds breaker state explicitly
- success and failure remain visible as first-class ports
- the normalized payload lane can continue downstream into analytics or export stages

### 6.6 Approval Barrier Before Export

This is a clean pattern when an export should happen only after both fresh data and operator approval exist.

Bind chain:

```text
Market Fetcher.rows -> Table Export.rows
Market Fetcher.fetched -> Trigger Join.left
Trigger Button.pulse -> Trigger Join.right
Trigger Join.joined -> Table Export.overwrite
Table Export.text -> Log Notes.append
```

Why it is useful:

- the export trigger is not hidden inside the provider
- one signal means "data is ready"
- one signal means "operator approves"
- the join makes the barrier explicit

## 7. Anti-Patterns

Avoid these unless you have a very specific, tested reason:

- using one destination input as an accidental merge point for unrelated sources
- hiding control flow inside auto modes when the operation is expensive or external
- ignoring bind warnings without understanding destination coercion behavior
- routing high-frequency trigger bursts directly into exports or providers
- assuming canvases isolate runtime behavior
- depending on transient outputs to be restored from saved projects
- generating dynamic ports from unstable or non-persisted state
- stacking provider retries, retry controllers, and breaker logic without a clear ownership model

## 8. Workflow Review Checklist

Use this before you call a workflow complete:

1. Every important side effect has an explicit control path.
2. Data, control, and observability lanes are all visible somewhere in the graph.
3. Bind warnings are either eliminated or consciously accepted.
4. Dynamic ports are deterministic and replay-safe.
5. Runtime policy matches the expected event rate.
6. Save/load replay has been tested on the actual project.
7. `error`, `text`, and `busy` outputs are routed where operators can see them.
8. Cross-canvas bindings are intentional, not accidental.
9. Exports and provider calls are protected from bursty or ambiguous triggers.
10. The graph still makes sense when read left-to-right by another person.

Mastery in Qt Modula is not about building the largest graph. It is about building the smallest graph that makes every dependency, state boundary, and failure path explicit.
