"""Workflow log sink module."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QPushButton, QTextEdit, QVBoxLayout, QWidget

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class LogNotesModule(BaseModule):
    """Accumulate lines for a visible, bindable error/status bus."""

    descriptor = ModuleDescriptor(
        module_type="log_notes",
        display_name="Log Notes",
        family="Control",
        description="Append-only log sink for workflow telemetry/errors.",
        inputs=(
            PortSpec("append", "string", default=""),
            PortSpec("text", "string", default=""),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("text", "string", default=""),
            PortSpec("line_count", "integer", default=0),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._lines: list[str] = []
        self._editor: QTextEdit | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        self._editor = QTextEdit()
        self._editor.setReadOnly(True)
        layout.addWidget(self._editor)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        set_control_height(clear_btn)
        layout.addWidget(clear_btn)
        return root

    def _refresh(self) -> None:
        text = "\n".join(self._lines)
        if self._editor is not None:
            self._editor.setPlainText(text)
        self.emit("text", text)
        self.emit("line_count", len(self._lines))
        self.emit("error", "")

    def _clear(self) -> None:
        self._lines.clear()
        self._refresh()

    def on_input(self, port: str, value: Any) -> None:
        if port == "append":
            text = str(value).strip()
            if text:
                self._lines.append(text)
                self._refresh()
            return
        if port == "text":
            self._lines = list(str(value).splitlines())
            self._refresh()
            return
        if port == "clear" and is_truthy(value):
            self._clear()
