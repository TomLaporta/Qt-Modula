"""Background text export module with workflow-first input bindings."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
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
    ServiceFailure,
    TextExportRequest,
    capture_service_result,
    text_writer_for_format,
)

_EXTENSIONS = ("txt", "docx", "json")
_MODES = ("overwrite", "append")
_JSON_KEY_CONFLICT_OPTIONS = ("overwrite", "error", "skip")
_JSON_DUPLICATE_OPTIONS = ("error", "last_wins")
_DEFAULT_FILE_STEM = "notes"


class TextExportModule(BaseModule):
    """Write `.txt`, `.docx`, or `.json` text with workflow-first controls."""

    persistent_inputs = (
        "file_name",
        "export_folder",
        "extension",
        "mode",
        "json_dictionary_bound",
        "json_key_conflict",
        "json_duplicate_keys",
    )

    descriptor = ModuleDescriptor(
        module_type="text_export",
        display_name="Text Export",
        family="Export",
        description="Exports text payloads with append sections and bind-friendly controls.",
        inputs=(
            PortSpec("text", "string", default=""),
            PortSpec("append_text", "string", default=""),
            PortSpec("file_name", "string", default=_DEFAULT_FILE_STEM),
            PortSpec("export_folder", "string", default=""),
            PortSpec("extension", "string", default="txt"),
            PortSpec("mode", "string", default="overwrite"),
            PortSpec("tag", "string", default=""),
            PortSpec("section_title", "string", default=""),
            PortSpec("auto_write", "boolean", default=False),
            PortSpec("json_dictionary_bound", "boolean", default=False),
            PortSpec("json_key_conflict", "string", default="overwrite"),
            PortSpec("json_duplicate_keys", "string", default="error"),
            PortSpec("write", "trigger", default=0, control_plane=True),
            PortSpec("export", "trigger", default=0, control_plane=True),
            PortSpec("overwrite", "trigger", default=0, control_plane=True),
            PortSpec("append", "trigger", default=0, control_plane=True),
            PortSpec("refresh", "trigger", default=0, control_plane=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("path", "string", default=""),
            PortSpec("wrote", "trigger", default=0, control_plane=True),
            PortSpec("busy", "boolean", default=False, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
            PortSpec("char_count", "integer", default=0),
            PortSpec("line_count", "integer", default=0),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._runner = AsyncServiceRunner()
        self._runner.completed.connect(self._on_done)
        self._runner.failed.connect(self._on_failed)
        self._option_warnings: dict[str, str] = {
            "extension": "",
            "mode": "",
            "json_key_conflict": "",
            "json_duplicate_keys": "",
        }

        self._file_name_edit: QLineEdit | None = None
        self._export_folder_edit: QLineEdit | None = None
        self._tag_edit: QLineEdit | None = None
        self._section_title_edit: QLineEdit | None = None
        self._extension_combo: QComboBox | None = None
        self._mode_combo: QComboBox | None = None
        self._auto_write_check: QCheckBox | None = None
        self._json_controls: QWidget | None = None
        self._json_bound_check: QCheckBox | None = None
        self._json_key_conflict_combo: QComboBox | None = None
        self._json_duplicate_combo: QComboBox | None = None
        self._text_edit: QTextEdit | None = None
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

        self._tag_edit = QLineEdit(str(self.inputs["tag"]))
        self._tag_edit.textChanged.connect(lambda text: self.receive_binding("tag", text))
        set_control_height(self._tag_edit)
        form.addRow("Tag", self._tag_edit)

        self._section_title_edit = QLineEdit(str(self.inputs["section_title"]))
        self._section_title_edit.textChanged.connect(
            lambda text: self.receive_binding("section_title", text)
        )
        set_control_height(self._section_title_edit)
        form.addRow("Section Title", self._section_title_edit)

        self._extension_combo = QComboBox()
        self._extension_combo.addItems(list(_EXTENSIONS))
        extension_token, extension_warning = self._normalized_extension(
            str(self.inputs["extension"])
        )
        self.inputs["extension"] = extension_token
        self._option_warnings["extension"] = extension_warning
        self._extension_combo.setCurrentText(extension_token)
        self._extension_combo.currentTextChanged.connect(
            lambda text: self.receive_binding("extension", text)
        )
        set_control_height(self._extension_combo)
        form.addRow("Extension", self._extension_combo)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(list(_MODES))
        mode_token, mode_warning = self._normalized_mode(str(self.inputs["mode"]))
        self.inputs["mode"] = mode_token
        self._option_warnings["mode"] = mode_warning
        self._mode_combo.setCurrentText(mode_token)
        self._mode_combo.currentTextChanged.connect(lambda text: self.receive_binding("mode", text))
        set_control_height(self._mode_combo)
        form.addRow("Mode", self._mode_combo)

        self._auto_write_check = QCheckBox("Auto Write on Text Change")
        self._auto_write_check.setChecked(bool(self.inputs["auto_write"]))
        self._auto_write_check.toggled.connect(
            lambda enabled: self.receive_binding("auto_write", enabled)
        )
        form.addRow("", self._auto_write_check)

        layout.addLayout(form)

        self._json_controls = QWidget()
        json_layout = QVBoxLayout(self._json_controls)
        json_layout.setContentsMargins(0, 0, 0, 0)
        json_layout.setSpacing(4)

        self._json_bound_check = QCheckBox("JSON Dictionary Bound")
        self._json_bound_check.setChecked(bool(self.inputs["json_dictionary_bound"]))
        self._json_bound_check.toggled.connect(
            lambda enabled: self.receive_binding("json_dictionary_bound", enabled)
        )
        set_control_height(self._json_bound_check)
        json_layout.addWidget(self._json_bound_check)

        json_row = QHBoxLayout()
        json_row.setContentsMargins(0, 0, 0, 0)
        json_row.setSpacing(6)
        json_row.addWidget(QLabel("Conflict"))

        self._json_key_conflict_combo = QComboBox()
        self._json_key_conflict_combo.addItems(list(_JSON_KEY_CONFLICT_OPTIONS))
        json_key_conflict, json_key_warning = self._normalized_json_key_conflict(
            str(self.inputs["json_key_conflict"])
        )
        self.inputs["json_key_conflict"] = json_key_conflict
        self._option_warnings["json_key_conflict"] = json_key_warning
        self._json_key_conflict_combo.setCurrentText(json_key_conflict)
        self._json_key_conflict_combo.currentTextChanged.connect(
            lambda text: self.receive_binding("json_key_conflict", text)
        )
        set_control_height(self._json_key_conflict_combo)
        json_row.addWidget(self._json_key_conflict_combo)

        json_row.addWidget(QLabel("Duplicate Keys"))
        self._json_duplicate_combo = QComboBox()
        self._json_duplicate_combo.addItems(list(_JSON_DUPLICATE_OPTIONS))
        json_duplicate, json_duplicate_warning = self._normalized_json_duplicate_keys(
            str(self.inputs["json_duplicate_keys"])
        )
        self.inputs["json_duplicate_keys"] = json_duplicate
        self._option_warnings["json_duplicate_keys"] = json_duplicate_warning
        self._json_duplicate_combo.setCurrentText(json_duplicate)
        self._json_duplicate_combo.currentTextChanged.connect(
            lambda text: self.receive_binding("json_duplicate_keys", text)
        )
        set_control_height(self._json_duplicate_combo)
        json_row.addWidget(self._json_duplicate_combo)

        json_layout.addLayout(json_row)
        layout.addWidget(self._json_controls)

        self._text_edit = QTextEdit()
        self._text_edit.setPlainText(str(self.inputs["text"]))
        self._text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._text_edit)

        write_btn = QPushButton("Write")
        write_btn.clicked.connect(lambda: self.receive_binding("write", 1))
        set_control_height(write_btn)
        layout.addWidget(write_btn)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._set_busy(False)
        self._sync_json_controls_visibility()
        self._publish_status(reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "text":
            text = str(value)
            self.inputs["text"] = text
            if self._text_edit is not None and self._text_edit.toPlainText() != text:
                self._text_edit.blockSignals(True)
                self._text_edit.setPlainText(text)
                self._text_edit.blockSignals(False)
            if bool(self.inputs["auto_write"]):
                self._start_export()
            else:
                self._publish_status(reason="text updated")
            return

        if port == "append_text":
            merged = f"{self.inputs['text']}{value}"
            self.inputs["text"] = merged
            self.inputs["append_text"] = ""
            if self._text_edit is not None:
                self._text_edit.blockSignals(True)
                self._text_edit.setPlainText(merged)
                self._text_edit.blockSignals(False)
            if bool(self.inputs["auto_write"]):
                self._start_export()
            else:
                self._publish_status(reason="text appended")
            return

        if port == "file_name":
            token = str(value).strip() or _DEFAULT_FILE_STEM
            self.inputs["file_name"] = token
            if self._file_name_edit is not None and self._file_name_edit.text() != token:
                self._file_name_edit.blockSignals(True)
                self._file_name_edit.setText(token)
                self._file_name_edit.blockSignals(False)
            self._publish_status(reason="file_name updated")
            return

        if port == "export_folder":
            token = str(value)
            self.inputs["export_folder"] = token
            if self._export_folder_edit is not None and self._export_folder_edit.text() != token:
                self._export_folder_edit.blockSignals(True)
                self._export_folder_edit.setText(token)
                self._export_folder_edit.blockSignals(False)
            self._publish_status(reason="export_folder updated")
            return

        if port == "extension":
            token, warning = self._normalized_extension(str(value))
            self.inputs["extension"] = token
            self._option_warnings["extension"] = warning
            if self._extension_combo is not None and self._extension_combo.currentText() != token:
                self._extension_combo.blockSignals(True)
                self._extension_combo.setCurrentText(token)
                self._extension_combo.blockSignals(False)
            self._sync_json_controls_visibility()
            self._publish_status(reason="extension updated")
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

        if port == "tag":
            token = str(value)
            self.inputs["tag"] = token
            if self._tag_edit is not None and self._tag_edit.text() != token:
                self._tag_edit.blockSignals(True)
                self._tag_edit.setText(token)
                self._tag_edit.blockSignals(False)
            self._publish_status(reason="tag updated")
            return

        if port == "section_title":
            token = str(value)
            self.inputs["section_title"] = token
            if self._section_title_edit is not None and self._section_title_edit.text() != token:
                self._section_title_edit.blockSignals(True)
                self._section_title_edit.setText(token)
                self._section_title_edit.blockSignals(False)
            self._publish_status(reason="section updated")
            return

        if port == "auto_write":
            enabled = bool(value)
            self.inputs["auto_write"] = enabled
            if self._auto_write_check is not None and self._auto_write_check.isChecked() != enabled:
                self._auto_write_check.blockSignals(True)
                self._auto_write_check.setChecked(enabled)
                self._auto_write_check.blockSignals(False)
            self._publish_status(reason="auto_write updated")
            return

        if port == "json_dictionary_bound":
            enabled = bool(value)
            self.inputs["json_dictionary_bound"] = enabled
            if self._json_bound_check is not None and self._json_bound_check.isChecked() != enabled:
                self._json_bound_check.blockSignals(True)
                self._json_bound_check.setChecked(enabled)
                self._json_bound_check.blockSignals(False)
            self._publish_status(reason="json_dictionary_bound updated")
            return

        if port == "json_key_conflict":
            token, warning = self._normalized_json_key_conflict(str(value))
            self.inputs["json_key_conflict"] = token
            self._option_warnings["json_key_conflict"] = warning
            if (
                self._json_key_conflict_combo is not None
                and self._json_key_conflict_combo.currentText() != token
            ):
                self._json_key_conflict_combo.blockSignals(True)
                self._json_key_conflict_combo.setCurrentText(token)
                self._json_key_conflict_combo.blockSignals(False)
            self._publish_status(reason="json_key_conflict updated")
            return

        if port == "json_duplicate_keys":
            token, warning = self._normalized_json_duplicate_keys(str(value))
            self.inputs["json_duplicate_keys"] = token
            self._option_warnings["json_duplicate_keys"] = warning
            if (
                self._json_duplicate_combo is not None
                and self._json_duplicate_combo.currentText() != token
            ):
                self._json_duplicate_combo.blockSignals(True)
                self._json_duplicate_combo.setCurrentText(token)
                self._json_duplicate_combo.blockSignals(False)
            self._publish_status(reason="json_duplicate_keys updated")
            return

        if port in {"write", "export"} and is_truthy(value):
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
            self._clear_transient_inputs()

    def _on_text_changed(self) -> None:
        if self._text_edit is None:
            return
        self.receive_binding("text", self._text_edit.toPlainText())

    def _start_export(self, *, force_mode: str | None = None) -> None:
        if self._runner.running():
            return

        extension, extension_warning = self._normalized_extension(str(self.inputs["extension"]))
        self._option_warnings["extension"] = extension_warning
        mode, mode_warning = self._normalized_mode(force_mode or str(self.inputs["mode"]))
        self._option_warnings["mode"] = mode_warning
        section_title = str(self.inputs["section_title"]).strip()
        payload = self._prepared_text_payload()
        target = self._resolved_target_path(extension)

        json_dictionary_bound = bool(self.inputs["json_dictionary_bound"])
        if extension == "json" and not json_dictionary_bound and not section_title:
            summary = (
                "skip: section_title is required for .json export when "
                "JSON Dictionary Bound is off"
            )
            self.emit("wrote", 0)
            self.emit("error", "")
            self.emit("text", summary)
            if self._status is not None:
                self._status.setText(summary)
            return

        self._set_busy(True)

        def call() -> dict[str, Any]:
            writer = text_writer_for_format(extension)
            result = writer.write(
                TextExportRequest(
                    path=target,
                    text=payload,
                    mode=mode,
                    section_title=section_title,
                    json_dictionary_bound=json_dictionary_bound,
                    json_key_conflict=self._normalized_json_key_conflict(
                        str(self.inputs["json_key_conflict"])
                    )[0],
                    json_duplicate_keys=self._normalized_json_duplicate_keys(
                        str(self.inputs["json_duplicate_keys"])
                    )[0],
                )
            )
            return {
                "path": str(result.path),
                "char_count": result.char_count,
                "line_count": result.line_count,
                "mode": mode,
                "extension": extension,
                "wrote": bool(result.wrote),
            }

        self._runner.submit(lambda: capture_service_result(call))

    def _on_done(self, payload: object) -> None:
        self._set_busy(False)
        if not isinstance(payload, dict):
            self._on_failed(ServiceFailure(message="Unexpected export payload", kind="unknown"))
            return

        path = str(payload.get("path", ""))
        char_count = int(payload.get("char_count", 0))
        line_count = int(payload.get("line_count", 0))
        mode = str(payload.get("mode", ""))
        extension = str(payload.get("extension", ""))
        wrote = bool(payload.get("wrote", True))

        self.emit("path", path)
        self.emit("char_count", char_count)
        self.emit("line_count", line_count)
        self.emit("wrote", 1 if wrote else 0)
        self.emit("error", self._compose_error(""))

        if wrote:
            summary = (
                f"{mode}: wrote {char_count} chars ({line_count} lines) "
                f"as .{extension} -> {path}"
            )
        else:
            summary = f"{mode}: no-op for .{extension} -> {path}"

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
                "char_count": 0,
                "line_count": 0,
                "wrote": 0,
            },
            status_sink=self._status,
        )

    def _publish_status(self, *, reason: str) -> None:
        extension, _ = self._normalized_extension(str(self.inputs["extension"]))
        target = self._resolved_target_path(extension)
        mode, _ = self._normalized_mode(str(self.inputs["mode"]))
        text_value = str(self.inputs["text"])
        lines = len(text_value.splitlines()) if text_value else 0

        if extension == "json":
            key_conflict, _ = self._normalized_json_key_conflict(
                str(self.inputs["json_key_conflict"])
            )
            duplicate_keys, _ = self._normalized_json_duplicate_keys(
                str(self.inputs["json_duplicate_keys"])
            )
            summary = (
                f"{reason}: mode={mode}, extension=.json, path={target}, "
                f"json_bound={bool(self.inputs['json_dictionary_bound'])}, "
                f"conflict={key_conflict}, duplicates={duplicate_keys}, "
                f"chars={len(text_value)}, lines={lines}"
            )
        else:
            summary = (
                f"{reason}: mode={mode}, extension=.{extension}, path={target}, "
                f"chars={len(text_value)}, lines={lines}"
            )

        self.emit("text", summary)
        self.emit("error", self._compose_error(""))
        if self._status is not None:
            self._status.setText(summary)

    def _clear_transient_inputs(self) -> None:
        self.inputs["text"] = ""
        self.inputs["append_text"] = ""
        self.inputs["tag"] = ""
        self.inputs["section_title"] = ""

        if self._text_edit is not None:
            self._text_edit.blockSignals(True)
            self._text_edit.clear()
            self._text_edit.blockSignals(False)
        if self._tag_edit is not None:
            self._tag_edit.blockSignals(True)
            self._tag_edit.clear()
            self._tag_edit.blockSignals(False)
        if self._section_title_edit is not None:
            self._section_title_edit.blockSignals(True)
            self._section_title_edit.clear()
            self._section_title_edit.blockSignals(False)

        self.emit("error", self._compose_error(""))
        self.emit("wrote", 0)
        self.emit("char_count", 0)
        self.emit("line_count", 0)
        self.emit("text", "")
        if self._status is not None:
            self._status.setText("")

    def _prepared_text_payload(self) -> str:
        text = str(self.inputs["text"])
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _resolved_target_path(self, extension: str) -> Any:
        return build_export_path(
            file_name=str(self.inputs["file_name"]),
            export_folder=str(self.inputs["export_folder"]),
            extension=extension,
            default_stem=_DEFAULT_FILE_STEM,
            tag=str(self.inputs["tag"]),
        )

    def _set_busy(self, busy: bool) -> None:
        self.emit("busy", busy)

    def _sync_json_controls_visibility(self) -> None:
        if self._json_controls is None:
            return
        is_json = self._normalized_extension(str(self.inputs["extension"]))[0] == "json"
        self._json_controls.setVisible(is_json)

    @staticmethod
    def _normalized_extension(value: str) -> tuple[str, str]:
        token = value.strip().lower().lstrip(".")
        if token in _EXTENSIONS:
            return token, ""
        return "txt", f"invalid extension '{value}'; using 'txt'"

    @staticmethod
    def _normalized_mode(value: str) -> tuple[str, str]:
        token = value.strip().lower()
        if token in _MODES:
            return token, ""
        return "overwrite", f"invalid mode '{value}'; using 'overwrite'"

    @staticmethod
    def _normalized_json_key_conflict(value: str) -> tuple[str, str]:
        token = value.strip().lower()
        if token in _JSON_KEY_CONFLICT_OPTIONS:
            return token, ""
        return "overwrite", f"invalid json_key_conflict '{value}'; using 'overwrite'"

    @staticmethod
    def _normalized_json_duplicate_keys(value: str) -> tuple[str, str]:
        token = value.strip().lower()
        if token in _JSON_DUPLICATE_OPTIONS:
            return token, ""
        return "error", f"invalid json_duplicate_keys '{value}'; using 'error'"

    def _compose_error(self, base: str) -> str:
        parts = [message for message in self._option_warnings.values() if message]
        if base:
            parts.append(base)
        return "; ".join(parts)

    def on_close(self) -> None:
        self._runner.shutdown()
