"""General table transform module for filter/sort/limit/projection lanes."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height


class TableTransformModule(BaseModule):
    """Apply deterministic transform operations over table rows."""

    persistent_inputs = (
        "filter_key",
        "filter_value",
        "sort_key",
        "descending",
        "limit",
        "columns",
        "auto",
    )

    descriptor = ModuleDescriptor(
        module_type="table_transform",
        display_name="Table Transform",
        family="Transform",
        description="Filters, sorts, limits, and projects table rows deterministically.",
        inputs=(
            PortSpec("rows", "table", default=[]),
            PortSpec("filter_key", "string", default=""),
            PortSpec("filter_value", "any", default=None),
            PortSpec("sort_key", "string", default=""),
            PortSpec("descending", "boolean", default=False),
            PortSpec("limit", "integer", default=0),
            PortSpec("columns", "json", default=[]),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("rows", "table", default=[]),
            PortSpec("row_count", "integer", default=0),
            PortSpec("transformed", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._columns_warning = ""
        self._limit_warning = ""

        self._filter_key_edit: QLineEdit | None = None
        self._filter_value_edit: QLineEdit | None = None
        self._sort_key_edit: QLineEdit | None = None
        self._descending_check: QCheckBox | None = None
        self._limit_spin: QSpinBox | None = None
        self._columns_edit: QLineEdit | None = None
        self._auto_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._filter_key_edit = QLineEdit(str(self.inputs["filter_key"]))
        self._filter_key_edit.textChanged.connect(
            lambda text: self.receive_binding("filter_key", text.strip())
        )
        set_control_height(self._filter_key_edit)
        form.addRow("Filter Key", self._filter_key_edit)

        self._filter_value_edit = QLineEdit(self._value_to_text(self.inputs["filter_value"]))
        self._filter_value_edit.textChanged.connect(
            lambda text: self.receive_binding("filter_value", self._value_from_text(text))
        )
        set_control_height(self._filter_value_edit)
        form.addRow("Filter Value", self._filter_value_edit)

        self._sort_key_edit = QLineEdit(str(self.inputs["sort_key"]))
        self._sort_key_edit.textChanged.connect(
            lambda text: self.receive_binding("sort_key", text.strip())
        )
        set_control_height(self._sort_key_edit)
        form.addRow("Sort Key", self._sort_key_edit)

        self._descending_check = QCheckBox("Descending")
        self._descending_check.setChecked(bool(self.inputs["descending"]))
        self._descending_check.toggled.connect(
            lambda enabled: self.receive_binding("descending", enabled)
        )
        form.addRow("", self._descending_check)

        self._limit_spin = QSpinBox()
        self._limit_spin.setRange(0, 1_000_000)
        self._limit_spin.setValue(max(0, int(self.inputs["limit"])))
        self._limit_spin.valueChanged.connect(
            lambda value: self.receive_binding("limit", int(value))
        )
        set_control_height(self._limit_spin)
        form.addRow("Limit (0=all)", self._limit_spin)

        self._columns_edit = QLineEdit(self._columns_to_text(self.inputs["columns"]))
        self._columns_edit.setPlaceholderText("col1,col2,col3")
        self._columns_edit.textChanged.connect(
            lambda text: self.receive_binding("columns", self._columns_from_text(text))
        )
        set_control_height(self._columns_edit)
        form.addRow("Columns", self._columns_edit)

        self._auto_check = QCheckBox("Auto Transform")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda enabled: self.receive_binding("auto", enabled))
        form.addRow("", self._auto_check)

        emit_btn = QPushButton("Transform")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        form.addRow("", emit_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(rows=[], transformed=0, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "filter_key":
            token = str(value).strip()
            self.inputs["filter_key"] = token
            if self._filter_key_edit is not None and self._filter_key_edit.text() != token:
                self._filter_key_edit.blockSignals(True)
                self._filter_key_edit.setText(token)
                self._filter_key_edit.blockSignals(False)
            self._dispatch_after_config(reason="filter_key")
            return

        if port == "filter_value":
            self.inputs["filter_value"] = deepcopy(value)
            if self._filter_value_edit is not None:
                text = self._value_to_text(value)
                if self._filter_value_edit.text() != text:
                    self._filter_value_edit.blockSignals(True)
                    self._filter_value_edit.setText(text)
                    self._filter_value_edit.blockSignals(False)
            self._dispatch_after_config(reason="filter_value")
            return

        if port == "sort_key":
            token = str(value).strip()
            self.inputs["sort_key"] = token
            if self._sort_key_edit is not None and self._sort_key_edit.text() != token:
                self._sort_key_edit.blockSignals(True)
                self._sort_key_edit.setText(token)
                self._sort_key_edit.blockSignals(False)
            self._dispatch_after_config(reason="sort_key")
            return

        if port == "descending":
            enabled = bool(value)
            self.inputs["descending"] = enabled
            if self._descending_check is not None and self._descending_check.isChecked() != enabled:
                self._descending_check.blockSignals(True)
                self._descending_check.setChecked(enabled)
                self._descending_check.blockSignals(False)
            self._dispatch_after_config(reason="descending")
            return

        if port == "limit":
            requested = int(value)
            limit = max(0, requested)
            self.inputs["limit"] = limit
            self._limit_warning = "limit clamped to 0" if requested < 0 else ""
            if self._limit_spin is not None and self._limit_spin.value() != limit:
                self._limit_spin.blockSignals(True)
                self._limit_spin.setValue(limit)
                self._limit_spin.blockSignals(False)
            self._dispatch_after_config(reason="limit")
            return

        if port == "columns":
            self.inputs["columns"] = self._normalize_columns(value)
            if self._columns_edit is not None:
                text = self._columns_to_text(self.inputs["columns"])
                if self._columns_edit.text() != text:
                    self._columns_edit.blockSignals(True)
                    self._columns_edit.setText(text)
                    self._columns_edit.blockSignals(False)
            self._dispatch_after_config(reason="columns")
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

        if port == "rows":
            self._dispatch_after_config(reason="rows")
            return

        if port == "emit" and is_truthy(value):
            self._transform(reason="emit", trigger_output=True)

    def replay_state(self) -> None:
        self._transform(reason="replay", trigger_output=False)

    def _dispatch_after_config(self, *, reason: str) -> None:
        if bool(self.inputs["auto"]):
            self._transform(reason=reason, trigger_output=True)
            return
        self._publish(rows=self.outputs.get("rows", []), transformed=0, reason=f"{reason} cached")

    def _normalize_columns(self, value: Any) -> list[str]:
        if isinstance(value, list):
            self._columns_warning = ""
            columns = [str(item).strip() for item in value]
            return [item for item in columns if item]
        self._columns_warning = "columns must be a list; using []"
        return []

    @staticmethod
    def _value_to_text(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _value_from_text(text: str) -> Any:
        token = text.strip()
        lower = token.lower()
        if lower == "null":
            return None
        if lower == "true":
            return True
        if lower == "false":
            return False
        try:
            if "." in token:
                return float(token)
            return int(token)
        except ValueError:
            return token

    @staticmethod
    def _columns_to_text(value: Any) -> str:
        if not isinstance(value, list):
            return ""
        return ",".join(str(item) for item in value)

    @staticmethod
    def _columns_from_text(text: str) -> list[str]:
        return [item.strip() for item in text.split(",") if item.strip()]

    @staticmethod
    def _normalize_rows(rows: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(rows, list):
            return out
        for item in rows:
            if isinstance(item, dict):
                out.append(deepcopy(item))
            else:
                out.append({"value": deepcopy(item)})
        return out

    @staticmethod
    def _sort_token(value: Any) -> tuple[int, Any]:
        if value is None:
            return (4, "")
        if isinstance(value, bool):
            return (0, 1 if value else 0)
        if isinstance(value, (int, float)):
            number = float(value)
            if math.isfinite(number):
                return (1, number)
            return (3, str(value))
        if isinstance(value, str):
            return (2, value)
        return (3, str(value))

    def _transform(self, *, reason: str, trigger_output: bool) -> None:
        rows = self._normalize_rows(self.inputs.get("rows", []))
        filter_key = str(self.inputs["filter_key"]).strip()
        sort_key = str(self.inputs["sort_key"]).strip()
        descending = bool(self.inputs["descending"])
        limit = max(0, int(self.inputs["limit"]))
        columns = self.inputs["columns"] if isinstance(self.inputs["columns"], list) else []

        if filter_key:
            filter_value = self.inputs["filter_value"]
            rows = [row for row in rows if row.get(filter_key) == filter_value]

        if sort_key:
            rows = sorted(
                rows,
                key=lambda row: self._sort_token(row.get(sort_key)),
                reverse=descending,
            )

        if columns:
            rows = [{column: deepcopy(row.get(column)) for column in columns} for row in rows]

        if limit > 0:
            rows = rows[:limit]

        self._publish(rows=rows, transformed=1 if trigger_output else 0, reason=reason)

    def _publish(self, *, rows: list[dict[str, Any]], transformed: int, reason: str) -> None:
        warnings = [item for item in (self._limit_warning, self._columns_warning) if item]
        error = "; ".join(warnings)
        payload = [deepcopy(item) for item in rows]
        self.emit("rows", payload)
        self.emit("row_count", len(payload))
        self.emit("transformed", 1 if transformed else 0)
        self.emit("error", error)
        text = (
            f"rows={len(payload)}, filter={self.inputs['filter_key']!r}, "
            f"sort={self.inputs['sort_key']!r}, limit={int(self.inputs['limit'])}, reason={reason}"
        )
        self.emit("text", text if not error else f"error: {error}")
        if self._status is not None:
            self._status.setText(text if not error else f"error: {error}")
