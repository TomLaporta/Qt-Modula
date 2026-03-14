"""Debounce bursty trigger lanes into deterministic pulse emissions."""

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


class TriggerDebounceModule(BaseModule):
    """Suppress repeated trigger pulses during a debounce window."""

    persistent_inputs = ("window_ms", "leading", "trailing")

    descriptor = ModuleDescriptor(
        module_type="trigger_debounce",
        display_name="Trigger Debounce",
        family="Control",
        description="Suppresses burst pulses using a deterministic debounce window.",
        inputs=(
            PortSpec("trigger", "trigger", default=0, control_plane=True),
            PortSpec("window_ms", "integer", default=250),
            PortSpec("leading", "boolean", default=False),
            PortSpec("trailing", "boolean", default=True),
            PortSpec("flush", "trigger", default=0, control_plane=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("pulse", "trigger", default=0, control_plane=True),
            PortSpec("dropped_count", "integer", default=0),
            PortSpec("pending", "boolean", default=False),
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
        self._dropped_count = 0

        self._window_warning = ""
        self._mode_warning = ""

        self._window_spin: QSpinBox | None = None
        self._leading_check: QCheckBox | None = None
        self._trailing_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._window_spin = QSpinBox()
        self._window_spin.setRange(1, 3_600_000)
        self._window_spin.setValue(max(1, int(self.inputs["window_ms"])))
        self._window_spin.valueChanged.connect(
            lambda value: self.receive_binding("window_ms", int(value))
        )
        set_control_height(self._window_spin)
        form.addRow("Window (ms)", self._window_spin)

        self._leading_check = QCheckBox("Emit Leading")
        self._leading_check.setChecked(bool(self.inputs["leading"]))
        self._leading_check.toggled.connect(
            lambda enabled: self.receive_binding("leading", enabled)
        )
        form.addRow("", self._leading_check)

        self._trailing_check = QCheckBox("Emit Trailing")
        self._trailing_check.setChecked(bool(self.inputs["trailing"]))
        self._trailing_check.toggled.connect(
            lambda enabled: self.receive_binding("trailing", enabled)
        )
        form.addRow("", self._trailing_check)

        trigger_btn = QPushButton("Trigger")
        trigger_btn.clicked.connect(lambda: self.receive_binding("trigger", 1))
        set_control_height(trigger_btn)
        form.addRow("", trigger_btn)

        flush_btn = QPushButton("Flush")
        flush_btn.clicked.connect(lambda: self.receive_binding("flush", 1))
        set_control_height(flush_btn)
        form.addRow("", flush_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.receive_binding("clear", 1))
        set_control_height(clear_btn)
        form.addRow("", clear_btn)

        layout.addLayout(form)

        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._normalize_modes()
        self._publish(pulse=0, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "window_ms":
            requested = int(value)
            window_ms = max(1, requested)
            self.inputs["window_ms"] = window_ms
            if self._window_spin is not None and self._window_spin.value() != window_ms:
                self._window_spin.blockSignals(True)
                self._window_spin.setValue(window_ms)
                self._window_spin.blockSignals(False)
            self._window_warning = "window_ms clamped to 1" if requested < 1 else ""
            self._publish(pulse=0, reason="window updated")
            return

        if port in {"leading", "trailing"}:
            enabled = bool(value)
            self.inputs[port] = enabled
            check = self._leading_check if port == "leading" else self._trailing_check
            if check is not None and check.isChecked() != enabled:
                check.blockSignals(True)
                check.setChecked(enabled)
                check.blockSignals(False)
            self._normalize_modes()
            self._publish(pulse=0, reason=f"{port} updated")
            return

        if port == "trigger" and is_truthy(value):
            self._on_trigger()
            return

        if port == "flush" and is_truthy(value):
            self._on_flush()
            return

        if port == "clear" and is_truthy(value):
            self._clear()

    def replay_state(self) -> None:
        self._publish(pulse=0, reason="replay")

    def _normalize_modes(self) -> None:
        leading = bool(self.inputs["leading"])
        trailing = bool(self.inputs["trailing"])
        if leading or trailing:
            self._mode_warning = ""
            return
        self.inputs["trailing"] = True
        if self._trailing_check is not None and not self._trailing_check.isChecked():
            self._trailing_check.blockSignals(True)
            self._trailing_check.setChecked(True)
            self._trailing_check.blockSignals(False)
        self._mode_warning = "leading and trailing cannot both be false; using trailing=true"

    def _on_trigger(self) -> None:
        leading = bool(self.inputs["leading"])
        trailing = bool(self.inputs["trailing"])

        if not self._timer.isActive():
            self._timer.start(max(1, int(self.inputs["window_ms"])))
            if leading:
                self._emit_pulse(reason="leading")
                return
            self._pending = trailing
            self._publish(pulse=0, reason="window started")
            return

        self._dropped_count += 1
        if trailing:
            self._pending = True
        self._publish(pulse=0, reason="suppressed")

    def _on_timeout(self) -> None:
        if self._pending and bool(self.inputs["trailing"]):
            self._pending = False
            self._emit_pulse(reason="trailing")
            return
        self._pending = False
        self._publish(pulse=0, reason="window elapsed")

    def _on_flush(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        if self._pending:
            self._pending = False
            self._emit_pulse(reason="flushed")
            return
        self._publish(pulse=0, reason="flush noop")

    def _clear(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self._pending = False
        self._dropped_count = 0
        self._publish(pulse=0, reason="cleared")

    def _emit_pulse(self, *, reason: str) -> None:
        self._publish(pulse=1, reason=reason)

    def _publish(self, *, pulse: int, reason: str) -> None:
        error = self._combined_warning()
        self.emit("pulse", 1 if pulse else 0)
        self.emit("dropped_count", self._dropped_count)
        self.emit("pending", self._pending)
        self.emit("error", error)
        text = (
            f"window_active={int(self._timer.isActive())}, pending={int(self._pending)}, "
            f"dropped={self._dropped_count}, reason={reason}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    def _combined_warning(self) -> str:
        warnings = [item for item in (self._window_warning, self._mode_warning) if item]
        return "; ".join(warnings)

    def on_close(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
