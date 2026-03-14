"""N-input boolean combinator for control/data workflow branching."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height

_OPERATORS = ("and", "or", "xor", "not")


class LogicCombinatorModule(BaseModule):
    """Evaluate boolean logic across a JSON value list."""

    persistent_inputs = ("operator", "auto")

    descriptor = ModuleDescriptor(
        module_type="logic_combinator",
        display_name="Logic Combinator",
        family="Logic",
        description="N-input boolean gate with deterministic true/false trigger outputs.",
        inputs=(
            PortSpec("values", "json", default=[]),
            PortSpec("operator", "string", default="and"),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("matched", "boolean", default=False),
            PortSpec("on_true", "trigger", default=0, control_plane=True),
            PortSpec("on_false", "trigger", default=0, control_plane=True),
            PortSpec("true_count", "integer", default=0),
            PortSpec("false_count", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._operator_warning = ""

        self._operator_combo: QComboBox | None = None
        self._auto_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._operator_combo = QComboBox()
        self._operator_combo.addItems(list(_OPERATORS))
        operator, warning = self._normalize_operator(self.inputs["operator"])
        self.inputs["operator"] = operator
        self._operator_warning = warning
        self._operator_combo.setCurrentText(operator)
        self._operator_combo.currentTextChanged.connect(
            lambda token: self.receive_binding("operator", token)
        )
        set_control_height(self._operator_combo)
        form.addRow("Operator", self._operator_combo)

        self._auto_check = QCheckBox("Auto Evaluate")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda enabled: self.receive_binding("auto", enabled))
        form.addRow("", self._auto_check)

        evaluate_btn = QPushButton("Evaluate")
        evaluate_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(evaluate_btn)
        form.addRow("", evaluate_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish_cached(reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "operator":
            operator, warning = self._normalize_operator(value)
            self.inputs["operator"] = operator
            self._operator_warning = warning
            if self._operator_combo is not None and self._operator_combo.currentText() != operator:
                self._operator_combo.blockSignals(True)
                self._operator_combo.setCurrentText(operator)
                self._operator_combo.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._evaluate(reason="operator", trigger_outputs=True)
            else:
                self._publish_cached(reason="operator updated")
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            if enabled:
                self._evaluate(reason="auto", trigger_outputs=True)
            else:
                self._publish_cached(reason="auto updated")
            return

        if port == "values":
            if bool(self.inputs["auto"]):
                self._evaluate(reason="values", trigger_outputs=True)
            else:
                self._publish_cached(reason="values cached")
            return

        if port == "emit" and is_truthy(value):
            self._evaluate(reason="emit", trigger_outputs=True)

    def replay_state(self) -> None:
        self._evaluate(reason="replay", trigger_outputs=False)

    def _evaluate(self, *, reason: str, trigger_outputs: bool) -> None:
        operator, warning = self._normalize_operator(self.inputs["operator"])
        self.inputs["operator"] = operator
        self._operator_warning = warning
        if self._operator_combo is not None and self._operator_combo.currentText() != operator:
            self._operator_combo.blockSignals(True)
            self._operator_combo.setCurrentText(operator)
            self._operator_combo.blockSignals(False)

        values_obj = self.inputs.get("values", [])
        if not isinstance(values_obj, list):
            bool_values: list[bool] = []
            values_warning = "values must be a list; using []"
        else:
            bool_values = [is_truthy(item) for item in values_obj]
            values_warning = ""

        matched = self._compute(operator, bool_values)
        true_count = sum(1 for item in bool_values if item)
        false_count = len(bool_values) - true_count

        warnings = [item for item in (self._operator_warning, values_warning) if item]
        error_text = "; ".join(warnings)

        self.emit("matched", matched)
        self.emit("on_true", 1 if trigger_outputs and matched else 0)
        self.emit("on_false", 1 if trigger_outputs and not matched else 0)
        self.emit("true_count", true_count)
        self.emit("false_count", false_count)
        self.emit("error", error_text)
        text = (
            f"operator={operator}, inputs={len(bool_values)}, "
            f"matched={int(matched)}, reason={reason}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    def _publish_cached(self, *, reason: str) -> None:
        self.emit("on_true", 0)
        self.emit("on_false", 0)
        self.emit("error", self._operator_warning)
        text = f"auto=0, reason={reason}"
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

    @staticmethod
    def _normalize_operator(value: Any) -> tuple[str, str]:
        token = str(value).strip().lower()
        if token in _OPERATORS:
            return token, ""
        return "and", f"invalid operator '{value}'; using 'and'"

    @staticmethod
    def _compute(operator: str, values: list[bool]) -> bool:
        if operator == "and":
            return bool(values) and all(values)
        if operator == "or":
            return any(values)
        if operator == "xor":
            return (sum(1 for item in values if item) % 2) == 1
        if operator == "not":
            first = values[0] if values else False
            return not first
        return False
