"""N-way value routing utility for deterministic payload selection."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height

_MAX_ROUTER_INPUTS = 8


class ValueRouterModule(BaseModule):
    """Route one of N value lanes based on a selector index."""

    persistent_inputs = ("input_count", "selector", "auto")

    descriptor = ModuleDescriptor(
        module_type="value_router",
        display_name="Value Router",
        family="Logic",
        description="Routes one of N value inputs with deterministic selector clamping.",
        inputs=(
            PortSpec("v0", "any", default=None),
            PortSpec("v1", "any", default=None),
            PortSpec("v2", "any", default=None),
            PortSpec("v3", "any", default=None),
            PortSpec("v4", "any", default=None),
            PortSpec("v5", "any", default=None),
            PortSpec("v6", "any", default=None),
            PortSpec("v7", "any", default=None),
            PortSpec("selector", "integer", default=0),
            PortSpec("input_count", "integer", default=2),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("value", "any", default=None),
            PortSpec("selected", "integer", default=0),
            PortSpec("in_range", "boolean", default=True),
            PortSpec("changed", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._selector_warning = ""
        self._count_warning = ""

        self._selector_spin: QSpinBox | None = None
        self._count_spin: QSpinBox | None = None
        self._auto_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._selector_spin = QSpinBox()
        self._selector_spin.setRange(0, _MAX_ROUTER_INPUTS - 1)
        self._selector_spin.setValue(int(self.inputs["selector"]))
        self._selector_spin.valueChanged.connect(
            lambda value: self.receive_binding("selector", int(value))
        )
        set_control_height(self._selector_spin)
        form.addRow("Selector", self._selector_spin)

        self._count_spin = QSpinBox()
        self._count_spin.setRange(2, _MAX_ROUTER_INPUTS)
        self._count_spin.setValue(self._clamp_count(int(self.inputs["input_count"])))
        self._count_spin.valueChanged.connect(
            lambda value: self.receive_binding("input_count", int(value))
        )
        set_control_height(self._count_spin)
        form.addRow("Input Count", self._count_spin)

        self._auto_check = QCheckBox("Auto Emit")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda enabled: self.receive_binding("auto", enabled))
        form.addRow("", self._auto_check)

        emit_btn = QPushButton("Emit")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        form.addRow("", emit_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._publish(trigger=False, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "selector":
            requested = int(value)
            selector, in_range = self._clamp_selector(
                requested, self._clamp_count(int(self.inputs["input_count"]))
            )
            self.inputs["selector"] = selector
            self._selector_warning = "" if in_range else f"selector clamped to {selector}"
            if self._selector_spin is not None and self._selector_spin.value() != selector:
                self._selector_spin.blockSignals(True)
                self._selector_spin.setValue(selector)
                self._selector_spin.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._publish(trigger=True, reason="selector")
            else:
                self._publish_cached(reason="selector updated")
            return

        if port == "input_count":
            requested = int(value)
            count = self._clamp_count(requested)
            self.inputs["input_count"] = count
            self._count_warning = "" if requested == count else f"input_count clamped to {count}"
            if self._count_spin is not None and self._count_spin.value() != count:
                self._count_spin.blockSignals(True)
                self._count_spin.setValue(count)
                self._count_spin.blockSignals(False)
            selector, in_range = self._clamp_selector(int(self.inputs["selector"]), count)
            self.inputs["selector"] = selector
            self._selector_warning = "" if in_range else f"selector clamped to {selector}"
            if self._selector_spin is not None and self._selector_spin.value() != selector:
                self._selector_spin.blockSignals(True)
                self._selector_spin.setValue(selector)
                self._selector_spin.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._publish(trigger=True, reason="input_count")
            else:
                self._publish_cached(reason="input_count updated")
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            if enabled:
                self._publish(trigger=True, reason="auto")
            else:
                self._publish_cached(reason="auto updated")
            return

        if port.startswith("v") and port[1:].isdigit():
            if bool(self.inputs["auto"]):
                self._publish(trigger=True, reason=port)
            else:
                self._publish_cached(reason=f"{port} cached")
            return

        if port == "emit" and is_truthy(value):
            self._publish(trigger=True, reason="emit")

    def replay_state(self) -> None:
        self._publish(trigger=False, reason="replay")

    def _selected_value(self) -> tuple[Any, int, bool]:
        count = self._clamp_count(int(self.inputs["input_count"]))
        requested = int(self.inputs["selector"])
        selector, in_range = self._clamp_selector(requested, count)
        self.inputs["selector"] = selector
        return self.inputs[f"v{selector}"], selector, in_range

    def _publish(self, *, trigger: bool, reason: str) -> None:
        value, selector, in_range = self._selected_value()
        warnings = [item for item in (self._count_warning, self._selector_warning) if item]
        self.emit("value", value)
        self.emit("selected", selector)
        self.emit("in_range", in_range)
        self.emit("changed", 1 if trigger else 0)
        self.emit("error", "; ".join(warnings))
        text = (
            f"selector={selector}, input_count={int(self.inputs['input_count'])}, "
            f"in_range={int(in_range)}, reason={reason}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    def _publish_cached(self, *, reason: str) -> None:
        warnings = [item for item in (self._count_warning, self._selector_warning) if item]
        self.emit("changed", 0)
        self.emit("error", "; ".join(warnings))
        text = f"auto=0, reason={reason}"
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    @staticmethod
    def _clamp_count(value: int) -> int:
        if value < 2:
            return 2
        if value > _MAX_ROUTER_INPUTS:
            return _MAX_ROUTER_INPUTS
        return value

    @staticmethod
    def _clamp_selector(value: int, count: int) -> tuple[int, bool]:
        if value < 0:
            return 0, False
        if value >= count:
            return count - 1, False
        return value, True
