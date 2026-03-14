"""Read-only value sink module."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from qt_modula.sdk import ModuleBase, ModuleDescriptor, PortSpec
from qt_modula.sdk.ui import apply_layout_defaults


class ValueViewModule(ModuleBase):
    """Display arbitrary incoming values."""

    descriptor = ModuleDescriptor(
        module_type="value_view",
        display_name="Value View",
        family="Control",
        description="Read-only sink that mirrors incoming values.",
        capabilities=("sink",),
        inputs=(
            PortSpec("value", "any", default=None),
            PortSpec("text", "string", default=""),
        ),
        outputs=(
            PortSpec("value", "any", default=None),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._label: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)
        self._label = QLabel("(no value)")
        self._label.setWordWrap(True)
        layout.addWidget(self._label)
        layout.addStretch(1)
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "value":
            self.emit("value", value)
            text = repr(value)
            self.emit("text", text)
            self.emit("error", "")
            if self._label is not None:
                self._label.setText(text)
            return

        if port == "text":
            text = str(value)
            self.emit("text", text)
            self.emit("error", "")
            if self._label is not None:
                self._label.setText(text)
