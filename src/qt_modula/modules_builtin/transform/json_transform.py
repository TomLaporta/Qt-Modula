"""General JSON transform module for filter/map/flatten workflows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height

_MODES = ("identity", "flatten", "pluck", "filter_eq")


class JsonTransformModule(BaseModule):
    """Apply deterministic operations over JSON arrays/objects."""

    persistent_inputs = ("mode", "path", "key", "match", "auto", "strict")

    descriptor = ModuleDescriptor(
        module_type="json_transform",
        display_name="JSON Transform",
        family="Transform",
        description="Filters, maps, and flattens JSON payloads with deterministic rules.",
        inputs=(
            PortSpec("json", "json", default={}),
            PortSpec("mode", "string", default="identity"),
            PortSpec("path", "string", default="$"),
            PortSpec("key", "string", default=""),
            PortSpec("match", "any", default=None),
            PortSpec("auto", "boolean", default=True),
            PortSpec("emit", "trigger", default=0, control_plane=True),
            PortSpec("strict", "boolean", default=False),
        ),
        outputs=(
            PortSpec("json", "json", default={}),
            PortSpec("count", "integer", default=0),
            PortSpec("transformed", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._mode_warning = ""

        self._mode_combo: QComboBox | None = None
        self._path_edit: QLineEdit | None = None
        self._key_edit: QLineEdit | None = None
        self._match_edit: QLineEdit | None = None
        self._auto_check: QCheckBox | None = None
        self._strict_check: QCheckBox | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(list(_MODES))
        mode, warning = self._normalize_mode(self.inputs["mode"])
        self.inputs["mode"] = mode
        self._mode_warning = warning
        self._mode_combo.setCurrentText(mode)
        self._mode_combo.currentTextChanged.connect(
            lambda token: self.receive_binding("mode", token)
        )
        set_control_height(self._mode_combo)
        form.addRow("Mode", self._mode_combo)

        self._path_edit = QLineEdit(str(self.inputs["path"]))
        self._path_edit.textChanged.connect(lambda text: self.receive_binding("path", text.strip()))
        set_control_height(self._path_edit)
        form.addRow("Path", self._path_edit)

        self._key_edit = QLineEdit(str(self.inputs["key"]))
        self._key_edit.textChanged.connect(lambda text: self.receive_binding("key", text))
        set_control_height(self._key_edit)
        form.addRow("Key", self._key_edit)

        self._match_edit = QLineEdit(self._match_to_text(self.inputs["match"]))
        self._match_edit.textChanged.connect(
            lambda text: self.receive_binding("match", self._match_from_text(text))
        )
        set_control_height(self._match_edit)
        form.addRow("Match", self._match_edit)

        self._auto_check = QCheckBox("Auto Transform")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda enabled: self.receive_binding("auto", enabled))
        form.addRow("", self._auto_check)

        self._strict_check = QCheckBox("Strict")
        self._strict_check.setChecked(bool(self.inputs["strict"]))
        self._strict_check.toggled.connect(lambda enabled: self.receive_binding("strict", enabled))
        form.addRow("", self._strict_check)

        emit_btn = QPushButton("Transform")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        form.addRow("", emit_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(json_payload={}, transformed=0, error=self._mode_warning, reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "mode":
            mode, warning = self._normalize_mode(value)
            self.inputs["mode"] = mode
            self._mode_warning = warning
            if self._mode_combo is not None and self._mode_combo.currentText() != mode:
                self._mode_combo.blockSignals(True)
                self._mode_combo.setCurrentText(mode)
                self._mode_combo.blockSignals(False)
            self._dispatch_after_config(reason="mode")
            return

        if port == "path":
            token = str(value).strip() or "$"
            self.inputs["path"] = token
            if self._path_edit is not None and self._path_edit.text() != token:
                self._path_edit.blockSignals(True)
                self._path_edit.setText(token)
                self._path_edit.blockSignals(False)
            self._dispatch_after_config(reason="path")
            return

        if port == "key":
            token = str(value)
            self.inputs["key"] = token
            if self._key_edit is not None and self._key_edit.text() != token:
                self._key_edit.blockSignals(True)
                self._key_edit.setText(token)
                self._key_edit.blockSignals(False)
            self._dispatch_after_config(reason="key")
            return

        if port == "match":
            self.inputs["match"] = deepcopy(value)
            if self._match_edit is not None:
                text = self._match_to_text(value)
                if self._match_edit.text() != text:
                    self._match_edit.blockSignals(True)
                    self._match_edit.setText(text)
                    self._match_edit.blockSignals(False)
            self._dispatch_after_config(reason="match")
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

        if port == "json":
            self._dispatch_after_config(reason="json")
            return

        if port == "emit" and is_truthy(value):
            self._transform(reason="emit", trigger_output=True)

    def replay_state(self) -> None:
        self._transform(reason="replay", trigger_output=False)

    def _dispatch_after_config(self, *, reason: str) -> None:
        if bool(self.inputs["auto"]):
            self._transform(reason=reason, trigger_output=True)
            return
        self._publish(
            json_payload=self.outputs.get("json", {}),
            transformed=0,
            error=self._mode_warning,
            reason=f"{reason} cached",
        )

    def _transform(self, *, reason: str, trigger_output: bool) -> None:
        mode, warning = self._normalize_mode(self.inputs["mode"])
        self.inputs["mode"] = mode
        self._mode_warning = warning
        if self._mode_combo is not None and self._mode_combo.currentText() != mode:
            self._mode_combo.blockSignals(True)
            self._mode_combo.setCurrentText(mode)
            self._mode_combo.blockSignals(False)

        payload = self.inputs.get("json", {})
        strict = bool(self.inputs["strict"])

        try:
            source = self._resolve_path(payload, self._parse_path(str(self.inputs["path"])))
            transformed_payload = self._apply_mode(
                mode=mode,
                source=source,
                key=str(self.inputs["key"]),
                match=self.inputs["match"],
                strict=strict,
            )
            error = warning
            self._publish(
                json_payload=transformed_payload,
                transformed=1 if trigger_output else 0,
                error=error,
                reason=reason,
            )
        except ValueError as exc:
            error = str(exc)
            if warning:
                error = f"{warning}; {error}"
            self._publish(json_payload={}, transformed=0, error=error, reason=f"{reason}: error")

    def _apply_mode(
        self,
        *,
        mode: str,
        source: Any,
        key: str,
        match: Any,
        strict: bool,
    ) -> dict[str, Any] | list[Any]:
        if mode == "identity":
            return self._json_payload(source)

        if mode == "flatten":
            if isinstance(source, list):
                return self._flatten_list(source)
            if isinstance(source, dict):
                return [{"key": name, "value": deepcopy(value)} for name, value in source.items()]
            if strict:
                raise ValueError("flatten mode requires list or object source")
            return [deepcopy(source)]

        if mode == "pluck":
            if not key:
                raise ValueError("pluck mode requires non-empty key")
            if isinstance(source, list):
                items: list[Any] = []
                for index, item in enumerate(source):
                    if not isinstance(item, dict):
                        if strict:
                            raise ValueError(f"pluck mode expected object at index {index}")
                        continue
                    if key in item:
                        items.append(deepcopy(item[key]))
                    elif strict:
                        raise ValueError(f"pluck mode missing key '{key}' at index {index}")
                return items
            if isinstance(source, dict):
                if key in source:
                    return {"value": deepcopy(source[key])}
                if strict:
                    raise ValueError(f"pluck mode missing key '{key}'")
                return {}
            if strict:
                raise ValueError("pluck mode requires list or object source")
            return []

        if mode == "filter_eq":
            if not key:
                raise ValueError("filter_eq mode requires non-empty key")
            if isinstance(source, list):
                rows: list[Any] = []
                for index, item in enumerate(source):
                    if not isinstance(item, dict):
                        if strict:
                            raise ValueError(f"filter_eq mode expected object at index {index}")
                        continue
                    if item.get(key) == match:
                        rows.append(deepcopy(item))
                return rows
            if isinstance(source, dict):
                if key not in source and strict:
                    raise ValueError(f"filter_eq mode missing key '{key}'")
                return deepcopy(source) if source.get(key) == match else {}
            if strict:
                raise ValueError("filter_eq mode requires list or object source")
            return {}

        raise ValueError(f"unsupported mode '{mode}'")

    @staticmethod
    def _json_payload(value: Any) -> dict[str, Any] | list[Any]:
        if isinstance(value, (dict, list)):
            return deepcopy(value)
        return {"value": deepcopy(value)}

    @staticmethod
    def _flatten_list(values: list[Any]) -> list[Any]:
        out: list[Any] = []
        stack: list[Any] = [deepcopy(values)]
        while stack:
            item = stack.pop(0)
            if isinstance(item, list):
                if item:
                    stack = list(item) + stack
                continue
            out.append(item)
        return out

    @staticmethod
    def _normalize_mode(value: Any) -> tuple[str, str]:
        token = str(value).strip().lower()
        if token in _MODES:
            return token, ""
        return "identity", f"invalid mode '{value}'; using 'identity'"

    @staticmethod
    def _parse_path(path: str) -> list[str | int]:
        token = path.strip() or "$"
        if token == "$":
            return []
        if not token.startswith("$"):
            raise ValueError(f"path must start with '$': {path}")

        out: list[str | int] = []
        index = 1
        while index < len(token):
            current = token[index]
            if current == ".":
                index += 1
                start = index
                while index < len(token) and (token[index].isalnum() or token[index] == "_"):
                    index += 1
                name = token[start:index]
                if not name:
                    raise ValueError(f"invalid path token in '{path}'")
                out.append(name)
                continue

            if current == "[":
                index += 1
                start = index
                while index < len(token) and token[index].isdigit():
                    index += 1
                if index >= len(token) or token[index] != "]" or start == index:
                    raise ValueError(f"invalid index token in '{path}'")
                out.append(int(token[start:index]))
                index += 1
                continue

            raise ValueError(f"unsupported path syntax in '{path}'")

        return out

    @staticmethod
    def _resolve_path(payload: Any, tokens: list[str | int]) -> Any:
        current = payload
        for token in tokens:
            if isinstance(token, str):
                if not isinstance(current, dict):
                    raise ValueError("path traversal expected object")
                if token not in current:
                    raise ValueError(f"path key not found: '{token}'")
                current = current[token]
                continue

            if not isinstance(current, list):
                raise ValueError("path traversal expected list")
            if token < 0 or token >= len(current):
                raise ValueError(f"path index out of range: {token}")
            current = current[token]
        return current

    @staticmethod
    def _match_to_text(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)

    @staticmethod
    def _match_from_text(text: str) -> Any:
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

    def _publish(
        self,
        *,
        json_payload: dict[str, Any] | list[Any] | Any,
        transformed: int,
        error: str,
        reason: str,
    ) -> None:
        payload = self._json_payload(json_payload)
        count = len(payload) if isinstance(payload, (dict, list)) else 0
        self.emit("json", payload)
        self.emit("count", count)
        self.emit("transformed", 1 if transformed else 0)
        self.emit("error", error)
        text = (
            f"mode={self.inputs['mode']}, path={self.inputs['path']}, "
            f"count={count}, reason={reason}"
        )
        self.emit("text", text if not error else f"error: {error}")
        if self._status is not None:
            self._status.setText(text if not error else f"error: {error}")
