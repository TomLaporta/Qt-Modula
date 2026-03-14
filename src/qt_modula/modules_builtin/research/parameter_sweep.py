"""Research module for deterministic parameter sweeps."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from qt_modula.modules_builtin.math.expression_engine import ExpressionEngine
from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class ParameterSweepModule(BaseModule):
    """Generate deterministic sweep datasets for downstream analytics/export."""

    persistent_inputs = ("start", "stop", "step", "variable", "formula")

    descriptor = ModuleDescriptor(
        module_type="parameter_sweep",
        display_name="Parameter Sweep",
        family="Research",
        description="Runs a scalar parameter sweep and emits a tabular dataset.",
        inputs=(
            PortSpec("start", "number", default=0.0),
            PortSpec("stop", "number", default=10.0),
            PortSpec("step", "number", default=1.0),
            PortSpec("variable", "string", default="x"),
            PortSpec("formula", "string", default="x"),
            PortSpec("run", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("rows", "table", default=[]),
            PortSpec("count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("done", "trigger", default=0, control_plane=True),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._formula_edit: QLineEdit | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()
        self._formula_edit = QLineEdit(str(self.inputs["formula"]))
        self._formula_edit.textChanged.connect(
            lambda text: self._set_input_value("formula", text.strip() or "x")
        )
        set_control_height(self._formula_edit)
        form.addRow("Formula", self._formula_edit)

        run_btn = QPushButton("Run Sweep")
        run_btn.clicked.connect(self._run)
        set_control_height(run_btn)
        form.addRow("", run_btn)

        layout.addLayout(form)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "formula":
            formula = str(value).strip() or "x"
            self._set_input_value("formula", formula)
            if self._formula_edit is not None and self._formula_edit.text() != formula:
                self._formula_edit.blockSignals(True)
                self._formula_edit.setText(formula)
                self._formula_edit.blockSignals(False)
            return

        if port == "run" and is_truthy(value):
            self._run()

    def _run(self) -> None:
        try:
            start = float(self.inputs["start"])
            stop = float(self.inputs["stop"])
            step = float(self.inputs["step"])
        except (TypeError, ValueError):
            self._fail("start, stop, and step must be finite numbers")
            return
        if not (math.isfinite(start) and math.isfinite(stop) and math.isfinite(step)):
            self._fail("start, stop, and step must be finite numbers")
            return
        variable = str(self.inputs["variable"]).strip() or "x"
        formula = str(self.inputs["formula"]).strip() or variable

        if abs(step) < 1e-18:
            self._fail("step must be non-zero")
            return

        direction = 1.0 if step > 0 else -1.0
        if direction > 0 and start > stop:
            self._fail("start must be <= stop for positive step")
            return
        if direction < 0 and start < stop:
            self._fail("start must be >= stop for negative step")
            return

        rows: list[dict[str, Any]] = []
        value = start
        guard = 0
        while (value <= stop if direction > 0 else value >= stop) and guard < 200_000:
            guard += 1
            try:
                result = ExpressionEngine.evaluate(formula, {variable: value})
            except Exception as exc:
                self._fail(str(exc))
                return
            rows.append({variable: value, "result": result})
            value += step

        if guard >= 200_000:
            self._fail("sweep limit exceeded (200000 rows)")
            return

        summary = f"generated {len(rows)} rows"
        self.emit("rows", rows)
        self.emit("count", len(rows))
        self.emit("text", summary)
        self.emit("done", 1)
        self.emit("error", "")
        if self._status is not None:
            self._status.setText(summary)

    def _fail(self, message: str) -> None:
        self.emit("rows", [])
        self.emit("count", 0)
        self.emit("error", message)
        self.emit("done", 0)
        self.emit("text", f"error: {message}")
        if self._status is not None:
            self._status.setText(f"error: {message}")

    def replay_state(self) -> None:
        self._run()
