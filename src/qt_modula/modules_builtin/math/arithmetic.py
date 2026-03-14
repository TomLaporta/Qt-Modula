"""Deterministic arithmetic module."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import ModuleBase, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height
from qt_modula.ui.advanced_section import AdvancedSection

_OPERATORS = ("add", "sub", "mul", "div", "pow", "min", "max")


class ArithmeticModule(ModuleBase):
    """Compute scalar arithmetic operations."""

    persistent_inputs = ("a", "b", "op", "auto")

    descriptor = ModuleDescriptor(
        module_type="arithmetic",
        display_name="Arithmetic",
        family="Math",
        description="Fast scalar arithmetic with explicit evaluate trigger.",
        capabilities=("transform",),
        inputs=(
            PortSpec("a", "number", default=0.0),
            PortSpec("b", "number", default=0.0),
            PortSpec("op", "string", default="add"),
            PortSpec(
                "auto",
                "boolean",
                default=True,
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec("evaluate", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("result", "number", default=0.0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
            PortSpec("evaluated", "trigger", default=0, control_plane=True),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._op_combo: QComboBox | None = None
        self._auto_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()
        self._op_combo = QComboBox()
        self._op_combo.addItems(list(_OPERATORS))
        self._op_combo.setCurrentText(str(self.inputs["op"]))
        self._op_combo.currentTextChanged.connect(lambda token: self.receive_binding("op", token))
        set_control_height(self._op_combo)
        form.addRow("Operation", self._op_combo)

        eval_btn = QPushButton("Evaluate")
        eval_btn.clicked.connect(lambda: self.receive_binding("evaluate", 1))
        set_control_height(eval_btn)
        form.addRow("", eval_btn)

        layout.addLayout(form)

        advanced = AdvancedSection("Advanced", expanded=False)
        self._auto_check = QCheckBox("Auto Evaluate")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda checked: self.receive_binding("auto", checked))
        advanced.content_layout.addWidget(self._auto_check)
        layout.addWidget(advanced)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._evaluate(trigger=False)
        return root

    def _evaluate(self, *, trigger: bool) -> None:
        a = float(self.inputs["a"])
        b = float(self.inputs["b"])
        op = str(self.inputs["op"]).strip().lower()

        try:
            if op == "add":
                result = a + b
            elif op == "sub":
                result = a - b
            elif op == "mul":
                result = a * b
            elif op == "div":
                if abs(b) < 1e-18:
                    raise ValueError("division by zero")
                result = a / b
            elif op == "pow":
                result = a**b
            elif op == "min":
                result = min(a, b)
            elif op == "max":
                result = max(a, b)
            else:
                raise ValueError(f"unsupported operator '{op}'")
            if not math.isfinite(result):
                raise ValueError("result is not finite")
        except Exception as exc:
            message = str(exc)
            self.emit("error", message)
            self.emit("text", f"error: {message}")
            self.emit("evaluated", 0)
            if self._status is not None:
                self._status.setText(f"error: {message}")
            return

        text = f"{result:.12g}"
        self.emit("result", result)
        self.emit("text", text)
        self.emit("error", "")
        self.emit("evaluated", 1 if trigger else 0)
        if self._status is not None:
            self._status.setText(f"{op} => {text}")

    def on_input(self, port: str, value: Any) -> None:
        if port == "op":
            token = str(value).strip().lower()
            if token not in _OPERATORS:
                token = "add"
            self.inputs["op"] = token
            if self._op_combo is not None and self._op_combo.currentText() != token:
                self._op_combo.blockSignals(True)
                self._op_combo.setCurrentText(token)
                self._op_combo.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._evaluate(trigger=True)
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            if enabled:
                self._evaluate(trigger=True)
            return

        if port in {"a", "b"} and bool(self.inputs["auto"]):
            self._evaluate(trigger=True)
            return

        if port == "evaluate" and is_truthy(value):
            self._evaluate(trigger=True)

    def replay_state(self) -> None:
        self._evaluate(trigger=False)
