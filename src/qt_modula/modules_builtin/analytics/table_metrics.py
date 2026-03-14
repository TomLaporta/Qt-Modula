"""Tabular dataset metrics module."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults


class TableMetricsModule(BaseModule):
    """Compute row/column metrics from table-shaped payloads."""

    descriptor = ModuleDescriptor(
        module_type="table_metrics",
        display_name="Table Metrics",
        family="Analytics",
        description="Computes row count and column count from table payloads.",
        inputs=(
            PortSpec("rows", "table", default=[]),
            PortSpec("emit", "trigger", default=1, control_plane=True),
        ),
        outputs=(
            PortSpec("row_count", "integer", default=0),
            PortSpec("column_count", "integer", default=0),
            PortSpec("columns", "json", default=[]),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)
        self._status = QLabel("rows=0, cols=0")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._publish()
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "rows":
            self.inputs["rows"] = value
            self._publish()
            return
        if port == "emit" and is_truthy(value):
            self._publish()

    def _publish(self) -> None:
        rows_raw = self.inputs.get("rows", [])
        if not isinstance(rows_raw, list):
            self.emit("error", "rows must be a list")
            return

        rows = rows_raw
        columns: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                columns.update(str(key) for key in row)
            elif isinstance(row, list):
                for idx in range(len(row)):
                    columns.add(f"c{idx}")

        col_list = sorted(columns)
        row_count = len(rows)
        col_count = len(col_list)
        summary = f"rows={row_count}, cols={col_count}"

        self.emit("row_count", row_count)
        self.emit("column_count", col_count)
        self.emit("columns", col_list)
        self.emit("text", summary)
        self.emit("error", "")

        if self._status is not None:
            self._status.setText(summary)
