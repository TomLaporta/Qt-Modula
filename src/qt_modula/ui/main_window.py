"""Main desktop shell for Qt Modula."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qt_modula.modules_builtin import build_registry
from qt_modula.paths import modules_root
from qt_modula.persistence import (
    AppConfig,
    AutosnapshotManager,
    BindingSnapshot,
    CanvasSnapshot,
    CustomThemePolicy,
    ModuleSnapshot,
    PersistenceError,
    Project,
    ProviderNetworkPolicy,
    RuntimePolicyModel,
    load_project,
    save_project,
)
from qt_modula.runtime import RuntimeEngine
from qt_modula.sdk import BindingEdge, ModuleLifecycle, PortSpec, RuntimePolicy
from qt_modula.services import configure_from_app_config
from qt_modula.ui.module_card import ModuleCard
from qt_modula.ui.settings_dialog import SettingsDialog
from qt_modula.ui.sizing import em
from qt_modula.ui.theme import Theme, app_stylesheet

_MODULE_TYPE_DISPLAY_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_MAX_MODULE_NAME_LEN = 32


@dataclass(slots=True)
class _ModuleRef:
    module_id: str
    module_type: str
    module_name: str
    module_type_display: str
    canvas_id: str
    module: ModuleLifecycle


@dataclass(slots=True)
class _StagedModule:
    ref: _ModuleRef
    widget: QWidget


@dataclass(slots=True)
class _StagedCanvas:
    canvas_id: str
    name: str
    modules: list[_StagedModule]


@dataclass(slots=True)
class _StagedProject:
    runtime: RuntimeEngine
    runtime_policy: RuntimePolicyModel
    canvases: list[_StagedCanvas]
    module_counter: int
    canvas_counter: int


class _CanvasWidget(QWidget):
    """Vertical card host for one canvas."""

    order_changed = Signal(str)

    def __init__(self, *, canvas_id: str) -> None:
        super().__init__()
        self._canvas_id = canvas_id
        self.setProperty("canvas_id", canvas_id)
        self._dragged_module_id: str | None = None
        self._drag_pointer_global: QPoint | None = None

        self._drag_scroll_timer = QTimer(self)
        self._drag_scroll_timer.setInterval(24)
        self._drag_scroll_timer.timeout.connect(self._on_drag_scroll_tick)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(em(0.4), em(0.4), em(0.4), em(0.4))
        layout.setSpacing(em(0.4))
        layout.addStretch(1)

    def _layout(self) -> QVBoxLayout | None:
        layout = self.layout()
        if isinstance(layout, QVBoxLayout):
            return layout
        return None

    def _card_widgets(self) -> list[ModuleCard]:
        layout = self._layout()
        if layout is None:
            return []

        cards: list[ModuleCard] = []
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, ModuleCard):
                cards.append(widget)
        return cards

    def module_ids_in_order(self) -> list[str]:
        return [card.module_id for card in self._card_widgets()]

    def _drop_index(self, y: int, *, exclude_card: ModuleCard | None = None) -> int:
        index = 0
        for card in self._card_widgets():
            if card is exclude_card:
                continue
            midpoint = card.y() + (card.height() // 2)
            if y < midpoint:
                return index
            index += 1
        return index

    def _scroll_area(self) -> QScrollArea | None:
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parentWidget()
        return None

    def _auto_scroll_for_pointer(self, global_pos: QPoint) -> bool:
        scroll_area = self._scroll_area()
        if scroll_area is None:
            return False

        viewport = scroll_area.viewport()
        viewport_y = viewport.mapFromGlobal(global_pos).y()
        margin = max(em(1.3), 24)
        max_y = viewport.height() - margin

        delta = 0
        if viewport_y < margin:
            delta = viewport_y - margin
        elif viewport_y > max_y:
            delta = viewport_y - max_y

        if delta == 0:
            return False

        step = max(1, (abs(delta) // 10) + 1)
        direction = -1 if delta < 0 else 1
        bar = scroll_area.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + (direction * step))
        return bar.value() != before

    def _dragged_card(self) -> ModuleCard | None:
        module_id = self._dragged_module_id
        if module_id is None:
            return None
        return next((card for card in self._card_widgets() if card.module_id == module_id), None)

    def _reorder_dragged_card(self, global_pos: QPoint) -> None:
        module_id = self._dragged_module_id
        if module_id is None:
            return
        local_y = self.mapFromGlobal(global_pos).y()
        target_index = self._drop_index(local_y, exclude_card=self._dragged_card())
        self.move_card(module_id, target_index)

    def _on_drag_scroll_tick(self) -> None:
        pointer = self._drag_pointer_global
        if self._dragged_module_id is None or pointer is None:
            self._drag_scroll_timer.stop()
            return
        if self._auto_scroll_for_pointer(pointer):
            self._reorder_dragged_card(pointer)

    def _on_card_reorder_started(self, module_id: str, global_pos: QPoint) -> None:
        if module_id not in self.module_ids_in_order():
            return
        self._dragged_module_id = module_id
        self._drag_pointer_global = QPoint(global_pos)
        self._reorder_dragged_card(global_pos)
        self._drag_scroll_timer.start()

    def _on_card_reorder_moved(self, module_id: str, global_pos: QPoint) -> None:
        if self._dragged_module_id != module_id:
            return
        self._drag_pointer_global = QPoint(global_pos)
        self._auto_scroll_for_pointer(global_pos)
        self._reorder_dragged_card(global_pos)

    def _on_card_reorder_finished(self, module_id: str) -> None:
        if self._dragged_module_id == module_id:
            self._dragged_module_id = None
            self._drag_pointer_global = None
            self._drag_scroll_timer.stop()

    def move_card(self, module_id: str, target_index: int) -> bool:
        cards = self._card_widgets()
        source_index = -1
        for index, card in enumerate(cards):
            if card.module_id == module_id:
                source_index = index
                break
        if source_index < 0:
            return False

        max_index = len(cards) - 1
        clamped_target = max(0, min(target_index, max_index))
        if clamped_target == source_index:
            return False

        layout = self._layout()
        if layout is None:
            return False

        card = cards[source_index]
        layout.removeWidget(card)
        layout.insertWidget(clamped_target, card)
        self.order_changed.emit(self._canvas_id)
        return True

    def add_card(self, card: ModuleCard) -> None:
        layout = self._layout()
        if layout is None:
            return
        card.reorder_started.connect(self._on_card_reorder_started)
        card.reorder_moved.connect(self._on_card_reorder_moved)
        card.reorder_finished.connect(self._on_card_reorder_finished)
        layout.insertWidget(layout.count() - 1, card)

    def remove_card(self, module_id: str) -> None:
        layout = self._layout()
        if layout is None:
            return
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, ModuleCard) and widget.module_id == module_id:
                with suppress(Exception):
                    widget.reorder_started.disconnect(self._on_card_reorder_started)
                with suppress(Exception):
                    widget.reorder_moved.disconnect(self._on_card_reorder_moved)
                with suppress(Exception):
                    widget.reorder_finished.disconnect(self._on_card_reorder_finished)
                layout.removeWidget(widget)
                widget.deleteLater()
                return


class _NoFocusRectItemDelegate(QStyledItemDelegate):
    """Delegate that suppresses Qt's inner focus rectangle for list items."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        patched = QStyleOptionViewItem(option)
        patched.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, patched, index)


class MainWindow(QMainWindow):
    """Cards + bind-panel workflow shell."""

    def __init__(
        self,
        app_config: AppConfig,
        on_app_config_saved: Callable[[AppConfig], None] | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Qt Modula")

        self._on_app_config_saved = on_app_config_saved
        self._app_config = app_config.model_copy(deep=True)
        self._active_runtime_policy = self._app_config.runtime.model_copy(deep=True)
        configure_from_app_config(self._app_config)

        plugin_root = modules_root()
        self._registry, self._plugin_issues = build_registry(plugin_root=plugin_root)

        self._runtime = self._build_runtime(self._active_runtime_policy)
        self._module_counter = 0
        self._canvas_counter = 0
        self._modules: dict[str, _ModuleRef] = {}
        self._current_project_id = "workspace"

        self._tabs = QTabWidget()
        self._tabs.setMovable(True)
        self._tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tabs.tabBar().customContextMenuRequested.connect(self._on_canvas_tab_context_menu)

        self._canvases: dict[str, _CanvasWidget] = {}
        self._canvas_tabs: dict[str, QScrollArea] = {}

        self._module_list = QListWidget()
        self._module_list.setItemDelegate(_NoFocusRectItemDelegate(self._module_list))
        self._module_list.currentItemChanged.connect(self._on_module_palette_changed)
        self._module_search_input = QLineEdit()
        self._module_search_input.setPlaceholderText("Search family or module name")
        self._module_search_input.textChanged.connect(self._on_module_palette_search_changed)
        self._module_name_input = QLineEdit()
        self._module_name_input.setMaxLength(_MAX_MODULE_NAME_LEN)

        self._source_module = QComboBox()
        self._source_port = QComboBox()
        self._target_module = QComboBox()
        self._target_port = QComboBox()
        self._show_advanced_ports = QCheckBox("Show Advanced Ports")
        self._binding_diagnostics = QListWidget()
        self._bindings_view = QListWidget()

        root = QSplitter(Qt.Orientation.Horizontal)
        self._palette_panel = self._build_palette_panel()
        self._canvas_panel = self._build_canvas_panel()
        self._bind_panel = self._build_bind_panel()

        root.addWidget(self._palette_panel)
        root.addWidget(self._canvas_panel)
        root.addWidget(self._bind_panel)
        root.setHandleWidth(em(0.55))
        root.setStretchFactor(1, 1)
        self.setCentralWidget(root)

        self._wire_runtime_hooks(self._runtime)

        self._autosnapshot = self._create_autosnapshot_manager(self._app_config)

        self._populate_palette()
        self._create_tab("Canvas 1")
        self._apply_theme_config(self._app_config.ui.theme)

        self.resize(em(96), em(58))
        self._maybe_prompt_snapshot_recovery()

    @staticmethod
    def _build_runtime(policy: RuntimePolicyModel) -> RuntimeEngine:
        runtime_policy = RuntimePolicy(
            max_queue_size=policy.max_queue_size,
            coalesce_pending_inputs=policy.coalesce_pending_inputs,
            max_deliveries_per_batch=policy.max_deliveries_per_batch,
        )
        return RuntimeEngine(runtime_policy)

    def _wire_runtime_hooks(self, runtime: RuntimeEngine) -> None:
        runtime.add_module_contract_listener(self._on_runtime_module_contract_changed)
        runtime.add_persistent_input_listener(self._on_runtime_persistent_input_changed)

    def _autosnapshot_root_path(self, config: AppConfig | None = None) -> Path:
        source = self._app_config if config is None else config
        return source.paths.resolved_autosnapshot_directory()

    def _project_root_path(self, config: AppConfig | None = None) -> Path:
        source = self._app_config if config is None else config
        return source.paths.resolved_project_directory()

    def _create_autosnapshot_manager(self, config: AppConfig) -> AutosnapshotManager:
        manager = AutosnapshotManager(
            root=self._autosnapshot_root_path(config),
            policy=config.autosnapshot.model_copy(deep=True),
            snapshot_factory=self._snapshot_project,
        )
        manager.set_project_id(self._current_project_id)
        return manager

    def _on_runtime_module_contract_changed(self, module_id: str) -> None:
        if module_id not in self._modules:
            return

        if self._source_module.currentData() == module_id:
            self._refresh_source_ports()
        if self._target_module.currentData() == module_id:
            self._refresh_target_ports()

        self._refresh_bindings_view()
        self._binding_diagnostics.clear()
        self._mark_project_dirty()

    def _on_runtime_persistent_input_changed(
        self,
        module_id: str,
        key: str,
        _value: object,
    ) -> None:
        if module_id not in self._modules:
            return
        _ = key
        self._mark_project_dirty()

    def _mark_project_dirty(self) -> None:
        self._autosnapshot.set_project_id(self._current_project_id)
        if not self._modules:
            self._autosnapshot.clear_project_snapshots(self._current_project_id)
            return
        self._autosnapshot.mark_dirty()

    def _maybe_prompt_snapshot_recovery(self) -> None:
        if os.getenv("QT_QPA_PLATFORM", "").strip().lower() == "offscreen":
            return

        if not self._autosnapshot.has_unsaved_snapshot(self._current_project_id):
            return

        latest = self._autosnapshot.latest_snapshot_path(self._current_project_id)
        if latest is None:
            return

        answer = QMessageBox.question(
            self,
            "Recover Autosnapshot",
            f"Unsaved autosnapshot found:\n{latest}\n\nRecover it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._autosnapshot.clear_project_snapshots(self._current_project_id)
            return

        try:
            project = self._autosnapshot.load_latest_snapshot(self._current_project_id)
            if project is None:
                return
            self._apply_project(project)
        except Exception as exc:
            QMessageBox.warning(self, "Recover Autosnapshot", str(exc))

    def _apply_theme_config(self, theme_name: str) -> None:
        token = theme_name.strip().lower()
        if token == "light":
            theme = Theme(
                primary_color="#f8f8f8",
                secondary_color="#202020",
                highlight_color="#2b7cd3",
                canvas_color="#ffffff",
            )
        elif token == "high_contrast":
            theme = Theme(
                primary_color="#111111",
                secondary_color="#ffffff",
                highlight_color="#12d9a5",
                canvas_color="#000000",
            )
        else:
            custom: CustomThemePolicy = self._app_config.ui.custom_theme
            theme = Theme(
                primary_color=custom.primary_color,
                secondary_color=custom.secondary_color,
                highlight_color=custom.highlight_color,
                canvas_color=custom.canvas_color,
            )
        self.setStyleSheet(app_stylesheet(theme))

    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(self._app_config, parent=self)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return

        selected = dialog.selected_config()
        if selected is None:
            return

        self._apply_settings_config(selected)

    def _apply_settings_config(self, config: AppConfig) -> None:
        previous_config = self._app_config.model_copy(deep=True)
        previous_network = previous_config.provider_network.model_copy(deep=True)
        previous_runtime_policy = self._active_runtime_policy.model_copy(deep=True)

        try:
            if self._on_app_config_saved is not None:
                self._on_app_config_saved(config)

            self._app_config = config.model_copy(deep=True)
            configure_from_app_config(self._app_config)
            self._apply_theme_config(self._app_config.ui.theme)
            self._reconfigure_autosnapshot(self._app_config)
            self._rebuild_runtime_with_policy(self._app_config.runtime)
            self._apply_http_defaults_to_existing_modules(
                previous_defaults=previous_network,
                next_defaults=self._app_config.provider_network,
            )
            self._mark_project_dirty()
        except Exception as exc:
            self._app_config = previous_config
            configure_from_app_config(self._app_config)
            self._apply_theme_config(self._app_config.ui.theme)
            self._reconfigure_autosnapshot(self._app_config)
            self._rebuild_runtime_with_policy(previous_runtime_policy)
            QMessageBox.critical(self, "Settings", str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        with suppress(Exception):
            self._autosnapshot.flush()
        with suppress(Exception):
            self._reset_workspace()
        super().closeEvent(event)

    def _reconfigure_autosnapshot(self, config: AppConfig) -> None:
        self._autosnapshot = self._create_autosnapshot_manager(config)

    def _rebuild_runtime_with_policy(self, policy: RuntimePolicyModel) -> None:
        previous_edges = self._runtime.list_bindings()
        runtime = self._build_runtime(policy)
        for module_id in self._module_ids_in_ui_order():
            module_ref = self._modules.get(module_id)
            if module_ref is None:
                continue
            runtime.register_module(module_ref.module)

        for edge in previous_edges:
            runtime.add_binding(
                edge.src_module_id,
                edge.src_port,
                edge.dst_module_id,
                edge.dst_port,
            )

        self._active_runtime_policy = policy.model_copy(deep=True)
        self._runtime = runtime
        self._wire_runtime_hooks(self._runtime)
        self._refresh_canvas_references()

    def _apply_http_defaults_to_existing_modules(
        self,
        *,
        previous_defaults: ProviderNetworkPolicy,
        next_defaults: ProviderNetworkPolicy,
    ) -> None:
        prev_timeout = float(previous_defaults.http.timeout_s)
        prev_retries = int(previous_defaults.http.retries)
        next_timeout = float(next_defaults.http.timeout_s)
        next_retries = int(next_defaults.http.retries)

        for module_ref in self._modules.values():
            if module_ref.module_type != "http_request":
                continue

            module = module_ref.module
            inputs = getattr(module, "inputs", None)
            if not isinstance(inputs, dict):
                continue

            current_timeout = inputs.get("timeout_s")
            current_retries = inputs.get("retries")

            timeout_value = (
                float(current_timeout)
                if isinstance(current_timeout, (int, float))
                else None
            )
            retries_value = (
                int(current_retries)
                if isinstance(current_retries, int) and not isinstance(current_retries, bool)
                else None
            )

            if timeout_value is not None and abs(timeout_value - prev_timeout) < 1e-9:
                module.receive_binding("timeout_s", next_timeout)
            if retries_value is not None and retries_value == prev_retries:
                module.receive_binding("retries", next_retries)

    def _build_palette_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._on_open_settings)
        layout.addWidget(settings_btn)

        layout.addWidget(QLabel("Module Palette"))
        layout.addWidget(self._module_search_input)
        layout.addWidget(self._module_list)

        layout.addWidget(QLabel("Module Name"))
        self._module_name_input.setPlaceholderText("Required")
        layout.addWidget(self._module_name_input)

        add_btn = QPushButton("Add Module")
        add_btn.clicked.connect(self._on_add_module)
        layout.addWidget(add_btn)

        canvas_btn = QPushButton("New Canvas")
        canvas_btn.clicked.connect(lambda: self._create_tab(f"Canvas {self._tabs.count() + 1}"))
        layout.addWidget(canvas_btn)

        save_btn = QPushButton("Save Project")
        save_btn.clicked.connect(self._on_save_project)
        layout.addWidget(save_btn)

        load_btn = QPushButton("Load Project")
        load_btn.clicked.connect(self._on_load_project)
        layout.addWidget(load_btn)

        reset_btn = QPushButton("Reset Workspace")
        reset_btn.clicked.connect(self._on_reset_workspace_requested)
        layout.addWidget(reset_btn)

        layout.addStretch(1)
        return panel

    def _build_canvas_panel(self) -> QWidget:
        panel = QWidget()
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        inset = em(0.25)
        layout.setContentsMargins(inset, inset, inset, inset)
        layout.setSpacing(0)
        layout.addWidget(self._tabs)
        return panel

    def _build_bind_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("Bind Chains"))

        layout.addWidget(QLabel("Source Module"))
        self._source_module.currentIndexChanged.connect(self._on_source_module_changed)
        layout.addWidget(self._source_module)

        layout.addWidget(QLabel("Source Port"))
        layout.addWidget(self._source_port)

        layout.addWidget(QLabel("Destination Module"))
        self._target_module.currentIndexChanged.connect(self._on_target_module_changed)
        layout.addWidget(self._target_module)

        layout.addWidget(QLabel("Destination Port"))
        layout.addWidget(self._target_port)

        self._show_advanced_ports.toggled.connect(self._on_show_advanced_ports_changed)
        layout.addWidget(self._show_advanced_ports)

        inspect_btn = QPushButton("Inspect Candidate")
        inspect_btn.clicked.connect(self._inspect_candidate_binding)
        layout.addWidget(inspect_btn)

        bind_btn = QPushButton("Create Binding")
        bind_btn.clicked.connect(self._on_bind)
        layout.addWidget(bind_btn)

        layout.addWidget(QLabel("Diagnostics"))
        layout.addWidget(self._binding_diagnostics)

        layout.addWidget(QLabel("Active Bindings"))
        layout.addWidget(self._bindings_view)

        remove_btn = QPushButton("Remove Selected Binding")
        remove_btn.clicked.connect(self._on_remove_binding)
        layout.addWidget(remove_btn)

        layout.addStretch(1)
        return panel

    def _populate_palette(self) -> None:
        current_item = self._module_list.currentItem()
        selected_module_type = (
            current_item.data(Qt.ItemDataRole.UserRole) if current_item is not None else None
        )
        query = self._module_search_input.text().strip().casefold()

        self._module_list.clear()
        for descriptor in self._registry.descriptors():
            if query:
                family_match = query in descriptor.family.casefold()
                name_match = query in descriptor.display_name.casefold()
                if not (family_match or name_match):
                    continue
            label = f"{descriptor.family} / {descriptor.display_name}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, descriptor.module_type)
            item.setData(_MODULE_TYPE_DISPLAY_ROLE, descriptor.display_name)
            self._module_list.addItem(item)

        if self._module_list.count() > 0:
            if isinstance(selected_module_type, str):
                for row in range(self._module_list.count()):
                    item = self._module_list.item(row)
                    if item is None:
                        continue
                    if item.data(Qt.ItemDataRole.UserRole) == selected_module_type:
                        self._module_list.setCurrentRow(row)
                        break
                else:
                    self._module_list.setCurrentRow(0)
            else:
                self._module_list.setCurrentRow(0)
        self._refresh_module_name_input()

    def _on_module_palette_search_changed(self, _text: str) -> None:
        self._populate_palette()

    def _on_module_palette_changed(
        self,
        _current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        self._refresh_module_name_input()

    def _selected_palette_module(self) -> tuple[str, str] | None:
        item = self._module_list.currentItem()
        if item is None:
            return None

        module_type = item.data(Qt.ItemDataRole.UserRole)
        module_display = item.data(_MODULE_TYPE_DISPLAY_ROLE)
        if not isinstance(module_type, str) or not isinstance(module_display, str):
            return None
        return module_type, module_display

    def _module_name_is_taken(self, name: str, *, exclude_module_id: str | None = None) -> bool:
        token = name.casefold()
        for module_ref in self._modules.values():
            if exclude_module_id is not None and module_ref.module_id == exclude_module_id:
                continue
            if module_ref.module_name.casefold() == token:
                return True
        return False

    @staticmethod
    def _format_auto_module_name(base_name: str, index: int) -> str:
        suffix = "" if index == 1 else f" {index}"
        if len(suffix) >= _MAX_MODULE_NAME_LEN:
            return suffix[-_MAX_MODULE_NAME_LEN :].strip()

        max_base_len = _MAX_MODULE_NAME_LEN - len(suffix)
        compact_base = base_name[:max_base_len].rstrip()
        if not compact_base:
            compact_base = base_name[:max_base_len]
        return f"{compact_base}{suffix}"

    def _auto_module_name(self, module_type: str, module_display: str) -> str:
        same_type_count = sum(
            1 for module_ref in self._modules.values() if module_ref.module_type == module_type
        )
        index = same_type_count + 1
        while True:
            candidate = self._format_auto_module_name(module_display, index)
            if not self._module_name_is_taken(candidate):
                return candidate
            index += 1

    def _refresh_module_name_input(self) -> None:
        selected = self._selected_palette_module()
        if selected is None:
            self._module_name_input.clear()
            return
        module_type, module_display = selected
        self._module_name_input.setText(self._auto_module_name(module_type, module_display))

    def _next_canvas_id(self) -> str:
        while True:
            self._canvas_counter += 1
            candidate = f"c_{self._canvas_counter:04d}"
            if candidate not in self._canvases:
                return candidate

    def _bump_canvas_counter(self, canvas_id: str) -> None:
        if not canvas_id.startswith("c_"):
            return
        suffix = canvas_id.split("_", 1)[1]
        if suffix.isdigit():
            self._canvas_counter = max(self._canvas_counter, int(suffix))

    def _create_tab(self, name: str, *, canvas_id: str | None = None) -> str:
        if canvas_id is None:
            canvas_id = self._next_canvas_id()
        else:
            self._bump_canvas_counter(canvas_id)

        if canvas_id in self._canvases:
            raise RuntimeError(f"Duplicate canvas id '{canvas_id}'.")

        canvas = _CanvasWidget(canvas_id=canvas_id)
        canvas.order_changed.connect(self._on_canvas_cards_reordered)

        tab = QScrollArea()
        tab.setWidgetResizable(True)
        tab.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tab.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tab.setProperty("canvas_id", canvas_id)
        tab.setWidget(canvas)

        self._canvases[canvas_id] = canvas
        self._canvas_tabs[canvas_id] = tab
        self._tabs.addTab(tab, name)
        return canvas_id

    def _on_canvas_cards_reordered(self, _canvas_id: str) -> None:
        self._refresh_canvas_references()
        self._mark_project_dirty()

    def _on_canvas_tab_context_menu(self, pos: QPoint) -> None:
        tab_bar = self._tabs.tabBar()
        tab_index = tab_bar.tabAt(pos)
        if tab_index < 0:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Rename Canvas")
        delete_action = menu.addAction("Delete Canvas")
        chosen = menu.exec(tab_bar.mapToGlobal(pos))
        if chosen is rename_action:
            self._rename_canvas_at(tab_index)
        elif chosen is delete_action:
            self._delete_canvas_at(tab_index)

    def _canvas_id_at(self, tab_index: int) -> str | None:
        tab = self._tabs.widget(tab_index)
        if tab is None:
            return None
        canvas_id = tab.property("canvas_id")
        if not isinstance(canvas_id, str):
            return None
        return canvas_id

    def _rename_canvas_at(self, tab_index: int) -> None:
        if tab_index < 0 or tab_index >= self._tabs.count():
            return

        current_name = self._tabs.tabText(tab_index) or f"Canvas {tab_index + 1}"
        raw, accepted = QInputDialog.getText(
            self,
            "Rename Canvas",
            "Canvas name:",
            text=current_name,
        )
        if not accepted:
            return

        name = raw.strip()
        if not name:
            QMessageBox.warning(self, "Rename Canvas", "Canvas name cannot be empty.")
            return

        self._tabs.setTabText(tab_index, name)
        self._refresh_canvas_references()
        self._mark_project_dirty()

    def _delete_canvas_at(self, tab_index: int) -> None:
        if tab_index < 0 or tab_index >= self._tabs.count():
            return

        canvas_id = self._canvas_id_at(tab_index)
        if canvas_id is None:
            return

        canvas_name = self._tabs.tabText(tab_index) or canvas_id
        if self._app_config.safety_prompts.confirm_canvas_delete:
            answer = QMessageBox.question(
                self,
                "Delete Canvas",
                f"Delete canvas '{canvas_name}' and all modules/bind chains?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        module_ids = [
            module_ref.module_id
            for module_ref in self._modules.values()
            if module_ref.canvas_id == canvas_id
        ]
        for module_id in module_ids:
            self._remove_module(module_id, refresh_ui=False)

        tab = self._canvas_tabs.pop(canvas_id, None)
        self._canvases.pop(canvas_id, None)

        remove_index = self._tabs.indexOf(tab) if tab is not None else tab_index
        if 0 <= remove_index < self._tabs.count():
            removed = self._tabs.widget(remove_index)
            self._tabs.removeTab(remove_index)
            if removed is not None:
                removed.deleteLater()
        elif tab is not None:
            tab.deleteLater()

        if self._tabs.count() == 0:
            self._create_tab("Canvas 1")
            self._tabs.setCurrentIndex(0)

        self._refresh_canvas_references()
        self._refresh_module_name_input()
        self._mark_project_dirty()

    def _current_canvas(self) -> _CanvasWidget:
        widget = self._tabs.currentWidget()
        if isinstance(widget, QScrollArea):
            canvas = widget.widget()
            if isinstance(canvas, _CanvasWidget):
                return canvas
        raise RuntimeError("Current tab is not a canvas widget.")

    def _current_canvas_id(self) -> str:
        canvas_id = self._current_canvas().property("canvas_id")
        if not isinstance(canvas_id, str):
            raise RuntimeError("Canvas widget missing canvas_id metadata.")
        return canvas_id

    def _canvas_name(self, canvas_id: str) -> str:
        tab = self._canvas_tabs.get(canvas_id)
        if tab is None:
            return canvas_id
        index = self._tabs.indexOf(tab)
        if index < 0:
            return canvas_id
        return self._tabs.tabText(index) or canvas_id

    def _on_add_module(self) -> None:
        selected = self._selected_palette_module()
        if selected is None:
            QMessageBox.warning(self, "Add Module", "Select a module from the palette.")
            return

        module_type, module_display = selected
        module_name = self._module_name_input.text().strip()
        if not module_name:
            QMessageBox.warning(self, "Add Module", "Module name is required.")
            return
        if len(module_name) > _MAX_MODULE_NAME_LEN:
            QMessageBox.warning(
                self,
                "Add Module",
                f"Module name must be {_MAX_MODULE_NAME_LEN} characters or fewer.",
            )
            return
        if self._module_name_is_taken(module_name):
            QMessageBox.warning(self, "Add Module", "Module name must be unique.")
            return

        self._module_counter += 1
        module_id = f"m_{self._module_counter:04d}"
        canvas_id = self._current_canvas_id()

        module = self._registry.create(module_type, module_id)
        self._runtime.register_module(module)

        card = ModuleCard(
            module_id=module_id,
            module_name=module_name,
            module_type_display=module_display,
            module_widget=module.widget(),
        )
        card.remove_requested.connect(self._on_remove_module_requested)
        self._current_canvas().add_card(card)

        self._modules[module_id] = _ModuleRef(
            module_id=module_id,
            module_type=module.descriptor.module_type,
            module_name=module_name,
            module_type_display=module_display,
            canvas_id=canvas_id,
            module=module,
        )

        self._refresh_canvas_references()
        self._refresh_module_name_input()
        self._mark_project_dirty()

    def _on_remove_module_requested(self, module_id: str) -> None:
        if self._app_config.safety_prompts.confirm_module_remove:
            module_ref = self._modules.get(module_id)
            label = module_ref.module_name if module_ref is not None else module_id
            answer = QMessageBox.question(
                self,
                "Remove Module",
                f"Remove module '{label}' and its bind chains?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._remove_module(module_id)

    def _remove_module(self, module_id: str, *, refresh_ui: bool = True) -> None:
        module_ref = self._modules.pop(module_id, None)
        self._runtime.unregister_module(module_id)

        if module_ref is None:
            for canvas in self._canvases.values():
                canvas.remove_card(module_id)
        else:
            canvas_widget = self._canvases.get(module_ref.canvas_id)
            if canvas_widget is not None:
                canvas_widget.remove_card(module_id)

        if refresh_ui:
            self._refresh_canvas_references()
            self._refresh_module_name_input()
            self._mark_project_dirty()

    def _refresh_canvas_references(self) -> None:
        self._refresh_module_selectors()
        self._refresh_bindings_view()
        self._binding_diagnostics.clear()

    def _refresh_module_selectors(self) -> None:
        self._source_module.blockSignals(True)
        self._target_module.blockSignals(True)

        current_src = self._source_module.currentData()
        current_dst = self._target_module.currentData()

        self._source_module.clear()
        self._target_module.clear()

        for module_id in self._module_ids_in_ui_order():
            module_ref = self._modules.get(module_id)
            if module_ref is None:
                continue
            canvas_name = self._canvas_name(module_ref.canvas_id)
            label = f"[{canvas_name}] {module_ref.module_name} :: {module_ref.module_type_display}"
            self._source_module.addItem(label, userData=module_ref.module_id)
            self._target_module.addItem(label, userData=module_ref.module_id)

        self._restore_combo_selection(self._source_module, current_src)
        self._restore_combo_selection(self._target_module, current_dst)

        self._source_module.blockSignals(False)
        self._target_module.blockSignals(False)

        self._refresh_source_ports()
        self._refresh_target_ports()

    @staticmethod
    def _restore_combo_selection(combo: QComboBox, value: object) -> None:
        if value is None:
            if combo.count() > 0:
                combo.setCurrentIndex(0)
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)

    def _on_source_module_changed(self) -> None:
        self._refresh_source_ports()
        self._binding_diagnostics.clear()

    def _on_target_module_changed(self) -> None:
        self._refresh_target_ports()
        self._binding_diagnostics.clear()

    def _on_show_advanced_ports_changed(self, _checked: bool) -> None:
        self._refresh_source_ports()
        self._refresh_target_ports()
        self._binding_diagnostics.clear()

    def _port_visible_in_bind_panel(self, port: PortSpec) -> bool:
        if port.bind_visibility == "hidden":
            return False
        if port.bind_visibility == "advanced":
            return bool(self._show_advanced_ports.isChecked())
        return True

    @staticmethod
    def _format_bind_port_label(port: PortSpec) -> str:
        return f"{port.key} [{port.kind}, {port.plane}]"

    def _refresh_source_ports(self) -> None:
        current_port = self._source_port.currentData()
        self._source_port.clear()

        module_id = self._source_module.currentData()
        if not isinstance(module_id, str):
            return
        module_ref = self._modules.get(module_id)
        if module_ref is None:
            return

        for port in module_ref.module.descriptor.outputs:
            if not self._port_visible_in_bind_panel(port):
                continue
            self._source_port.addItem(self._format_bind_port_label(port), userData=port.key)

        self._restore_combo_selection(self._source_port, current_port)

    def _refresh_target_ports(self) -> None:
        current_port = self._target_port.currentData()
        self._target_port.clear()

        module_id = self._target_module.currentData()
        if not isinstance(module_id, str):
            return
        module_ref = self._modules.get(module_id)
        if module_ref is None:
            return

        for port in module_ref.module.descriptor.inputs:
            if not self._port_visible_in_bind_panel(port):
                continue
            self._target_port.addItem(self._format_bind_port_label(port), userData=port.key)

        self._restore_combo_selection(self._target_port, current_port)

    def _candidate_edge(self) -> BindingEdge | None:
        src_id = self._source_module.currentData()
        dst_id = self._target_module.currentData()
        src_port = self._source_port.currentData()
        dst_port = self._target_port.currentData()
        if not isinstance(src_id, str) or not isinstance(dst_id, str):
            return None
        if not isinstance(src_port, str) or not isinstance(dst_port, str):
            return None
        return BindingEdge(
            src_module_id=src_id,
            src_port=src_port,
            dst_module_id=dst_id,
            dst_port=dst_port,
        )

    def _inspect_candidate_binding(self) -> None:
        edge = self._candidate_edge()
        self._binding_diagnostics.clear()
        if edge is None:
            self._binding_diagnostics.addItem("error: select modules and ports")
            return

        for item in self._runtime.diagnostics_for_edge(edge):
            self._binding_diagnostics.addItem(f"{item.level}: {item.message}")

    def _on_bind(self) -> None:
        edge = self._candidate_edge()
        if edge is None:
            QMessageBox.warning(self, "Bind", "Select source and destination modules/ports.")
            return

        diagnostics = self._runtime.diagnostics_for_edge(edge)
        self._binding_diagnostics.clear()
        has_error = False
        for diagnostic in diagnostics:
            self._binding_diagnostics.addItem(f"{diagnostic.level}: {diagnostic.message}")
            if diagnostic.level == "error":
                has_error = True

        if has_error:
            QMessageBox.warning(self, "Bind", "Candidate binding has validation errors.")
            return

        try:
            self._runtime.add_binding(
                edge.src_module_id,
                edge.src_port,
                edge.dst_module_id,
                edge.dst_port,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Bind", str(exc))
            return

        self._refresh_bindings_view()
        self._mark_project_dirty()

    @staticmethod
    def _lookup_port(ports: tuple[PortSpec, ...], key: str) -> PortSpec | None:
        for port in ports:
            if port.key == key:
                return port
        return None

    def _edge_text(self, edge: BindingEdge) -> str:
        src_ref = self._modules[edge.src_module_id]
        dst_ref = self._modules[edge.dst_module_id]
        src_out = self._lookup_port(src_ref.module.descriptor.outputs, edge.src_port)
        dst_in = self._lookup_port(dst_ref.module.descriptor.inputs, edge.dst_port)

        plane = src_out.plane if src_out is not None else "data"
        src_kind = src_out.kind if src_out is not None else "?"
        dst_kind = dst_in.kind if dst_in is not None else "?"

        src_canvas = self._canvas_name(src_ref.canvas_id)
        dst_canvas = self._canvas_name(dst_ref.canvas_id)
        return (
            f"[{plane}] [{src_canvas}] {src_ref.module_name}.{edge.src_port}({src_kind}) -> "
            f"[{dst_canvas}] {dst_ref.module_name}.{edge.dst_port}({dst_kind})"
        )

    def _refresh_bindings_view(self) -> None:
        self._bindings_view.clear()
        for edge in self._runtime.list_bindings():
            if edge.src_module_id not in self._modules or edge.dst_module_id not in self._modules:
                continue
            item = QListWidgetItem(self._edge_text(edge))
            item.setData(Qt.ItemDataRole.UserRole, edge)
            self._bindings_view.addItem(item)

    def _on_remove_binding(self) -> None:
        item = self._bindings_view.currentItem()
        if item is None:
            return

        edge = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(edge, BindingEdge):
            return

        if self._app_config.safety_prompts.confirm_binding_remove:
            answer = QMessageBox.question(
                self,
                "Remove Binding",
                f"Remove binding:\n{self._edge_text(edge)}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        removed = self._runtime.remove_binding(edge)
        if removed:
            self._refresh_bindings_view()
            self._mark_project_dirty()

    def _sorted_canvas_ids(self) -> list[str]:
        ids: list[str] = []
        for index in range(self._tabs.count()):
            widget = self._tabs.widget(index)
            if widget is None:
                continue
            canvas_id = widget.property("canvas_id")
            if isinstance(canvas_id, str):
                ids.append(canvas_id)
        return ids

    def _module_ids_for_canvas(self, canvas_id: str) -> list[str]:
        ordered_ids: list[str] = []
        seen: set[str] = set()

        canvas = self._canvases.get(canvas_id)
        if canvas is not None:
            for module_id in canvas.module_ids_in_order():
                module_ref = self._modules.get(module_id)
                if module_ref is None or module_ref.canvas_id != canvas_id:
                    continue
                ordered_ids.append(module_id)
                seen.add(module_id)

        fallback_ids = sorted(
            module_ref.module_id
            for module_ref in self._modules.values()
            if module_ref.canvas_id == canvas_id and module_ref.module_id not in seen
        )
        ordered_ids.extend(fallback_ids)
        return ordered_ids

    def _module_ids_in_ui_order(self) -> list[str]:
        ordered_ids: list[str] = []
        seen: set[str] = set()

        for canvas_id in self._sorted_canvas_ids():
            for module_id in self._module_ids_for_canvas(canvas_id):
                if module_id in seen:
                    continue
                ordered_ids.append(module_id)
                seen.add(module_id)

        remaining_ids = sorted(module_id for module_id in self._modules if module_id not in seen)
        ordered_ids.extend(remaining_ids)
        return ordered_ids

    def _snapshot_project(self) -> Project:
        canvases: list[CanvasSnapshot] = []
        for index, canvas_id in enumerate(self._sorted_canvas_ids()):
            modules: list[ModuleSnapshot] = []
            for module_id in self._module_ids_for_canvas(canvas_id):
                module_ref = self._modules.get(module_id)
                if module_ref is None:
                    continue
                modules.append(
                    ModuleSnapshot(
                        module_id=module_ref.module_id,
                        module_type=module_ref.module_type,
                        name=module_ref.module_name,
                        inputs=module_ref.module.snapshot_inputs(),
                    )
                )

            name = self._tabs.tabText(index) or f"Canvas {index + 1}"
            canvases.append(CanvasSnapshot(canvas_id=canvas_id, name=name, modules=modules))

        bindings = [
            BindingSnapshot(
                src_module_id=edge.src_module_id,
                src_port=edge.src_port,
                dst_module_id=edge.dst_module_id,
                dst_port=edge.dst_port,
            )
            for edge in self._runtime.list_bindings()
        ]

        return Project(
            project_id=self._current_project_id,
            runtime=self._active_runtime_policy.model_copy(deep=True),
            canvases=canvases,
            bindings=bindings,
        )

    def _project_dialog_directory(self) -> str:
        directory = self._project_root_path()
        directory.mkdir(parents=True, exist_ok=True)
        return str(directory)

    def _on_save_project(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            self._project_dialog_directory(),
            "JSON (*.json)",
        )
        if not path_str:
            return

        path = Path(path_str)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")

        try:
            project = self._snapshot_project()
            save_project(path, project)
            self._autosnapshot.record_manual_save(project.project_id)
        except Exception as exc:
            QMessageBox.critical(self, "Save Project", str(exc))

    def _validate_project(self, project: Project) -> None:
        if not project.canvases:
            raise PersistenceError("Project contains no canvases.")

        canvas_ids: set[str] = set()
        module_ids: set[str] = set()
        module_names: set[str] = set()

        for canvas in project.canvases:
            if canvas.canvas_id in canvas_ids:
                raise PersistenceError(f"Duplicate canvas_id '{canvas.canvas_id}'.")
            canvas_ids.add(canvas.canvas_id)

            for snapshot in canvas.modules:
                if snapshot.module_id in module_ids:
                    raise PersistenceError(f"Duplicate module_id '{snapshot.module_id}'.")
                module_ids.add(snapshot.module_id)

                stripped_name = snapshot.name.strip()
                if not stripped_name:
                    raise PersistenceError(
                        f"Module '{snapshot.module_id}' has an empty custom name."
                    )

                lowered_name = stripped_name.casefold()
                if lowered_name in module_names:
                    raise PersistenceError(f"Duplicate module name '{snapshot.name}'.")
                module_names.add(lowered_name)

                if not self._registry.has(snapshot.module_type):
                    raise PersistenceError(
                        f"Unknown module_type '{snapshot.module_type}' for '{snapshot.module_id}'."
                    )

        for edge in project.bindings:
            if edge.src_module_id not in module_ids:
                raise PersistenceError(
                    f"Binding source module '{edge.src_module_id}' not found in project modules."
                )
            if edge.dst_module_id not in module_ids:
                raise PersistenceError(
                    "Binding destination module "
                    f"'{edge.dst_module_id}' not found in project modules."
                )

    def _on_reset_workspace_requested(self) -> None:
        if self._app_config.safety_prompts.confirm_workspace_reset:
            answer = QMessageBox.question(
                self,
                "Reset Workspace",
                "Reset workspace and remove all canvases/modules/bind chains?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._reset_workspace()
        self._create_tab("Canvas 1")
        self._tabs.setCurrentIndex(0)
        self._current_project_id = "workspace"
        self._autosnapshot.set_project_id(self._current_project_id)
        self._refresh_canvas_references()
        self._refresh_module_name_input()
        self._mark_project_dirty()

    def _reset_workspace(self) -> None:
        for module_id in list(self._modules):
            self._runtime.unregister_module(module_id)
        self._modules.clear()
        self._runtime.clear_bindings()

        self._tabs.clear()
        self._canvases.clear()
        self._canvas_tabs.clear()
        self._module_counter = 0
        self._canvas_counter = 0

    def _stage_project(self, project: Project) -> _StagedProject:
        self._validate_project(project)

        runtime_policy = project.runtime.model_copy(deep=True)
        runtime = self._build_runtime(runtime_policy)

        staged_canvases: list[_StagedCanvas] = []
        staged_modules: list[ModuleLifecycle] = []
        staged_widgets: list[QWidget] = []
        max_module_counter = 0
        max_canvas_counter = 0

        try:
            for canvas in project.canvases:
                staged_canvas_modules: list[_StagedModule] = []
                for snapshot in canvas.modules:
                    module = self._registry.create(snapshot.module_type, snapshot.module_id)
                    try:
                        module.restore_inputs(snapshot.inputs)
                    except Exception as exc:
                        raise PersistenceError(
                            "Invalid persisted inputs for "
                            f"'{snapshot.module_id}' ({snapshot.module_type}): {exc}"
                        ) from exc

                    runtime.register_module(module)
                    widget = module.widget()

                    staged_modules.append(module)
                    staged_widgets.append(widget)

                    staged_canvas_modules.append(
                        _StagedModule(
                            ref=_ModuleRef(
                                module_id=snapshot.module_id,
                                module_type=module.descriptor.module_type,
                                module_name=snapshot.name.strip(),
                                module_type_display=module.descriptor.display_name,
                                canvas_id=canvas.canvas_id,
                                module=module,
                            ),
                            widget=widget,
                        )
                    )

                    if snapshot.module_id.startswith("m_"):
                        suffix = snapshot.module_id.split("_", 1)[1]
                        if suffix.isdigit():
                            max_module_counter = max(max_module_counter, int(suffix))

                staged_canvases.append(
                    _StagedCanvas(
                        canvas_id=canvas.canvas_id,
                        name=canvas.name,
                        modules=staged_canvas_modules,
                    )
                )

                if canvas.canvas_id.startswith("c_"):
                    suffix = canvas.canvas_id.split("_", 1)[1]
                    if suffix.isdigit():
                        max_canvas_counter = max(max_canvas_counter, int(suffix))

            for edge in project.bindings:
                runtime.add_binding(
                    edge.src_module_id,
                    edge.src_port,
                    edge.dst_module_id,
                    edge.dst_port,
                )

            return _StagedProject(
                runtime=runtime,
                runtime_policy=runtime_policy,
                canvases=staged_canvases,
                module_counter=max_module_counter,
                canvas_counter=max_canvas_counter,
            )
        except Exception:
            for staged_module in staged_modules:
                with suppress(Exception):
                    staged_module.on_close()
            for widget in staged_widgets:
                widget.close()
                widget.deleteLater()
            raise

    @staticmethod
    def _dispose_staged_project(staged: _StagedProject) -> None:
        seen_module_ids: set[str] = set()
        for canvas in staged.canvases:
            for staged_module in canvas.modules:
                module_ref = staged_module.ref
                if module_ref.module_id not in seen_module_ids:
                    seen_module_ids.add(module_ref.module_id)
                    with suppress(Exception):
                        module_ref.module.on_close()
                staged_module.widget.close()
                staged_module.widget.deleteLater()

    @staticmethod
    def _replay_staged_project_state(staged: _StagedProject) -> None:
        staged_modules = {
            staged_module.ref.module_id: staged_module.ref.module
            for canvas in staged.canvases
            for staged_module in canvas.modules
        }
        for module_id in staged.runtime.module_ids_in_order():
            module = staged_modules.get(module_id)
            if module is None:
                continue
            try:
                module.replay_state()
            except Exception as exc:
                raise PersistenceError(
                    f"Failed to replay module '{module_id}' state: {exc}"
                ) from exc

    def _apply_project(self, project: Project) -> None:
        staged = self._stage_project(project)
        try:
            self._replay_staged_project_state(staged)
        except Exception:
            self._dispose_staged_project(staged)
            raise

        self._reset_workspace()

        self._active_runtime_policy = staged.runtime_policy.model_copy(deep=True)
        self._runtime = staged.runtime
        self._wire_runtime_hooks(self._runtime)

        for canvas in staged.canvases:
            self._create_tab(canvas.name, canvas_id=canvas.canvas_id)

        for canvas in staged.canvases:
            canvas_widget = self._canvases[canvas.canvas_id]
            for staged_module in canvas.modules:
                module_ref = staged_module.ref
                card = ModuleCard(
                    module_id=module_ref.module_id,
                    module_name=module_ref.module_name,
                    module_type_display=module_ref.module_type_display,
                    module_widget=staged_module.widget,
                )
                card.remove_requested.connect(self._on_remove_module_requested)
                canvas_widget.add_card(card)
                self._modules[module_ref.module_id] = module_ref

        self._module_counter = staged.module_counter
        self._canvas_counter = staged.canvas_counter
        self._tabs.setCurrentIndex(0)

        self._current_project_id = project.project_id
        self._autosnapshot.set_project_id(self._current_project_id)

        self._refresh_module_selectors()
        self._refresh_bindings_view()
        self._binding_diagnostics.clear()
        self._refresh_module_name_input()

    def _on_load_project(self) -> None:
        if (
            self._app_config.safety_prompts.confirm_load_over_unsaved
            and self._autosnapshot.has_unsaved_snapshot(self._current_project_id)
        ):
            answer = QMessageBox.question(
                self,
                "Load Project",
                "Unsaved changes are available in autosnapshots. Load another project anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Load Project",
            self._project_dialog_directory(),
            "JSON (*.json)",
        )
        if not path_str:
            return

        try:
            project = load_project(Path(path_str))
            self._apply_project(project)
            self._autosnapshot.record_manual_save(project.project_id)
        except Exception as exc:
            QMessageBox.critical(self, "Load Project", str(exc))
