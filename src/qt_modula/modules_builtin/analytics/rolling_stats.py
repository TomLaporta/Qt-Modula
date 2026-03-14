"""Rolling-window statistics analytics module ."""

from __future__ import annotations

import math
from collections import deque
from statistics import fmean, pstdev
from typing import Any

from PySide6.QtWidgets import QFormLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class RollingStatsModule(BaseModule):
    """Compute rolling mean/stddev/min/max from numeric streams."""

    persistent_inputs = ("window",)

    descriptor = ModuleDescriptor(
        module_type="rolling_stats",
        display_name="Rolling Stats",
        family="Analytics",
        description="Rolling mean/stddev/min/max over bounded numeric window.",
        capabilities=("transform", "sink"),
        inputs=(
            PortSpec("value", "number", default=0.0),
            PortSpec("window", "integer", default=32),
            PortSpec("reset", "trigger", default=0, control_plane=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("mean", "number", default=0.0),
            PortSpec("stddev", "number", default=0.0),
            PortSpec("min", "number", default=0.0),
            PortSpec("max", "number", default=0.0),
            PortSpec("count", "integer", default=0),
            PortSpec("ready", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._values: deque[float] = deque(maxlen=max(2, int(self.inputs["window"])))
        self._window_spin: QSpinBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()
        self._window_spin = QSpinBox()
        self._window_spin.setRange(2, 10_000)
        self._window_spin.setValue(int(self.inputs["window"]))
        self._window_spin.valueChanged.connect(self._on_window_changed)
        set_control_height(self._window_spin)
        form.addRow("Window", self._window_spin)
        layout.addLayout(form)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._publish()
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "window":
            window = max(2, int(value))
            self.inputs["window"] = window
            self._values = deque(list(self._values), maxlen=window)
            if self._window_spin is not None and self._window_spin.value() != window:
                self._window_spin.blockSignals(True)
                self._window_spin.setValue(window)
                self._window_spin.blockSignals(False)
            self._publish()
            return

        if port == "reset" and is_truthy(value):
            self._values.clear()
            self._publish()
            return

        if port == "value":
            numeric = float(value)
            if not math.isfinite(numeric):
                self.emit("error", "value must be finite")
                return
            self._values.append(numeric)
            self._publish()
            return

        if port == "emit" and is_truthy(value):
            self._publish()

    def _on_window_changed(self, window: int) -> None:
        self.on_input("window", window)

    def _publish(self) -> None:
        values = list(self._values)
        count = len(values)
        if count == 0:
            mean = 0.0
            stddev = 0.0
            minimum = 0.0
            maximum = 0.0
            ready = 0
            text = "n=0"
        else:
            mean = float(fmean(values))
            stddev = float(pstdev(values)) if count > 1 else 0.0
            minimum = min(values)
            maximum = max(values)
            ready = 1
            text = (
                f"n={count}, mean={mean:.6g}, std={stddev:.6g}, "
                f"min={minimum:.6g}, max={maximum:.6g}"
            )

        self.emit("mean", mean)
        self.emit("stddev", stddev)
        self.emit("min", minimum)
        self.emit("max", maximum)
        self.emit("count", count)
        self.emit("ready", ready)
        self.emit("text", text)
        self.emit("error", "")

        if self._status is not None:
            self._status.setText(text)
