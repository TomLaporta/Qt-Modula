"""Rate limiting utility for trigger control lanes."""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class TriggerRateLimitModule(BaseModule):
    """Allow at most N trigger pulses per time window."""

    persistent_inputs = ("max_events", "window_ms")

    descriptor = ModuleDescriptor(
        module_type="trigger_rate_limit",
        display_name="Trigger Rate Limit",
        family="Control",
        description="Limits trigger throughput using a deterministic fixed window.",
        inputs=(
            PortSpec("trigger", "trigger", default=0, control_plane=True),
            PortSpec("max_events", "integer", default=1),
            PortSpec("window_ms", "integer", default=1000),
            PortSpec("reset", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("pulse", "trigger", default=0, control_plane=True),
            PortSpec("blocked", "trigger", default=0, control_plane=True),
            PortSpec("window_count", "integer", default=0),
            PortSpec("allowed_count", "integer", default=0),
            PortSpec("blocked_count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._window_start_ns: int | None = None
        self._window_count = 0
        self._allowed_count = 0
        self._blocked_count = 0
        self._max_warning = ""
        self._window_warning = ""

        self._max_spin: QSpinBox | None = None
        self._window_spin: QSpinBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._max_spin = QSpinBox()
        self._max_spin.setRange(1, 1_000_000)
        self._max_spin.setValue(max(1, int(self.inputs["max_events"])))
        self._max_spin.valueChanged.connect(
            lambda value: self.receive_binding("max_events", int(value))
        )
        set_control_height(self._max_spin)
        form.addRow("Max Events", self._max_spin)

        self._window_spin = QSpinBox()
        self._window_spin.setRange(1, 3_600_000)
        self._window_spin.setValue(max(1, int(self.inputs["window_ms"])))
        self._window_spin.valueChanged.connect(
            lambda value: self.receive_binding("window_ms", int(value))
        )
        set_control_height(self._window_spin)
        form.addRow("Window (ms)", self._window_spin)

        trigger_btn = QPushButton("Trigger")
        trigger_btn.clicked.connect(lambda: self.receive_binding("trigger", 1))
        set_control_height(trigger_btn)
        form.addRow("", trigger_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(lambda: self.receive_binding("reset", 1))
        set_control_height(reset_btn)
        form.addRow("", reset_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._publish(pulse=0, blocked=0, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "max_events":
            requested = int(value)
            max_events = max(1, requested)
            self.inputs["max_events"] = max_events
            self._max_warning = "max_events clamped to 1" if requested < 1 else ""
            if self._max_spin is not None and self._max_spin.value() != max_events:
                self._max_spin.blockSignals(True)
                self._max_spin.setValue(max_events)
                self._max_spin.blockSignals(False)
            self._publish(pulse=0, blocked=0, reason="max_events updated")
            return

        if port == "window_ms":
            requested = int(value)
            window_ms = max(1, requested)
            self.inputs["window_ms"] = window_ms
            self._window_warning = "window_ms clamped to 1" if requested < 1 else ""
            if self._window_spin is not None and self._window_spin.value() != window_ms:
                self._window_spin.blockSignals(True)
                self._window_spin.setValue(window_ms)
                self._window_spin.blockSignals(False)
            self._publish(pulse=0, blocked=0, reason="window_ms updated")
            return

        if port == "trigger" and is_truthy(value):
            self._on_trigger()
            return

        if port == "reset" and is_truthy(value):
            self._reset()

    def replay_state(self) -> None:
        self._publish(pulse=0, blocked=0, reason="replay")

    def _on_trigger(self) -> None:
        now_ns = time.monotonic_ns()
        max_events = max(1, int(self.inputs["max_events"]))
        window_ns = max(1, int(self.inputs["window_ms"])) * 1_000_000

        if self._window_start_ns is None or (now_ns - self._window_start_ns) >= window_ns:
            self._window_start_ns = now_ns
            self._window_count = 0

        if self._window_count < max_events:
            self._window_count += 1
            self._allowed_count += 1
            self._publish(pulse=1, blocked=0, reason="allowed")
            return

        self._blocked_count += 1
        self._publish(pulse=0, blocked=1, reason="blocked")

    def _reset(self) -> None:
        self._window_start_ns = None
        self._window_count = 0
        self._allowed_count = 0
        self._blocked_count = 0
        self._publish(pulse=0, blocked=0, reason="reset")

    def _publish(self, *, pulse: int, blocked: int, reason: str) -> None:
        warnings = [item for item in (self._max_warning, self._window_warning) if item]
        self.emit("pulse", 1 if pulse else 0)
        self.emit("blocked", 1 if blocked else 0)
        self.emit("window_count", self._window_count)
        self.emit("allowed_count", self._allowed_count)
        self.emit("blocked_count", self._blocked_count)
        self.emit("error", "; ".join(warnings))
        text = (
            f"window_count={self._window_count}, max_events={int(self.inputs['max_events'])}, "
            f"allowed={self._allowed_count}, blocked={self._blocked_count}, reason={reason}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)
