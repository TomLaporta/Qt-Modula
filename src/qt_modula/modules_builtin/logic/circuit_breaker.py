"""Circuit breaker for resilient provider/request pipelines."""

from __future__ import annotations

from typing import Any, Literal

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height

BreakerState = Literal["closed", "open", "half_open"]


class CircuitBreakerModule(BaseModule):
    """Gate request triggers based on failure-rate state transitions."""

    persistent_inputs = ("failure_threshold", "cooldown_ms", "half_open_budget")

    descriptor = ModuleDescriptor(
        module_type="circuit_breaker",
        display_name="Circuit Breaker",
        family="Logic",
        description="Protects request lanes by opening after repeated failures.",
        inputs=(
            PortSpec("request", "trigger", default=0, control_plane=True),
            PortSpec("success", "trigger", default=0, control_plane=True),
            PortSpec("failure", "trigger", default=0, control_plane=True),
            PortSpec("failure_threshold", "integer", default=3),
            PortSpec("cooldown_ms", "integer", default=1000),
            PortSpec("half_open_budget", "integer", default=1),
            PortSpec("reset", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("allow", "trigger", default=0, control_plane=True),
            PortSpec("blocked", "trigger", default=0, control_plane=True),
            PortSpec("state", "string", default="closed"),
            PortSpec("failure_count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._state: BreakerState = "closed"
        self._failure_count = 0
        self._half_open_remaining = max(1, int(self.inputs["half_open_budget"]))

        self._cooldown_timer = QTimer()
        self._cooldown_timer.setSingleShot(True)
        self._cooldown_timer.timeout.connect(self._on_cooldown_elapsed)

        self._threshold_spin: QSpinBox | None = None
        self._cooldown_spin: QSpinBox | None = None
        self._budget_spin: QSpinBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._threshold_spin = QSpinBox()
        self._threshold_spin.setRange(1, 1_000_000)
        self._threshold_spin.setValue(max(1, int(self.inputs["failure_threshold"])))
        self._threshold_spin.valueChanged.connect(
            lambda value: self.receive_binding("failure_threshold", int(value))
        )
        set_control_height(self._threshold_spin)
        form.addRow("Failure Threshold", self._threshold_spin)

        self._cooldown_spin = QSpinBox()
        self._cooldown_spin.setRange(0, 3_600_000)
        self._cooldown_spin.setValue(max(0, int(self.inputs["cooldown_ms"])))
        self._cooldown_spin.valueChanged.connect(
            lambda value: self.receive_binding("cooldown_ms", int(value))
        )
        set_control_height(self._cooldown_spin)
        form.addRow("Cooldown (ms)", self._cooldown_spin)

        self._budget_spin = QSpinBox()
        self._budget_spin.setRange(1, 1_000_000)
        self._budget_spin.setValue(max(1, int(self.inputs["half_open_budget"])))
        self._budget_spin.valueChanged.connect(
            lambda value: self.receive_binding("half_open_budget", int(value))
        )
        set_control_height(self._budget_spin)
        form.addRow("Half-Open Budget", self._budget_spin)

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
        self._status = QLabel("closed")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(allow=0, blocked=0, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "failure_threshold":
            requested = int(value)
            threshold = max(1, requested)
            self.inputs["failure_threshold"] = threshold
            if self._threshold_spin is not None and self._threshold_spin.value() != threshold:
                self._threshold_spin.blockSignals(True)
                self._threshold_spin.setValue(threshold)
                self._threshold_spin.blockSignals(False)
            if requested < 1:
                self.emit("error", "failure_threshold clamped to 1")
            else:
                self.emit("error", "")
            self._publish(allow=0, blocked=0, reason="config")
            return

        if port == "cooldown_ms":
            requested = int(value)
            cooldown_ms = max(0, requested)
            self.inputs["cooldown_ms"] = cooldown_ms
            if self._cooldown_spin is not None and self._cooldown_spin.value() != cooldown_ms:
                self._cooldown_spin.blockSignals(True)
                self._cooldown_spin.setValue(cooldown_ms)
                self._cooldown_spin.blockSignals(False)
            if requested < 0:
                self.emit("error", "cooldown_ms clamped to 0")
            else:
                self.emit("error", "")
            self._publish(allow=0, blocked=0, reason="config")
            return

        if port == "half_open_budget":
            requested = int(value)
            budget = max(1, requested)
            self.inputs["half_open_budget"] = budget
            if self._budget_spin is not None and self._budget_spin.value() != budget:
                self._budget_spin.blockSignals(True)
                self._budget_spin.setValue(budget)
                self._budget_spin.blockSignals(False)
            if requested < 1:
                self.emit("error", "half_open_budget clamped to 1")
            else:
                self.emit("error", "")
            if self._state == "half_open":
                self._half_open_remaining = budget
            self._publish(allow=0, blocked=0, reason="config")
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
            self._close(reason="reset")

    def _on_request(self) -> None:
        if self._state == "closed":
            self._publish(allow=1, blocked=0, reason="allow(closed)")
            return

        if self._state == "open":
            self._publish(allow=0, blocked=1, reason="blocked(open)")
            return

        if self._half_open_remaining > 0:
            self._half_open_remaining -= 1
            self._publish(
                allow=1,
                blocked=0,
                reason=f"allow(half_open, remaining={self._half_open_remaining})",
            )
            return

        self._publish(allow=0, blocked=1, reason="blocked(half_open budget exhausted)")

    def _on_success(self) -> None:
        if self._state == "half_open":
            self._close(reason="half_open success")
            return

        if self._state == "closed":
            self._failure_count = 0
            self._publish(allow=0, blocked=0, reason="success(closed)")
            return

        self._publish(allow=0, blocked=0, reason="success ignored(open)")

    def _on_failure(self) -> None:
        if self._state == "half_open":
            self._open(reason="half_open failure")
            return

        if self._state == "open":
            self._publish(allow=0, blocked=0, reason="failure(open)")
            return

        self._failure_count += 1
        threshold = max(1, int(self.inputs["failure_threshold"]))
        if self._failure_count >= threshold:
            self._open(reason="threshold reached")
            return
        self._publish(allow=0, blocked=0, reason="failure(closed)")

    def _open(self, *, reason: str) -> None:
        self._state = "open"
        self._half_open_remaining = 0
        cooldown_ms = max(0, int(self.inputs["cooldown_ms"]))
        if cooldown_ms > 0:
            self._cooldown_timer.start(cooldown_ms)
        else:
            self._on_cooldown_elapsed()
            return
        self._publish(allow=0, blocked=0, reason=reason)

    def _on_cooldown_elapsed(self) -> None:
        if self._state != "open":
            return
        self._state = "half_open"
        self._half_open_remaining = max(1, int(self.inputs["half_open_budget"]))
        self._publish(allow=0, blocked=0, reason="cooldown elapsed")

    def _close(self, *, reason: str) -> None:
        self._cooldown_timer.stop()
        self._state = "closed"
        self._failure_count = 0
        self._half_open_remaining = max(1, int(self.inputs["half_open_budget"]))
        self._publish(allow=0, blocked=0, reason=reason)
        self.emit("error", "")

    def _publish(self, *, allow: int, blocked: int, reason: str) -> None:
        self.emit("allow", 1 if allow else 0)
        self.emit("blocked", 1 if blocked else 0)
        self.emit("state", self._state)
        self.emit("failure_count", self._failure_count)
        text = (
            f"state={self._state}, failures={self._failure_count}, "
            f"half_open_remaining={self._half_open_remaining}, reason={reason}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    def replay_state(self) -> None:
        self._publish(allow=0, blocked=0, reason="replay")

    def on_close(self) -> None:
        self._cooldown_timer.stop()
