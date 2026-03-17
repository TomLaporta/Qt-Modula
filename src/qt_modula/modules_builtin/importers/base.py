"""Shared base for single-file import modules."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from qt_modula.sdk import AsyncServiceRunner, ModuleBase, apply_async_error_policy, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults
from qt_modula.services import ServiceFailure, capture_service_result
from qt_modula.ui.file_selector import SingleFileSelector


class BaseImportModule(ModuleBase):
    """Shared widget, async, and staged-path behavior for import modules."""

    file_filter = "All Files (*)"

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._runner = AsyncServiceRunner()
        self._runner.completed.connect(self._on_done)
        self._runner.failed.connect(self._on_failed)

        self._selector: SingleFileSelector | None = None
        self._status: QLabel | None = None
        self._restoring_inputs = False

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        self._selector = SingleFileSelector(
            dialog_title=f"Select {self.descriptor.display_name} File",
            file_filter=self.file_filter,
        )
        self._selector.set_path(str(self.inputs.get("path", "")))
        self._selector.set_auto_import(bool(self.inputs.get("auto_import", False)))
        self._selector.pathCommitted.connect(lambda path: self.receive_binding("path", path))
        self._selector.autoImportChanged.connect(
            lambda enabled: self.receive_binding("auto_import", enabled)
        )
        self._selector.importRequested.connect(lambda: self.receive_binding("import", 1))
        self._selector.selectionRejected.connect(self._on_selector_rejected)
        layout.addWidget(self._selector)

        self._build_controls(layout)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._sync_controls()
        self._publish_status(reason="ready")
        return root

    def restore_inputs(self, inputs: dict[str, Any]) -> None:
        self._restoring_inputs = True
        try:
            super().restore_inputs(inputs)
        finally:
            self._restoring_inputs = False

    def replay_state(self) -> None:
        return None

    def on_input(self, port: str, value: Any) -> None:
        if port == "path":
            self._handle_path_input(str(value))
            return

        if port == "auto_import":
            enabled = bool(value)
            self.inputs["auto_import"] = enabled
            if self._selector is not None:
                self._selector.set_auto_import(enabled)
            self._publish_status(reason="auto_import updated")
            return

        if port == "import" and is_truthy(value):
            self._start_import(reason="manual import")
            return

        self._handle_module_input(port, value)

    def on_close(self) -> None:
        self._runner.shutdown()

    def _handle_path_input(self, value: str) -> None:
        token = self._normalized_path(value)
        self.inputs["path"] = token
        if self._selector is not None:
            self._selector.set_path(token)

        if self._restoring_inputs:
            self._publish_status(reason="path restored")
            return
        if token and bool(self.inputs.get("auto_import", False)):
            self._start_import(reason="path updated")
            return
        self._publish_status(reason="path updated" if token else "path cleared")

    def _start_import(self, *, reason: str) -> None:
        if self._runner.running():
            return

        path = str(self.inputs.get("path", "")).strip()
        if not path:
            self._on_failed(ServiceFailure(message="path is required", kind="validation"))
            return

        self.emit("busy", True)
        importing_summary = self._build_busy_summary(reason=reason)
        self.emit("text", importing_summary)
        self.emit("error", self._compose_error(""))
        if self._status is not None:
            self._status.setText(importing_summary)

        self._runner.submit(lambda: capture_service_result(lambda: self._run_import(path)))

    def _on_done(self, payload: object) -> None:
        self.emit("busy", False)
        try:
            self._apply_success(payload)
        except Exception as exc:
            message = str(exc).strip() or "Unexpected import payload"
            self._on_failed(ServiceFailure(message=message, kind="unknown"))

    def _on_failed(self, failure: object) -> None:
        self.emit("busy", False)
        normalized = (
            failure
            if isinstance(failure, ServiceFailure)
            else ServiceFailure(message="Unknown async failure", kind="unknown")
        )
        apply_async_error_policy(
            self,
            normalized,
            reset_outputs=self._reset_outputs(),
            status_sink=self._status,
        )
        self.emit("error", self._compose_error(normalized.message))

    def _publish_status(self, *, reason: str) -> None:
        summary = self._build_status_summary(reason=reason)
        error_message = self._compose_error("")
        self.emit("text", summary)
        self.emit("error", error_message)
        if self._status is None:
            return
        if error_message:
            self._status.setText(f"{summary}; warning: {error_message}")
            return
        self._status.setText(summary)

    def _on_selector_rejected(self, message: str) -> None:
        summary = f"selection rejected: {message}"
        self.emit("text", summary)
        self.emit("error", message)
        if self._status is not None:
            self._status.setText(summary)

    @staticmethod
    def _normalized_path(value: str) -> str:
        token = value.strip()
        if not token:
            return ""
        return str(Path(token).expanduser().resolve(strict=False))

    def _compose_error(self, base: str) -> str:
        return base

    def _build_busy_summary(self, *, reason: str) -> str:
        path = str(self.inputs.get("path", ""))
        return f"importing: reason={reason}, path={path}"

    @abstractmethod
    def _build_controls(self, layout: QVBoxLayout) -> None:
        """Attach module-specific controls below the shared file selector."""

    @abstractmethod
    def _sync_controls(self) -> None:
        """Sync module-specific widgets from inputs."""

    @abstractmethod
    def _handle_module_input(self, port: str, value: Any) -> None:
        """Handle module-specific input ports."""

    @abstractmethod
    def _build_status_summary(self, *, reason: str) -> str:
        """Build module-specific status text."""

    @abstractmethod
    def _run_import(self, path: str) -> object:
        """Execute one typed import request."""

    @abstractmethod
    def _apply_success(self, payload: object) -> None:
        """Publish one successful import payload."""

    @abstractmethod
    def _reset_outputs(self) -> dict[str, Any]:
        """Reset stale success outputs after a failed import."""
