"""Deterministic retry orchestrator for trigger-driven workflows."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class RetryControllerModule(BaseModule):
    """Coordinate retry attempts based on success/failure trigger feedback."""

    persistent_inputs = ("max_attempts", "backoff_ms")

    descriptor = ModuleDescriptor(
        module_type="retry_controller",
        display_name="Retry Controller",
        family="Logic",
        description="Deterministic retry scheduler for fetch/request lanes.",
        inputs=(
            PortSpec("request", "trigger", default=0, control_plane=True),
            PortSpec("success", "trigger", default=0, control_plane=True),
            PortSpec("failure", "trigger", default=0, control_plane=True),
            PortSpec("max_attempts", "integer", default=3),
            PortSpec("backoff_ms", "integer", default=250),
            PortSpec("reset", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("attempt", "trigger", default=0, control_plane=True),
            PortSpec("attempt_index", "integer", default=0),
            PortSpec("active", "boolean", default=False, control_plane=True),
            PortSpec("exhausted", "trigger", default=0, control_plane=True),
            PortSpec("done", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._active = False
        self._attempt_index = 0
        self._retry_timer = QTimer()
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._on_retry_timeout)

        self._attempt_spin: QSpinBox | None = None
        self._backoff_spin: QSpinBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._attempt_spin = QSpinBox()
        self._attempt_spin.setRange(1, 1_000_000)
        self._attempt_spin.setValue(max(1, int(self.inputs["max_attempts"])))
        self._attempt_spin.valueChanged.connect(
            lambda value: self.receive_binding("max_attempts", int(value))
        )
        set_control_height(self._attempt_spin)
        form.addRow("Max Attempts", self._attempt_spin)

        self._backoff_spin = QSpinBox()
        self._backoff_spin.setRange(0, 3_600_000)
        self._backoff_spin.setValue(max(0, int(self.inputs["backoff_ms"])))
        self._backoff_spin.valueChanged.connect(
            lambda value: self.receive_binding("backoff_ms", int(value))
        )
        set_control_height(self._backoff_spin)
        form.addRow("Backoff (ms)", self._backoff_spin)

        request_btn = QPushButton("Request")
        request_btn.clicked.connect(lambda: self.receive_binding("request", 1))
        set_control_height(request_btn)
        form.addRow("", request_btn)

        success_btn = QPushButton("Success")
        success_btn.clicked.connect(lambda: self.receive_binding("success", 1))
        set_control_height(success_btn)
        form.addRow("", success_btn)

        failure_btn = QPushButton("Failure")
        failure_btn.clicked.connect(lambda: self.receive_binding("failure", 1))
        set_control_height(failure_btn)
        form.addRow("", failure_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(lambda: self.receive_binding("reset", 1))
        set_control_height(reset_btn)
        form.addRow("", reset_btn)

        layout.addLayout(form)
        self._status = QLabel("idle")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(attempt=0, exhausted=0, done=0, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "max_attempts":
            requested = int(value)
            max_attempts = max(1, requested)
            self.inputs["max_attempts"] = max_attempts
            if self._attempt_spin is not None and self._attempt_spin.value() != max_attempts:
                self._attempt_spin.blockSignals(True)
                self._attempt_spin.setValue(max_attempts)
                self._attempt_spin.blockSignals(False)
            if requested < 1:
                self.emit("error", "max_attempts clamped to 1")
            else:
                self.emit("error", "")
            self._publish(attempt=0, exhausted=0, done=0, reason="config")
            return

        if port == "backoff_ms":
            requested = int(value)
            backoff_ms = max(0, requested)
            self.inputs["backoff_ms"] = backoff_ms
            if self._backoff_spin is not None and self._backoff_spin.value() != backoff_ms:
                self._backoff_spin.blockSignals(True)
                self._backoff_spin.setValue(backoff_ms)
                self._backoff_spin.blockSignals(False)
            if requested < 0:
                self.emit("error", "backoff_ms clamped to 0")
            else:
                self.emit("error", "")
            self._publish(attempt=0, exhausted=0, done=0, reason="config")
            return

        if port == "request" and is_truthy(value):
            self._on_request()
            return

        if port == "success" and is_truthy(value):
            self._on_success()
            return

        if port == "failure" and is_truthy(value):
            self._on_failure()
            return

        if port == "reset" and is_truthy(value):
            self._reset(reason="reset")

    def _on_request(self) -> None:
        if self._active:
            self._publish(attempt=0, exhausted=0, done=0, reason="request ignored (active)")
            return
        self._active = True
        self._attempt_index = 1
        self._publish(attempt=1, exhausted=0, done=0, reason="request")

    def _on_success(self) -> None:
        if not self._active:
            self._publish(attempt=0, exhausted=0, done=0, reason="success ignored (idle)")
            return
        self._retry_timer.stop()
        self._active = False
        self._publish(attempt=0, exhausted=0, done=1, reason="success")

    def _on_failure(self) -> None:
        if not self._active:
            self._publish(attempt=0, exhausted=0, done=0, reason="failure ignored (idle)")
            return

        max_attempts = max(1, int(self.inputs["max_attempts"]))
        if self._attempt_index >= max_attempts:
            self._retry_timer.stop()
            self._active = False
            self._publish(attempt=0, exhausted=1, done=1, reason="exhausted")
            return

        backoff_ms = max(0, int(self.inputs["backoff_ms"]))
        if backoff_ms == 0:
            self._attempt_index += 1
            self._publish(attempt=1, exhausted=0, done=0, reason="retry")
            return

        self._retry_timer.start(backoff_ms)
        self._publish(attempt=0, exhausted=0, done=0, reason=f"retry scheduled ({backoff_ms}ms)")

    def _on_retry_timeout(self) -> None:
        if not self._active:
            return
        self._attempt_index += 1
        self._publish(attempt=1, exhausted=0, done=0, reason="retry")

    def _reset(self, *, reason: str) -> None:
        self._retry_timer.stop()
        self._active = False
        self._attempt_index = 0
        self._publish(attempt=0, exhausted=0, done=0, reason=reason)
        self.emit("error", "")

    def _publish(self, *, attempt: int, exhausted: int, done: int, reason: str) -> None:
        self.emit("attempt", 1 if attempt else 0)
        self.emit("attempt_index", self._attempt_index)
        self.emit("active", self._active)
        self.emit("exhausted", 1 if exhausted else 0)
        self.emit("done", 1 if done else 0)
        text = (
            f"active={int(self._active)}, attempt_index={self._attempt_index}, "
            f"max_attempts={int(self.inputs['max_attempts'])}, reason={reason}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    def replay_state(self) -> None:
        self._publish(attempt=0, exhausted=0, done=0, reason="replay")

    def on_close(self) -> None:
        self._retry_timer.stop()
