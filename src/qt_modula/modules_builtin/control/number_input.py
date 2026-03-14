"""Numeric source module."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from qt_modula.sdk import ModuleBase, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height
from qt_modula.ui.advanced_section import AdvancedSection


class NumberInputModule(ModuleBase):
    """Emit numeric values and changed pulses."""

    persistent_inputs = ("value", "min", "max")

    descriptor = ModuleDescriptor(
        module_type="number_input",
        display_name="Number Input",
        family="Control",
        description="Numeric source with deterministic changed trigger output.",
        capabilities=("source", "scheduler"),
        inputs=(
            PortSpec("value", "number", default=0.0),
            PortSpec(
                "min",
                "number",
                default=-1_000_000.0,
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec(
                "max",
                "number",
                default=1_000_000.0,
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("value", "number", default=0.0),
            PortSpec("text", "string", default=""),
            PortSpec("changed", "trigger", default=0, control_plane=True),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._value_spin: QDoubleSpinBox | None = None
        self._min_spin: QDoubleSpinBox | None = None
        self._max_spin: QDoubleSpinBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()
        self._value_spin = QDoubleSpinBox()
        self._value_spin.setDecimals(8)
        self._value_spin.setRange(float(self.inputs["min"]), float(self.inputs["max"]))
        self._value_spin.setValue(float(self.inputs["value"]))
        self._value_spin.valueChanged.connect(lambda value: self.receive_binding("value", value))
        set_control_height(self._value_spin)
        form.addRow("Value", self._value_spin)

        emit_btn = QPushButton("Emit")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        form.addRow("", emit_btn)
        layout.addLayout(form)

        advanced = AdvancedSection("Advanced", expanded=False)
        self._min_spin = QDoubleSpinBox()
        self._max_spin = QDoubleSpinBox()
        for spin in (self._min_spin, self._max_spin):
            spin.setDecimals(8)
            spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
            set_control_height(spin)

        self._min_spin.setValue(float(self.inputs["min"]))
        self._max_spin.setValue(float(self.inputs["max"]))
        self._min_spin.valueChanged.connect(lambda value: self.receive_binding("min", value))
        self._max_spin.valueChanged.connect(lambda value: self.receive_binding("max", value))

        advanced_form = QFormLayout()
        advanced_form.addRow("Min", self._min_spin)
        advanced_form.addRow("Max", self._max_spin)
        advanced.content_layout.addLayout(advanced_form)
        layout.addWidget(advanced)

        self._status = QLabel("")
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(trigger=False)
        return root

    def _sync_ranges(self) -> bool:
        minimum = float(self.inputs["min"])
        maximum = float(self.inputs["max"])
        if minimum > maximum:
            self.emit("error", "min must be <= max")
            return False

        if self._value_spin is not None:
            self._value_spin.setRange(minimum, maximum)
        self.emit("error", "")
        return True

    def _publish(self, *, trigger: bool) -> None:
        value = float(self.inputs["value"])
        text = f"{value:g}"
        self.emit("value", value)
        self.emit("text", text)
        self.emit("changed", 1 if trigger else 0)
        if self._status is not None:
            self._status.setText(f"Current: {text}")

    def on_input(self, port: str, value: Any) -> None:
        if port in {"min", "max"}:
            if self._sync_ranges():
                self._publish(trigger=False)
            return

        if port == "value":
            parsed = float(value)
            self.inputs["value"] = parsed
            if self._value_spin is not None and abs(self._value_spin.value() - parsed) > 1e-12:
                self._value_spin.blockSignals(True)
                self._value_spin.setValue(parsed)
                self._value_spin.blockSignals(False)
            self._publish(trigger=True)
            return

        if port == "emit" and is_truthy(value):
            self._publish(trigger=True)

    def replay_state(self) -> None:
        self._publish(trigger=False)
