"""Manual trigger source."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from qt_modula.sdk import ModuleBase, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class TriggerButtonModule(ModuleBase):
    """Emit one-shot control-plane pulses."""

    persistent_inputs = ("label",)

    descriptor = ModuleDescriptor(
        module_type="trigger_button",
        display_name="Trigger Button",
        family="Control",
        description="Manual pulse source for deterministic trigger chains.",
        capabilities=("source", "scheduler"),
        inputs=(
            PortSpec("trigger", "trigger", default=0, control_plane=True),
            PortSpec("label", "string", default="Trigger"),
        ),
        outputs=(
            PortSpec("pulse", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._button: QPushButton | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        self._button = QPushButton(str(self.inputs["label"]))
        self._button.clicked.connect(self._pulse)
        set_control_height(self._button)
        layout.addWidget(self._button)
        layout.addStretch(1)
        return root

    def _pulse(self) -> None:
        self.emit("pulse", 1)
        self.emit("text", "pulse")
        self.emit("error", "")

    def on_input(self, port: str, value: Any) -> None:
        if port == "trigger" and is_truthy(value):
            self._pulse()
            return
        if port == "label":
            label = str(value)
            if self._button is not None:
                self._button.setText(label)
            self.emit("text", f"label={label}")
            self.emit("error", "")

    def replay_state(self) -> None:
        self.emit("text", f"label={self.inputs['label']}")
        self.emit("error", "")
