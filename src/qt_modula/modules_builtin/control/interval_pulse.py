"""Interval-driven pulse source for automated workflow cadence."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class IntervalPulseModule(BaseModule):
    """Emit pulses on a deterministic timer with explicit start/stop control."""

    persistent_inputs = ("enabled", "interval_ms", "fire_immediately")

    descriptor = ModuleDescriptor(
        module_type="interval_pulse",
        display_name="Interval Pulse",
        family="Control",
        description="Deterministic timer-based pulse source with explicit controls.",
        inputs=(
            PortSpec("enabled", "boolean", default=False),
            PortSpec("interval_ms", "integer", default=1000),
            PortSpec("fire_immediately", "boolean", default=False),
            PortSpec("start", "trigger", default=0, control_plane=True),
            PortSpec("stop", "trigger", default=0, control_plane=True),
            PortSpec("pulse", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("pulse", "trigger", default=0, control_plane=True),
            PortSpec("running", "boolean", default=False, control_plane=True),
            PortSpec("tick_count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._timer = QTimer()
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(lambda: self._emit_pulse("interval"))
        self._tick_count = 0

        self._enabled_check: QCheckBox | None = None
        self._interval_spin: QSpinBox | None = None
        self._fire_immediately_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._enabled_check = QCheckBox("Enabled")
        self._enabled_check.setChecked(bool(self.inputs["enabled"]))
        self._enabled_check.toggled.connect(
            lambda enabled: self.receive_binding("enabled", enabled)
        )
        form.addRow("", self._enabled_check)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 86_400_000)
        self._interval_spin.setValue(int(self.inputs["interval_ms"]))
        self._interval_spin.valueChanged.connect(
            lambda value: self.receive_binding("interval_ms", int(value))
        )
        set_control_height(self._interval_spin)
        form.addRow("Interval (ms)", self._interval_spin)

        self._fire_immediately_check = QCheckBox("Fire Immediately On Start")
        self._fire_immediately_check.setChecked(bool(self.inputs["fire_immediately"]))
        self._fire_immediately_check.toggled.connect(
            lambda enabled: self.receive_binding("fire_immediately", enabled)
        )
        form.addRow("", self._fire_immediately_check)

        start_btn = QPushButton("Start")
        start_btn.clicked.connect(lambda: self.receive_binding("start", 1))
        set_control_height(start_btn)
        form.addRow("", start_btn)

        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(lambda: self.receive_binding("stop", 1))
        set_control_height(stop_btn)
        form.addRow("", stop_btn)

        pulse_btn = QPushButton("Pulse Once")
        pulse_btn.clicked.connect(lambda: self.receive_binding("pulse", 1))
        set_control_height(pulse_btn)
        form.addRow("", pulse_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish_state(reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "enabled":
            enabled = bool(value)
            self.inputs["enabled"] = enabled
            if self._enabled_check is not None and self._enabled_check.isChecked() != enabled:
                self._enabled_check.blockSignals(True)
                self._enabled_check.setChecked(enabled)
                self._enabled_check.blockSignals(False)
            if self._context is None:
                return
            if enabled:
                self._start_timer()
            else:
                self._stop_timer(reason="disabled")
            return

        if port == "interval_ms":
            requested = int(value)
            interval_ms = max(1, requested)
            self.inputs["interval_ms"] = interval_ms
            if self._interval_spin is not None and self._interval_spin.value() != interval_ms:
                self._interval_spin.blockSignals(True)
                self._interval_spin.setValue(interval_ms)
                self._interval_spin.blockSignals(False)
            if requested < 1:
                self.emit("error", "interval_ms clamped to 1")
            else:
                self.emit("error", "")
            self._timer.setInterval(interval_ms)
            self._publish_state(reason="interval updated")
            return

        if port == "fire_immediately":
            enabled = bool(value)
            self.inputs["fire_immediately"] = enabled
            if (
                self._fire_immediately_check is not None
                and self._fire_immediately_check.isChecked() != enabled
            ):
                self._fire_immediately_check.blockSignals(True)
                self._fire_immediately_check.setChecked(enabled)
                self._fire_immediately_check.blockSignals(False)
            self._publish_state(reason="fire_immediately updated")
            return

        if port == "start" and is_truthy(value):
            self.inputs["enabled"] = True
            if self._enabled_check is not None and not self._enabled_check.isChecked():
                self._enabled_check.blockSignals(True)
                self._enabled_check.setChecked(True)
                self._enabled_check.blockSignals(False)
            self._start_timer()
            return

        if port == "stop" and is_truthy(value):
            self.inputs["enabled"] = False
            if self._enabled_check is not None and self._enabled_check.isChecked():
                self._enabled_check.blockSignals(True)
                self._enabled_check.setChecked(False)
                self._enabled_check.blockSignals(False)
            self._stop_timer(reason="stopped")
            return

        if port == "pulse" and is_truthy(value):
            self._emit_pulse("manual")

    def _start_timer(self) -> None:
        interval_ms = max(1, int(self.inputs["interval_ms"]))
        self._timer.setInterval(interval_ms)
        if bool(self.inputs["fire_immediately"]):
            self._emit_pulse("immediate")
        if not self._timer.isActive():
            self._timer.start()
        self.emit("running", True)
        self.emit("error", "")
        self._publish_state(reason="running")

    def _stop_timer(self, *, reason: str) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self.emit("running", False)
        self._publish_state(reason=reason)

    def _emit_pulse(self, reason: str) -> None:
        self._tick_count += 1
        self.emit("tick_count", self._tick_count)
        self.emit("pulse", 1)
        self.emit("error", "")
        self._publish_state(reason=reason)

    def _publish_state(self, *, reason: str) -> None:
        running = bool(self._timer.isActive())
        self.emit("running", running)
        text = (
            f"running={int(running)}, interval_ms={int(self.inputs['interval_ms'])}, "
            f"ticks={self._tick_count}, reason={reason}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    def replay_state(self) -> None:
        if bool(self.inputs["enabled"]):
            if self._timer.isActive():
                self._publish_state(reason="replay")
            else:
                self._start_timer()
            return
        self._stop_timer(reason="replay")

    def on_close(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
