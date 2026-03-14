# Formula Calculator Module

## Purpose

`Formula Calculator` is the integrated expression and equation module for Qt Modula. It supports deterministic expression evaluation, equation solving, formula-library selection, and parser-safe identifier remapping for advanced formulas.

- Module type: `formula_calculator`
- Family: `Math`
- Capabilities: `transform`

## Port Contract

### Inputs

| Port | Kind | Plane | Persisted | Notes |
| --- | --- | --- | --- | --- |
| `formula` | `string` | `data` | yes | Expression or equation text. |
| `solve_for` | `string` | `data` | yes | Optional equation target variable. |
| `variables` | `string` | `data` | yes | Assignment list (`a=1, b=2`). |
| `evaluate` | `trigger` | `control` | no | Explicit evaluation trigger. |
| `auto_evaluate` | `boolean` | `data` | yes | Recompute whenever formula/variables/target change. |
| `clear` | `trigger` | `control` | no | Clears formula, target, variables, and outputs. |
| `open_library` | `trigger` | `control` | no | Opens formula library dialog. |
| `full_professional_generality` | `boolean` | `data` | yes | Enables professional variant selection when available. |

### Outputs

| Port | Kind | Plane | Notes |
| --- | --- | --- | --- |
| `value` | `number` | `data` | Primary scalar result (first real root when solved). |
| `text` | `string` | `data` | Human-readable evaluation/solution summary. |
| `error` | `string` | `data` | Deterministic evaluation error (`""` on success). |
| `formula` | `string` | `data` | Normalized canonical formula (with refs prefix if used). |
| `variables` | `string` | `data` | Canonicalized assignment summary. |
| `roots` | `json` | `data` | Solution list (numbers for real roots, strings for complex). |
| `root_count` | `integer` | `data` | Root count in current result. |
| `solved` | `boolean` | `data` | True when equation solving path was used. |

## Formula Language

### Normalization

Before evaluation, formula text is normalized:

- Unicode operators to parser tokens (`−`, `×`, `·`, `÷`, `^`, `√`, `π`)
- `±` expansion token handling (`+/-`, `-/+`)
- whitespace collapse
- implicit multiplication insertion when safe (`2x`, `(a+b)c`, etc.)

### Variables and Assignments

`variables` accepts comma/semicolon/newline separated assignments:

```text
m=2, a=9.81
x=1; y=2
```

Assignments are resolved left-to-right and may reference prior assignments.

### Parser-Safe Identifier Remapping (`refs{}`)

To support external names that are parser-unsafe (for example language keywords), formulas can start with:

```text
refs{external=internal}; expression
```

Example:

```text
refs{lambda=lam}; N = N0*exp(-lambda*t)
```

Validation enforces:

- valid external/internal identifiers
- no duplicate external or internal mappings
- no unused refs mappings
- no unsafe overlap between internal names and expression variables

## Evaluation Modes

### Expression Mode (no `=`)

- Evaluates expression branches after `+/-` expansion.
- Deduplicates near-equal finite results.
- Multi-result output is represented in `text` and `roots`.

### Equation Mode (`lhs = rhs`)

Target resolution priority:

1. explicit `solve_for`
2. inferred target if one side is a bare variable not explicitly assigned

Solving strategy:

1. direct substitution path when algebraically direct
2. numeric solve path (Newton + scan/bisection fallback)
3. symbolic fallback when SymPy is available and numeric path fails

If no target is resolved, module emits residual diagnostics (`lhs`, `rhs`, `residual`).

## Branching and Limits

- `+/-` and `-/+` create deterministic branch expansion.
- A hard limit prevents combinatorial explosion.
- Root/value deduplication uses tolerance-based comparisons.

## Error Behavior

On failure:

- `error` is populated with deterministic message text.
- `value` resets to `0.0`.
- `text` clears.
- `roots` resets to `[]`.
- `root_count` resets to `0`.
- `solved` resets to `False`.

## Formula Library Dialog

- Provides local search over catalog entries.
- Supports standard and professional variants.
- `Confirm` injects selected expression into `formula`.
- If `auto_evaluate=true`, injected expressions evaluate immediately.

## Persistence

Persisted keys:

- `formula`
- `solve_for`
- `variables`
- `auto_evaluate`
- `full_professional_generality`

## Recommended Bind Chains

### Triggered Solve Chain

1. input modules -> `formula`/`variables`
2. `Trigger Mapper.evaluate` -> `Formula Calculator.evaluate`
3. `Formula Calculator.value` -> downstream analytics/export

### Parameter Sweep Integration

- Reuse equivalent expressions in `Parameter Sweep` for batch exploration.
- Keep expression syntax aligned with shared `ExpressionEngine` behavior.

## Operational Guidance

- Prefer explicit `solve_for` in multi-variable equations to avoid ambiguity.
- Use `refs{}` only when needed; keep mappings minimal and explicit.
- Keep variable assignments finite and domain-valid for the selected formulas.
