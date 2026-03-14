"""Template formatting utility for deterministic text composition."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height

_FIELD_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d+\])*)\}")
_FIELD_PART_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\[\d+\])*$")
_INDEX_RE = re.compile(r"\[(\d+)\]")


class TemplateFormatterModule(BaseModule):
    """Render template text from context/value inputs."""

    persistent_inputs = ("template", "auto", "strict")

    descriptor = ModuleDescriptor(
        module_type="template_formatter",
        display_name="Template Formatter",
        family="Transform",
        description="Formats template text from context and value fields.",
        inputs=(
            PortSpec("template", "string", default="{value}"),
            PortSpec("context", "json", default={}),
            PortSpec("value", "any", default=None),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
            PortSpec("strict", "boolean", default=False),
        ),
        outputs=(
            PortSpec("value", "string", default=""),
            PortSpec("fields", "json", default=[]),
            PortSpec("rendered", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._template_edit: QLineEdit | None = None
        self._auto_check: QCheckBox | None = None
        self._strict_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._template_edit = QLineEdit(str(self.inputs["template"]))
        self._template_edit.textChanged.connect(lambda text: self.receive_binding("template", text))
        set_control_height(self._template_edit)
        form.addRow("Template", self._template_edit)

        self._auto_check = QCheckBox("Auto Render")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda enabled: self.receive_binding("auto", enabled))
        form.addRow("", self._auto_check)

        self._strict_check = QCheckBox("Strict Missing Fields")
        self._strict_check.setChecked(bool(self.inputs["strict"]))
        self._strict_check.toggled.connect(
            lambda enabled: self.receive_binding("strict", enabled)
        )
        form.addRow("", self._strict_check)

        render_btn = QPushButton("Render")
        render_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(render_btn)
        form.addRow("", render_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._publish(
            rendered_value=str(self.outputs.get("value", "")),
            fields=list(self.outputs.get("fields", [])),
            rendered=0,
            error="",
            reason="ready",
        )
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "template":
            template = str(value)
            self.inputs["template"] = template
            if self._template_edit is not None and self._template_edit.text() != template:
                self._template_edit.blockSignals(True)
                self._template_edit.setText(template)
                self._template_edit.blockSignals(False)
            self._dispatch_after_config(reason="template")
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            self._dispatch_after_config(reason="auto")
            return

        if port == "strict":
            enabled = bool(value)
            self.inputs["strict"] = enabled
            if self._strict_check is not None and self._strict_check.isChecked() != enabled:
                self._strict_check.blockSignals(True)
                self._strict_check.setChecked(enabled)
                self._strict_check.blockSignals(False)
            self._dispatch_after_config(reason="strict")
            return

        if port in {"context", "value"}:
            self._dispatch_after_config(reason=port)
            return

        if port == "emit" and is_truthy(value):
            self._render(reason="emit", trigger_output=True)

    def replay_state(self) -> None:
        self._render(reason="replay", trigger_output=False)

    def _dispatch_after_config(self, *, reason: str) -> None:
        if bool(self.inputs["auto"]):
            self._render(reason=reason, trigger_output=True)
            return
        self._publish(
            rendered_value=str(self.outputs.get("value", "")),
            fields=list(self.outputs.get("fields", [])),
            rendered=0,
            error="",
            reason=f"{reason} cached",
        )

    def _render(self, *, reason: str, trigger_output: bool) -> None:
        template = str(self.inputs.get("template", ""))
        fields = self._extract_fields(template)
        strict = bool(self.inputs.get("strict", False))
        context = self._build_context()

        replacements: dict[str, str] = {}
        missing: list[str] = []
        for field in fields:
            found, resolved = self._resolve_field(context, field)
            if not found:
                missing.append(field)
                replacements[field] = ""
                continue
            replacements[field] = self._stringify(resolved)

        if missing and strict:
            self._publish(
                rendered_value="",
                fields=fields,
                rendered=0,
                error=f"missing fields: {', '.join(missing)}",
                reason=f"{reason}: error",
            )
            return

        rendered_value = _FIELD_RE.sub(
            lambda match: replacements.get(match.group(1), ""),
            template,
        )
        error = ""
        if missing:
            error = f"missing fields: {', '.join(missing)}"

        self._publish(
            rendered_value=rendered_value,
            fields=fields,
            rendered=1 if trigger_output else 0,
            error=error,
            reason=reason,
        )

    def _build_context(self) -> dict[str, Any]:
        context = self.inputs.get("context", {})
        value = deepcopy(self.inputs.get("value"))
        if isinstance(context, dict):
            root = deepcopy(context)
            root.setdefault("value", value)
            return root
        if isinstance(context, list):
            return {"context": deepcopy(context), "value": value}
        return {"value": value}

    @staticmethod
    def _extract_fields(template: str) -> list[str]:
        fields: list[str] = []
        for token in _FIELD_RE.findall(template):
            if token not in fields:
                fields.append(token)
        return fields

    @staticmethod
    def _resolve_field(context: dict[str, Any], field: str) -> tuple[bool, Any]:
        current: Any = context
        for part in field.split("."):
            match = _FIELD_PART_RE.match(part)
            if match is None:
                return False, None
            name = match.group(1)
            if not isinstance(current, dict) or name not in current:
                return False, None
            current = current[name]
            for index_match in _INDEX_RE.finditer(part):
                if not isinstance(current, list):
                    return False, None
                index = int(index_match.group(1))
                if index < 0 or index >= len(current):
                    return False, None
                current = current[index]
        return True, current

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _publish(
        self,
        *,
        rendered_value: str,
        fields: list[str],
        rendered: int,
        error: str,
        reason: str,
    ) -> None:
        self.emit("value", rendered_value)
        self.emit("fields", list(fields))
        self.emit("rendered", 1 if rendered else 0)
        self.emit("error", error)
        text = f"fields={len(fields)}, chars={len(rendered_value)}, reason={reason}"
        self.emit("text", text if not error else f"error: {error}")
        if self._status is not None:
            self._status.setText(text if not error else f"error: {error}")
