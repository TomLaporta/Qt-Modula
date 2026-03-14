"""Control-plane trigger mapper for deterministic action channels."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height

_CHANNELS = ("evaluate", "refresh", "fetch", "run", "flush", "emit")


class TriggerMapperModule(BaseModule):
    """Map generic trigger pulses into explicit action channels."""

    persistent_inputs = ("channel",)

    descriptor = ModuleDescriptor(
        module_type="trigger_mapper",
        display_name="Trigger Mapper",
        family="Control",
        description="Routes a generic trigger input to a selected action channel.",
        inputs=(
            PortSpec("trigger", "trigger", default=0, control_plane=True),
            PortSpec("channel", "string", default="evaluate"),
        ),
        outputs=(
            PortSpec("pulse", "trigger", default=0, control_plane=True),
            PortSpec("evaluate", "trigger", default=0, control_plane=True),
            PortSpec("refresh", "trigger", default=0, control_plane=True),
            PortSpec("fetch", "trigger", default=0, control_plane=True),
            PortSpec("run", "trigger", default=0, control_plane=True),
            PortSpec("flush", "trigger", default=0, control_plane=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._combo: QComboBox | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)
        layout.addWidget(QLabel("Channel"))
        self._combo = QComboBox()
        self._combo.addItems(list(_CHANNELS))
        channel, warning = self._normalize_channel(self.inputs["channel"])
        self.inputs["channel"] = channel
        self._combo.setCurrentText(channel)
        self._combo.currentTextChanged.connect(self._on_channel_changed)
        set_control_height(self._combo)
        layout.addWidget(self._combo)
        layout.addStretch(1)
        self.emit("error", warning)
        return root

    def _on_channel_changed(self, channel: str) -> None:
        self.inputs["channel"] = channel
        self.emit("error", "")

    def _route(self) -> None:
        channel, warning = self._normalize_channel(self.inputs["channel"])
        self.inputs["channel"] = channel
        if self._combo is not None and self._combo.currentText() != channel:
            self._combo.blockSignals(True)
            self._combo.setCurrentText(channel)
            self._combo.blockSignals(False)
        self.emit("pulse", 1)
        for key in _CHANNELS:
            self.emit(key, 1 if key == channel else 0)
        self.emit("text", f"trigger->{channel}")
        self.emit("error", warning)

    def on_input(self, port: str, value: Any) -> None:
        if port == "channel":
            channel, warning = self._normalize_channel(value)
            self.inputs["channel"] = channel
            if self._combo is not None and self._combo.currentText() != channel:
                self._combo.blockSignals(True)
                self._combo.setCurrentText(channel)
                self._combo.blockSignals(False)
            self.emit("error", warning)
            return

        if port == "trigger" and is_truthy(value):
            self._route()

    @staticmethod
    def _normalize_channel(value: Any) -> tuple[str, str]:
        token = str(value).strip().lower()
        if token in _CHANNELS:
            return token, ""
        return "evaluate", f"invalid channel '{value}'; using 'evaluate'"
