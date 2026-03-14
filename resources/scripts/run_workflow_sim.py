#!/usr/bin/env python3
"""Run workflow simulation scenarios."""

from __future__ import annotations

import os

from _bootstrap import REPO_ROOT

from qt_modula.modules_builtin import build_registry
from qt_modula.runtime import RuntimeEngine
from qt_modula.sdk import RuntimePolicy


def _scenario_trigger_math_gate_view() -> None:
    registry, _issues = build_registry(plugin_root=REPO_ROOT / "modules")
    runtime = RuntimeEngine(RuntimePolicy())

    trigger = registry.create("trigger_button", "m_trigger")
    source = registry.create("number_input", "m_source")
    arithmetic = registry.create("arithmetic", "m_math")
    gate = registry.create("condition_gate", "m_gate")
    sink = registry.create("value_view", "m_sink")

    for module in (trigger, source, arithmetic, gate, sink):
        runtime.register_module(module)

    runtime.add_binding("m_source", "value", "m_math", "a")
    runtime.add_binding("m_source", "value", "m_math", "b")
    runtime.add_binding("m_trigger", "pulse", "m_math", "evaluate")
    runtime.add_binding("m_math", "result", "m_gate", "a")
    runtime.add_binding("m_trigger", "pulse", "m_gate", "evaluate")
    runtime.add_binding("m_gate", "passed", "m_sink", "value")

    source.receive_binding("value", 4)
    arithmetic.receive_binding("op", "mul")
    gate.receive_binding("operator", "gte")
    gate.receive_binding("b", 8)

    trigger.receive_binding("trigger", 1)

    if sink.outputs["value"] != 16.0:
        raise AssertionError(f"unexpected sink value: {sink.outputs['value']!r}")


def _scenario_formula_calculator_parity() -> None:
    registry, _issues = build_registry(plugin_root=REPO_ROOT / "modules")
    runtime = RuntimeEngine(RuntimePolicy())

    trigger = registry.create("trigger_button", "m_trigger")
    formula = registry.create("formula_calculator", "m_formula")
    sink = registry.create("value_view", "m_sink")

    for module in (trigger, formula, sink):
        runtime.register_module(module)

    runtime.add_binding("m_trigger", "pulse", "m_formula", "evaluate")
    runtime.add_binding("m_formula", "value", "m_sink", "value")

    formula.receive_binding("formula", "x = 10 +/- 2")
    formula.receive_binding("solve_for", "x")
    trigger.receive_binding("trigger", 1)

    if formula.outputs["root_count"] != 2:
        raise AssertionError(f"expected 2 +/- roots, got {formula.outputs['root_count']!r}")
    if sink.outputs["value"] != 12.0:
        raise AssertionError(f"unexpected formula sink value: {sink.outputs['value']!r}")

    formula.receive_binding("formula", "x^2 + 1 = 0")
    formula.receive_binding("solve_for", "x")
    trigger.receive_binding("trigger", 1)

    roots = formula.outputs["roots"]
    if not formula.outputs["solved"]:
        raise AssertionError("expected solved=True for complex-root equation")
    if formula.outputs["root_count"] != 2:
        raise AssertionError(f"expected 2 complex roots, got {formula.outputs['root_count']!r}")
    if not isinstance(roots, list) or not roots or not all("i" in str(item) for item in roots):
        raise AssertionError(f"expected complex roots from symbolic path, got {roots!r}")


def _scenario_table_chain_transform_metrics() -> None:
    registry, _issues = build_registry(plugin_root=REPO_ROOT / "modules")
    runtime = RuntimeEngine(RuntimePolicy())

    buffer = registry.create("table_buffer", "m_buffer")
    transform = registry.create("table_transform", "m_transform")
    metrics = registry.create("table_metrics", "m_metrics")

    for module in (buffer, transform, metrics):
        runtime.register_module(module)

    runtime.add_binding("m_buffer", "rows", "m_transform", "rows")
    runtime.add_binding("m_transform", "rows", "m_metrics", "rows")

    transform.receive_binding("filter_key", "kind")
    transform.receive_binding("filter_value", "keep")

    for row in (
        {"kind": "keep", "value": 1},
        {"kind": "drop", "value": 2},
        {"kind": "keep", "value": 3},
    ):
        buffer.receive_binding("row", row)
        buffer.receive_binding("append", 1)

    if metrics.outputs["row_count"] != 2:
        raise AssertionError(f"unexpected transformed row count: {metrics.outputs['row_count']!r}")
    if metrics.outputs["column_count"] != 2:
        raise AssertionError(
            f"unexpected transformed column count: {metrics.outputs['column_count']!r}"
        )


def _scenario_parameter_sweep_to_line_plotter() -> None:
    registry, _issues = build_registry(plugin_root=REPO_ROOT / "modules")
    runtime = RuntimeEngine(RuntimePolicy())

    sweep = registry.create("parameter_sweep", "m_sweep")
    plot = registry.create("line_plotter", "m_plot")

    for module in (sweep, plot):
        runtime.register_module(module)

    runtime.add_binding("m_sweep", "rows", "m_plot", "rows")

    plot.receive_binding("x_key", "x")
    plot.receive_binding("y_key", "result")

    sweep.receive_binding("start", 0.0)
    sweep.receive_binding("stop", 10.0)
    sweep.receive_binding("step", 1.0)
    sweep.receive_binding("formula", "x*2")
    sweep.receive_binding("run", 1)

    if sweep.outputs["count"] != 11:
        raise AssertionError(f"unexpected sweep count: {sweep.outputs['count']!r}")
    if plot.outputs["point_count"] != 11:
        raise AssertionError(f"unexpected plot point count: {plot.outputs['point_count']!r}")
    if plot.outputs["series_count"] != 1:
        raise AssertionError(f"unexpected plot series count: {plot.outputs['series_count']!r}")
    if plot.outputs["error"] != "":
        raise AssertionError(f"unexpected plot error: {plot.outputs['error']!r}")

    plot.receive_binding("range_mode", "last_n")
    plot.receive_binding("range_points", 3)
    if "last_n" not in str(plot.outputs["range_applied"]):
        raise AssertionError(f"unexpected range applied: {plot.outputs['range_applied']!r}")


def _scenario_value_router_selection() -> None:
    registry, _issues = build_registry(plugin_root=REPO_ROOT / "modules")
    runtime = RuntimeEngine(RuntimePolicy())

    left = registry.create("number_input", "m_left")
    right = registry.create("number_input", "m_right")
    router = registry.create("value_router", "m_router")
    sink = registry.create("value_view", "m_sink")

    for module in (left, right, router, sink):
        runtime.register_module(module)

    runtime.add_binding("m_left", "value", "m_router", "v0")
    runtime.add_binding("m_right", "value", "m_router", "v1")
    runtime.add_binding("m_router", "value", "m_sink", "value")

    left.receive_binding("value", 5.0)
    right.receive_binding("value", 9.0)
    router.receive_binding("selector", 1)

    if sink.outputs["value"] != 9.0:
        raise AssertionError(f"unexpected routed value: {sink.outputs['value']!r}")
    if router.outputs["selected"] != 1:
        raise AssertionError(f"unexpected router selection: {router.outputs['selected']!r}")


def run() -> tuple[bool, str]:
    os.chdir(REPO_ROOT)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    scenarios = [
        ("trigger_math_gate_view", _scenario_trigger_math_gate_view),
        ("formula_calculator_parity", _scenario_formula_calculator_parity),
        ("table_chain_transform_metrics", _scenario_table_chain_transform_metrics),
        ("parameter_sweep_to_line_plotter", _scenario_parameter_sweep_to_line_plotter),
        ("value_router_selection", _scenario_value_router_selection),
    ]

    for name, fn in scenarios:
        try:
            fn()
        except Exception as exc:
            return False, f"{name} failed: {exc}"
    return True, "workflow simulation passed"


def main() -> int:
    ok, message = run()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
