"""Option list source with dynamic select ports."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import ModuleBase, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height, set_expand
from qt_modula.ui.advanced_section import AdvancedSection


class OptionsModule(ModuleBase):
    """Manage selectable options and dynamic trigger ports."""

    _DYNAMIC_PORT_PREFIX = "select_"
    _MAX_SLUG_LEN = 24

    persistent_inputs = ("entry", "options", "selected", "auto", "value")

    descriptor = ModuleDescriptor(
        module_type="options",
        display_name="Options",
        family="Control",
        description="Selectable option source with dynamic trigger inputs.",
        capabilities=("source", "scheduler"),
        inputs=(
            PortSpec("entry", "string", default=""),
            PortSpec("add", "trigger", default=0, control_plane=True),
            PortSpec(
                "options",
                "json",
                default=[],
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec("selected", "string", default=""),
            PortSpec(
                "auto",
                "boolean",
                default=True,
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec(
                "value",
                "string",
                default="",
                bind_visibility="advanced",
                ui_group="advanced",
            ),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("selected", "string", default=""),
            PortSpec("options", "json", default=[]),
            PortSpec("in_list", "boolean", default=False),
            PortSpec("changed", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._entry_edit: QLineEdit | None = None
        self._auto_check: QCheckBox | None = None
        self._value_edit: QLineEdit | None = None
        self._combo: QComboBox | None = None
        self._status: QLabel | None = None
        self._option_binding_map: dict[str, str] = {}

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        entry_row = QHBoxLayout()
        self._entry_edit = QLineEdit()
        self._entry_edit.setPlaceholderText("Option text")
        self._entry_edit.setText(str(self.inputs["entry"]))
        self._entry_edit.textChanged.connect(lambda text: self.receive_binding("entry", text))
        self._entry_edit.returnPressed.connect(lambda: self.receive_binding("add", 1))
        set_expand(self._entry_edit)
        set_control_height(self._entry_edit)
        entry_row.addWidget(self._entry_edit)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(lambda: self.receive_binding("add", 1))
        set_control_height(add_btn)
        entry_row.addWidget(add_btn)
        layout.addLayout(entry_row)

        self._combo = QComboBox()
        self._combo.currentTextChanged.connect(lambda text: self.receive_binding("selected", text))
        self._combo.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._combo.customContextMenuRequested.connect(self._show_combo_context_menu)
        set_control_height(self._combo)
        layout.addWidget(self._combo)

        emit_btn = QPushButton("Emit")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        layout.addWidget(emit_btn)

        advanced = AdvancedSection("Advanced", expanded=False)
        self._auto_check = QCheckBox("Auto Emit")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(lambda checked: self.receive_binding("auto", checked))
        advanced.content_layout.addWidget(self._auto_check)

        self._value_edit = QLineEdit(str(self.inputs["value"]))
        self._value_edit.setPlaceholderText("Membership check value")
        self._value_edit.textChanged.connect(lambda text: self.receive_binding("value", text))
        set_control_height(self._value_edit)
        advanced.content_layout.addWidget(self._value_edit)

        layout.addWidget(advanced)

        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._publish(trigger=False, reason="ready", error_message="")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "entry":
            entry = str(value)
            self.inputs["entry"] = entry
            if self._entry_edit is not None and self._entry_edit.text() != entry:
                self._entry_edit.blockSignals(True)
                self._entry_edit.setText(entry)
                self._entry_edit.blockSignals(False)
            self.emit("error", "")
            return

        if port == "add" and is_truthy(value):
            self._add_entry()
            return

        if port == "options":
            if not isinstance(value, list):
                self._set_input_value("options", self._current_options())
                self._publish(
                    trigger=False,
                    error_message="options must be a JSON list",
                    reason="options",
                )
                return
            self._publish(trigger=True, error_message="", reason="options")
            return

        if port == "selected":
            self._select_option(value, trigger=bool(self.inputs["auto"]), reason="selected")
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            self._publish(trigger=False, error_message="", reason="auto")
            return

        if port == "value":
            text = str(value)
            self.inputs["value"] = text
            if self._value_edit is not None and self._value_edit.text() != text:
                self._value_edit.blockSignals(True)
                self._value_edit.setText(text)
                self._value_edit.blockSignals(False)
            self._publish(trigger=True, error_message="", reason="value")
            return

        if port == "emit" and is_truthy(value):
            self._publish(trigger=True, error_message="", reason="emit")
            return

        selected_option = self._option_binding_map.get(port)
        if selected_option is not None and is_truthy(value):
            self._select_option(selected_option, trigger=bool(self.inputs["auto"]), reason=port)

    def replay_state(self) -> None:
        self._publish(trigger=False, error_message="", reason="replay")

    def _add_entry(self) -> None:
        option = self._normalize_option(self.inputs["entry"])
        if not option:
            self._publish(trigger=False, error_message="entry must be non-empty", reason="add")
            return

        options = self._current_options()
        if option in options:
            self._set_input_value("selected", option)
            self._sync_combo(options, option)
            self._publish(
                trigger=False,
                error_message=f"option '{option}' already exists",
                reason="add",
            )
            return

        options.append(option)
        options.sort(key=str.casefold)
        self._set_input_value("options", options)
        self._set_input_value("selected", option)
        self._set_input_value("entry", "")

        if self._entry_edit is not None and self._entry_edit.text():
            self._entry_edit.blockSignals(True)
            self._entry_edit.clear()
            self._entry_edit.blockSignals(False)

        self._sync_combo(options, option)
        self._publish(trigger=bool(self.inputs["auto"]), error_message="", reason="add")

    def _remove_option(self, option: str) -> None:
        target = self._normalize_option(option)
        if not target:
            return

        options = [item for item in self._current_options() if item != target]
        self._set_input_value("options", options)

        if not options:
            self._set_input_value("selected", "")
        elif self.inputs["selected"] == target:
            self._set_input_value("selected", options[0])

        self._publish(trigger=bool(self.inputs["auto"]), error_message="", reason="delete")

    def _show_combo_context_menu(self, position: QPoint) -> None:
        if self._combo is None:
            return

        option = self._normalize_option(self._combo.currentText())
        if not option or option not in self._current_options():
            return

        menu = QMenu(self._combo)
        delete_action = menu.addAction(f'Delete "{option}"')
        if delete_action is None:
            return
        chosen = menu.exec(self._combo.mapToGlobal(position))
        if chosen is delete_action:
            self._remove_option(option)

    def _select_option(self, value: Any, *, trigger: bool, reason: str) -> None:
        options = self._current_options()
        if not options:
            self._set_input_value("selected", "")
            self._sync_combo(options, "")
            self._publish(
                trigger=False,
                error_message="cannot select option; list is empty",
                reason=reason,
            )
            return

        option = self._normalize_option(value)
        if not option:
            selected = options[0]
            self._set_input_value("selected", selected)
            self._sync_combo(options, selected)
            self._publish(trigger=trigger, error_message="", reason=reason)
            return

        if option not in options:
            fallback = options[0]
            self._set_input_value("selected", fallback)
            self._sync_combo(options, fallback)
            self._publish(trigger=False, error_message=f"unknown option '{value}'", reason=reason)
            return

        self._set_input_value("selected", option)
        self._sync_combo(options, option)
        self._publish(trigger=trigger, error_message="", reason=reason)

    def _publish(self, *, trigger: bool, error_message: str, reason: str) -> None:
        options, options_warning = self._normalize_options(self.inputs["options"])
        self._set_input_value("options", options)
        self._sync_dynamic_input_ports(options)

        selected, selected_warning = self._resolve_selected(self.inputs["selected"], options)
        self._set_input_value("selected", selected)
        self._sync_combo(options, selected)

        candidate = self._normalize_option(self.inputs["value"])
        in_list = candidate in options if candidate else False

        warning = "; ".join(
            message
            for message in (options_warning, selected_warning, error_message)
            if message
        )

        self.emit("selected", selected)
        self.emit("options", options)
        self.emit("in_list", in_list)
        self.emit("changed", 1 if trigger else 0)
        self.emit("error", warning)

        text = (
            f"selected={selected!r}, options={len(options)}, "
            f"in_list={int(in_list)}, reason={reason}"
        )
        status = text if not warning else f"{text}; warning={warning}"
        self.emit("text", status)
        if self._status is not None:
            self._status.setText(status)

    def _current_options(self) -> list[str]:
        raw = self.inputs.get("options", [])
        options, _warning = self._normalize_options(raw)
        return options

    def _sync_dynamic_input_ports(self, options: list[str]) -> None:
        port_map = self._build_option_port_map(options)
        dynamic_specs = tuple(
            PortSpec(
                key=port_key,
                kind="trigger",
                default=0,
                control_plane=True,
                description=f"Select option '{option}' when triggered.",
                bind_visibility="advanced",
                ui_group="advanced",
            )
            for port_key, option in port_map.items()
        )

        static_specs = tuple(
            spec
            for spec in self.descriptor.inputs
            if not spec.key.startswith(self._DYNAMIC_PORT_PREFIX)
        )

        next_inputs = static_specs + dynamic_specs
        current_keys = tuple(spec.key for spec in self.descriptor.inputs)
        next_keys = tuple(spec.key for spec in next_inputs)

        self._option_binding_map = port_map
        if current_keys == next_keys:
            return

        self._set_descriptor_inputs(next_inputs)

    @staticmethod
    def _normalize_option(value: Any) -> str:
        return str(value).strip()

    @classmethod
    def port_key_for_option(cls, options: list[str], option: str) -> str:
        normalized_options, _warning = cls._normalize_options(options)
        normalized_option = cls._normalize_option(option)
        port_map = cls._build_option_port_map(normalized_options)
        for port_key, option_value in port_map.items():
            if option_value == normalized_option:
                return port_key
        raise KeyError(f"Unknown option '{option}'.")

    @classmethod
    def _normalize_options(cls, value: Any) -> tuple[list[str], str]:
        if not isinstance(value, list):
            return [], "options must be a JSON list"

        options: list[str] = []
        seen: set[str] = set()
        dropped_empty = 0
        dropped_duplicate = 0

        for raw_option in value:
            option = cls._normalize_option(raw_option)
            if not option:
                dropped_empty += 1
                continue
            if option in seen:
                dropped_duplicate += 1
                continue
            seen.add(option)
            options.append(option)

        options.sort(key=str.casefold)

        warnings: list[str] = []
        if dropped_empty:
            warnings.append(f"ignored {dropped_empty} empty options")
        if dropped_duplicate:
            warnings.append(f"ignored {dropped_duplicate} duplicate options")

        return options, "; ".join(warnings)

    @classmethod
    def _build_option_port_map(cls, options: list[str]) -> dict[str, str]:
        slug_counts: dict[str, int] = {}
        for option in options:
            slug = cls._option_slug(option)
            slug_counts[slug] = slug_counts.get(slug, 0) + 1

        port_map: dict[str, str] = {}
        for option in options:
            slug = cls._option_slug(option)
            if slug_counts[slug] <= 1:
                port_key = f"{cls._DYNAMIC_PORT_PREFIX}{slug}"
            else:
                digest = hashlib.sha1(option.encode("utf-8")).hexdigest()[:8]
                port_key = f"{cls._DYNAMIC_PORT_PREFIX}{slug}_{digest}"

            if port_key in port_map:
                index = 2
                candidate = f"{port_key}_{index}"
                while candidate in port_map:
                    index += 1
                    candidate = f"{port_key}_{index}"
                port_key = candidate

            port_map[port_key] = option

        return port_map

    @classmethod
    def _option_slug(cls, option: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", option.casefold()).strip("_")
        if not slug:
            slug = "item"
        return slug[: cls._MAX_SLUG_LEN]

    @classmethod
    def _resolve_selected(cls, value: Any, options: list[str]) -> tuple[str, str]:
        if not options:
            return "", ""

        selected = cls._normalize_option(value)
        if not selected:
            return options[0], ""
        if selected in options:
            return selected, ""

        fallback = options[0]
        return fallback, f"unknown selected option '{value}'; using '{fallback}'"

    def _sync_combo(self, options: list[str], selected: str) -> None:
        if self._combo is None:
            return

        self._combo.blockSignals(True)
        existing = [self._combo.itemText(index) for index in range(self._combo.count())]
        if existing != options:
            self._combo.clear()
            self._combo.addItems(options)

        if not options:
            self._combo.setCurrentIndex(-1)
        elif selected in options and self._combo.currentText() != selected:
            self._combo.setCurrentText(selected)
        elif selected not in options:
            self._combo.setCurrentIndex(0)
        self._combo.blockSignals(False)
