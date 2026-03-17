"""UTF-8 text import module."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QVBoxLayout

from qt_modula.modules_builtin.importers.base import BaseImportModule
from qt_modula.sdk import ModuleDescriptor, PortSpec
from qt_modula.services.file_import import TextImportRequest, TextImportResult, read_text_file


class TextImportModule(BaseImportModule):
    """Import UTF-8 text files into workflow graphs."""

    file_filter = "Text Files (*.txt *.text *.md *.log);;All Files (*)"
    persistent_inputs = ("path", "auto_import")

    descriptor = ModuleDescriptor(
        module_type="text_import",
        display_name="Text Import",
        family="Import",
        description="Imports UTF-8 text files with staged path selection and auto-import.",
        inputs=(
            PortSpec("path", "string", default=""),
            PortSpec("auto_import", "boolean", default=False),
            PortSpec("import", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("content", "string", default=""),
            PortSpec("char_count", "integer", default=0),
            PortSpec("line_count", "integer", default=0),
            PortSpec("path", "string", default=""),
            PortSpec("imported", "trigger", default=0, control_plane=True),
            PortSpec("busy", "boolean", default=False, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
        capabilities=("source",),
    )

    def _build_controls(self, layout: QVBoxLayout) -> None:
        del layout

    def _sync_controls(self) -> None:
        return None

    def _handle_module_input(self, port: str, value: Any) -> None:
        del port, value

    def _build_status_summary(self, *, reason: str) -> str:
        path = str(self.inputs.get("path", ""))
        auto_import = int(bool(self.inputs.get("auto_import", False)))
        if path:
            return f"{reason}: staged path={path}, auto_import={auto_import}"
        return f"{reason}: no file selected, auto_import={auto_import}"

    def _run_import(self, path: str) -> object:
        return read_text_file(TextImportRequest(path=path))

    def _apply_success(self, payload: object) -> None:
        if not isinstance(payload, TextImportResult):
            raise TypeError("Unexpected text import payload")

        self.emit("content", payload.content)
        self.emit("char_count", payload.char_count)
        self.emit("line_count", payload.line_count)
        self.emit("path", str(payload.path))
        self.emit("imported", 1)
        self.emit("error", "")
        summary = (
            f"imported text: chars={payload.char_count}, lines={payload.line_count}, "
            f"path={payload.path}"
        )
        self.emit("text", summary)
        if self._status is not None:
            self._status.setText(summary)

    def _reset_outputs(self) -> dict[str, Any]:
        return {
            "content": "",
            "char_count": 0,
            "line_count": 0,
            "path": "",
            "imported": 0,
        }
