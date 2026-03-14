"""Deterministic text membership scanner for value payloads."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class ValueScannerModule(BaseModule):
    """Scan `value` text for a case-sensitive `entry` substring."""

    persistent_inputs = ("entry", "auto")

    descriptor = ModuleDescriptor(
        module_type="value_scanner",
        display_name="Value Scanner",
        family="Transform",
        description="Scans stringified value input for a case-sensitive text entry.",
        inputs=(
            PortSpec("value", "any", default=None),
            PortSpec("entry", "string", default=""),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("in_value", "boolean", default=False),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._value_input: QLineEdit | None = None
        self._entry_input: QLineEdit | None = None
        self._auto_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._value_input = QLineEdit(self._display_value(self.inputs["value"]))
        self._value_input.setPlaceholderText("Optional manual value text")
        self._value_input.textChanged.connect(
            lambda text: self.receive_binding("value", text)
        )
        set_control_height(self._value_input)
        form.addRow("Value", self._value_input)

        self._entry_input = QLineEdit(str(self.inputs["entry"]))
        self._entry_input.setPlaceholderText("Text to scan for")
        self._entry_input.textChanged.connect(
            lambda text: self.receive_binding("entry", text)
        )
        set_control_height(self._entry_input)
        form.addRow("Entry", self._entry_input)

        self._auto_check = QCheckBox("Auto Evaluate")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(
            lambda enabled: self.receive_binding("auto", enabled)
        )
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

        self._publish(
            in_value=bool(self.outputs["in_value"]),
            error_message="",
            reason="ready",
        )
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "value":
            display_value = self._display_value(value)
            if self._value_input is not None and self._value_input.text() != display_value:
                self._value_input.blockSignals(True)
                self._value_input.setText(display_value)
                self._value_input.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._evaluate(reason="value")
            else:
                self._publish_cached(reason="value cached")
            return

        if port == "entry":
            entry_text = str(value)
            if self._entry_input is not None and self._entry_input.text() != entry_text:
                self._entry_input.blockSignals(True)
                self._entry_input.setText(entry_text)
                self._entry_input.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._evaluate(reason="entry")
            else:
                self._publish_cached(reason="entry cached")
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            if enabled:
                self._evaluate(reason="auto")
            else:
                self._publish_cached(reason="auto updated")
            return

        if port == "emit" and is_truthy(value):
            self._evaluate(reason="emit")

    def replay_state(self) -> None:
        self._evaluate(reason="replay")

    def _evaluate(self, *, reason: str) -> None:
        entry = str(self.inputs["entry"])
        if entry == "":
            self._publish(
                in_value=False,
                error_message="entry must be non-empty",
                reason=f"{reason}: empty entry",
            )
            return
        matched = entry in str(self.inputs["value"])
        self._publish(in_value=matched, error_message="", reason=reason)

    def _publish_cached(self, *, reason: str) -> None:
        self._publish(
            in_value=bool(self.outputs.get("in_value", False)),
            error_message=str(self.outputs.get("error", "")),
            reason=reason,
        )

    def _publish(self, *, in_value: bool, error_message: str, reason: str) -> None:
        self.emit("in_value", bool(in_value))
        self.emit("error", error_message)
        value_text = str(self.inputs["value"])
        entry_text = str(self.inputs["entry"])
        summary = (
            f"in_value={int(bool(in_value))}, entry={entry_text!r}, "
            f"value={value_text!r}, reason={reason}"
        )
        self.emit("text", summary)

        rendered = summary if not error_message else f"{summary}; warning: {error_message}"
        if self._status is not None:
            self._status.setText(rendered)

    @staticmethod
    def _display_value(value: Any) -> str:
        if value is None:
            return ""
        return str(value)
