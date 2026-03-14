"""Trigger-released latch for stabilizing downstream value flow."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class ValueLatchModule(BaseModule):
    """Hold incoming values and release on demand unless transparent mode is enabled."""

    persistent_inputs = ("transparent",)

    descriptor = ModuleDescriptor(
        module_type="value_latch",
        display_name="Value Latch",
        family="Logic",
        description="Holds values until release pulse unless transparent mode is active.",
        inputs=(
            PortSpec("value", "any", default=None),
            PortSpec("release", "trigger", default=0, control_plane=True),
            PortSpec("transparent", "boolean", default=True),
            PortSpec("clear", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("value", "any", default=None),
            PortSpec("held", "any", default=None),
            PortSpec("released", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._held_value: Any = None
        self._has_held_value = False
        self._last_released_value: Any = None
        self._last_error = ""

        self._transparent_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._transparent_check = QCheckBox("Transparent (Pass Through)")
        self._transparent_check.setChecked(bool(self.inputs["transparent"]))
        self._transparent_check.toggled.connect(
            lambda enabled: self.receive_binding("transparent", enabled)
        )
        form.addRow("", self._transparent_check)

        release_btn = QPushButton("Release")
        release_btn.clicked.connect(lambda: self.receive_binding("release", 1))
        set_control_height(release_btn)
        form.addRow("", release_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: self.receive_binding("clear", 1))
        set_control_height(clear_btn)
        form.addRow("", clear_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._emit_text("ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "transparent":
            enabled = bool(value)
            self.inputs["transparent"] = enabled
            if (
                self._transparent_check is not None
                and self._transparent_check.isChecked() != enabled
            ):
                self._transparent_check.blockSignals(True)
                self._transparent_check.setChecked(enabled)
                self._transparent_check.blockSignals(False)
            mode = "transparent" if enabled else "latched"
            self._last_error = ""
            self._emit_text(f"mode={mode}")
            return

        if port == "value":
            if bool(self.inputs["transparent"]):
                self._last_error = ""
                self._last_released_value = value
                self.emit("value", value)
                self.emit("held", None)
                self.emit("released", 1)
                self._emit_text(f"released={value!r} (transparent)")
            else:
                self._last_error = ""
                self._held_value = value
                self._has_held_value = True
                self.emit("held", value)
                self.emit("released", 0)
                self._emit_text(f"held={value!r}")
            return

        if port == "release" and is_truthy(value):
            self._release()
            return

        if port == "clear" and is_truthy(value):
            self._clear()

    def _release(self) -> None:
        if bool(self.inputs["transparent"]):
            self._last_error = ""
            current = self.inputs.get("value")
            self._last_released_value = current
            self.emit("value", current)
            self.emit("held", None)
            self.emit("released", 1)
            self._emit_text(f"released={current!r}")
            return

        if not self._has_held_value:
            self._last_error = "release ignored (no held value)"
            self.emit("released", 0)
            self._emit_text("release ignored (no held value)")
            return

        self._last_error = ""
        self._last_released_value = self._held_value
        self.emit("value", self._held_value)
        self._held_value = None
        self._has_held_value = False
        self.emit("held", None)
        self.emit("released", 1)
        self._emit_text(f"released={self._last_released_value!r}")

    def _clear(self) -> None:
        self._last_error = ""
        self._held_value = None
        self._has_held_value = False
        self._last_released_value = None
        self.emit("value", None)
        self.emit("held", None)
        self.emit("released", 0)
        self._emit_text("cleared")

    def _emit_text(self, text: str) -> None:
        held = self._held_value if self._has_held_value else None
        summary = f"{text}, held={held!r}, last_released={self._last_released_value!r}"
        self.emit("text", summary)
        self.emit("error", self._last_error)
        if self._status is not None:
            self._status.setText(summary)
