"""Deterministic key-based value wrapper for text templates."""

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


class ValueWrapperModule(BaseModule):
    """Replace all key occurrences in `entry` with the current value."""

    persistent_inputs = ("key", "entry", "auto")

    descriptor = ModuleDescriptor(
        module_type="value_wrapper",
        display_name="Value Wrapper",
        family="Transform",
        description="Replaces all case-sensitive key matches inside entry text.",
        inputs=(
            PortSpec("value", "any", default=None),
            PortSpec("key", "string", default=""),
            PortSpec("entry", "string", default=""),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("value", "string", default=""),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._value_input: QLineEdit | None = None
        self._key_input: QLineEdit | None = None
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

        self._key_input = QLineEdit(str(self.inputs["key"]))
        self._key_input.setPlaceholderText("Key to replace")
        self._key_input.textChanged.connect(
            lambda text: self.receive_binding("key", text)
        )
        set_control_height(self._key_input)
        form.addRow("Key", self._key_input)

        self._entry_input = QLineEdit(str(self.inputs["entry"]))
        self._entry_input.setPlaceholderText("Template entry text")
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
            output_value=str(self.outputs["value"]),
            replacements=0,
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

        if port == "key":
            key_text = str(value)
            if self._key_input is not None and self._key_input.text() != key_text:
                self._key_input.blockSignals(True)
                self._key_input.setText(key_text)
                self._key_input.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._evaluate(reason="key")
            else:
                self._publish_cached(reason="key cached")
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
        template = str(self.inputs["entry"])
        key = str(self.inputs["key"])
        replacement = str(self.inputs["value"])

        if key == "":
            self._publish(
                output_value=template,
                replacements=0,
                error_message="key must be non-empty",
                reason=f"{reason}: empty key",
            )
            return

        replacements = template.count(key)
        if replacements == 0:
            self._publish(
                output_value=template,
                replacements=0,
                error_message=f"key '{key}' not found in entry",
                reason=f"{reason}: key missing",
            )
            return

        output_value = template.replace(key, replacement)
        self._publish(
            output_value=output_value,
            replacements=replacements,
            error_message="",
            reason=reason,
        )

    def _publish_cached(self, *, reason: str) -> None:
        self._publish(
            output_value=str(self.outputs.get("value", "")),
            replacements=0,
            error_message=str(self.outputs.get("error", "")),
            reason=reason,
        )

    def _publish(
        self,
        *,
        output_value: str,
        replacements: int,
        error_message: str,
        reason: str,
    ) -> None:
        key_text = str(self.inputs["key"])
        self.emit("value", output_value)
        self.emit("error", error_message)
        summary = (
            f"replacements={replacements}, key={key_text!r}, "
            f"value={output_value!r}, reason={reason}"
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
