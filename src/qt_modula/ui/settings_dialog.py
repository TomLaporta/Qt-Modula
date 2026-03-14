"""Settings dialog for app-wide policy controls."""

from __future__ import annotations

import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import orjson
from pydantic import ValidationError
from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from qt_modula.paths import theme_presets_path as runtime_theme_presets_path
from qt_modula.persistence import (
    AppConfig,
    AutosnapshotPolicy,
    CustomThemePolicy,
    HttpNetworkPolicy,
    PathPolicy,
    ProviderNetworkPolicy,
    RuntimePolicyModel,
    SafetyPromptPolicy,
    UiPolicy,
    YFinanceNetworkPolicy,
)

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True, slots=True)
class _RuntimePreset:
    """Runtime policy preset for quick selection."""

    max_queue_size: int
    coalesce_pending_inputs: bool
    max_deliveries_per_batch: int


_RUNTIME_PRESET_SAFE = _RuntimePreset(
    max_queue_size=50_000,
    coalesce_pending_inputs=True,
    max_deliveries_per_batch=75_000,
)
_RUNTIME_PRESET_BALANCED = _RuntimePreset(
    max_queue_size=100_000,
    coalesce_pending_inputs=True,
    max_deliveries_per_batch=250_000,
)
_RUNTIME_PRESET_FAST = _RuntimePreset(
    max_queue_size=500_000,
    coalesce_pending_inputs=True,
    max_deliveries_per_batch=1_000_000,
)


@dataclass(frozen=True, slots=True)
class _ThemeRoleSpec:
    """Theme role metadata for editor tabs."""

    field_name: str
    label: str
    description: str


_THEME_PRESET_DEFAULT = "default"
_THEME_PRESET_NAME_MAX_LEN = 64
_THEME_ROLE_SPECS: tuple[_ThemeRoleSpec, ...] = (
    _ThemeRoleSpec(
        field_name="primary_color",
        label="Primary",
        description="Top-level chrome, toolbars, tabs, and control surfaces.",
    ),
    _ThemeRoleSpec(
        field_name="secondary_color",
        label="Secondary",
        description="Text and labels across app windows and dialogs.",
    ),
    _ThemeRoleSpec(
        field_name="highlight_color",
        label="Highlight",
        description="Selected, focused, and active UI states.",
    ),
    _ThemeRoleSpec(
        field_name="canvas_color",
        label="Canvas",
        description="Canvas and module-card surfaces.",
    ),
)


def _theme_presets_path() -> Path:
    return runtime_theme_presets_path()


def _normalize_theme_preset_name(value: str) -> str:
    token = " ".join(str(value).strip().split())
    token = "".join(ch for ch in token if ch.isprintable())
    if len(token) > _THEME_PRESET_NAME_MAX_LEN:
        token = token[:_THEME_PRESET_NAME_MAX_LEN].rstrip()
    return token


def _load_theme_presets(path: Path) -> dict[str, CustomThemePolicy]:
    if not path.exists():
        return {}

    try:
        payload = orjson.loads(path.read_bytes())
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}

    presets: list[tuple[str, CustomThemePolicy]] = []
    for raw_name, raw_value in payload.items():
        name = _normalize_theme_preset_name(str(raw_name))
        if not name or name.casefold() == _THEME_PRESET_DEFAULT:
            continue
        try:
            preset = CustomThemePolicy.model_validate(raw_value)
        except ValidationError:
            continue
        presets.append((name, preset))

    presets.sort(key=lambda entry: entry[0].casefold())
    return dict(presets)


def _save_theme_presets(path: Path, presets: dict[str, CustomThemePolicy]) -> None:
    ordered = {
        name: preset.model_dump(mode="json")
        for name, preset in sorted(presets.items(), key=lambda entry: entry[0].casefold())
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = orjson.dumps(ordered, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


class _ColorWheelWidget(QWidget):
    """Interactive HSV wheel with an inner saturation/value square."""

    color_changed = Signal(QColor)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hue = 220
        self._saturation = 0.6
        self._value = 0.8
        self._drag_mode: str | None = None
        self._sv_cache_hue = -1
        self._sv_cache_size = QSize()
        self._sv_cache_image: QImage | None = None
        self.setMinimumSize(220, 220)

    def color(self) -> QColor:
        return QColor.fromHsvF(self._hue / 360.0, self._saturation, self._value)

    def set_color(self, color: QColor) -> None:
        hue = color.hueF()
        saturation = color.saturationF()
        value = color.valueF()
        if hue >= 0:
            self._hue = int(hue * 360) % 360
        self._saturation = max(0.0, min(1.0, saturation if saturation >= 0 else 0.0))
        self._value = max(0.0, min(1.0, value if value >= 0 else 0.0))
        self.update()

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.height() / 2.0)

    def _wheel_radii(self) -> tuple[float, float]:
        outer = max(12.0, (min(self.width(), self.height()) / 2.0) - 6.0)
        inner = outer * 0.70
        return outer, inner

    def _square_rect(self) -> QRect:
        _outer, inner = self._wheel_radii()
        half = inner / 1.42
        center = self._center()
        return QRect(
            int(center.x() - half),
            int(center.y() - half),
            int(half * 2.0),
            int(half * 2.0),
        )

    def _sv_image_for_square(self, square_rect: QRect) -> QImage | None:
        width = square_rect.width()
        height = square_rect.height()
        if width <= 0 or height <= 0:
            return None

        size = QSize(width, height)
        if (
            self._sv_cache_image is not None
            and self._sv_cache_hue == self._hue
            and self._sv_cache_size == size
        ):
            return self._sv_cache_image

        image = QImage(width, height, QImage.Format.Format_RGB32)
        hue = self._hue / 360.0
        max_x = max(width - 1, 1)
        max_y = max(height - 1, 1)
        for x in range(width):
            saturation = x / max_x
            for y in range(height):
                value = 1.0 - (y / max_y)
                image.setPixel(x, y, QColor.fromHsvF(hue, saturation, value).rgb())

        self._sv_cache_hue = self._hue
        self._sv_cache_size = size
        self._sv_cache_image = image
        return image

    def _hue_ring_path(self, outer_radius: float, inner_radius: float) -> QPainterPath:
        center = self._center()
        outer = QPainterPath()
        outer.addEllipse(center, outer_radius, outer_radius)
        inner = QPainterPath()
        inner.addEllipse(center, inner_radius, inner_radius)
        return outer.subtracted(inner)

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self._center()
        outer_radius, inner_radius = self._wheel_radii()
        mid_radius = (outer_radius + inner_radius) / 2.0
        ring_width = outer_radius - inner_radius

        hue_gradient = QConicalGradient(center, 0.0)
        for degrees in range(0, 361, 15):
            position = degrees / 360.0
            hue_gradient.setColorAt(position, QColor.fromHsvF(position, 1.0, 1.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(hue_gradient)
        painter.drawPath(self._hue_ring_path(outer_radius, inner_radius))

        square_rect = self._square_rect()
        sv_image = self._sv_image_for_square(square_rect)
        if sv_image is not None:
            painter.drawImage(square_rect, sv_image)

        angle = math.radians(self._hue)
        painter.setPen(QPen(Qt.GlobalColor.white, max(2, ring_width * 0.06)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(
            QPointF(
                center.x() + (mid_radius * math.cos(angle)),
                center.y() - (mid_radius * math.sin(angle)),
            ),
            ring_width * 0.42,
            ring_width * 0.42,
        )

        cross_x = square_rect.x() + (self._saturation * max(square_rect.width() - 1, 1))
        cross_y = square_rect.y() + ((1.0 - self._value) * max(square_rect.height() - 1, 1))
        painter.drawEllipse(QPointF(cross_x, cross_y), 5.0, 5.0)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        self._drag_mode = self._hit_test(pos)
        self._apply_mouse(pos)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_mode is None:
            return
        self._apply_mouse(event.position().toPoint())

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:  # noqa: N802
        self._drag_mode = None

    def _hit_test(self, pos: QPoint) -> str | None:
        center = self._center()
        outer_radius, inner_radius = self._wheel_radii()
        distance = math.hypot(pos.x() - center.x(), pos.y() - center.y())
        if inner_radius <= distance <= outer_radius:
            return "wheel"
        if self._square_rect().contains(pos):
            return "square"
        return None

    def _apply_mouse(self, pos: QPoint) -> None:
        center = self._center()
        if self._drag_mode == "wheel":
            angle = math.degrees(math.atan2(center.y() - pos.y(), pos.x() - center.x()))
            self._hue = int(angle) % 360
        elif self._drag_mode == "square":
            square = self._square_rect()
            self._saturation = max(
                0.0,
                min(1.0, (pos.x() - square.x()) / max(square.width() - 1, 1)),
            )
            self._value = max(
                0.0,
                min(1.0, 1.0 - ((pos.y() - square.y()) / max(square.height() - 1, 1))),
            )
        else:
            return

        self.update()
        self.color_changed.emit(self.color())


class _ThemePreview(QFrame):
    """Compact preview used in settings dialog."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("settings-theme-preview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._title = QLabel("Qt Modula")
        self._subtitle = QLabel("Minimal Preview")
        self._button = QPushButton("Action")
        self._card = QFrame()
        self._card.setObjectName("settings-theme-card")
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.addWidget(QLabel("Module Card"))
        card_layout.addWidget(QLabel("Providers / HTTP Request"))

        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addWidget(self._button)
        layout.addWidget(self._card)

    def apply(self, *, primary: str, secondary: str, highlight: str, canvas: str) -> None:
        self.setStyleSheet(
            f"""
            QFrame#settings-theme-preview {{
                background: {primary};
                border: 1px solid {highlight};
                border-radius: 8px;
            }}
            QFrame#settings-theme-preview QLabel {{
                color: {secondary};
                background: transparent;
            }}
            QFrame#settings-theme-preview QPushButton {{
                color: {secondary};
                background: {canvas};
                border: 1px solid {highlight};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QFrame#settings-theme-card {{
                background: {canvas};
                border: 1px solid {highlight};
                border-radius: 6px;
            }}
            """
        )


class SettingsDialog(QDialog):
    """Dialog that edits a full app settings snapshot and commits on Save."""

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(900, 720)

        self._initial = config.model_copy(deep=True)
        self._defaults = AppConfig()
        self._selected: AppConfig | None = None
        self._theme_presets_path = _theme_presets_path()
        self._theme_presets = _load_theme_presets(self._theme_presets_path)
        self._theme_preset_populating = False

        root = QVBoxLayout(self)
        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        self._build_runtime_tab()
        self._build_autosnapshot_tab()
        self._build_provider_tab()
        self._build_paths_tab()
        self._build_safety_tab()
        self._build_theme_tab()

        actions = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        actions.accepted.connect(self._on_save)
        actions.rejected.connect(self.reject)
        root.addWidget(actions)

    def selected_config(self) -> AppConfig | None:
        if self._selected is None:
            return None
        return self._selected.model_copy(deep=True)

    def _build_runtime_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(6)
        preset_row.addWidget(QLabel("Presets"))

        self._preset_safe_btn = QPushButton("Safe")
        self._preset_safe_btn.clicked.connect(self._apply_runtime_safe_preset)
        preset_row.addWidget(self._preset_safe_btn)

        self._preset_balanced_btn = QPushButton("Balanced")
        self._preset_balanced_btn.clicked.connect(self._apply_runtime_balanced_preset)
        preset_row.addWidget(self._preset_balanced_btn)

        self._preset_fast_btn = QPushButton("Fast")
        self._preset_fast_btn.clicked.connect(self._apply_runtime_fast_preset)
        preset_row.addWidget(self._preset_fast_btn)
        preset_row.addStretch(1)
        layout.addLayout(preset_row)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        runtime = self._initial.runtime

        self._runtime_max_queue = QSpinBox()
        self._runtime_max_queue.setRange(1, 5_000_000)
        self._runtime_max_queue.setValue(runtime.max_queue_size)
        form.addRow("Max Queue Size", self._runtime_max_queue)

        self._runtime_coalesce = QCheckBox("Coalesce Pending Inputs")
        self._runtime_coalesce.setChecked(runtime.coalesce_pending_inputs)
        form.addRow("", self._runtime_coalesce)

        self._runtime_max_batch = QSpinBox()
        self._runtime_max_batch.setRange(1, 10_000_000)
        self._runtime_max_batch.setValue(runtime.max_deliveries_per_batch)
        form.addRow("Max Deliveries Per Batch", self._runtime_max_batch)

        layout.addLayout(form)

        self._tabs.addTab(tab, "Runtime")

    def _build_autosnapshot_tab(self) -> None:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(16, 16, 16, 16)

        autosnapshot = self._initial.autosnapshot

        self._autosnapshot_enabled = QCheckBox("Enable Autosnapshot")
        self._autosnapshot_enabled.setChecked(autosnapshot.enabled)
        form.addRow("", self._autosnapshot_enabled)

        self._autosnapshot_debounce = QSpinBox()
        self._autosnapshot_debounce.setRange(100, 30_000)
        self._autosnapshot_debounce.setValue(autosnapshot.debounce_ms)
        form.addRow("Debounce (ms)", self._autosnapshot_debounce)

        self._autosnapshot_history = QSpinBox()
        self._autosnapshot_history.setRange(1, 500)
        self._autosnapshot_history.setValue(autosnapshot.max_history)
        form.addRow("Max History", self._autosnapshot_history)

        reset_button = QPushButton("Reset Defaults")
        reset_button.clicked.connect(self._reset_autosnapshot_defaults)
        form.addRow("", reset_button)

        self._tabs.addTab(tab, "Autosnapshot")

    def _build_provider_tab(self) -> None:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(16, 16, 16, 16)

        network = self._initial.provider_network

        self._http_timeout = QDoubleSpinBox()
        self._http_timeout.setRange(0.1, 300.0)
        self._http_timeout.setDecimals(2)
        self._http_timeout.setSingleStep(0.1)
        self._http_timeout.setValue(network.http.timeout_s)
        form.addRow("HTTP Timeout (s)", self._http_timeout)

        self._http_retries = QSpinBox()
        self._http_retries.setRange(0, 20)
        self._http_retries.setValue(network.http.retries)
        form.addRow("HTTP Retries", self._http_retries)

        self._http_backoff = QDoubleSpinBox()
        self._http_backoff.setRange(0.0, 60.0)
        self._http_backoff.setDecimals(2)
        self._http_backoff.setSingleStep(0.05)
        self._http_backoff.setValue(network.http.backoff_s)
        form.addRow("HTTP Backoff (s)", self._http_backoff)

        self._http_min_gap = QDoubleSpinBox()
        self._http_min_gap.setRange(0.0, 60.0)
        self._http_min_gap.setDecimals(2)
        self._http_min_gap.setSingleStep(0.05)
        self._http_min_gap.setValue(network.http.min_gap_s)
        form.addRow("HTTP Min Gap (s)", self._http_min_gap)

        self._http_proxy = QLineEdit(network.http.proxy_url)
        self._http_proxy.setPlaceholderText("Optional (http://... or socks5://...)")
        form.addRow("HTTP Proxy URL", self._http_proxy)

        self._yf_retries = QSpinBox()
        self._yf_retries.setRange(0, 20)
        self._yf_retries.setValue(network.yfinance.retries)
        form.addRow("yfinance Retries", self._yf_retries)

        self._yf_backoff = QDoubleSpinBox()
        self._yf_backoff.setRange(0.0, 60.0)
        self._yf_backoff.setDecimals(2)
        self._yf_backoff.setSingleStep(0.05)
        self._yf_backoff.setValue(network.yfinance.backoff_s)
        form.addRow("yfinance Backoff (s)", self._yf_backoff)

        reset_button = QPushButton("Reset Defaults")
        reset_button.clicked.connect(self._reset_provider_defaults)
        form.addRow("", reset_button)

        self._tabs.addTab(tab, "Provider/Network")

    def _build_paths_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        hint = QLabel("Leave a path blank to use the app-relative default shown as placeholder.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()

        paths = self._initial.paths
        defaults = self._defaults.paths

        self._project_path = QLineEdit(paths.project_directory or "")
        self._project_path.setPlaceholderText(str(defaults.resolved_project_directory()))
        self._autosnapshot_path = QLineEdit(paths.autosnapshot_directory or "")
        self._autosnapshot_path.setPlaceholderText(
            str(defaults.resolved_autosnapshot_directory())
        )
        self._export_path = QLineEdit(paths.export_directory or "")
        self._export_path.setPlaceholderText(str(defaults.resolved_export_directory()))

        form.addRow("Projects", self._path_row(self._project_path))
        form.addRow("Autosnapshots", self._path_row(self._autosnapshot_path))
        form.addRow("Exports", self._path_row(self._export_path))

        reset_button = QPushButton("Reset Defaults")
        reset_button.clicked.connect(self._reset_paths_defaults)
        form.addRow("", reset_button)
        layout.addLayout(form)

        self._tabs.addTab(tab, "Default Paths")

    def _path_row(self, line_edit: QLineEdit) -> QWidget:
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(lambda: self._pick_directory(line_edit))
        row.addWidget(line_edit, 1)
        row.addWidget(browse_button)
        return row_widget

    def _pick_directory(self, target: QLineEdit) -> None:
        start = target.text().strip() or target.placeholderText().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Select Directory", start)
        if selected:
            target.setText(selected)

    def _build_safety_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        prompts = self._initial.safety_prompts

        self._prompt_module_remove = QCheckBox("Confirm Module Remove")
        self._prompt_module_remove.setChecked(prompts.confirm_module_remove)
        layout.addWidget(self._prompt_module_remove)

        self._prompt_binding_remove = QCheckBox("Confirm Binding Remove")
        self._prompt_binding_remove.setChecked(prompts.confirm_binding_remove)
        layout.addWidget(self._prompt_binding_remove)

        self._prompt_canvas_delete = QCheckBox("Confirm Canvas Delete")
        self._prompt_canvas_delete.setChecked(prompts.confirm_canvas_delete)
        layout.addWidget(self._prompt_canvas_delete)

        self._prompt_workspace_reset = QCheckBox("Confirm Workspace Reset")
        self._prompt_workspace_reset.setChecked(prompts.confirm_workspace_reset)
        layout.addWidget(self._prompt_workspace_reset)

        self._prompt_load_unsaved = QCheckBox("Confirm Load Over Unsaved")
        self._prompt_load_unsaved.setChecked(prompts.confirm_load_over_unsaved)
        layout.addWidget(self._prompt_load_unsaved)

        reset_button = QPushButton("Reset Defaults")
        reset_button.clicked.connect(self._reset_safety_defaults)
        layout.addWidget(reset_button)

        layout.addStretch(1)
        self._tabs.addTab(tab, "Safety Prompts")

    def _build_theme_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        form = QFormLayout()

        self._theme_preset = QComboBox()
        form.addRow("Theme", self._theme_preset)
        layout.addLayout(form)

        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 0, 0, 0)
        save_row.setSpacing(6)
        self._theme_name_input = QLineEdit()
        self._theme_name_input.setPlaceholderText("Preset name")
        self._save_theme_button = QPushButton("Save Theme")
        self._save_theme_button.clicked.connect(self._on_save_theme_preset)
        save_row.addWidget(self._theme_name_input, 1)
        save_row.addWidget(self._save_theme_button)
        layout.addLayout(save_row)

        initial_theme = self._initial.ui.custom_theme
        self._theme_colors: dict[str, str] = {
            "primary_color": initial_theme.primary_color.upper(),
            "secondary_color": initial_theme.secondary_color.upper(),
            "highlight_color": initial_theme.highlight_color.upper(),
            "canvas_color": initial_theme.canvas_color.upper(),
        }

        self._theme_role_tabs = QTabWidget()
        self._theme_role_tabs.setTabPosition(QTabWidget.TabPosition.North)
        for spec in _THEME_ROLE_SPECS:
            role_tab = QWidget()
            role_layout = QVBoxLayout(role_tab)
            role_layout.setContentsMargins(10, 10, 10, 10)
            role_layout.setSpacing(6)

            help_label = QLabel(spec.description)
            help_label.setWordWrap(True)
            role_layout.addWidget(help_label)
            role_layout.addStretch(1)
            self._theme_role_tabs.addTab(role_tab, spec.label)
        layout.addWidget(self._theme_role_tabs)

        self._theme_wheel = _ColorWheelWidget()
        layout.addWidget(self._theme_wheel)

        hex_row = QHBoxLayout()
        hex_row.setContentsMargins(0, 0, 0, 0)
        hex_row.setSpacing(6)
        hex_row.addWidget(QLabel("#"))
        self._theme_hex_input = QLineEdit()
        self._theme_hex_input.setMaxLength(6)
        self._theme_hex_input.setPlaceholderText("RRGGBB")
        self._theme_hex_input.setFixedWidth(120)
        hex_row.addWidget(self._theme_hex_input)
        hex_row.addStretch(1)
        layout.addLayout(hex_row)

        swatch_row = QHBoxLayout()
        swatch_row.setContentsMargins(0, 0, 0, 0)
        swatch_row.setSpacing(12)
        self._theme_swatches: dict[str, QLabel] = {}
        for spec in _THEME_ROLE_SPECS:
            group = QVBoxLayout()
            group.setContentsMargins(0, 0, 0, 0)
            group.setSpacing(4)

            swatch = QLabel()
            swatch.setFixedSize(30, 30)
            swatch.setObjectName("settings-theme-swatch")
            group.addWidget(swatch, alignment=Qt.AlignmentFlag.AlignHCenter)

            title = QLabel(spec.label)
            title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            group.addWidget(title)

            swatch_row.addLayout(group)
            self._theme_swatches[spec.field_name] = swatch
        swatch_row.addStretch(1)
        layout.addLayout(swatch_row)

        self._theme_preview = _ThemePreview()
        layout.addWidget(self._theme_preview)

        layout.addStretch(1)

        self._theme_preset.currentIndexChanged.connect(self._on_theme_preset_changed)
        self._theme_role_tabs.currentChanged.connect(self._on_theme_role_changed)
        self._theme_wheel.color_changed.connect(self._on_theme_wheel_changed)
        self._theme_hex_input.editingFinished.connect(self._on_theme_hex_entered)
        self._theme_preset.view().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._theme_preset.view().customContextMenuRequested.connect(
            self._on_theme_preset_context_menu
        )

        self._populate_theme_preset_dropdown(selected_token=self._initial.ui.theme)
        self._sync_theme_editor_for_active_role()
        self._refresh_theme_swatches()
        self._update_theme_preview()
        self._tabs.addTab(tab, "Custom Theme")

    def _active_theme_role(self) -> _ThemeRoleSpec:
        index = self._theme_role_tabs.currentIndex()
        if index < 0 or index >= len(_THEME_ROLE_SPECS):
            return _THEME_ROLE_SPECS[0]
        return _THEME_ROLE_SPECS[index]

    def _theme_colors_from_policy(self, policy: CustomThemePolicy) -> dict[str, str]:
        return {
            "primary_color": policy.primary_color.upper(),
            "secondary_color": policy.secondary_color.upper(),
            "highlight_color": policy.highlight_color.upper(),
            "canvas_color": policy.canvas_color.upper(),
        }

    def _find_theme_preset_name(self, token: str) -> str | None:
        needle = token.strip().casefold()
        if not needle:
            return None
        for name in self._theme_presets:
            if name.casefold() == needle:
                return name
        return None

    def _populate_theme_preset_dropdown(self, *, selected_token: str | None = None) -> None:
        selected_name = _THEME_PRESET_DEFAULT
        if selected_token:
            selected = selected_token.strip()
            if selected and selected.casefold() != _THEME_PRESET_DEFAULT:
                matched = self._find_theme_preset_name(selected)
                if matched is not None:
                    selected_name = matched

        self._theme_preset_populating = True
        self._theme_preset.blockSignals(True)
        self._theme_preset.clear()
        self._theme_preset.addItem("Default", _THEME_PRESET_DEFAULT)
        for name in sorted(self._theme_presets, key=str.casefold):
            self._theme_preset.addItem(name, name)

        selected_index = self._theme_preset.findData(selected_name)
        if selected_index < 0:
            selected_index = 0
        self._theme_preset.setCurrentIndex(selected_index)
        self._theme_preset.blockSignals(False)
        self._theme_preset_populating = False

    def _selected_theme_preset_token(self) -> str:
        data = self._theme_preset.currentData()
        if not isinstance(data, str):
            return _THEME_PRESET_DEFAULT

        token = _normalize_theme_preset_name(data)
        if not token or token.casefold() == _THEME_PRESET_DEFAULT:
            return _THEME_PRESET_DEFAULT

        matched = self._find_theme_preset_name(token)
        return matched if matched is not None else _THEME_PRESET_DEFAULT

    def _apply_theme_preset_policy(self, policy: CustomThemePolicy) -> None:
        self._theme_colors = self._theme_colors_from_policy(policy)
        self._sync_theme_editor_for_active_role()
        self._refresh_theme_swatches()
        self._update_theme_preview()

    def _on_theme_preset_changed(self, _index: int) -> None:
        if self._theme_preset_populating:
            return

        selected = self._selected_theme_preset_token()
        if selected == _THEME_PRESET_DEFAULT:
            self._apply_theme_default_preset()
            return

        preset = self._theme_presets.get(selected)
        if preset is None:
            return
        self._apply_theme_preset_policy(preset)

    def _apply_theme_default_preset(self) -> None:
        self._apply_theme_preset_policy(self._defaults.ui.custom_theme)

    def _on_theme_preset_context_menu(self, pos: QPoint) -> None:
        if self._theme_preset_populating:
            return

        view = self._theme_preset.view()
        index = view.indexAt(pos)
        if not index.isValid():
            return

        row = index.row()
        token = self._theme_preset.itemData(row)
        if not isinstance(token, str):
            return
        normalized = _normalize_theme_preset_name(token)
        if normalized.casefold() == _THEME_PRESET_DEFAULT:
            return

        menu = QMenu(self)
        delete_action = menu.addAction("Delete Preset")
        chosen = menu.exec(view.viewport().mapToGlobal(pos))
        if chosen is delete_action:
            self._delete_theme_preset(normalized)

    def _delete_theme_preset(self, token: str) -> bool:
        matched = self._find_theme_preset_name(token)
        if matched is None or matched.casefold() == _THEME_PRESET_DEFAULT:
            return False

        selected_before = self._selected_theme_preset_token()
        removed = self._theme_presets.pop(matched)
        try:
            _save_theme_presets(self._theme_presets_path, self._theme_presets)
        except OSError as exc:
            self._theme_presets[matched] = removed
            QMessageBox.warning(self, "Theme Presets", str(exc))
            return False

        deleting_selected = selected_before.casefold() == matched.casefold()
        next_selected = _THEME_PRESET_DEFAULT if deleting_selected else selected_before
        self._populate_theme_preset_dropdown(selected_token=next_selected)
        if deleting_selected:
            self._apply_theme_default_preset()
        return True

    def _on_save_theme_preset(self) -> None:
        raw_name = self._theme_name_input.text()
        name = _normalize_theme_preset_name(raw_name)
        if not name:
            QMessageBox.warning(self, "Theme Presets", "Enter a preset name before saving.")
            return
        if name.casefold() == _THEME_PRESET_DEFAULT:
            QMessageBox.warning(self, "Theme Presets", '"Default" is reserved.')
            return

        existing = self._find_theme_preset_name(name)
        if existing is not None:
            QMessageBox.warning(
                self,
                "Theme Presets",
                f'Theme preset "{existing}" already exists. Choose a different name.',
            )
            return

        try:
            preset = CustomThemePolicy(
                primary_color=self._theme_colors["primary_color"],
                secondary_color=self._theme_colors["secondary_color"],
                highlight_color=self._theme_colors["highlight_color"],
                canvas_color=self._theme_colors["canvas_color"],
            )
        except ValidationError as exc:
            QMessageBox.warning(self, "Theme Presets", str(exc))
            return

        self._theme_presets[name] = preset
        try:
            _save_theme_presets(self._theme_presets_path, self._theme_presets)
        except OSError as exc:
            QMessageBox.warning(self, "Theme Presets", str(exc))
            return

        self._populate_theme_preset_dropdown(selected_token=name)
        self._theme_name_input.clear()

    def _on_theme_role_changed(self, _index: int) -> None:
        self._sync_theme_editor_for_active_role()

    def _sync_theme_editor_for_active_role(self) -> None:
        active = self._active_theme_role()
        current = self._theme_colors[active.field_name]
        color = QColor(current)
        if not color.isValid():
            defaults = self._defaults.ui.custom_theme
            color = QColor(getattr(defaults, active.field_name))

        self._theme_wheel.blockSignals(True)
        self._theme_wheel.set_color(color)
        self._theme_wheel.blockSignals(False)
        self._theme_hex_input.setText(color.name()[1:].upper())

    def _on_theme_wheel_changed(self, color: QColor) -> None:
        if not color.isValid():
            return
        active = self._active_theme_role()
        self._theme_colors[active.field_name] = color.name().upper()
        self._theme_hex_input.setText(color.name()[1:].upper())
        self._refresh_theme_swatches()
        self._update_theme_preview()

    def _on_theme_hex_entered(self) -> None:
        token = self._theme_hex_input.text().strip().lstrip("#")
        if len(token) != 6:
            self._sync_theme_editor_for_active_role()
            return
        color = QColor(f"#{token}")
        if not color.isValid():
            self._sync_theme_editor_for_active_role()
            return

        active = self._active_theme_role()
        self._theme_colors[active.field_name] = color.name().upper()
        self._theme_wheel.blockSignals(True)
        self._theme_wheel.set_color(color)
        self._theme_wheel.blockSignals(False)
        self._theme_hex_input.setText(color.name()[1:].upper())
        self._refresh_theme_swatches()
        self._update_theme_preview()

    def _refresh_theme_swatches(self) -> None:
        defaults = self._defaults.ui.custom_theme
        border_color = self._theme_colors.get("highlight_color", defaults.highlight_color)
        for spec in _THEME_ROLE_SPECS:
            swatch = self._theme_swatches[spec.field_name]
            value = self._theme_colors.get(spec.field_name, getattr(defaults, spec.field_name))
            swatch.setStyleSheet(
                f"background:{value}; border:1px solid {border_color}; border-radius:6px;"
            )

    def _preview_color(self, value: str, fallback: str) -> str:
        token = value.strip()
        if _HEX_COLOR_RE.fullmatch(token):
            return token
        return fallback

    def _update_theme_preview(self) -> None:
        defaults = self._defaults.ui.custom_theme
        primary = self._preview_color(self._theme_colors["primary_color"], defaults.primary_color)
        secondary = self._preview_color(
            self._theme_colors["secondary_color"],
            defaults.secondary_color,
        )
        highlight = self._preview_color(
            self._theme_colors["highlight_color"],
            defaults.highlight_color,
        )
        canvas = self._preview_color(self._theme_colors["canvas_color"], defaults.canvas_color)
        self._theme_preview.apply(
            primary=primary,
            secondary=secondary,
            highlight=highlight,
            canvas=canvas,
        )

    def _on_save(self) -> None:
        try:
            selected = self._build_selected_config()
        except (ValueError, ValidationError) as exc:
            QMessageBox.warning(self, "Settings", str(exc))
            return

        self._selected = selected
        self.accept()

    def _set_runtime_preset(self, preset: _RuntimePreset) -> None:
        self._runtime_max_queue.setValue(preset.max_queue_size)
        self._runtime_coalesce.setChecked(preset.coalesce_pending_inputs)
        self._runtime_max_batch.setValue(preset.max_deliveries_per_batch)

    def _apply_runtime_safe_preset(self) -> None:
        self._set_runtime_preset(_RUNTIME_PRESET_SAFE)

    def _apply_runtime_balanced_preset(self) -> None:
        self._set_runtime_preset(_RUNTIME_PRESET_BALANCED)

    def _apply_runtime_fast_preset(self) -> None:
        self._set_runtime_preset(_RUNTIME_PRESET_FAST)

    def _reset_runtime_defaults(self) -> None:
        self._apply_runtime_balanced_preset()

    def _reset_autosnapshot_defaults(self) -> None:
        defaults = self._defaults.autosnapshot
        self._autosnapshot_enabled.setChecked(defaults.enabled)
        self._autosnapshot_debounce.setValue(defaults.debounce_ms)
        self._autosnapshot_history.setValue(defaults.max_history)

    def _reset_provider_defaults(self) -> None:
        defaults = self._defaults.provider_network
        self._http_timeout.setValue(defaults.http.timeout_s)
        self._http_retries.setValue(defaults.http.retries)
        self._http_backoff.setValue(defaults.http.backoff_s)
        self._http_min_gap.setValue(defaults.http.min_gap_s)
        self._http_proxy.setText(defaults.http.proxy_url)
        self._yf_retries.setValue(defaults.yfinance.retries)
        self._yf_backoff.setValue(defaults.yfinance.backoff_s)

    def _reset_paths_defaults(self) -> None:
        self._project_path.clear()
        self._autosnapshot_path.clear()
        self._export_path.clear()

    def _reset_safety_defaults(self) -> None:
        defaults = self._defaults.safety_prompts
        self._prompt_module_remove.setChecked(defaults.confirm_module_remove)
        self._prompt_binding_remove.setChecked(defaults.confirm_binding_remove)
        self._prompt_canvas_delete.setChecked(defaults.confirm_canvas_delete)
        self._prompt_workspace_reset.setChecked(defaults.confirm_workspace_reset)
        self._prompt_load_unsaved.setChecked(defaults.confirm_load_over_unsaved)

    def _reset_theme_defaults(self) -> None:
        self._populate_theme_preset_dropdown(selected_token=_THEME_PRESET_DEFAULT)
        self._apply_theme_default_preset()

    def _build_selected_config(self) -> AppConfig:
        runtime = RuntimePolicyModel(
            max_queue_size=int(self._runtime_max_queue.value()),
            coalesce_pending_inputs=bool(self._runtime_coalesce.isChecked()),
            max_deliveries_per_batch=int(self._runtime_max_batch.value()),
        )

        autosnapshot = AutosnapshotPolicy(
            enabled=bool(self._autosnapshot_enabled.isChecked()),
            debounce_ms=int(self._autosnapshot_debounce.value()),
            max_history=int(self._autosnapshot_history.value()),
        )

        provider_network = ProviderNetworkPolicy(
            http=HttpNetworkPolicy(
                timeout_s=float(self._http_timeout.value()),
                retries=int(self._http_retries.value()),
                backoff_s=float(self._http_backoff.value()),
                min_gap_s=float(self._http_min_gap.value()),
                proxy_url=self._http_proxy.text().strip(),
            ),
            yfinance=YFinanceNetworkPolicy(
                retries=int(self._yf_retries.value()),
                backoff_s=float(self._yf_backoff.value()),
            ),
        )

        project_directory = self._project_path.text().strip() or None
        autosnapshot_directory = self._autosnapshot_path.text().strip() or None
        export_directory = self._export_path.text().strip() or None
        for label, token in (
            ("project_directory", project_directory),
            ("autosnapshot_directory", autosnapshot_directory),
            ("export_directory", export_directory),
        ):
            if token is not None and not Path(token).is_absolute():
                raise ValueError(f"{label} must be an absolute path.")

        paths = PathPolicy(
            project_directory=project_directory,
            autosnapshot_directory=autosnapshot_directory,
            export_directory=export_directory,
        )

        safety = SafetyPromptPolicy(
            confirm_module_remove=bool(self._prompt_module_remove.isChecked()),
            confirm_binding_remove=bool(self._prompt_binding_remove.isChecked()),
            confirm_canvas_delete=bool(self._prompt_canvas_delete.isChecked()),
            confirm_workspace_reset=bool(self._prompt_workspace_reset.isChecked()),
            confirm_load_over_unsaved=bool(self._prompt_load_unsaved.isChecked()),
        )

        custom_theme = CustomThemePolicy(
            primary_color=self._theme_colors["primary_color"].strip().upper(),
            secondary_color=self._theme_colors["secondary_color"].strip().upper(),
            highlight_color=self._theme_colors["highlight_color"].strip().upper(),
            canvas_color=self._theme_colors["canvas_color"].strip().upper(),
        )
        ui = UiPolicy(
            theme=self._selected_theme_preset_token(),
            custom_theme=custom_theme,
        )

        return AppConfig(
            version="AppConfig",
            runtime=runtime,
            ui=ui,
            autosnapshot=autosnapshot,
            provider_network=provider_network,
            paths=paths,
            safety_prompts=safety,
        )
