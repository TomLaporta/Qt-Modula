"""Qt Modula v1 module template.

Use this file as a starting point for new built-in or plugin modules.
"""

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

from qt_modula.sdk import ModuleBase, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height
from qt_modula.ui.advanced_section import AdvancedSection


class TemplateModule(ModuleBase):
    """Reference implementation for Qt Modula v1 modules."""

    persistent_inputs = (
        "value",
        "auto",
    )

    descriptor = ModuleDescriptor(
        module_type="template_module",
        display_name="Template Module",
        family="Transform",
        description="Template module for contract-first authoring.",
        inputs=(
            PortSpec("value", "string", default=""),
            PortSpec(
                "auto",
                "boolean",
                default=True,
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec("emit", "trigger", default=0, control_plane=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("value", "string", default=""),
            PortSpec("changed", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._value_edit: QLineEdit | None = None
        self._auto_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._value_edit = QLineEdit(str(self.inputs["value"]))
        self._value_edit.textChanged.connect(lambda text: self.receive_binding("value", text))
        set_control_height(self._value_edit)
        form.addRow("Value", self._value_edit)

        emit_btn = QPushButton("Emit")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        form.addRow("", emit_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.receive_binding("clear", 1))
        set_control_height(clear_btn)
        form.addRow("", clear_btn)

        layout.addLayout(form)

        advanced = AdvancedSection("Advanced", expanded=False)
        self._auto_check = QCheckBox("Auto Emit")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda checked: self.receive_binding("auto", checked))
        advanced.content_layout.addWidget(self._auto_check)
        layout.addWidget(advanced)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(trigger=False, reason="ready", error_message="")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "value":
            text = str(value)
            self.inputs["value"] = text
            if self._value_edit is not None and self._value_edit.text() != text:
                self._value_edit.blockSignals(True)
                self._value_edit.setText(text)
                self._value_edit.blockSignals(False)
            self._publish(
                trigger=bool(self.inputs["auto"]),
                reason="value",
                error_message="",
            )
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            self._publish(trigger=False, reason="auto", error_message="")
            return

        if port == "emit" and is_truthy(value):
            self._publish(trigger=True, reason="emit", error_message="")
            return

        if port == "clear" and is_truthy(value):
            self.inputs["value"] = ""
            if self._value_edit is not None and self._value_edit.text() != "":
                self._value_edit.blockSignals(True)
                self._value_edit.clear()
                self._value_edit.blockSignals(False)
            self._publish(trigger=True, reason="clear", error_message="")

    def replay_state(self) -> None:
        self._publish(trigger=False, reason="replay", error_message="")

    def _publish(self, *, trigger: bool, reason: str, error_message: str) -> None:
        text = str(self.inputs["value"])
        self.emit("value", text)
        self.emit("changed", 1 if trigger else 0)
        self.emit("error", error_message)

        summary = f"{reason}: value={text!r}"
        if error_message:
            summary = f"{summary}; error={error_message}"

        self.emit("text", summary)
        if self._status is not None:
            self._status.setText(summary)
