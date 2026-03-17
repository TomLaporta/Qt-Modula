"""Tabular file import module."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QWidget, QVBoxLayout

from qt_modula.modules_builtin.importers.base import BaseImportModule
from qt_modula.sdk import ModuleDescriptor, PortSpec
from qt_modula.sdk.ui import set_control_height
from qt_modula.services.file_import import TableImportRequest, TableImportResult, read_table_file

_TABLE_FORMATS = ("auto", "csv", "jsonl", "xlsx")


class TableImportModule(BaseImportModule):
    """Import CSV, JSONL, or XLSX tables into workflow graphs."""

    file_filter = "Table Files (*.csv *.jsonl *.xlsx);;All Files (*)"
    persistent_inputs = ("path", "auto_import", "format", "sheet_name")

    descriptor = ModuleDescriptor(
        module_type="table_import",
        display_name="Table Import",
        family="Import",
        description="Imports CSV, JSONL, or XLSX tables with staged path selection.",
        inputs=(
            PortSpec("path", "string", default=""),
            PortSpec("auto_import", "boolean", default=False),
            PortSpec("format", "string", default="auto"),
            PortSpec("sheet_name", "string", default=""),
            PortSpec("import", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("rows", "table", default=[]),
            PortSpec("row_count", "integer", default=0),
            PortSpec("column_count", "integer", default=0),
            PortSpec("columns", "json", default=[]),
            PortSpec("path", "string", default=""),
            PortSpec("imported", "trigger", default=0, control_plane=True),
            PortSpec("busy", "boolean", default=False, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
        capabilities=("source",),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._format_warning = ""
        self._format_combo: QComboBox | None = None
        self._sheet_name_edit: QLineEdit | None = None

    def _build_controls(self, layout: QVBoxLayout) -> None:
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)

        self._format_combo = QComboBox()
        self._format_combo.addItems(list(_TABLE_FORMATS))
        self._format_combo.currentTextChanged.connect(
            lambda text: self.receive_binding("format", text)
        )
        set_control_height(self._format_combo)
        form.addRow("Format", self._format_combo)

        self._sheet_name_edit = QLineEdit()
        self._sheet_name_edit.setPlaceholderText("Active sheet")
        self._sheet_name_edit.textChanged.connect(
            lambda text: self.receive_binding("sheet_name", text)
        )
        set_control_height(self._sheet_name_edit)
        form.addRow("Sheet Name", self._sheet_name_edit)

        layout.addWidget(form_widget)

    def _sync_controls(self) -> None:
        format_token, warning = self._normalized_format(str(self.inputs.get("format", "auto")))
        self.inputs["format"] = format_token
        self._format_warning = warning
        if self._format_combo is not None:
            self._format_combo.blockSignals(True)
            self._format_combo.setCurrentText(format_token)
            self._format_combo.blockSignals(False)

        sheet_name = str(self.inputs.get("sheet_name", ""))
        if self._sheet_name_edit is not None and self._sheet_name_edit.text() != sheet_name:
            self._sheet_name_edit.blockSignals(True)
            self._sheet_name_edit.setText(sheet_name)
            self._sheet_name_edit.blockSignals(False)

    def _handle_module_input(self, port: str, value: Any) -> None:
        if port == "format":
            token, warning = self._normalized_format(str(value))
            self.inputs["format"] = token
            self._format_warning = warning
            if self._format_combo is not None and self._format_combo.currentText() != token:
                self._format_combo.blockSignals(True)
                self._format_combo.setCurrentText(token)
                self._format_combo.blockSignals(False)
            self._publish_status(reason="format updated")
            return

        if port == "sheet_name":
            sheet_name = str(value).strip()
            self.inputs["sheet_name"] = sheet_name
            if (
                self._sheet_name_edit is not None
                and self._sheet_name_edit.text() != sheet_name
            ):
                self._sheet_name_edit.blockSignals(True)
                self._sheet_name_edit.setText(sheet_name)
                self._sheet_name_edit.blockSignals(False)
            self._publish_status(reason="sheet updated")

    def _build_status_summary(self, *, reason: str) -> str:
        path = str(self.inputs.get("path", ""))
        format_token = str(self.inputs.get("format", "auto"))
        sheet_name = str(self.inputs.get("sheet_name", "")).strip() or "<active>"
        auto_import = int(bool(self.inputs.get("auto_import", False)))
        if path:
            return (
                f"{reason}: staged path={path}, format={format_token}, "
                f"sheet={sheet_name}, auto_import={auto_import}"
            )
        return (
            f"{reason}: no file selected, format={format_token}, "
            f"sheet={sheet_name}, auto_import={auto_import}"
        )

    def _run_import(self, path: str) -> object:
        return read_table_file(
            TableImportRequest(
                path=path,
                format=str(self.inputs.get("format", "auto")),
                sheet_name=str(self.inputs.get("sheet_name", "")),
            )
        )

    def _apply_success(self, payload: object) -> None:
        if not isinstance(payload, TableImportResult):
            raise TypeError("Unexpected table import payload")

        self.emit("rows", payload.rows)
        self.emit("row_count", payload.row_count)
        self.emit("column_count", payload.column_count)
        self.emit("columns", payload.columns)
        self.emit("path", str(payload.path))
        self.emit("imported", 1)
        self.emit("error", self._compose_error(""))
        sheet_part = f", sheet={payload.sheet_name}" if payload.sheet_name else ""
        summary = (
            f"imported table: rows={payload.row_count}, columns={payload.column_count}, "
            f"format={payload.format}{sheet_part}, path={payload.path}"
        )
        self.emit("text", summary)
        if self._status is not None:
            self._status.setText(summary)

    def _reset_outputs(self) -> dict[str, Any]:
        return {
            "rows": [],
            "row_count": 0,
            "column_count": 0,
            "columns": [],
            "path": "",
            "imported": 0,
        }

    def _compose_error(self, base: str) -> str:
        parts = [self._format_warning] if self._format_warning else []
        if base:
            parts.append(base)
        return "; ".join(parts)

    @staticmethod
    def _normalized_format(value: str) -> tuple[str, str]:
        token = value.strip().lower().lstrip(".")
        if token in _TABLE_FORMATS:
            return token, ""
        return "auto", f"invalid format '{value}'; using 'auto'"
