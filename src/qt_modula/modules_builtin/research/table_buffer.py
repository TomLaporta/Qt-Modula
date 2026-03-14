"""Bounded row buffer for deterministic table-assembly lanes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class TableBufferModule(BaseModule):
    """Accumulate bounded table rows with optional deduplication."""

    persistent_inputs = ("max_rows", "dedupe_key")

    descriptor = ModuleDescriptor(
        module_type="table_buffer",
        display_name="Table Buffer",
        family="Research",
        description="Buffers JSON rows into bounded table output for export lanes.",
        inputs=(
            PortSpec("row", "json", default={}),
            PortSpec("append", "trigger", default=0, control_plane=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
            PortSpec("max_rows", "integer", default=1000),
            PortSpec("dedupe_key", "string", default=""),
        ),
        outputs=(
            PortSpec("rows", "table", default=[]),
            PortSpec("row_count", "integer", default=0),
            PortSpec("appended", "trigger", default=0, control_plane=True),
            PortSpec("evicted_count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._rows: list[dict[str, Any]] = []
        self._pending_row: dict[str, Any] | None = None
        self._evicted_count = 0

        self._max_rows_spin: QSpinBox | None = None
        self._dedupe_edit: QLineEdit | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._max_rows_spin = QSpinBox()
        self._max_rows_spin.setRange(1, 10_000_000)
        self._max_rows_spin.setValue(max(1, int(self.inputs["max_rows"])))
        self._max_rows_spin.valueChanged.connect(
            lambda value: self.receive_binding("max_rows", int(value))
        )
        set_control_height(self._max_rows_spin)
        form.addRow("Max Rows", self._max_rows_spin)

        self._dedupe_edit = QLineEdit(str(self.inputs["dedupe_key"]))
        self._dedupe_edit.textChanged.connect(
            lambda text: self.receive_binding("dedupe_key", text.strip())
        )
        set_control_height(self._dedupe_edit)
        form.addRow("Dedupe Key", self._dedupe_edit)

        append_btn = QPushButton("Append")
        append_btn.clicked.connect(lambda: self.receive_binding("append", 1))
        set_control_height(append_btn)
        form.addRow("", append_btn)

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

        self._publish(appended=0, error="", reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "row":
            if isinstance(value, dict):
                self._pending_row = deepcopy(value)
                self._publish(appended=0, error="", reason="row cached")
                return
            self._publish(appended=0, error="row must be an object", reason="row rejected")
            return

        if port == "max_rows":
            requested = int(value)
            max_rows = max(1, requested)
            self.inputs["max_rows"] = max_rows
            if self._max_rows_spin is not None and self._max_rows_spin.value() != max_rows:
                self._max_rows_spin.blockSignals(True)
                self._max_rows_spin.setValue(max_rows)
                self._max_rows_spin.blockSignals(False)
            if requested < 1:
                self._publish(appended=0, error="max_rows clamped to 1", reason="config")
            else:
                self._publish(appended=0, error="", reason="config")
            self._trim_to_capacity()
            return

        if port == "dedupe_key":
            token = str(value).strip()
            self.inputs["dedupe_key"] = token
            if self._dedupe_edit is not None and self._dedupe_edit.text() != token:
                self._dedupe_edit.blockSignals(True)
                self._dedupe_edit.setText(token)
                self._dedupe_edit.blockSignals(False)
            self._publish(appended=0, error="", reason="dedupe_key updated")
            return

        if port == "append" and is_truthy(value):
            self._append_pending_row()
            return

        if port == "emit" and is_truthy(value):
            self._publish(appended=0, error="", reason="emit")
            return

        if port == "clear" and is_truthy(value):
            self._rows = []
            self._pending_row = None
            self._evicted_count = 0
            self._publish(appended=0, error="", reason="cleared")

    def _append_pending_row(self) -> None:
        if self._pending_row is None:
            self._publish(appended=0, error="no pending row", reason="append ignored")
            return

        row = deepcopy(self._pending_row)
        dedupe_key = str(self.inputs["dedupe_key"]).strip()

        if dedupe_key and dedupe_key in row:
            original_len = len(self._rows)
            self._rows = [item for item in self._rows if item.get(dedupe_key) != row[dedupe_key]]
            self._evicted_count += original_len - len(self._rows)

        self._rows.append(row)
        self._trim_to_capacity()
        self._publish(appended=1, error="", reason="appended")

    def _trim_to_capacity(self) -> None:
        max_rows = max(1, int(self.inputs["max_rows"]))
        overflow = len(self._rows) - max_rows
        if overflow <= 0:
            return
        self._rows = self._rows[overflow:]
        self._evicted_count += overflow

    def _publish(self, *, appended: int, error: str, reason: str) -> None:
        rows = [deepcopy(item) for item in self._rows]
        self.emit("rows", rows)
        self.emit("row_count", len(rows))
        self.emit("appended", 1 if appended else 0)
        self.emit("evicted_count", self._evicted_count)
        self.emit("error", error)
        text = (
            f"rows={len(rows)}, evicted={self._evicted_count}, "
            f"max_rows={int(self.inputs['max_rows'])}, reason={reason}"
        )
        self.emit("text", text if not error else f"error: {error}")
        if self._status is not None:
            self._status.setText(text if not error else f"error: {error}")
