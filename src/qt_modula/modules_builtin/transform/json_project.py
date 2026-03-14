"""Deterministic JSON projection module for provider payload shaping."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height

_CLAUSE_SPLIT_RE = re.compile(r"[\n;,]")


class JsonProjectModule(BaseModule):
    """Project selected JSON fields into deterministic flat record outputs."""

    persistent_inputs = ("mapping", "auto", "strict")

    descriptor = ModuleDescriptor(
        module_type="json_project",
        display_name="JSON Project",
        family="Transform",
        description="Extracts flat records from JSON payloads using path mapping rules.",
        inputs=(
            PortSpec("json", "json", default={}),
            PortSpec("mapping", "string", default=""),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
            PortSpec("strict", "boolean", default=False),
        ),
        outputs=(
            PortSpec("record", "json", default={}),
            PortSpec("keys", "json", default=[]),
            PortSpec("projected", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._mapping_edit: QTextEdit | None = None
        self._auto_check: QCheckBox | None = None
        self._strict_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._auto_check = QCheckBox("Auto Project")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda enabled: self.receive_binding("auto", enabled))
        form.addRow("", self._auto_check)

        self._strict_check = QCheckBox("Strict Missing Paths")
        self._strict_check.setChecked(bool(self.inputs["strict"]))
        self._strict_check.toggled.connect(lambda enabled: self.receive_binding("strict", enabled))
        form.addRow("", self._strict_check)

        emit_btn = QPushButton("Project")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        form.addRow("", emit_btn)

        layout.addLayout(form)

        self._mapping_edit = QTextEdit()
        self._mapping_edit.setPlaceholderText("price=$.price\nsymbol=$.symbol")
        self._mapping_edit.setPlainText(str(self.inputs["mapping"]))
        self._mapping_edit.textChanged.connect(self._on_mapping_changed)
        layout.addWidget(self._mapping_edit)

        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(record={}, keys=[], projected=0, error="", reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "mapping":
            mapping = str(value)
            self.inputs["mapping"] = mapping
            if self._mapping_edit is not None and self._mapping_edit.toPlainText() != mapping:
                self._mapping_edit.blockSignals(True)
                self._mapping_edit.setPlainText(mapping)
                self._mapping_edit.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._project(reason="mapping")
            else:
                self._publish(
                    record=self.outputs.get("record", {}),
                    keys=self.outputs.get("keys", []),
                    projected=0,
                    error="",
                    reason="mapping updated",
                )
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            if enabled:
                self._project(reason="auto")
            else:
                self._publish(
                    record=self.outputs.get("record", {}),
                    keys=self.outputs.get("keys", []),
                    projected=0,
                    error="",
                    reason="auto updated",
                )
            return

        if port == "strict":
            enabled = bool(value)
            self.inputs["strict"] = enabled
            if self._strict_check is not None and self._strict_check.isChecked() != enabled:
                self._strict_check.blockSignals(True)
                self._strict_check.setChecked(enabled)
                self._strict_check.blockSignals(False)
            if bool(self.inputs["auto"]):
                self._project(reason="strict")
            else:
                self._publish(
                    record=self.outputs.get("record", {}),
                    keys=self.outputs.get("keys", []),
                    projected=0,
                    error="",
                    reason="strict updated",
                )
            return

        if port == "json":
            if bool(self.inputs["auto"]):
                self._project(reason="json")
            else:
                self._publish(
                    record=self.outputs.get("record", {}),
                    keys=self.outputs.get("keys", []),
                    projected=0,
                    error="",
                    reason="json updated",
                )
            return

        if port == "emit" and is_truthy(value):
            self._project(reason="emit")

    def _on_mapping_changed(self) -> None:
        if self._mapping_edit is None:
            return
        self.receive_binding("mapping", self._mapping_edit.toPlainText())

    def _project(self, *, reason: str) -> None:
        payload = self.inputs.get("json", {})
        mapping_text = str(self.inputs.get("mapping", ""))
        strict = bool(self.inputs.get("strict", False))

        try:
            clauses = self._parse_mapping(mapping_text)
            record: dict[str, Any] = {}
            for output_key, path_tokens, raw_path in clauses:
                try:
                    record[output_key] = self._resolve_path(payload, path_tokens)
                except (KeyError, IndexError, TypeError):
                    if strict:
                        raise ValueError(f"missing path for '{output_key}': {raw_path}") from None
            keys = list(record.keys())
            self._publish(
                record=record,
                keys=keys,
                projected=1,
                error="",
                reason=f"{reason}: projected {len(keys)}",
            )
        except ValueError as exc:
            self._publish(
                record={},
                keys=[],
                projected=0,
                error=str(exc),
                reason=f"{reason}: error",
            )

    @staticmethod
    def _parse_mapping(mapping: str) -> list[tuple[str, list[str | int], str]]:
        clauses: list[tuple[str, list[str | int], str]] = []
        for raw_clause in _CLAUSE_SPLIT_RE.split(mapping):
            clause = raw_clause.strip()
            if not clause:
                continue
            if "=" not in clause:
                raise ValueError(f"invalid mapping clause '{clause}'")
            left, right = clause.split("=", 1)
            key = left.strip()
            path = right.strip()
            if not key:
                raise ValueError("mapping output key must be non-empty")
            clauses.append((key, JsonProjectModule._parse_path(path), path))
        return clauses

    @staticmethod
    def _parse_path(path: str) -> list[str | int]:
        if path == "$":
            return []
        if not path.startswith("$"):
            raise ValueError(f"path must start with '$': {path}")

        tokens: list[str | int] = []
        index = 1
        while index < len(path):
            token = path[index]
            if token == ".":
                index += 1
                start = index
                while index < len(path) and (path[index].isalnum() or path[index] == "_"):
                    index += 1
                name = path[start:index]
                if not name:
                    raise ValueError(f"invalid path token in '{path}'")
                tokens.append(name)
                continue

            if token == "[":
                index += 1
                start = index
                while index < len(path) and path[index].isdigit():
                    index += 1
                if index >= len(path) or path[index] != "]" or start == index:
                    raise ValueError(f"invalid index token in '{path}'")
                tokens.append(int(path[start:index]))
                index += 1
                continue

            raise ValueError(f"unsupported path syntax in '{path}'")

        return tokens

    @staticmethod
    def _resolve_path(payload: Any, tokens: list[str | int]) -> Any:
        current = payload
        for token in tokens:
            if isinstance(token, str):
                if not isinstance(current, dict):
                    raise TypeError("expected object")
                if token not in current:
                    raise KeyError(token)
                current = current[token]
                continue

            if not isinstance(current, list):
                raise TypeError("expected list")
            if token < 0 or token >= len(current):
                raise IndexError(token)
            current = current[token]

        return current

    def _publish(
        self,
        *,
        record: dict[str, Any] | Any,
        keys: list[str] | Any,
        projected: int,
        error: str,
        reason: str,
    ) -> None:
        record_obj = record if isinstance(record, dict) else {}
        key_list = keys if isinstance(keys, list) else []
        self.emit("record", record_obj)
        self.emit("keys", key_list)
        self.emit("projected", 1 if projected else 0)
        self.emit("error", error)
        text = (
            f"keys={len(key_list)}, strict={int(bool(self.inputs['strict']))}, "
            f"reason={reason}"
        )
        self.emit("text", text if not error else f"error: {error}")
        if self._status is not None:
            self._status.setText(text if not error else f"error: {error}")
