"""Background table export module for workflow-oriented write/append lanes."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.modules_builtin.export.path_utils import build_export_path
from qt_modula.sdk import (
    AsyncServiceRunner,
    BaseModule,
    ModuleDescriptor,
    PortSpec,
    apply_async_error_policy,
    is_truthy,
)
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height
from qt_modula.services import (
    ExportRequest,
    ServiceFailure,
    capture_service_result,
    writer_for_format,
)

_FORMATS = ("csv", "jsonl", "xlsx")
_MODES = ("overwrite", "append")
_DEFAULT_FILE_STEM = "output"


class TableExportModule(BaseModule):
    """Write or append table rows to CSV/JSONL/XLSX targets."""

    persistent_inputs = ("file_name", "export_folder", "format", "mode")

    descriptor = ModuleDescriptor(
        module_type="table_export",
        display_name="Table Export",
        family="Export",
        description="Workflow-grade table export with overwrite/append controls.",
        inputs=(
            PortSpec("rows", "table", default=[]),
            PortSpec("file_name", "string", default=_DEFAULT_FILE_STEM),
            PortSpec("export_folder", "string", default=""),
            PortSpec("format", "string", default="csv"),
            PortSpec("mode", "string", default="overwrite"),
            PortSpec("write", "trigger", default=0, control_plane=True),
            PortSpec("overwrite", "trigger", default=0, control_plane=True),
            PortSpec("append", "trigger", default=0, control_plane=True),
            PortSpec("refresh", "trigger", default=0, control_plane=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("path", "string", default=""),
            PortSpec("row_count", "integer", default=0),
            PortSpec("total_row_count", "integer", default=0),
            PortSpec("wrote", "trigger", default=0, control_plane=True),
            PortSpec("busy", "boolean", default=False, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._runner = AsyncServiceRunner()
        self._runner.completed.connect(self._on_done)
        self._runner.failed.connect(self._on_failed)
        self._option_warnings: dict[str, str] = {"format": "", "mode": ""}

        self._file_name_edit: QLineEdit | None = None
        self._export_folder_edit: QLineEdit | None = None
        self._format_combo: QComboBox | None = None
        self._mode_combo: QComboBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._file_name_edit = QLineEdit(str(self.inputs["file_name"]))
        self._file_name_edit.textChanged.connect(
            lambda text: self.receive_binding("file_name", text)
        )
        set_control_height(self._file_name_edit)
        form.addRow("File Name", self._file_name_edit)

        self._export_folder_edit = QLineEdit(str(self.inputs["export_folder"]))
        self._export_folder_edit.textChanged.connect(
            lambda text: self.receive_binding("export_folder", text)
        )
        set_control_height(self._export_folder_edit)
        form.addRow("Export Folder", self._export_folder_edit)

        self._format_combo = QComboBox()
        self._format_combo.addItems(list(_FORMATS))
        format_token, format_warning = self._normalized_format(str(self.inputs["format"]))
        self.inputs["format"] = format_token
        self._option_warnings["format"] = format_warning
        self._format_combo.setCurrentText(format_token)
        self._format_combo.currentTextChanged.connect(
            lambda text: self.receive_binding("format", text)
        )
        set_control_height(self._format_combo)
        form.addRow("Format", self._format_combo)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(list(_MODES))
        mode_token, mode_warning = self._normalized_mode(str(self.inputs["mode"]))
        self.inputs["mode"] = mode_token
        self._option_warnings["mode"] = mode_warning
        self._mode_combo.setCurrentText(mode_token)
        self._mode_combo.currentTextChanged.connect(lambda text: self.receive_binding("mode", text))
        set_control_height(self._mode_combo)
        form.addRow("Mode", self._mode_combo)

        layout.addLayout(form)

        write_btn = QPushButton("Write")
        write_btn.clicked.connect(lambda: self.receive_binding("write", 1))
        set_control_height(write_btn)
        layout.addWidget(write_btn)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._set_busy(False)
        self._publish_status(reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "file_name":
            text = str(value).strip() or _DEFAULT_FILE_STEM
            self.inputs["file_name"] = text
            if self._file_name_edit is not None and self._file_name_edit.text() != text:
                self._file_name_edit.blockSignals(True)
                self._file_name_edit.setText(text)
                self._file_name_edit.blockSignals(False)
            self._publish_status(reason="file_name updated")
            return

        if port == "export_folder":
            text = str(value)
            self.inputs["export_folder"] = text
            if (
                self._export_folder_edit is not None
                and self._export_folder_edit.text() != text
            ):
                self._export_folder_edit.blockSignals(True)
                self._export_folder_edit.setText(text)
                self._export_folder_edit.blockSignals(False)
            self._publish_status(reason="export_folder updated")
            return

        if port == "format":
            token, warning = self._normalized_format(str(value))
            self.inputs["format"] = token
            self._option_warnings["format"] = warning
            if self._format_combo is not None and self._format_combo.currentText() != token:
                self._format_combo.blockSignals(True)
                self._format_combo.setCurrentText(token)
                self._format_combo.blockSignals(False)
            self._publish_status(reason="format updated")
            return

        if port == "mode":
            token, warning = self._normalized_mode(str(value))
            self.inputs["mode"] = token
            self._option_warnings["mode"] = warning
            if self._mode_combo is not None and self._mode_combo.currentText() != token:
                self._mode_combo.blockSignals(True)
                self._mode_combo.setCurrentText(token)
                self._mode_combo.blockSignals(False)
            self._publish_status(reason="mode updated")
            return

        if port == "rows":
            self._publish_status(reason="rows updated")
            return

        if port == "write" and is_truthy(value):
            self._start_export()
            return

        if port == "overwrite" and is_truthy(value):
            self._start_export(force_mode="overwrite")
            return

        if port == "append" and is_truthy(value):
            self._start_export(force_mode="append")
            return

        if port == "refresh" and is_truthy(value):
            self._publish_status(reason="refreshed")
            return

        if port == "clear" and is_truthy(value):
            self.emit("error", self._compose_error(""))
            self.emit("text", "")
            self.emit("wrote", 0)
            if self._status is not None:
                self._status.setText("")

    def _start_export(self, *, force_mode: str | None = None) -> None:
        if self._runner.running():
            return

        rows_any = self.inputs.get("rows", [])
        if not isinstance(rows_any, list):
            self._on_failed(ServiceFailure(message="rows must be a list", kind="validation"))
            return

        rows: list[dict[str, Any]] = []
        for item in rows_any:
            if isinstance(item, dict):
                rows.append({str(key): value for key, value in item.items()})
            else:
                rows.append({"value": item})

        export_format, format_warning = self._normalized_format(str(self.inputs["format"]))
        self._option_warnings["format"] = format_warning
        export_path = self._resolved_target_path(export_format)
        mode, mode_warning = self._normalized_mode(force_mode or str(self.inputs["mode"]))
        self._option_warnings["mode"] = mode_warning
        self._set_busy(True)

        def call() -> dict[str, Any]:
            writer = writer_for_format(export_format)
            result = writer.write(ExportRequest(path=export_path, rows=rows, mode=mode))
            return {
                "path": str(result.path),
                "row_count": result.row_count,
                "total_row_count": result.total_row_count,
                "format": export_format,
                "mode": mode,
            }

        self._runner.submit(lambda: capture_service_result(call))

    def _on_done(self, payload: object) -> None:
        self._set_busy(False)
        if not isinstance(payload, dict):
            self._on_failed(ServiceFailure(message="Unexpected export payload", kind="unknown"))
            return

        path = str(payload.get("path", ""))
        row_count = int(payload.get("row_count", 0))
        total_row_count = int(payload.get("total_row_count", row_count))
        fmt = str(payload.get("format", ""))
        mode = str(payload.get("mode", ""))

        self.emit("path", path)
        self.emit("row_count", row_count)
        self.emit("total_row_count", total_row_count)
        self.emit("wrote", 1)
        self.emit("error", self._compose_error(""))
        summary = f"{mode}: wrote {row_count} rows (total {total_row_count}) as {fmt} -> {path}"
        self.emit("text", summary)
        if self._status is not None:
            self._status.setText(summary)

    def _on_failed(self, failure: object) -> None:
        self._set_busy(False)
        normalized = (
            failure
            if isinstance(failure, ServiceFailure)
            else ServiceFailure(message="Unknown async failure", kind="unknown")
        )
        apply_async_error_policy(
            self,
            normalized,
            reset_outputs={
                "path": "",
                "row_count": 0,
                "total_row_count": 0,
                "wrote": 0,
            },
            status_sink=self._status,
        )

    def _publish_status(self, *, reason: str) -> None:
        rows_any = self.inputs.get("rows", [])
        row_count = len(rows_any) if isinstance(rows_any, list) else 0
        format_token, _ = self._normalized_format(str(self.inputs["format"]))
        mode_token, _ = self._normalized_mode(str(self.inputs["mode"]))
        path_preview = str(self._resolved_target_path(format_token))
        summary = (
            f"{reason}: rows_ready={row_count}, format={format_token}, "
            f"mode={mode_token}, path={path_preview}"
        )
        self.emit("text", summary)
        self.emit("error", self._compose_error(""))
        if self._status is not None:
            self._status.setText(summary)

    def _set_busy(self, busy: bool) -> None:
        self.emit("busy", busy)

    @staticmethod
    def _normalized_format(value: str) -> tuple[str, str]:
        token = value.strip().lower().lstrip(".")
        if token in _FORMATS:
            return token, ""
        return "csv", f"invalid format '{value}'; using 'csv'"

    @staticmethod
    def _normalized_mode(value: str) -> tuple[str, str]:
        token = value.strip().lower()
        if token in _MODES:
            return token, ""
        return "overwrite", f"invalid mode '{value}'; using 'overwrite'"

    def _compose_error(self, base: str) -> str:
        parts = [message for message in self._option_warnings.values() if message]
        if base:
            parts.append(base)
        return "; ".join(parts)

    def _resolved_target_path(self, export_format: str) -> Any:
        return build_export_path(
            file_name=str(self.inputs["file_name"]),
            export_folder=str(self.inputs["export_folder"]),
            extension=export_format,
            default_stem=_DEFAULT_FILE_STEM,
        )

    def on_close(self) -> None:
        self._runner.shutdown()
