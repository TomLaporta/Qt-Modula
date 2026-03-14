"""Text source module."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from qt_modula.sdk import ModuleBase, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class TextInputModule(ModuleBase):
    """Emit text values with deterministic change pulses."""

    persistent_inputs = ("text",)

    descriptor = ModuleDescriptor(
        module_type="text_input",
        display_name="Text Input",
        family="Control",
        description="Text source module with append/emit/clear controls.",
        capabilities=("source", "scheduler"),
        inputs=(
            PortSpec("text", "string", default=""),
            PortSpec(
                "append",
                "string",
                default="",
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec("emit", "trigger", default=0, control_plane=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("text", "string", default=""),
            PortSpec("changed", "trigger", default=0, control_plane=True),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._editor: QTextEdit | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        self._editor = QTextEdit()
        self._editor.setPlainText(str(self.inputs["text"]))
        self._editor.textChanged.connect(self._on_text_changed)
        doc_layout = self._editor.document().documentLayout()
        if doc_layout is not None:
            doc_layout.documentSizeChanged.connect(self._on_document_size_changed)
        self._sync_editor_height()
        layout.addWidget(self._editor)

        emit_btn = QPushButton("Emit")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        layout.addWidget(emit_btn)

        self._status = QLabel("")
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(trigger=False)
        return root

    def _editor_height_for_lines(self, lines: int) -> int:
        if self._editor is None:
            return 120
        line_height = max(1, self._editor.fontMetrics().lineSpacing())
        margin = float(self._editor.document().documentMargin()) * 2.0
        frame = self._editor.frameWidth() * 2
        return math.ceil((max(1, lines) * line_height) + margin + frame)

    def _sync_editor_height(self) -> None:
        if self._editor is None:
            return
        layout = self._editor.document().documentLayout()
        if layout is None:
            return
        line_height = max(1, self._editor.fontMetrics().lineSpacing())
        margin = float(self._editor.document().documentMargin()) * 2.0
        content = max(0.0, layout.documentSize().height() - margin)
        lines = min(10, max(1, math.ceil(content / float(line_height))))
        self._editor.setFixedHeight(self._editor_height_for_lines(lines))

    def _on_document_size_changed(self, _size: object) -> None:
        self._sync_editor_height()

    def _on_text_changed(self) -> None:
        if self._editor is None:
            return
        self.inputs["text"] = self._editor.toPlainText()
        self._sync_editor_height()
        self._publish(trigger=True)

    def _publish(self, *, trigger: bool) -> None:
        text = str(self.inputs["text"])
        self.emit("text", text)
        self.emit("changed", 1 if trigger else 0)
        self.emit("error", "")
        if self._status is not None:
            self._status.setText(f"Length: {len(text)}")

    def on_input(self, port: str, value: Any) -> None:
        if port == "text":
            text = str(value)
            self.inputs["text"] = text
            if self._editor is not None and self._editor.toPlainText() != text:
                self._editor.blockSignals(True)
                self._editor.setPlainText(text)
                self._editor.blockSignals(False)
                self._sync_editor_height()
            self._publish(trigger=True)
            return

        if port == "append":
            merged = f"{self.inputs['text']}{value}"
            self.inputs["text"] = str(merged)
            if self._editor is not None:
                self._editor.blockSignals(True)
                self._editor.setPlainText(str(self.inputs["text"]))
                self._editor.blockSignals(False)
                self._sync_editor_height()
            self._publish(trigger=True)
            return

        if port == "emit" and is_truthy(value):
            self._publish(trigger=True)
            return

        if port == "clear" and is_truthy(value):
            self.inputs["text"] = ""
            if self._editor is not None:
                self._editor.blockSignals(True)
                self._editor.clear()
                self._editor.blockSignals(False)
                self._sync_editor_height()
            self._publish(trigger=True)

    def replay_state(self) -> None:
        self._publish(trigger=False)
