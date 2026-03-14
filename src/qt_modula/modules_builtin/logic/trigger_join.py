"""Two-input trigger barrier for deterministic fan-in synchronization."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class TriggerJoinModule(BaseModule):
    """Emit one joined pulse after both left/right triggers arrive."""

    persistent_inputs = ("auto_reset",)

    descriptor = ModuleDescriptor(
        module_type="trigger_join",
        display_name="Trigger Join",
        family="Logic",
        description="2-input trigger barrier that emits once when both sides are seen.",
        inputs=(
            PortSpec("left", "trigger", default=0, control_plane=True),
            PortSpec("right", "trigger", default=0, control_plane=True),
            PortSpec("auto_reset", "boolean", default=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("joined", "trigger", default=0, control_plane=True),
            PortSpec("left_seen", "boolean", default=False),
            PortSpec("right_seen", "boolean", default=False),
            PortSpec("count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._left_seen = False
        self._right_seen = False
        self._joined_since_reset = False
        self._count = 0

        self._auto_reset_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._auto_reset_check = QCheckBox("Auto Reset After Join")
        self._auto_reset_check.setChecked(bool(self.inputs["auto_reset"]))
        self._auto_reset_check.toggled.connect(
            lambda enabled: self.receive_binding("auto_reset", enabled)
        )
        form.addRow("", self._auto_reset_check)

        pulse_left = QPushButton("Pulse Left")
        pulse_left.clicked.connect(lambda: self.receive_binding("left", 1))
        set_control_height(pulse_left)
        form.addRow("", pulse_left)

        pulse_right = QPushButton("Pulse Right")
        pulse_right.clicked.connect(lambda: self.receive_binding("right", 1))
        set_control_height(pulse_right)
        form.addRow("", pulse_right)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.receive_binding("clear", 1))
        set_control_height(clear_btn)
        form.addRow("", clear_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._publish(joined=0, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "auto_reset":
            enabled = bool(value)
            self.inputs["auto_reset"] = enabled
            if self._auto_reset_check is not None and self._auto_reset_check.isChecked() != enabled:
                self._auto_reset_check.blockSignals(True)
                self._auto_reset_check.setChecked(enabled)
                self._auto_reset_check.blockSignals(False)
            self._publish(joined=0, reason="auto_reset updated")
            return

        if port == "clear" and is_truthy(value):
            self._clear()
            return

        if port == "left" and is_truthy(value):
            self._left_seen = True
            self._on_seen(source="left")
            return

        if port == "right" and is_truthy(value):
            self._right_seen = True
            self._on_seen(source="right")

    def _on_seen(self, *, source: str) -> None:
        joined = 0
        reason = f"seen:{source}"
        if self._left_seen and self._right_seen and not self._joined_since_reset:
            joined = 1
            self._count += 1
            self._joined_since_reset = True
            reason = "joined"
            if bool(self.inputs["auto_reset"]):
                self._left_seen = False
                self._right_seen = False
                self._joined_since_reset = False
                reason = "joined+reset"
        self._publish(joined=joined, reason=reason)

    def _clear(self) -> None:
        self._left_seen = False
        self._right_seen = False
        self._joined_since_reset = False
        self._count = 0
        self._publish(joined=0, reason="cleared")

    def _publish(self, *, joined: int, reason: str) -> None:
        self.emit("joined", 1 if joined else 0)
        self.emit("left_seen", self._left_seen)
        self.emit("right_seen", self._right_seen)
        self.emit("count", self._count)
        text = (
            f"left_seen={int(self._left_seen)}, right_seen={int(self._right_seen)}, "
            f"count={self._count}, reason={reason}"
        )
        self.emit("text", text)
        self.emit("error", "")
        if self._status is not None:
            self._status.setText(text)
