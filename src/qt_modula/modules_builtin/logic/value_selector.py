"""Two-input value selector for deterministic routing."""

from __future__ import annotations

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

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class ValueSelectorModule(BaseModule):
    """Select input `a` or `b` and emit one routed value."""

    persistent_inputs = ("selector", "auto")

    descriptor = ModuleDescriptor(
        module_type="value_selector",
        display_name="Value Selector",
        family="Logic",
        description="Routes one of two value inputs based on selector index.",
        inputs=(
            PortSpec("a", "any", default=None),
            PortSpec("b", "any", default=None),
            PortSpec("selector", "integer", default=0),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("value", "any", default=None),
            PortSpec("selected", "integer", default=0),
            PortSpec("changed", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._selector_combo: QComboBox | None = None
        self._auto_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._selector_combo = QComboBox()
        self._selector_combo.addItems(["0", "1"])
        self._selector_combo.setCurrentIndex(self._clamp_selector(int(self.inputs["selector"])))
        self._selector_combo.currentIndexChanged.connect(
            lambda index: self.receive_binding("selector", int(index))
        )
        set_control_height(self._selector_combo)
        form.addRow("Selector", self._selector_combo)

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
        self._publish(trigger=False, error_message="", reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "selector":
            requested = int(value)
            selector = self._clamp_selector(requested)
            self.inputs["selector"] = selector
            if self._selector_combo is not None and self._selector_combo.currentIndex() != selector:
                self._selector_combo.blockSignals(True)
                self._selector_combo.setCurrentIndex(selector)
                self._selector_combo.blockSignals(False)

            error_message = ""
            if selector != requested:
                error_message = f"selector clamped to {selector}"

            if bool(self.inputs["auto"]):
                self._publish(trigger=True, error_message=error_message, reason="selector")
            else:
                self.emit("selected", selector)
                self.emit("changed", 0)
                self.emit("error", error_message)
                self._set_status(reason="selector updated", value=self._selected_value())
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            if enabled:
                self._publish(trigger=True, error_message="", reason="auto")
            return

        if port in {"a", "b"}:
            if bool(self.inputs["auto"]):
                self._publish(trigger=True, error_message="", reason=port)
            else:
                self._set_status(reason=f"cached {port}", value=self._selected_value())
            return

        if port == "emit" and is_truthy(value):
            self._publish(trigger=True, error_message="", reason="emit")

    def _publish(self, *, trigger: bool, error_message: str, reason: str) -> None:
        selector = self._clamp_selector(int(self.inputs["selector"]))
        self.inputs["selector"] = selector
        value = self._selected_value()
        self.emit("value", value)
        self.emit("selected", selector)
        self.emit("changed", 1 if trigger else 0)
        self.emit("error", error_message)
        text = f"selector={selector}, value={value!r}, reason={reason}"
        self.emit("text", text)
        self._set_status(reason=reason, value=value)

    def replay_state(self) -> None:
        self._publish(trigger=False, error_message="", reason="replay")

    def _selected_value(self) -> Any:
        selector = self._clamp_selector(int(self.inputs["selector"]))
        return self.inputs["a"] if selector == 0 else self.inputs["b"]

    def _set_status(self, *, reason: str, value: Any) -> None:
        if self._status is not None:
            self._status.setText(f"{reason}: {value!r}")

    @staticmethod
    def _clamp_selector(value: int) -> int:
        if value <= 0:
            return 0
        return 1
