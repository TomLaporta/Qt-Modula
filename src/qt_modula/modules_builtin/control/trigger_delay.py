"""Deterministic trigger delay utility for control-lane scheduling."""

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


class TriggerDelayModule(BaseModule):
    """Emit trigger pulses after a configurable delay."""

    persistent_inputs = ("delay_ms", "restart_on_trigger")

    descriptor = ModuleDescriptor(
        module_type="trigger_delay",
        display_name="Trigger Delay",
        family="Control",
        description="Schedules delayed trigger pulses with cancel/reset controls.",
        inputs=(
            PortSpec("trigger", "trigger", default=0, control_plane=True),
            PortSpec("delay_ms", "integer", default=250),
            PortSpec("restart_on_trigger", "boolean", default=True),
            PortSpec("cancel", "trigger", default=0, control_plane=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("pulse", "trigger", default=0, control_plane=True),
            PortSpec("pending", "boolean", default=False),
            PortSpec("delayed_count", "integer", default=0),
            PortSpec("canceled_count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

        self._pending = False
        self._delayed_count = 0
        self._canceled_count = 0
        self._delay_warning = ""

        self._delay_spin: QSpinBox | None = None
        self._restart_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 3_600_000)
        self._delay_spin.setValue(max(0, int(self.inputs["delay_ms"])))
        self._delay_spin.valueChanged.connect(
            lambda value: self.receive_binding("delay_ms", int(value))
        )
        set_control_height(self._delay_spin)
        form.addRow("Delay (ms)", self._delay_spin)

        self._restart_check = QCheckBox("Restart On Trigger")
        self._restart_check.setChecked(bool(self.inputs["restart_on_trigger"]))
        self._restart_check.toggled.connect(
            lambda enabled: self.receive_binding("restart_on_trigger", enabled)
        )
        form.addRow("", self._restart_check)

        trigger_btn = QPushButton("Trigger")
        trigger_btn.clicked.connect(lambda: self.receive_binding("trigger", 1))
        set_control_height(trigger_btn)
        form.addRow("", trigger_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(lambda: self.receive_binding("cancel", 1))
        set_control_height(cancel_btn)
        form.addRow("", cancel_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.receive_binding("clear", 1))
        set_control_height(clear_btn)
        form.addRow("", clear_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._publish(pulse=0, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "delay_ms":
            requested = int(value)
            delay_ms = max(0, requested)
            self.inputs["delay_ms"] = delay_ms
            self._delay_warning = "delay_ms clamped to 0" if requested < 0 else ""
            if self._delay_spin is not None and self._delay_spin.value() != delay_ms:
                self._delay_spin.blockSignals(True)
                self._delay_spin.setValue(delay_ms)
                self._delay_spin.blockSignals(False)
            self._publish(pulse=0, reason="delay updated")
            return

        if port == "restart_on_trigger":
            enabled = bool(value)
            self.inputs["restart_on_trigger"] = enabled
            if self._restart_check is not None and self._restart_check.isChecked() != enabled:
                self._restart_check.blockSignals(True)
                self._restart_check.setChecked(enabled)
                self._restart_check.blockSignals(False)
            self._publish(pulse=0, reason="restart updated")
            return

        if port == "trigger" and is_truthy(value):
            self._on_trigger()
            return

        if port == "cancel" and is_truthy(value):
            self._on_cancel(reason="cancel")
            return

        if port == "clear" and is_truthy(value):
            self._clear()

    def replay_state(self) -> None:
        self._publish(pulse=0, reason="replay")

    def _on_trigger(self) -> None:
        delay_ms = max(0, int(self.inputs["delay_ms"]))
        restart = bool(self.inputs["restart_on_trigger"])

        if delay_ms == 0:
            if self._timer.isActive():
                self._timer.stop()
            self._pending = False
            self._delayed_count += 1
            self._publish(pulse=1, reason="immediate")
            return

        if self._timer.isActive():
            if not restart:
                self._publish(pulse=0, reason="ignored (active)")
                return
            self._timer.start(delay_ms)
            self._pending = True
            self._publish(pulse=0, reason="restarted")
            return

        self._timer.start(delay_ms)
        self._pending = True
        self._publish(pulse=0, reason="scheduled")

    def _on_timeout(self) -> None:
        self._pending = False
        self._delayed_count += 1
        self._publish(pulse=1, reason="timeout")

    def _on_cancel(self, *, reason: str) -> None:
        if self._timer.isActive() or self._pending:
            self._timer.stop()
            self._pending = False
            self._canceled_count += 1
            self._publish(pulse=0, reason=reason)
            return
        self._publish(pulse=0, reason=f"{reason} noop")

    def _clear(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self._pending = False
        self._delayed_count = 0
        self._canceled_count = 0
        self._publish(pulse=0, reason="cleared")

    def _publish(self, *, pulse: int, reason: str) -> None:
        self.emit("pulse", 1 if pulse else 0)
        self.emit("pending", self._pending)
        self.emit("delayed_count", self._delayed_count)
        self.emit("canceled_count", self._canceled_count)
        self.emit("error", self._delay_warning)
        text = (
            f"pending={int(self._pending)}, delay_ms={int(self.inputs['delay_ms'])}, "
            f"delayed={self._delayed_count}, canceled={self._canceled_count}, reason={reason}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    def on_close(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
