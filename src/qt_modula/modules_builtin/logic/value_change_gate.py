"""Noise/duplicate suppression gate for expensive downstream lanes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import (
    BaseModule,
    ModuleDescriptor,
    PortSpec,
    coerce_finite_float,
    is_truthy,
)
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class ValueChangeGateModule(BaseModule):
    """Emit change pulses only when incoming values materially differ."""

    persistent_inputs = ("epsilon", "emit_initial", "auto")

    descriptor = ModuleDescriptor(
        module_type="value_change_gate",
        display_name="Value Change Gate",
        family="Logic",
        description="Suppresses unchanged values using epsilon-aware comparison.",
        inputs=(
            PortSpec("value", "any", default=None),
            PortSpec("epsilon", "number", default=1e-9),
            PortSpec("emit_initial", "boolean", default=True),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("value", "any", default=None),
            PortSpec("changed", "trigger", default=0, control_plane=True),
            PortSpec("unchanged", "trigger", default=0, control_plane=True),
            PortSpec("change_count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._has_candidate = False
        self._candidate: Any = None
        self._has_baseline = False
        self._baseline: Any = None
        self._change_count = 0
        self._last_error = ""

        self._epsilon_spin: QDoubleSpinBox | None = None
        self._emit_initial_check: QCheckBox | None = None
        self._auto_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._epsilon_spin = QDoubleSpinBox()
        self._epsilon_spin.setDecimals(12)
        self._epsilon_spin.setRange(0.0, 1_000_000_000.0)
        self._epsilon_spin.setValue(max(0.0, float(self.inputs["epsilon"])))
        self._epsilon_spin.valueChanged.connect(
            lambda value: self.receive_binding("epsilon", float(value))
        )
        set_control_height(self._epsilon_spin)
        form.addRow("Epsilon", self._epsilon_spin)

        self._emit_initial_check = QCheckBox("Emit Initial Value")
        self._emit_initial_check.setChecked(bool(self.inputs["emit_initial"]))
        self._emit_initial_check.toggled.connect(
            lambda enabled: self.receive_binding("emit_initial", enabled)
        )
        form.addRow("", self._emit_initial_check)

        self._auto_check = QCheckBox("Auto Evaluate")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda enabled: self.receive_binding("auto", enabled))
        form.addRow("", self._auto_check)

        emit_btn = QPushButton("Emit")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        form.addRow("", emit_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.receive_binding("clear", 1))
        set_control_height(clear_btn)
        form.addRow("", clear_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(changed=0, unchanged=0, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "epsilon":
            parsed = coerce_finite_float(value)
            if parsed is None:
                epsilon = 0.0
                self._set_error("epsilon must be finite numeric; clamped to 0")
            else:
                epsilon = max(0.0, parsed)
                if parsed < 0.0:
                    self._set_error("epsilon clamped to 0")
                else:
                    self._set_error("")
            self.inputs["epsilon"] = epsilon
            if self._epsilon_spin is not None and abs(self._epsilon_spin.value() - epsilon) > 1e-12:
                self._epsilon_spin.blockSignals(True)
                self._epsilon_spin.setValue(epsilon)
                self._epsilon_spin.blockSignals(False)
            if bool(self.inputs["auto"]) and self._has_candidate:
                self._evaluate(reason="epsilon")
            else:
                self._publish(changed=0, unchanged=0, reason="epsilon updated")
            return

        if port == "emit_initial":
            enabled = bool(value)
            self.inputs["emit_initial"] = enabled
            if (
                self._emit_initial_check is not None
                and self._emit_initial_check.isChecked() != enabled
            ):
                self._emit_initial_check.blockSignals(True)
                self._emit_initial_check.setChecked(enabled)
                self._emit_initial_check.blockSignals(False)
            self._publish(changed=0, unchanged=0, reason="emit_initial updated")
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            if enabled and self._has_candidate:
                self._evaluate(reason="auto")
            else:
                self._publish(changed=0, unchanged=0, reason="auto updated")
            return

        if port == "value":
            self._candidate = deepcopy(value)
            self._has_candidate = True
            if bool(self.inputs["auto"]):
                self._evaluate(reason="value")
            else:
                self._publish(changed=0, unchanged=0, reason="value cached")
            return

        if port == "emit" and is_truthy(value):
            self._evaluate(reason="emit")
            return

        if port == "clear" and is_truthy(value):
            self._has_candidate = False
            self._candidate = None
            self._has_baseline = False
            self._baseline = None
            self._change_count = 0
            self.emit("value", None)
            self._publish(changed=0, unchanged=0, reason="cleared")

    def _evaluate(self, *, reason: str) -> None:
        if not self._has_candidate:
            self._publish(changed=0, unchanged=1, reason=f"{reason}: no candidate")
            return

        current = deepcopy(self._candidate)
        emit_initial = bool(self.inputs["emit_initial"])
        epsilon = max(0.0, float(self.inputs["epsilon"]))

        if not self._has_baseline:
            self._baseline = deepcopy(current)
            self._has_baseline = True
            if emit_initial:
                self._change_count += 1
                self.emit("value", deepcopy(current))
                self._publish(changed=1, unchanged=0, reason=f"{reason}: initial emitted")
            else:
                self._publish(changed=0, unchanged=1, reason=f"{reason}: initial suppressed")
            return

        if self._is_changed(self._baseline, current, epsilon):
            self._baseline = deepcopy(current)
            self._change_count += 1
            self.emit("value", deepcopy(current))
            self._publish(changed=1, unchanged=0, reason=f"{reason}: changed")
            return

        self._publish(changed=0, unchanged=1, reason=f"{reason}: unchanged")

    @staticmethod
    def _is_changed(previous: Any, current: Any, epsilon: float) -> bool:
        prev_num = coerce_finite_float(previous)
        curr_num = coerce_finite_float(current)
        if prev_num is not None and curr_num is not None:
            return abs(prev_num - curr_num) > epsilon
        return bool(previous != current)

    def _publish(self, *, changed: int, unchanged: int, reason: str) -> None:
        self.emit("changed", 1 if changed else 0)
        self.emit("unchanged", 1 if unchanged else 0)
        self.emit("change_count", self._change_count)
        text = (
            f"has_candidate={int(self._has_candidate)}, has_baseline={int(self._has_baseline)}, "
            f"change_count={self._change_count}, reason={reason}"
        )
        self.emit("text", text)
        self.emit("error", self._last_error)
        if self._status is not None:
            self._status.setText(text)

    def _set_error(self, message: str) -> None:
        self._last_error = message
