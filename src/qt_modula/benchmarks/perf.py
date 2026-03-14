"""Performance benchmark helpers for quality gates."""

from __future__ import annotations

import time
import tracemalloc
from typing import Any

from PySide6.QtWidgets import QApplication, QWidget

from qt_modula.modules_builtin.analytics import LinePlotterModule
from qt_modula.modules_builtin.math.expression_engine import ExpressionEngine
from qt_modula.persistence import AppConfig
from qt_modula.runtime import RuntimeEngine
from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, RuntimePolicy
from qt_modula.ui.main_window import MainWindow


class _BenchSource(BaseModule):
    descriptor = ModuleDescriptor(
        module_type="bench_source",
        display_name="Bench Source",
        family="Bench",
        description="",
        inputs=(PortSpec("value", "number", default=0.0),),
        outputs=(PortSpec("out", "number", default=0.0),),
    )

    def widget(self) -> QWidget:
        return QWidget()

    def on_input(self, port: str, value: Any) -> None:
        if port == "value":
            self.emit("out", value)


class _BenchSink(BaseModule):
    descriptor = ModuleDescriptor(
        module_type="bench_sink",
        display_name="Bench Sink",
        family="Bench",
        description="",
        inputs=(PortSpec("in", "number", default=0.0),),
        outputs=(PortSpec("seen", "number", default=0.0),),
    )

    def widget(self) -> QWidget:
        return QWidget()

    def on_input(self, port: str, value: Any) -> None:
        if port == "in":
            self.emit("seen", value)


def dispatch_latency_benchmark(iterations: int = 4_000) -> dict[str, float]:
    runtime = RuntimeEngine(RuntimePolicy(max_queue_size=max(8_000, iterations * 4)))
    src = _BenchSource("src")
    mid = _BenchSink("mid")
    sink = _BenchSink("sink")

    runtime.register_module(src)
    runtime.register_module(mid)
    runtime.register_module(sink)
    runtime.add_binding("src", "out", "mid", "in")
    runtime.add_binding("mid", "seen", "sink", "in")

    started = time.perf_counter()
    for idx in range(iterations):
        src.receive_binding("value", float(idx))
    elapsed_s = time.perf_counter() - started

    events = iterations * 2
    throughput = events / max(1e-9, elapsed_s)
    avg_latency_us = (elapsed_s / max(1, events)) * 1_000_000.0
    return {
        "events": float(events),
        "elapsed_s": elapsed_s,
        "events_per_s": throughput,
        "avg_latency_us": avg_latency_us,
    }


def ui_responsiveness_benchmark(cycles: int = 200) -> dict[str, float]:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    window = MainWindow(AppConfig())
    try:
        started = time.perf_counter()
        for _ in range(cycles):
            app.processEvents()
        elapsed_s = time.perf_counter() - started
    finally:
        window.close()
    return {
        "cycles": float(cycles),
        "elapsed_s": elapsed_s,
        "cycle_ms": (elapsed_s / max(1, cycles)) * 1000.0,
    }


def formula_throughput_benchmark(iterations: int = 20_000) -> dict[str, float]:
    started = time.perf_counter()
    value = 0.0
    for idx in range(iterations):
        value = ExpressionEngine.evaluate("x*x + 2*x + 1", {"x": float(idx)})
    elapsed_s = time.perf_counter() - started
    return {
        "iterations": float(iterations),
        "elapsed_s": elapsed_s,
        "evals_per_s": iterations / max(1e-9, elapsed_s),
        "last_value": value,
    }


def dataset_throughput_benchmark(rows: int = 50_000) -> dict[str, float]:
    payload = [{"a": idx, "b": idx * 2} for idx in range(rows)]
    started = time.perf_counter()
    total = 0
    for row in payload:
        total += int(row["a"]) + int(row["b"])
    elapsed_s = time.perf_counter() - started
    return {
        "rows": float(rows),
        "elapsed_s": elapsed_s,
        "rows_per_s": rows / max(1e-9, elapsed_s),
        "checksum": float(total),
    }


def memory_ceiling_benchmark(iterations: int = 10_000) -> dict[str, float]:
    tracemalloc.start()
    try:
        runtime = RuntimeEngine(RuntimePolicy(max_queue_size=max(20_000, iterations * 4)))
        src = _BenchSource("src")
        sink = _BenchSink("sink")
        runtime.register_module(src)
        runtime.register_module(sink)
        runtime.add_binding("src", "out", "sink", "in")

        for idx in range(iterations):
            src.receive_binding("value", float(idx))

        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    return {
        "iterations": float(iterations),
        "current_bytes": float(current),
        "peak_bytes": float(peak),
        "peak_mib": peak / (1024.0 * 1024.0),
    }


def lineplot_benchmark(rows: int = 150_000, hover_queries: int = 20_000) -> dict[str, float]:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    module = LinePlotterModule("bench_lineplot")
    widget = module.widget()

    payload = [
        {
            "x": float(idx),
            "y": float((idx % 1024) - 512),
            "series": f"s{idx % 8}",
        }
        for idx in range(rows)
    ]
    compressed_payload = [
        {
            "x": float(idx + ((idx // 512) * 4_096)),
            "y": float((idx % 1024) - 512),
            "series": f"s{idx % 8}",
        }
        for idx in range(rows)
    ]

    def _run_hover_pass() -> tuple[float, int]:
        hover_started = time.perf_counter()
        view = module._view_range()
        cursor_x = float(view[0]) if view is not None else 0.0
        view_span = abs(float(view[1] - view[0])) if view is not None else float(rows)
        step = max(1.0, view_span / max(1, hover_queries))
        matched_queries = 0
        for _ in range(hover_queries):
            if module._nearest_point(cursor_x, 0.0) is not None:
                matched_queries += 1
            cursor_x += step
            if view is not None and cursor_x >= float(view[1]):
                cursor_x = float(view[0])
        app.processEvents()
        return time.perf_counter() - hover_started, matched_queries

    tracemalloc.start()
    try:
        ingest_started = time.perf_counter()
        module.receive_binding("rows", payload)
        app.processEvents()
        ingest_elapsed_s = time.perf_counter() - ingest_started

        hover_elapsed_s, matched_queries = _run_hover_pass()

        module.receive_binding("x_compression_threshold", 1_000.0)
        module.receive_binding("x_compression_span", 10.0)
        module.receive_binding("rows", compressed_payload)
        app.processEvents()
        compressed_hover_elapsed_s, compressed_matched_queries = _run_hover_pass()

        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        module.on_close()
        widget.close()

    return {
        "rows": float(rows),
        "ingest_elapsed_s": ingest_elapsed_s,
        "rows_per_s": rows / max(1e-9, ingest_elapsed_s),
        "hover_queries": float(hover_queries),
        "matched_queries": float(matched_queries),
        "hover_elapsed_s": hover_elapsed_s,
        "hover_queries_per_s": hover_queries / max(1e-9, hover_elapsed_s),
        "compressed_matched_queries": float(compressed_matched_queries),
        "compressed_hover_elapsed_s": compressed_hover_elapsed_s,
        "compressed_hover_queries_per_s": hover_queries
        / max(1e-9, compressed_hover_elapsed_s),
        "current_bytes": float(current),
        "peak_bytes": float(peak),
        "peak_mib": peak / (1024.0 * 1024.0),
    }


def run_all_benchmarks() -> dict[str, dict[str, float]]:
    return {
        "dispatch": dispatch_latency_benchmark(),
        "ui": ui_responsiveness_benchmark(),
        "formula": formula_throughput_benchmark(),
        "dataset": dataset_throughput_benchmark(),
        "memory": memory_ceiling_benchmark(),
        "lineplot": lineplot_benchmark(),
    }
