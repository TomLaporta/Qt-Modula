#!/usr/bin/env python3
"""Run benchmark suite and enforce baseline thresholds."""

from __future__ import annotations

import json
import os

from _bootstrap import REPO_ROOT

from qt_modula.benchmarks import run_all_benchmarks


def _threshold(name: str, default: float) -> float:
    token = os.getenv(f"QT_MODULA_BENCH_{name.upper()}")
    if token is None:
        return default
    try:
        return float(token)
    except ValueError:
        return default


def main() -> int:
    os.chdir(REPO_ROOT)
    metrics = run_all_benchmarks()
    print(json.dumps(metrics, indent=2, sort_keys=True))

    failures: list[str] = []

    dispatch = metrics["dispatch"]
    if dispatch["events_per_s"] < _threshold("dispatch_events_per_s_min", 2_000.0):
        failures.append("dispatch events/s below baseline")
    if dispatch["avg_latency_us"] > _threshold("dispatch_latency_us_max", 2_000.0):
        failures.append("dispatch latency above baseline")

    ui = metrics["ui"]
    if ui["cycle_ms"] > _threshold("ui_cycle_ms_max", 25.0):
        failures.append("ui event cycle latency above baseline")

    formula = metrics["formula"]
    if formula["evals_per_s"] < _threshold("formula_evals_per_s_min", 50_000.0):
        failures.append("formula throughput below baseline")

    dataset = metrics["dataset"]
    if dataset["rows_per_s"] < _threshold("dataset_rows_per_s_min", 50_000.0):
        failures.append("dataset throughput below baseline")

    memory = metrics["memory"]
    if memory["peak_mib"] > _threshold("memory_peak_mib_max", 256.0):
        failures.append("memory peak above baseline")

    lineplot = metrics["lineplot"]
    if lineplot["rows_per_s"] < _threshold("lineplot_rows_per_s_min", 20_000.0):
        failures.append("lineplot ingest throughput below baseline")
    if lineplot["hover_queries_per_s"] < _threshold(
        "lineplot_hover_queries_per_s_min", 2_500.0
    ):
        failures.append("lineplot hover query throughput below baseline")
    if lineplot["peak_mib"] > _threshold("lineplot_peak_mib_max", 512.0):
        failures.append("lineplot memory peak above baseline")

    if failures:
        print("\nBenchmark gate failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nBenchmark gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
