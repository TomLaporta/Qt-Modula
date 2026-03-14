"""Comparator-oriented condition gate module."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import ModuleBase, ModuleDescriptor, PortSpec, coerce_finite_float, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height
from qt_modula.ui.advanced_section import AdvancedSection

_OPERATORS = ("truthy", "falsy", "eq", "neq", "gt", "gte", "lt", "lte")


class ConditionGateModule(ModuleBase):
    """Split payload flow through true/false comparator paths."""

    persistent_inputs = ("operator", "auto", "b", "epsilon")

    descriptor = ModuleDescriptor(
        module_type="condition_gate",
        display_name="Condition Gate",
        family="Logic",
        description="Comparator-focused gate with true/false trigger outputs.",
        capabilities=("gate", "transform"),
        inputs=(
            PortSpec("a", "any", default=None),
            PortSpec(
                "b",
                "any",
                default=0.0,
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec("value", "any", default=None),
            PortSpec("operator", "string", default="truthy"),
            PortSpec(
                "auto",
                "boolean",
                default=True,
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec("evaluate", "trigger", default=0, control_plane=True),
            PortSpec(
                "epsilon",
                "number",
                default=1e-9,
                bind_visibility="advanced",
                ui_group="advanced",
            ),
        ),
        outputs=(
            PortSpec("matched", "boolean", default=False),
            PortSpec("on_true", "trigger", default=0, control_plane=True),
            PortSpec("on_false", "trigger", default=0, control_plane=True),
            PortSpec("passed", "any", default=None),
            PortSpec("blocked", "any", default=None),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._operator_combo: QComboBox | None = None
        self._auto_check: QCheckBox | None = None
        self._epsilon_spin: QDoubleSpinBox | None = None
        self._status: QLabel | None = None
        self._value_seen = False
        self._operator_warning = ""

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()
        self._operator_combo = QComboBox()
        self._operator_combo.addItems(list(_OPERATORS))
        self._operator_combo.setCurrentText(str(self.inputs["operator"]))
        self._operator_combo.currentTextChanged.connect(
            lambda token: self.receive_binding("operator", token)
        )
        set_control_height(self._operator_combo)
        form.addRow("Operator", self._operator_combo)

        evaluate_btn = QPushButton("Evaluate")
        evaluate_btn.clicked.connect(lambda: self.receive_binding("evaluate", 1))
        set_control_height(evaluate_btn)
        form.addRow("", evaluate_btn)
        layout.addLayout(form)

        advanced = AdvancedSection("Advanced", expanded=False)
        advanced_form = QFormLayout()

        self._auto_check = QCheckBox("Auto Evaluate")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda enabled: self.receive_binding("auto", enabled))
        advanced_form.addRow("", self._auto_check)

        self._epsilon_spin = QDoubleSpinBox()
        self._epsilon_spin.setDecimals(12)
        self._epsilon_spin.setRange(0.0, 1_000_000_000.0)
        self._epsilon_spin.setValue(float(self.inputs["epsilon"]))
        self._epsilon_spin.valueChanged.connect(
            lambda value: self.receive_binding("epsilon", float(value))
        )
        set_control_height(self._epsilon_spin)
        advanced_form.addRow("Epsilon", self._epsilon_spin)

        advanced.content_layout.addLayout(advanced_form)
        layout.addWidget(advanced)

        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        return root

    def _normalize_operator(self, value: Any) -> tuple[str, str]:
        token = str(value).strip().lower()
        if token in _OPERATORS:
            return token, ""
        return "truthy", f"invalid operator '{value}'; using 'truthy'"

    def _compute(self, operator: str, left: Any, right: Any, epsilon: float) -> bool:
        if operator == "truthy":
            return is_truthy(left)
        if operator == "falsy":
            return not is_truthy(left)

        left_number = coerce_finite_float(left)
        right_number = coerce_finite_float(right)

        if operator in {"eq", "neq"}:
            if left_number is not None and right_number is not None:
                difference = abs(left_number - right_number)
                matched = difference <= epsilon
            else:
                matched = left == right
            return matched if operator == "eq" else not matched

        if left_number is None or right_number is None:
            raise ValueError(f"operator '{operator}' requires finite numeric 'a' and 'b'")

        if operator == "gt":
            return left_number > (right_number + epsilon)
        if operator == "gte":
            return left_number >= (right_number - epsilon)
        if operator == "lt":
            return left_number < (right_number - epsilon)
        if operator == "lte":
            return left_number <= (right_number + epsilon)

        raise ValueError(f"unsupported operator '{operator}'")

    def _evaluate(self) -> None:
        operator, warning = self._normalize_operator(self.inputs["operator"])
        self.inputs["operator"] = operator
        self._operator_warning = warning

        left = self.inputs["a"]
        right = self.inputs["b"]
        candidate = self.inputs["value"] if self._value_seen else left
        epsilon = max(0.0, float(self.inputs["epsilon"]))

        try:
            matched = self._compute(operator, left, right, epsilon)
        except ValueError as exc:
            message = str(exc)
            error_message = message if not warning else f"{warning}; {message}"
            self.emit("matched", False)
            self.emit("on_true", 0)
            self.emit("on_false", 0)
            self.emit("passed", None)
            self.emit("blocked", candidate)
            self.emit("error", error_message)
            text = f"error: {error_message}"
            self.emit("text", text)
            if self._status is not None:
                self._status.setText(text)
            return

        self.emit("matched", matched)
        self.emit("on_true", 1 if matched else 0)
        self.emit("on_false", 0 if matched else 1)
        self.emit("passed", candidate if matched else None)
        self.emit("blocked", None if matched else candidate)
        self.emit("error", warning)

        text = (
            f"{operator}: a={left!r}, b={right!r}, matched={int(matched)}, "
            f"route={'passed' if matched else 'blocked'}"
        )
        self.emit("text", text)
        if self._status is not None:
            self._status.setText(text)

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
                self._evaluate()
            else:
                self.emit("error", warning)
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            if enabled:
                self._evaluate()
            return

        if port == "epsilon":
            epsilon = max(0.0, float(value))
            self.inputs["epsilon"] = epsilon
            if self._epsilon_spin is not None and abs(self._epsilon_spin.value() - epsilon) > 1e-12:
                self._epsilon_spin.blockSignals(True)
                self._epsilon_spin.setValue(epsilon)
                self._epsilon_spin.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._evaluate()
            return

        if port == "value":
            self._value_seen = True
            if bool(self.inputs["auto"]):
                self._evaluate()
            return

        if port in {"a", "b"} and bool(self.inputs["auto"]):
            self._evaluate()
            return

        if port == "evaluate" and is_truthy(value):
            self._evaluate()

    def replay_state(self) -> None:
        self._evaluate()
