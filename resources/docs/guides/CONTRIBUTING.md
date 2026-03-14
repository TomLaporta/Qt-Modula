# Contributing Guide

This guide defines engineering and verification standards for Qt Modula contributions.

## Local Setup

```bash
python3 -m pip install -e .[dev]
```

Headless environments should use:

```bash
export QT_QPA_PLATFORM=offscreen
```

## Standard Verification Workflow

Preferred single-command gate:

```bash
QT_QPA_PLATFORM=offscreen python3 resources/scripts/run_quality_gate.py
```

Equivalent manual sequence:

```bash
python3 -m ruff check src/qt_modula resources/scripts
python3 -m mypy src/qt_modula
QT_QPA_PLATFORM=offscreen python3 -m pytest -q
QT_QPA_PLATFORM=offscreen python3 resources/scripts/run_workflow_sim.py
QT_QPA_PLATFORM=offscreen python3 resources/scripts/run_benchmarks.py
```

If `tests/` is not present in your checkout, use `resources/scripts/run_quality_gate.py`; it
skips the pytest step automatically.

## Benchmark Threshold Overrides

`resources/scripts/run_benchmarks.py` supports environment-variable overrides.

- `QT_MODULA_BENCH_DISPATCH_EVENTS_PER_S_MIN` (default `2000`)
- `QT_MODULA_BENCH_DISPATCH_LATENCY_US_MAX` (default `2000`)
- `QT_MODULA_BENCH_UI_CYCLE_MS_MAX` (default `25`)
- `QT_MODULA_BENCH_FORMULA_EVALS_PER_S_MIN` (default `50000`)
- `QT_MODULA_BENCH_DATASET_ROWS_PER_S_MIN` (default `50000`)
- `QT_MODULA_BENCH_MEMORY_PEAK_MIB_MAX` (default `256`)
- `QT_MODULA_BENCH_LINEPLOT_ROWS_PER_S_MIN` (default `20000`)
- `QT_MODULA_BENCH_LINEPLOT_HOVER_QUERIES_PER_S_MIN` (default `2500`)
- `QT_MODULA_BENCH_LINEPLOT_PEAK_MIB_MAX` (default `512`)

## Engineering Standards

### Determinism

- preserve stable runtime ordering semantics
- avoid unordered iteration dependence in runtime-critical paths
- keep queue/coalescing behavior explicit and testable

### Contract Integrity

- keep descriptors, schema models, and UI/runtime behavior synchronized
- avoid implicit compatibility or migration branches unless explicitly designed
- keep current-contract-only rejection semantics deterministic

### Failure Semantics

- failure paths must be reproducible and testable
- module `error` and status `text` lanes must be actionable
- async modules must clear stale success outputs on failure

### Persistence Discipline

- persist user intent only (`persistent_inputs`)
- do not persist transient runtime outputs/counters
- keep dynamic-port regeneration deterministic from persisted inputs

### Documentation Discipline

Behavior and contract changes require docs updates.

At minimum, update:

- `README.md` for user-visible operational changes
- `resources/docs/platform/*` for architectural/runtime/schema contract changes
- `resources/docs/modules/MODULE_CATALOG.md` and module docs for contract changes
- relevant workflow/authoring guide docs when engineering workflow changes

## Change-Specific Checklists

### Module Changes

1. descriptor and capabilities are accurate
2. port kind/plane/visibility metadata is intentional
3. `persistent_inputs` are minimal and correct
4. tests cover success and deterministic failure paths
5. docs for changed modules are updated

### Runtime Changes

1. runtime invariant tests are updated
2. queue/coalescing/cycle behavior remains explicit
3. workflow simulation still passes
4. project replay behavior remains deterministic

### Persistence Changes

1. schema reference is updated
2. validation and rejection tests are updated
3. deterministic writer behavior is preserved
4. load/apply semantic validation remains strict

## Pull Request Expectations

Include in each PR:

1. problem statement
2. implementation summary
3. risk areas and mitigations
4. exact verification commands and outcomes
5. documentation updates performed
6. follow-up work (if any)

## Review Priorities

Reviewers should prioritize:

- behavioral regressions
- deterministic ordering risks
- contract/schema drift
- failure-path correctness
- missing tests for changed behavior
- documentation drift versus implementation
