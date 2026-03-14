"""N-way trigger barrier for deterministic control-lane fan-in."""

from __future__ import annotations

from typing import Any

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

_MAX_JOIN_INPUTS = 8


class TriggerJoinNModule(BaseModule):
    """Join up to 8 trigger lanes into one barrier pulse."""

    persistent_inputs = ("input_count", "auto_reset")

    descriptor = ModuleDescriptor(
        module_type="trigger_join_n",
        display_name="Trigger Join N",
        family="Logic",
        description="N-input trigger barrier with deterministic join/reset behavior.",
        inputs=(
            PortSpec("in_0", "trigger", default=0, control_plane=True),
            PortSpec("in_1", "trigger", default=0, control_plane=True),
            PortSpec("in_2", "trigger", default=0, control_plane=True),
            PortSpec("in_3", "trigger", default=0, control_plane=True),
            PortSpec("in_4", "trigger", default=0, control_plane=True),
            PortSpec("in_5", "trigger", default=0, control_plane=True),
            PortSpec("in_6", "trigger", default=0, control_plane=True),
            PortSpec("in_7", "trigger", default=0, control_plane=True),
            PortSpec("input_count", "integer", default=3),
            PortSpec("auto_reset", "boolean", default=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("joined", "trigger", default=0, control_plane=True),
            PortSpec("seen_count", "integer", default=0),
            PortSpec("seen_mask", "json", default=[]),
            PortSpec("count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._seen = [False] * _MAX_JOIN_INPUTS
        self._joined_since_reset = False
        self._count = 0
        self._count_warning = ""

        self._count_spin: QSpinBox | None = None
        self._auto_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._count_spin = QSpinBox()
        self._count_spin.setRange(2, _MAX_JOIN_INPUTS)
        self._count_spin.setValue(self._clamp_count(int(self.inputs["input_count"])))
        self._count_spin.valueChanged.connect(
            lambda value: self.receive_binding("input_count", int(value))
        )
        set_control_height(self._count_spin)
        form.addRow("Input Count", self._count_spin)

        self._auto_check = QCheckBox("Auto Reset")
        self._auto_check.setChecked(bool(self.inputs["auto_reset"]))
        self._auto_check.toggled.connect(
            lambda enabled: self.receive_binding("auto_reset", enabled)
        )
        form.addRow("", self._auto_check)

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
        if port == "input_count":
            requested = int(value)
            count = self._clamp_count(requested)
            self.inputs["input_count"] = count
            self._count_warning = (
                f"input_count clamped to {count}" if requested != count else ""
            )
            if self._count_spin is not None and self._count_spin.value() != count:
                self._count_spin.blockSignals(True)
                self._count_spin.setValue(count)
                self._count_spin.blockSignals(False)
            self._publish(joined=0, reason="input_count updated")
            return

        if port == "auto_reset":
            enabled = bool(value)
            self.inputs["auto_reset"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            self._publish(joined=0, reason="auto_reset updated")
            return

        if port == "clear" and is_truthy(value):
            self._clear()
            return

        if port.startswith("in_") and is_truthy(value):
            try:
                index = int(port[3:])
            except ValueError:
                return
            if 0 <= index < _MAX_JOIN_INPUTS:
                self._seen[index] = True
                self._on_seen(source=index)

    def replay_state(self) -> None:
        self._publish(joined=0, reason="replay")

    def _on_seen(self, *, source: int) -> None:
        active_count = self._clamp_count(int(self.inputs["input_count"]))
        joined = 0
        reason = f"seen:{source}"
        if all(self._seen[:active_count]) and not self._joined_since_reset:
            self._count += 1
            joined = 1
            if bool(self.inputs["auto_reset"]):
                for index in range(active_count):
                    self._seen[index] = False
                self._joined_since_reset = False
                reason = "joined+reset"
            else:
                self._joined_since_reset = True
                reason = "joined"
        self._publish(joined=joined, reason=reason)

    def _clear(self) -> None:
        self._seen = [False] * _MAX_JOIN_INPUTS
        self._joined_since_reset = False
        self._count = 0
        self._publish(joined=0, reason="cleared")

    def _publish(self, *, joined: int, reason: str) -> None:
        active_count = self._clamp_count(int(self.inputs["input_count"]))
        seen_mask = self._seen[:active_count]
        seen_count = sum(1 for item in seen_mask if item)
        self.emit("joined", 1 if joined else 0)
        self.emit("seen_count", seen_count)
        self.emit("seen_mask", list(seen_mask))
        self.emit("count", self._count)
        self.emit("error", self._count_warning)
        text = (
            f"inputs={active_count}, seen={seen_count}, count={self._count}, "
            f"auto_reset={int(bool(self.inputs['auto_reset']))}, reason={reason}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    @staticmethod
    def _clamp_count(value: int) -> int:
        if value < 2:
            return 2
        if value > _MAX_JOIN_INPUTS:
            return _MAX_JOIN_INPUTS
        return value
