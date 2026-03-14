"""Line plotting sink for scientific and financial workflows."""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pyqtgraph as pg  # type: ignore[import-untyped]
import pyqtgraph.exporters  # type: ignore[import-untyped]
from numpy.typing import NDArray
from PySide6.QtCore import QDateTime, QPointF, Qt, QTimeZone
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from qt_modula.modules_builtin.export.path_utils import build_export_path
from qt_modula.sdk import (
    BaseModule,
    ModuleDescriptor,
    PortSpec,
    coerce_finite_float,
    is_truthy,
)
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height, set_expand

_DEFAULT_FILE_STEM = "line_plot"
_DEFAULT_SERIES = "series"
_DEFAULT_X_KEY = "x"
_DEFAULT_Y_KEY = "y"
_DEFAULT_X_MODE = "auto"
_DEFAULT_EPOCH_UNIT = "auto"
_DEFAULT_RANGE_MODE = "all"
_DEFAULT_FOLLOW_LATEST = True
_X_MODES = ("auto", "number", "datetime", "index")
_EPOCH_UNITS = ("auto", "s", "ms")
_RANGE_MODES = ("all", "last_n", "last_seconds", "x_between")
_PNG_EXPORT_MIN_WIDTH = 1920
_PNG_EXPORT_SCALE = 2
_PNG_EXPORT_MAX_WIDTH = 8192
_LOCK_AXIS_TIE_EPS_SCENE = 0.75
_Y_VIEW_PADDING_RATIO = 0.005
_AXIS_SPIN_MIN = -1_000_000_000_000_000.0
_AXIS_SPIN_MAX = 1_000_000_000_000_000.0
_DEFAULT_SHOW_LEGEND = True
_DEFAULT_SHOW_GRID = True
_DEFAULT_LOCAL_TIME = True
_GRID_ALPHA = int(255 * 0.25)
_DURATION_RE = re.compile(
    r"^P(?:(?P<weeks>\d+(?:\.\d+)?)W)?(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$",
    re.IGNORECASE,
)
_COLOR_PALETTE = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#4e79a7",
    "#f28e2c",
    "#59a14f",
    "#e15759",
    "#76b7b2",
    "#edc948",
)


@dataclass(slots=True)
class _SeriesBuilder:
    x: list[float]
    y: list[float]
    row_index: list[int]
    is_datetime: list[bool]


@dataclass(frozen=True, slots=True)
class _SeriesData:
    label: str
    x_sorted: NDArray[np.float64]
    y_sorted: NDArray[np.float64]
    row_indices_sorted: NDArray[np.int64]
    is_datetime_sorted: NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class _DisplaySeriesData:
    label: str
    raw_x_sorted: NDArray[np.float64]
    raw_y_sorted: NDArray[np.float64]
    display_x_sorted: NDArray[np.float64]
    display_y_sorted: NDArray[np.float64]
    row_indices_sorted: NDArray[np.int64]
    is_datetime_sorted: NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class _ParseResult:
    series: dict[str, _SeriesData]
    invalid_count: int


@dataclass(frozen=True, slots=True)
class _ActivePoint:
    series: str
    row_index: int
    x: float
    y: float
    view_x: float
    view_y: float
    is_datetime: bool


@dataclass(frozen=True, slots=True)
class _AxisTransform:
    raw_breaks: NDArray[np.float64]
    display_breaks: NDArray[np.float64]

    @classmethod
    def identity(cls) -> _AxisTransform:
        base = np.asarray([0.0, 1.0], dtype=np.float64)
        return cls(raw_breaks=base, display_breaks=base)

    @classmethod
    def from_values(
        cls,
        values: NDArray[np.float64],
        *,
        threshold: float,
        span: float,
    ) -> _AxisTransform:
        if values.size <= 1 or not np.isfinite(threshold) or threshold <= 0.0:
            return cls.identity()

        unique = np.unique(np.asarray(values, dtype=np.float64))
        if unique.size <= 1:
            return cls.identity()

        display = np.empty_like(unique)
        display[0] = unique[0]
        changed = False
        for index in range(1, int(unique.size)):
            raw_gap = float(unique[index] - unique[index - 1])
            display_gap = span if raw_gap >= threshold else raw_gap
            if raw_gap >= threshold and abs(display_gap - raw_gap) > 1e-12:
                changed = True
            display[index] = display[index - 1] + display_gap

        if not changed:
            return cls.identity()
        return cls(raw_breaks=unique, display_breaks=display)

    def is_identity(self) -> bool:
        return np.array_equal(self.raw_breaks, self.display_breaks)

    def _segment_scale(
        self,
        raw0: float,
        raw1: float,
        display0: float,
        display1: float,
        *,
        inverse: bool,
    ) -> float:
        raw_delta = raw1 - raw0
        display_delta = display1 - display0
        if inverse:
            if abs(display_delta) <= 1e-12 or not np.isfinite(display_delta):
                return 1.0
            return raw_delta / display_delta
        if abs(raw_delta) <= 1e-12 or not np.isfinite(raw_delta):
            return 1.0
        return display_delta / raw_delta

    def raw_to_display(self, value: float) -> float:
        if not np.isfinite(value):
            return value
        raw = self.raw_breaks
        display = self.display_breaks
        if raw.size < 2:
            return value
        if value <= float(raw[0]):
            scale = self._segment_scale(
                float(raw[0]), float(raw[1]), float(display[0]), float(display[1]), inverse=False
            )
            return float(display[0] + ((value - float(raw[0])) * scale))
        if value >= float(raw[-1]):
            scale = self._segment_scale(
                float(raw[-2]),
                float(raw[-1]),
                float(display[-2]),
                float(display[-1]),
                inverse=False,
            )
            return float(display[-1] + ((value - float(raw[-1])) * scale))

        index = int(np.searchsorted(raw, value, side="right")) - 1
        index = max(0, min(index, int(raw.size) - 2))
        raw0 = float(raw[index])
        raw1 = float(raw[index + 1])
        display0 = float(display[index])
        display1 = float(display[index + 1])
        scale = self._segment_scale(raw0, raw1, display0, display1, inverse=False)
        return float(display0 + ((value - raw0) * scale))

    def raw_to_display_array(self, values: NDArray[np.float64]) -> NDArray[np.float64]:
        if values.size <= 0 or self.is_identity():
            return np.asarray(values, dtype=np.float64)
        mapped = np.empty_like(values, dtype=np.float64)
        for index, value in enumerate(values):
            mapped[index] = self.raw_to_display(float(value))
        return mapped

    def display_to_raw(self, value: float) -> float:
        if not np.isfinite(value):
            return value
        raw = self.raw_breaks
        display = self.display_breaks
        if raw.size < 2:
            return value
        if value <= float(display[0]):
            scale = self._segment_scale(
                float(raw[0]), float(raw[1]), float(display[0]), float(display[1]), inverse=True
            )
            return float(raw[0] + ((value - float(display[0])) * scale))
        if value >= float(display[-1]):
            scale = self._segment_scale(
                float(raw[-2]), float(raw[-1]), float(display[-2]), float(display[-1]), inverse=True
            )
            return float(raw[-1] + ((value - float(display[-1])) * scale))

        index = int(np.searchsorted(display, value, side="right")) - 1
        index = max(0, min(index, int(display.size) - 2))
        raw0 = float(raw[index])
        raw1 = float(raw[index + 1])
        display0 = float(display[index])
        display1 = float(display[index + 1])
        if abs(display1 - display0) <= 1e-12:
            return raw1
        scale = self._segment_scale(raw0, raw1, display0, display1, inverse=True)
        return float(raw0 + ((value - display0) * scale))


class _CompressedAxisItem(pg.AxisItem):  # type: ignore[misc]
    def __init__(self, orientation: str, *, transform: _AxisTransform | None = None) -> None:
        super().__init__(orientation=orientation)
        self._transform = transform or _AxisTransform.identity()

    def set_transform(self, transform: _AxisTransform | None) -> None:
        self._transform = transform or _AxisTransform.identity()
        self.picture = None
        self.update()

    def tickValues(
        self, minVal: float, maxVal: float, size: float
    ) -> list[tuple[float, list[float]]]:
        if self._transform.is_identity():
            return cast(
                list[tuple[float, list[float]]],
                pg.AxisItem.tickValues(self, minVal, maxVal, size),
            )

        raw_min = self._transform.display_to_raw(minVal)
        raw_max = self._transform.display_to_raw(maxVal)
        raw_levels = pg.AxisItem.tickValues(self, raw_min, raw_max, size)
        tolerance = max(1e-9, abs(maxVal - minVal) / max(1.0, size))

        mapped_levels: list[tuple[float, list[float]]] = []
        for spacing, values in raw_levels:
            mapped_values: list[float] = []
            last_display: float | None = None
            for raw_value in values:
                display_value = self._transform.raw_to_display(float(raw_value))
                if not np.isfinite(display_value):
                    continue
                if last_display is not None and abs(display_value - last_display) <= tolerance:
                    continue
                mapped_values.append(display_value)
                last_display = display_value
            mapped_levels.append((spacing, mapped_values))
        return mapped_levels

    def tickStrings(self, values: list[float], scale: float, spacing: float) -> list[str]:
        if self._transform.is_identity():
            return cast(list[str], pg.AxisItem.tickStrings(self, values, scale, spacing))
        raw_values = [self._transform.display_to_raw(float(value)) for value in values]
        return cast(list[str], pg.AxisItem.tickStrings(self, raw_values, scale, spacing))


class _CompressedDateAxisItem(pg.DateAxisItem):  # type: ignore[misc]
    def __init__(
        self,
        orientation: str,
        *,
        transform: _AxisTransform | None = None,
        use_local_time: bool,
    ) -> None:
        super().__init__(
            orientation=orientation,
            utcOffset=None if use_local_time else 0,
        )
        self.utcOffset: int | None = None if use_local_time else 0
        self._transform = transform or _AxisTransform.identity()

    def set_transform(self, transform: _AxisTransform | None) -> None:
        self._transform = transform or _AxisTransform.identity()
        self.picture = None
        self.update()

    def set_timezone_mode(self, *, use_local_time: bool) -> None:
        utc_offset: int | None = None if use_local_time else 0
        current_offset = self.utcOffset
        if current_offset == utc_offset:
            return
        self.utcOffset = utc_offset
        self.picture = None
        self.update()

    def tickValues(
        self, minVal: float, maxVal: float, size: float
    ) -> list[tuple[float, list[float]]]:
        if self._transform.is_identity():
            return cast(
                list[tuple[float, list[float]]],
                pg.DateAxisItem.tickValues(self, minVal, maxVal, size),
            )

        raw_min = self._transform.display_to_raw(minVal)
        raw_max = self._transform.display_to_raw(maxVal)
        raw_levels = pg.DateAxisItem.tickValues(self, raw_min, raw_max, size)
        tolerance = max(1e-9, abs(maxVal - minVal) / max(1.0, size))

        mapped_levels: list[tuple[float, list[float]]] = []
        for spacing, values in raw_levels:
            mapped_values: list[float] = []
            last_display: float | None = None
            for raw_value in values:
                display_value = self._transform.raw_to_display(float(raw_value))
                if not np.isfinite(display_value):
                    continue
                if last_display is not None and abs(display_value - last_display) <= tolerance:
                    continue
                mapped_values.append(display_value)
                last_display = display_value
            mapped_levels.append((spacing, mapped_values))
        return mapped_levels

    def tickStrings(self, values: list[float], scale: float, spacing: float) -> list[str]:
        if self._transform.is_identity():
            return cast(list[str], pg.DateAxisItem.tickStrings(self, values, scale, spacing))
        raw_values = [self._transform.display_to_raw(float(value)) for value in values]
        return cast(list[str], pg.DateAxisItem.tickStrings(self, raw_values, scale, spacing))


class LinePlotterModule(BaseModule):
    """High-fidelity plotting sink with deterministic bind-chain outputs."""

    persistent_inputs = (
        "x_key",
        "y_key",
        "series_key",
        "x_mode",
        "epoch_unit",
        "max_points",
        "range_mode",
        "range_points",
        "range_seconds",
        "range_x_min",
        "x_compression_threshold",
        "x_compression_span",
        "y_compression_threshold",
        "y_compression_span",
        "follow_latest",
        "show_points",
        "antialias",
        "lock_on_click",
        "show_legend",
        "show_grid",
        "local_time",
        "export_folder",
        "file_name",
    )

    descriptor = ModuleDescriptor(
        module_type="line_plotter",
        display_name="Line Plotter",
        family="Analytics",
        description=(
            "Professional line plotting with strict range control, "
            "exact point-snapped hover, and export."
        ),
        capabilities=("sink", "transform"),
        inputs=(
            PortSpec("rows", "table", default=[], display_name="Rows"),
            PortSpec("row", "json", default={}, display_name="Live Row"),
            PortSpec(
                "append",
                "trigger",
                default=0,
                control_plane=True,
                display_name="Append Row",
            ),
            PortSpec(
                "clear",
                "trigger",
                default=0,
                control_plane=True,
                display_name="Clear Plot",
            ),
            PortSpec("x_key", "string", default=_DEFAULT_X_KEY, display_name="X Key"),
            PortSpec("y_key", "string", default=_DEFAULT_Y_KEY, display_name="Y Key"),
            PortSpec("series_key", "string", default="series", display_name="Series Key"),
            PortSpec("x_mode", "string", default=_DEFAULT_X_MODE, display_name="X Mode"),
            PortSpec(
                "epoch_unit",
                "string",
                default=_DEFAULT_EPOCH_UNIT,
                display_name="Epoch Unit",
                bind_visibility="advanced",
            ),
            PortSpec(
                "max_points",
                "integer",
                default=200_000,
                display_name="Max Points",
                bind_visibility="advanced",
            ),
            PortSpec(
                "range_mode",
                "string",
                default=_DEFAULT_RANGE_MODE,
                display_name="Range Mode",
            ),
            PortSpec("range_points", "integer", default=2_000, display_name="Range Points"),
            PortSpec(
                "range_seconds",
                "number",
                default=3_600.0,
                display_name="Range Span (Number)",
                bind_visibility="advanced",
            ),
            PortSpec(
                "range_seconds_iso",
                "string",
                default="",
                display_name="Range Duration",
            ),
            PortSpec(
                "range_x_min",
                "number",
                default=0.0,
                display_name="Range X Min (Number)",
                bind_visibility="advanced",
            ),
            PortSpec("range_x_min_iso", "string", default="", display_name="Range X Min"),
            PortSpec(
                "x_compression_threshold",
                "number",
                default=0.0,
                display_name="X Compression Threshold",
                bind_visibility="advanced",
            ),
            PortSpec(
                "x_compression_span",
                "number",
                default=0.0,
                display_name="X Compression Span",
                bind_visibility="advanced",
            ),
            PortSpec(
                "x_compression_threshold_iso",
                "string",
                default="",
                display_name="X Compression Threshold (ISO)",
                bind_visibility="advanced",
            ),
            PortSpec(
                "x_compression_span_iso",
                "string",
                default="",
                display_name="X Compression Span (ISO)",
                bind_visibility="advanced",
            ),
            PortSpec(
                "y_compression_threshold",
                "number",
                default=0.0,
                display_name="Y Compression Threshold",
                bind_visibility="advanced",
            ),
            PortSpec(
                "y_compression_span",
                "number",
                default=0.0,
                display_name="Y Compression Span",
                bind_visibility="advanced",
            ),
            PortSpec(
                "follow_latest",
                "boolean",
                default=_DEFAULT_FOLLOW_LATEST,
                display_name="Follow Latest",
            ),
            PortSpec(
                "show_points",
                "boolean",
                default=False,
                display_name="Show Points",
                bind_visibility="advanced",
            ),
            PortSpec(
                "antialias",
                "boolean",
                default=True,
                display_name="Antialias",
                bind_visibility="advanced",
            ),
            PortSpec(
                "lock_on_click",
                "boolean",
                default=True,
                display_name="Lock Hover On Click",
                bind_visibility="advanced",
            ),
            PortSpec(
                "show_legend",
                "boolean",
                default=_DEFAULT_SHOW_LEGEND,
                display_name="Show Legend",
                bind_visibility="advanced",
            ),
            PortSpec(
                "show_grid",
                "boolean",
                default=_DEFAULT_SHOW_GRID,
                display_name="Show Grid",
                bind_visibility="advanced",
            ),
            PortSpec(
                "local_time",
                "boolean",
                default=_DEFAULT_LOCAL_TIME,
                display_name="Local Time",
                bind_visibility="advanced",
            ),
            PortSpec(
                "reset_view",
                "trigger",
                default=0,
                control_plane=True,
                display_name="Reset View",
            ),
            PortSpec("export_folder", "string", default="", display_name="Export Folder"),
            PortSpec("file_name", "string", default=_DEFAULT_FILE_STEM, display_name="File Name"),
            PortSpec("tag", "string", default="", display_name="Tag"),
            PortSpec(
                "export_png",
                "trigger",
                default=0,
                control_plane=True,
                display_name="Export PNG",
            ),
            PortSpec(
                "export_svg",
                "trigger",
                default=0,
                control_plane=True,
                display_name="Export SVG",
            ),
        ),
        outputs=(
            PortSpec("point_count", "integer", default=0, display_name="Point Count"),
            PortSpec(
                "source_point_count",
                "integer",
                default=0,
                display_name="Source Point Count",
                bind_visibility="advanced",
            ),
            PortSpec("series_count", "integer", default=0, display_name="Series Count"),
            PortSpec(
                "invalid_count",
                "integer",
                default=0,
                display_name="Invalid Row Count",
                bind_visibility="advanced",
            ),
            PortSpec(
                "visible_x_min",
                "number",
                default=0.0,
                display_name="Visible X Min",
                bind_visibility="advanced",
            ),
            PortSpec(
                "visible_x_max",
                "number",
                default=0.0,
                display_name="Visible X Max",
                bind_visibility="advanced",
            ),
            PortSpec(
                "range_mode",
                "string",
                default=_DEFAULT_RANGE_MODE,
                display_name="Range Mode",
                bind_visibility="advanced",
            ),
            PortSpec("range_applied", "string", default="all", display_name="Range Applied"),
            PortSpec("hover_active", "boolean", default=False, display_name="Hover Active"),
            PortSpec("hover_series", "string", default="", display_name="Hover Series"),
            PortSpec(
                "hover_index",
                "integer",
                default=-1,
                display_name="Hover Index",
                bind_visibility="advanced",
            ),
            PortSpec("hover_x", "number", default=0.0, display_name="Hover X"),
            PortSpec("hover_y", "number", default=0.0, display_name="Hover Y"),
            PortSpec("hover_x_text", "string", default="", display_name="Hover X Text"),
            PortSpec("hover_y_text", "string", default="", display_name="Hover Y Text"),
            PortSpec("path", "string", default="", display_name="Export Path"),
            PortSpec(
                "exported",
                "trigger",
                default=0,
                control_plane=True,
                display_name="Exported",
            ),
            PortSpec("text", "string", default="", display_name="Status Text"),
            PortSpec("error", "string", default="", display_name="Error"),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)

        self._row_buffer: list[Any] = []
        self._pending_row: dict[str, Any] | None = None

        self._source_series_data: dict[str, _SeriesData] = {}
        self._series_data: dict[str, _SeriesData] = {}
        self._display_series_data: dict[str, _DisplaySeriesData] = {}
        self._display_series_items: tuple[tuple[str, _DisplaySeriesData], ...] = ()
        self._invalid_count = 0
        self._x_transform = _AxisTransform.identity()
        self._y_transform = _AxisTransform.identity()
        self._data_x_span = 1.0
        self._data_y_span = 1.0
        self._range_applied = "all"
        self._visible_x_bounds: tuple[float, float] | None = None
        self._option_warnings: dict[str, str] = {
            "x_mode": "",
            "epoch_unit": "",
            "range_mode": "",
            "range_x_min_iso": "",
            "range_seconds_iso": "",
            "x_compression_threshold": "",
            "x_compression_span": "",
            "x_compression_threshold_iso": "",
            "x_compression_span_iso": "",
        }
        self._using_datetime_axis = False

        self._plot_widget: Any | None = None
        self._plot_item: Any | None = None
        self._legend: Any | None = None
        self._curve_items: dict[str, Any] = {}
        self._crosshair_x: Any | None = None
        self._crosshair_y: Any | None = None
        self._locked_badge_bg_item: QGraphicsRectItem | None = None
        self._locked_badge_item: QGraphicsSimpleTextItem | None = None

        self._active_point: _ActivePoint | None = None
        self._hover_locked = False
        self._cursor_view: tuple[float, float] | None = None
        self._cached_view_range: tuple[float, float, float, float] | None = None
        self._enforcing_view = False

        self._x_key_edit: QLineEdit | None = None
        self._y_key_edit: QLineEdit | None = None
        self._series_key_edit: QLineEdit | None = None
        self._x_mode_combo: QComboBox | None = None
        self._epoch_unit_label: QLabel | None = None
        self._epoch_unit_combo: QComboBox | None = None
        self._max_points_spin: QSpinBox | None = None
        self._range_mode_combo: QComboBox | None = None
        self._range_points_label: QLabel | None = None
        self._range_points_spin: QSpinBox | None = None
        self._range_seconds_label: QLabel | None = None
        self._range_seconds_stack: QStackedWidget | None = None
        self._range_seconds_spin: QDoubleSpinBox | None = None
        self._range_seconds_iso_edit: QLineEdit | None = None
        self._range_x_min_label: QLabel | None = None
        self._range_x_min_stack: QStackedWidget | None = None
        self._range_x_min_spin: QDoubleSpinBox | None = None
        self._range_x_min_datetime_edit: QDateTimeEdit | None = None
        self._range_x_max_label: QLabel | None = None
        self._range_x_max_stack: QStackedWidget | None = None
        self._range_x_max_spin: QDoubleSpinBox | None = None
        self._range_x_max_datetime_edit: QDateTimeEdit | None = None
        self._x_compression_threshold_stack: QStackedWidget | None = None
        self._x_compression_threshold_spin: QDoubleSpinBox | None = None
        self._x_compression_threshold_iso_edit: QLineEdit | None = None
        self._x_compression_span_stack: QStackedWidget | None = None
        self._x_compression_span_spin: QDoubleSpinBox | None = None
        self._x_compression_span_iso_edit: QLineEdit | None = None
        self._y_compression_threshold_spin: QDoubleSpinBox | None = None
        self._y_compression_span_spin: QDoubleSpinBox | None = None
        self._follow_latest_check: QCheckBox | None = None
        self._show_points_check: QCheckBox | None = None
        self._antialias_check: QCheckBox | None = None
        self._lock_check: QCheckBox | None = None
        self._legend_check: QCheckBox | None = None
        self._grid_check: QCheckBox | None = None
        self._local_time_check: QCheckBox | None = None
        self._file_name_edit: QLineEdit | None = None
        self._tag_edit: QLineEdit | None = None
        self._export_folder_edit: QLineEdit | None = None
        self._summary_label: QLabel | None = None
        self._hover_label: QLabel | None = None
        self._core_options_bar: QPushButton | None = None
        self._core_options_container: QWidget | None = None
        self._core_options_expanded = False
        self._options_bar: QPushButton | None = None
        self._options_container: QWidget | None = None
        self._options_expanded = False

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        core_form = QFormLayout()

        self._x_key_edit = QLineEdit(self._normalized_x_key(str(self.inputs["x_key"])))
        self._x_key_edit.textChanged.connect(lambda text: self.receive_binding("x_key", text))
        set_control_height(self._x_key_edit)
        core_form.addRow("X Key", self._x_key_edit)

        self._y_key_edit = QLineEdit(self._normalized_y_key(str(self.inputs["y_key"])))
        self._y_key_edit.textChanged.connect(lambda text: self.receive_binding("y_key", text))
        set_control_height(self._y_key_edit)
        core_form.addRow("Y Key", self._y_key_edit)

        self._series_key_edit = QLineEdit(str(self.inputs["series_key"]))
        self._series_key_edit.textChanged.connect(
            lambda text: self.receive_binding("series_key", text)
        )
        set_control_height(self._series_key_edit)
        core_form.addRow("Series Key", self._series_key_edit)

        self._x_mode_combo = QComboBox()
        self._x_mode_combo.addItems(list(_X_MODES))
        x_mode_token, x_mode_warning = self._normalized_x_mode(str(self.inputs["x_mode"]))
        self.inputs["x_mode"] = x_mode_token
        self._option_warnings["x_mode"] = x_mode_warning
        self._x_mode_combo.setCurrentText(x_mode_token)
        self._x_mode_combo.currentTextChanged.connect(
            lambda text: self.receive_binding("x_mode", text)
        )
        set_control_height(self._x_mode_combo)
        core_form.addRow("X Mode", self._x_mode_combo)

        self._range_mode_combo = QComboBox()
        self._range_mode_combo.addItems(list(_RANGE_MODES))
        range_mode_token, range_mode_warning = self._normalized_range_mode(
            str(self.inputs["range_mode"])
        )
        self.inputs["range_mode"] = range_mode_token
        self._option_warnings["range_mode"] = range_mode_warning
        self._range_mode_combo.setCurrentText(range_mode_token)
        self._range_mode_combo.currentTextChanged.connect(
            lambda text: self.receive_binding("range_mode", text)
        )
        set_control_height(self._range_mode_combo)
        core_form.addRow("Range Mode", self._range_mode_combo)

        self._range_points_spin = QSpinBox()
        self._range_points_spin.setRange(1, 1_000_000)
        range_points = self._normalized_range_points(int(self.inputs["range_points"]))
        self.inputs["range_points"] = range_points
        self._range_points_spin.setValue(range_points)
        self._range_points_spin.valueChanged.connect(
            lambda value: self.receive_binding("range_points", int(value))
        )
        set_control_height(self._range_points_spin)
        self._range_points_label = QLabel("Range Points")
        core_form.addRow(self._range_points_label, self._range_points_spin)

        self._range_seconds_label = QLabel("Range Span")
        self._range_seconds_stack = QStackedWidget()
        self._range_seconds_spin = QDoubleSpinBox()
        self._range_seconds_spin.setRange(0.0, 1_000_000_000.0)
        self._range_seconds_spin.setDecimals(3)
        self._range_seconds_spin.setSingleStep(60.0)
        range_seconds = self._normalized_range_seconds(self.inputs["range_seconds"])
        self.inputs["range_seconds"] = range_seconds
        self._range_seconds_spin.setValue(range_seconds)
        self._range_seconds_spin.valueChanged.connect(
            lambda value: self.receive_binding("range_seconds", float(value))
        )
        set_control_height(self._range_seconds_spin)
        self._range_seconds_stack.addWidget(self._range_seconds_spin)
        self._range_seconds_iso_edit = QLineEdit(str(self.inputs["range_seconds_iso"]))
        self._range_seconds_iso_edit.setPlaceholderText("PT1H")
        self._range_seconds_iso_edit.editingFinished.connect(
            lambda: self.receive_binding(
                "range_seconds_iso",
                self._range_seconds_iso_edit.text()
                if self._range_seconds_iso_edit is not None
                else "",
            )
        )
        set_control_height(self._range_seconds_iso_edit)
        self._range_seconds_stack.addWidget(self._range_seconds_iso_edit)
        core_form.addRow(self._range_seconds_label, self._range_seconds_stack)

        self._range_x_min_label = QLabel("Range X Min")
        self._range_x_min_stack = QStackedWidget()
        self._range_x_min_spin = QDoubleSpinBox()
        self._range_x_min_spin.setRange(_AXIS_SPIN_MIN, _AXIS_SPIN_MAX)
        self._range_x_min_spin.setDecimals(6)
        range_x_min = self._normalized_range_bound(self.inputs["range_x_min"], default=0.0)
        self.inputs["range_x_min"] = range_x_min
        self._range_x_min_spin.setValue(range_x_min)
        self._range_x_min_spin.valueChanged.connect(
            lambda value: self.receive_binding("range_x_min", float(value))
        )
        set_control_height(self._range_x_min_spin)
        self._range_x_min_stack.addWidget(self._range_x_min_spin)
        self._range_x_min_datetime_edit = self._build_datetime_edit(
            lambda: self.receive_binding(
                "range_x_min_iso",
                self._datetime_edit_iso_value(self._range_x_min_datetime_edit),
            )
        )
        self._range_x_min_stack.addWidget(self._range_x_min_datetime_edit)
        core_form.addRow(self._range_x_min_label, self._range_x_min_stack)

        self._range_x_max_label = QLabel("Range X Max (Auto)")
        self._range_x_max_stack = QStackedWidget()
        self._range_x_max_spin = QDoubleSpinBox()
        self._range_x_max_spin.setRange(_AXIS_SPIN_MIN, _AXIS_SPIN_MAX)
        self._range_x_max_spin.setDecimals(6)
        self._range_x_max_spin.setReadOnly(True)
        self._range_x_max_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._range_x_max_spin.setToolTip("Automatically set from latest input data X.")
        set_control_height(self._range_x_max_spin)
        self._range_x_max_stack.addWidget(self._range_x_max_spin)
        self._range_x_max_datetime_edit = self._build_datetime_edit(lambda: None, read_only=True)
        self._range_x_max_stack.addWidget(self._range_x_max_datetime_edit)
        core_form.addRow(self._range_x_max_label, self._range_x_max_stack)

        self._follow_latest_check = QCheckBox("Follow Latest")
        self._follow_latest_check.setChecked(bool(self.inputs["follow_latest"]))
        self._follow_latest_check.toggled.connect(
            lambda checked: self.receive_binding("follow_latest", checked)
        )
        core_form.addRow("", self._follow_latest_check)

        self._core_options_bar = QPushButton()
        self._core_options_bar.setCheckable(True)
        self._core_options_bar.toggled.connect(self._set_core_options_expanded)
        set_control_height(self._core_options_bar)
        layout.addWidget(self._core_options_bar)

        self._core_options_container = QWidget()
        core_options_layout = QVBoxLayout(self._core_options_container)
        core_options_layout.setContentsMargins(0, 0, 0, 0)
        core_options_layout.setSpacing(0)
        core_options_layout.addLayout(core_form)
        layout.addWidget(self._core_options_container)
        self._set_core_options_expanded(False)

        self._options_bar = QPushButton()
        self._options_bar.setCheckable(True)
        self._options_bar.toggled.connect(self._set_options_expanded)
        set_control_height(self._options_bar)
        layout.addWidget(self._options_bar)

        self._options_container = QWidget()
        options_layout = QVBoxLayout(self._options_container)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(6)

        runtime_label = QLabel("Runtime")
        options_layout.addWidget(runtime_label)

        advanced_form = QFormLayout()
        self._epoch_unit_combo = QComboBox()
        self._epoch_unit_combo.addItems(list(_EPOCH_UNITS))
        epoch_token, epoch_warning = self._normalized_epoch_unit(str(self.inputs["epoch_unit"]))
        self.inputs["epoch_unit"] = epoch_token
        self._option_warnings["epoch_unit"] = epoch_warning
        self._epoch_unit_combo.setCurrentText(epoch_token)
        self._epoch_unit_combo.currentTextChanged.connect(
            lambda text: self.receive_binding("epoch_unit", text)
        )
        set_control_height(self._epoch_unit_combo)
        self._epoch_unit_label = QLabel("Epoch Unit")
        advanced_form.addRow(self._epoch_unit_label, self._epoch_unit_combo)

        self._max_points_spin = QSpinBox()
        self._max_points_spin.setRange(1, 1_000_000)
        max_points = self._normalized_max_points(int(self.inputs["max_points"]))
        self.inputs["max_points"] = max_points
        self._max_points_spin.setValue(max_points)
        self._max_points_spin.valueChanged.connect(
            lambda value: self.receive_binding("max_points", int(value))
        )
        set_control_height(self._max_points_spin)
        advanced_form.addRow("Max Points", self._max_points_spin)
        options_layout.addLayout(advanced_form)

        compression_label = QLabel("Compression")
        options_layout.addWidget(compression_label)

        compression_form = QFormLayout()
        self._x_compression_threshold_stack = QStackedWidget()
        self._x_compression_threshold_spin = self._build_span_spin(
            lambda value: self.receive_binding("x_compression_threshold", float(value))
        )
        self._x_compression_threshold_stack.addWidget(self._x_compression_threshold_spin)
        self._x_compression_threshold_iso_edit = self._build_duration_edit(
            "PT1H",
            lambda: self.receive_binding(
                "x_compression_threshold_iso",
                self._x_compression_threshold_iso_edit.text()
                if self._x_compression_threshold_iso_edit is not None
                else "",
            ),
        )
        self._x_compression_threshold_stack.addWidget(self._x_compression_threshold_iso_edit)
        compression_form.addRow("X Compression Threshold", self._x_compression_threshold_stack)

        self._x_compression_span_stack = QStackedWidget()
        self._x_compression_span_spin = self._build_span_spin(
            lambda value: self.receive_binding("x_compression_span", float(value))
        )
        self._x_compression_span_stack.addWidget(self._x_compression_span_spin)
        self._x_compression_span_iso_edit = self._build_duration_edit(
            "PT15M",
            lambda: self.receive_binding(
                "x_compression_span_iso",
                self._x_compression_span_iso_edit.text()
                if self._x_compression_span_iso_edit is not None
                else "",
            ),
        )
        self._x_compression_span_stack.addWidget(self._x_compression_span_iso_edit)
        compression_form.addRow("X Compression Span", self._x_compression_span_stack)

        self._y_compression_threshold_spin = self._build_span_spin(
            lambda value: self.receive_binding("y_compression_threshold", float(value))
        )
        compression_form.addRow("Y Compression Threshold", self._y_compression_threshold_spin)

        self._y_compression_span_spin = self._build_span_spin(
            lambda value: self.receive_binding("y_compression_span", float(value))
        )
        compression_form.addRow("Y Compression Span", self._y_compression_span_spin)
        options_layout.addLayout(compression_form)

        display_label = QLabel("Display")
        options_layout.addWidget(display_label)

        display_grid = QGridLayout()
        display_grid.setContentsMargins(0, 0, 0, 0)
        display_grid.setHorizontalSpacing(12)
        display_grid.setVerticalSpacing(6)

        self._show_points_check = QCheckBox("Show Points")
        self._show_points_check.setChecked(bool(self.inputs["show_points"]))
        self._show_points_check.toggled.connect(
            lambda checked: self.receive_binding("show_points", checked)
        )
        display_grid.addWidget(self._show_points_check, 0, 0)

        self._antialias_check = QCheckBox("Antialias")
        self._antialias_check.setChecked(bool(self.inputs["antialias"]))
        self._antialias_check.toggled.connect(
            lambda checked: self.receive_binding("antialias", checked)
        )
        display_grid.addWidget(self._antialias_check, 0, 1)

        self._lock_check = QCheckBox("Lock Hover On Click")
        self._lock_check.setChecked(bool(self.inputs["lock_on_click"]))
        self._lock_check.toggled.connect(
            lambda checked: self.receive_binding("lock_on_click", checked)
        )
        display_grid.addWidget(self._lock_check, 1, 0)

        self._legend_check = QCheckBox("Show Legend")
        self._legend_check.setChecked(bool(self.inputs["show_legend"]))
        self._legend_check.toggled.connect(
            lambda checked: self.receive_binding("show_legend", checked)
        )
        display_grid.addWidget(self._legend_check, 1, 1)

        self._grid_check = QCheckBox("Show Grid")
        self._grid_check.setChecked(bool(self.inputs["show_grid"]))
        self._grid_check.toggled.connect(lambda checked: self.receive_binding("show_grid", checked))
        display_grid.addWidget(self._grid_check, 2, 0)

        self._local_time_check = QCheckBox("Local Time")
        self._local_time_check.setChecked(bool(self.inputs["local_time"]))
        self._local_time_check.toggled.connect(
            lambda checked: self.receive_binding("local_time", checked)
        )
        display_grid.addWidget(self._local_time_check, 2, 1)

        options_layout.addLayout(display_grid)
        layout.addWidget(self._options_container)
        self._set_options_expanded(False)

        export_form = QFormLayout()

        file_tag_row = QHBoxLayout()
        file_tag_row.setContentsMargins(0, 0, 0, 0)
        file_tag_row.setSpacing(6)

        self._file_name_edit = QLineEdit(str(self.inputs["file_name"]))
        self._file_name_edit.textChanged.connect(
            lambda text: self.receive_binding("file_name", text)
        )
        set_control_height(self._file_name_edit)
        file_tag_row.addWidget(self._file_name_edit, 1)

        file_tag_row.addWidget(QLabel("Tag"))
        self._tag_edit = QLineEdit(str(self.inputs["tag"]))
        self._tag_edit.setPlaceholderText("optional")
        self._tag_edit.textChanged.connect(lambda text: self.receive_binding("tag", text))
        set_control_height(self._tag_edit)
        file_tag_row.addWidget(self._tag_edit)

        export_form.addRow("File Name", file_tag_row)

        self._export_folder_edit = QLineEdit(str(self.inputs["export_folder"]))
        self._export_folder_edit.textChanged.connect(
            lambda text: self.receive_binding("export_folder", text)
        )
        set_control_height(self._export_folder_edit)
        export_form.addRow("Export Folder", self._export_folder_edit)

        layout.addLayout(export_form)

        actions = QHBoxLayout()

        reset_btn = QPushButton("Reset View")
        reset_btn.clicked.connect(lambda: self.receive_binding("reset_view", 1))
        set_control_height(reset_btn)
        actions.addWidget(reset_btn)

        export_png_btn = QPushButton("Export PNG")
        export_png_btn.clicked.connect(lambda: self.receive_binding("export_png", 1))
        set_control_height(export_png_btn)
        actions.addWidget(export_png_btn)

        export_svg_btn = QPushButton("Export SVG")
        export_svg_btn.clicked.connect(lambda: self.receive_binding("export_svg", 1))
        set_control_height(export_svg_btn)
        actions.addWidget(export_svg_btn)

        layout.addLayout(actions)

        self._plot_widget = pg.PlotWidget()
        set_expand(self._plot_widget)
        self._plot_item = self._plot_widget.getPlotItem()
        self._plot_item.setClipToView(True)
        with suppress(Exception):
            self._plot_item.hideButtons()
        self._configure_axes(force=True)
        self._plot_item.setLabel("bottom", text=self._x_axis_label())
        self._plot_item.setLabel("left", text=self._y_axis_label())
        self._legend = self._plot_item.addLegend()
        view_box = self._plot_item.getViewBox()
        view_box.setMouseEnabled(x=False, y=True)
        view_box.sigRangeChanged.connect(self._on_view_range_changed)

        pen = pg.mkPen(color="#9a9a9a", width=1)
        self._crosshair_x = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        self._crosshair_y = pg.InfiniteLine(angle=0, movable=False, pen=pen)
        self._crosshair_x.setVisible(False)
        self._crosshair_y.setVisible(False)
        self._plot_item.addItem(self._crosshair_x, ignoreBounds=True)
        self._plot_item.addItem(self._crosshair_y, ignoreBounds=True)

        self._locked_badge_bg_item = QGraphicsRectItem(self._plot_item)
        self._locked_badge_bg_item.setPen(pg.mkPen(color=(88, 88, 88, 255), width=1))
        self._locked_badge_bg_item.setBrush(pg.mkBrush(0, 0, 0, 255))
        self._locked_badge_bg_item.setZValue(999_999)
        self._locked_badge_bg_item.setVisible(False)

        self._locked_badge_item = QGraphicsSimpleTextItem(self._plot_item)
        self._locked_badge_item.setBrush(pg.mkBrush("#d8d8d8"))
        self._locked_badge_item.setZValue(1_000_000)
        self._locked_badge_item.setVisible(False)
        with suppress(Exception):
            font = self._locked_badge_item.font()
            if font.pointSize() > 1:
                font.setPointSize(font.pointSize() - 1)
            self._locked_badge_item.setFont(font)
        self._position_locked_badge()

        scene = self._plot_widget.scene()
        scene.sigMouseMoved.connect(self._on_scene_mouse_moved)
        scene.sigMouseClicked.connect(self._on_scene_mouse_clicked)

        layout.addWidget(self._plot_widget, 1)

        self._hover_label = QLabel("")
        self._hover_label.setWordWrap(True)
        self._hover_label.setMinimumHeight(self._hover_label.fontMetrics().height() + 8)
        layout.addWidget(self._hover_label)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        self._sync_config_controls()
        self._rebuild_plot(reason="ready", preserve_view=False)
        self._sync_hover_label()
        return root

    def _build_span_spin(self, on_change: Any) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, _AXIS_SPIN_MAX)
        spin.setDecimals(6)
        spin.setSingleStep(1.0)
        spin.valueChanged.connect(on_change)
        set_control_height(spin)
        return spin

    def _build_duration_edit(self, placeholder: str, on_apply: Any) -> QLineEdit:
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        widget.editingFinished.connect(on_apply)
        set_control_height(widget)
        return widget

    def _build_datetime_edit(self, on_apply: Any, *, read_only: bool = False) -> QDateTimeEdit:
        widget = QDateTimeEdit()
        widget.setDisplayFormat("yyyy-MM-dd HH:mm:ss.zzz 'UTC'")
        widget.setTimeZone(QTimeZone.utc())
        widget.setDateTime(QDateTime.fromMSecsSinceEpoch(0, QTimeZone.utc()))
        widget.setReadOnly(read_only)
        if read_only:
            widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        else:
            widget.dateTimeChanged.connect(lambda _value: on_apply())
        set_control_height(widget)
        return widget

    @staticmethod
    def _datetime_edit_iso_value(widget: QDateTimeEdit | None) -> str:
        if widget is None:
            return ""
        return LinePlotterModule._format_timestamp_iso(
            widget.dateTime().toMSecsSinceEpoch() / 1000.0
        )

    @staticmethod
    def _format_timestamp_iso(epoch_seconds: float) -> str:
        if not np.isfinite(epoch_seconds):
            return ""
        value = QDateTime.fromMSecsSinceEpoch(
            int(round(epoch_seconds * 1000.0)),
            QTimeZone.utc(),
        )
        rendered = value.toString(Qt.DateFormat.ISODateWithMs)
        return rendered[:-6] + "Z" if rendered.endswith("+00:00") else rendered

    def _uses_datetime_controls(self) -> bool:
        mode, _ = self._normalized_x_mode(str(self.inputs["x_mode"]))
        return mode == "datetime" or (mode == "auto" and self._uses_datetime_axis())

    @staticmethod
    def _sync_stack(widget: QStackedWidget | None, use_datetime: bool) -> None:
        if widget is None:
            return
        index = 1 if use_datetime else 0
        if widget.currentIndex() != index:
            widget.setCurrentIndex(index)

    @staticmethod
    def _set_labeled_row_visible(
        label: QLabel | None,
        field: QWidget | None,
        visible: bool,
    ) -> None:
        if label is not None:
            label.setVisible(visible)
        if field is not None:
            field.setVisible(visible)

    @staticmethod
    def _sync_datetime_widget(widget: QDateTimeEdit | None, epoch_seconds: float) -> None:
        if widget is None or not np.isfinite(epoch_seconds):
            return
        target = QDateTime.fromMSecsSinceEpoch(
            int(round(epoch_seconds * 1000.0)),
            QTimeZone.utc(),
        )
        current = widget.dateTime()
        if current.toMSecsSinceEpoch() == target.toMSecsSinceEpoch():
            return
        widget.blockSignals(True)
        widget.setDateTime(target)
        widget.blockSignals(False)

    def _sync_config_controls(self) -> None:
        x_mode, _ = self._normalized_x_mode(str(self.inputs["x_mode"]))
        range_mode, _ = self._normalized_range_mode(str(self.inputs["range_mode"]))
        use_datetime = self._uses_datetime_controls()
        self._sync_stack(self._range_seconds_stack, use_datetime)
        self._sync_stack(self._range_x_min_stack, use_datetime)
        self._sync_stack(self._range_x_max_stack, use_datetime)
        self._sync_stack(self._x_compression_threshold_stack, use_datetime)
        self._sync_stack(self._x_compression_span_stack, use_datetime)

        self._set_labeled_row_visible(
            self._epoch_unit_label,
            self._epoch_unit_combo,
            x_mode in {"auto", "datetime"},
        )
        self._set_labeled_row_visible(
            self._range_points_label,
            self._range_points_spin,
            range_mode == "last_n",
        )
        self._set_labeled_row_visible(
            self._range_seconds_label,
            self._range_seconds_stack,
            range_mode == "last_seconds",
        )
        self._set_labeled_row_visible(
            self._range_x_min_label,
            self._range_x_min_stack,
            range_mode == "x_between",
        )
        self._set_labeled_row_visible(
            self._range_x_max_label,
            self._range_x_max_stack,
            range_mode == "x_between",
        )

        if self._range_seconds_label is not None:
            self._range_seconds_label.setText("Range Duration" if use_datetime else "Range Span")

        range_seconds = self._normalized_range_seconds(self.inputs["range_seconds"])
        self.inputs["range_seconds"] = range_seconds
        self._sync_double_spin(self._range_seconds_spin, range_seconds)
        range_seconds_iso = self._format_duration_iso(range_seconds)
        if not self._option_warnings["range_seconds_iso"]:
            self.inputs["range_seconds_iso"] = range_seconds_iso
            self._sync_line_edit(self._range_seconds_iso_edit, range_seconds_iso)

        range_x_min = self._normalized_range_bound(self.inputs["range_x_min"], default=0.0)
        self.inputs["range_x_min"] = range_x_min
        self._sync_double_spin(self._range_x_min_spin, range_x_min)
        self._sync_datetime_widget(self._range_x_min_datetime_edit, range_x_min)
        if not self._option_warnings["range_x_min_iso"]:
            self.inputs["range_x_min_iso"] = self._format_timestamp_iso(range_x_min)

        x_threshold, x_span = self._current_compression_pair("x")
        y_threshold, y_span = self._current_compression_pair("y")
        self._sync_double_spin(self._x_compression_threshold_spin, x_threshold)
        self._sync_double_spin(self._x_compression_span_spin, x_span)
        self._sync_double_spin(self._y_compression_threshold_spin, y_threshold)
        self._sync_double_spin(self._y_compression_span_spin, y_span)
        x_threshold_iso = self._format_duration_iso(x_threshold)
        x_span_iso = self._format_duration_iso(x_span)
        if not self._option_warnings["x_compression_threshold_iso"]:
            self.inputs["x_compression_threshold_iso"] = x_threshold_iso
            self._sync_line_edit(self._x_compression_threshold_iso_edit, x_threshold_iso)
        if not self._option_warnings["x_compression_span_iso"]:
            self.inputs["x_compression_span_iso"] = x_span_iso
            self._sync_line_edit(self._x_compression_span_iso_edit, x_span_iso)

        self._sync_auto_range_x_max_display(self._auto_range_x_max())

    @staticmethod
    def _parse_iso_duration(value: str) -> float | None:
        token = value.strip().upper()
        if not token:
            return 0.0
        match = _DURATION_RE.fullmatch(token)
        if match is None:
            return None

        weeks = float(match.group("weeks") or 0.0)
        days = float(match.group("days") or 0.0)
        hours = float(match.group("hours") or 0.0)
        minutes = float(match.group("minutes") or 0.0)
        seconds = float(match.group("seconds") or 0.0)
        total = (weeks * 7.0 * 86400.0) + (days * 86400.0) + (hours * 3600.0)
        total += (minutes * 60.0) + seconds
        return total if np.isfinite(total) and total >= 0.0 else None

    @staticmethod
    def _format_duration_iso(seconds: float) -> str:
        if not np.isfinite(seconds) or seconds <= 0.0:
            return "PT0S"

        total = float(seconds)
        days = int(total // 86400.0)
        total -= days * 86400.0
        hours = int(total // 3600.0)
        total -= hours * 3600.0
        minutes = int(total // 60.0)
        total -= minutes * 60.0
        secs = round(total, 3)

        parts: list[str] = ["P"]
        if days > 0:
            parts.append(f"{days}D")

        time_parts: list[str] = []
        if hours > 0:
            time_parts.append(f"{hours}H")
        if minutes > 0:
            time_parts.append(f"{minutes}M")
        if secs > 0.0 or (not time_parts and days <= 0):
            if abs(secs - round(secs)) <= 1e-9:
                time_parts.append(f"{int(round(secs))}S")
            else:
                time_parts.append(f"{secs:.3f}".rstrip("0").rstrip(".") + "S")

        if time_parts:
            parts.append("T")
            parts.extend(time_parts)

        return "".join(parts)

    def _sync_auto_range_x_max_display(self, value: float | None) -> None:
        numeric = 0.0 if value is None or not np.isfinite(value) else float(value)
        self._sync_double_spin(self._range_x_max_spin, numeric)
        self._sync_datetime_widget(self._range_x_max_datetime_edit, numeric)

    def _current_compression_pair(self, axis: str) -> tuple[float, float]:
        threshold = max(
            0.0,
            self._normalized_range_seconds(self.inputs.get(f"{axis}_compression_threshold", 0.0)),
        )
        span = max(
            0.0,
            self._normalized_range_seconds(self.inputs.get(f"{axis}_compression_span", 0.0)),
        )
        if threshold <= 0.0:
            span = 0.0
        elif span > threshold:
            span = threshold
        self.inputs[f"{axis}_compression_threshold"] = threshold
        self.inputs[f"{axis}_compression_span"] = span
        return threshold, span

    def _normalized_compression_pair(self, axis: str) -> tuple[float, float, str]:
        threshold = max(
            0.0,
            self._normalized_range_seconds(self.inputs.get(f"{axis}_compression_threshold", 0.0)),
        )
        requested_span = max(
            0.0,
            self._normalized_range_seconds(self.inputs.get(f"{axis}_compression_span", 0.0)),
        )
        span = requested_span
        warning = ""
        if threshold <= 0.0:
            if requested_span > 0.0:
                span = 0.0
                warning = (
                    f"{axis}_compression_span clamped to 0 while {axis}_compression_threshold <= 0"
                )
        elif requested_span > threshold:
            span = threshold
            warning = f"{axis}_compression_span clamped to <= {axis}_compression_threshold"

        self.inputs[f"{axis}_compression_threshold"] = threshold
        self.inputs[f"{axis}_compression_span"] = span
        return threshold, span, warning

    def _apply_numeric_seconds_input(
        self,
        *,
        port: str,
        value: Any,
        reason: str,
        preserve_view: bool,
    ) -> str | None:
        requested_seconds = coerce_finite_float(value)
        if requested_seconds is None:
            self._publish_summary(
                f"{port} ignored",
                error=self._compose_error(f"{port} must be a finite number"),
            )
            return None
        normalized_seconds = max(0.0, requested_seconds)
        self.inputs[port] = normalized_seconds
        self._option_warnings[f"{port}_iso"] = ""
        clamp_message = f"{port} clamped to >= 0" if requested_seconds < 0.0 else ""
        return self._rebuild_config(
            reason=reason, preserve_view=preserve_view, base_error=clamp_message
        )

    def _apply_duration_mirror_input(
        self,
        *,
        mirror_port: str,
        numeric_port: str,
        value: str,
        reason: str,
        preserve_view: bool,
    ) -> str | None:
        parsed = self._parse_iso_duration(value)
        if parsed is None:
            self._option_warnings[mirror_port] = f"invalid {mirror_port} '{value}'"
            self._publish_summary(reason, error=self._compose_error(self._validation_message()))
            return None
        self.inputs[mirror_port] = value
        self.inputs[numeric_port] = parsed
        self._option_warnings[mirror_port] = ""
        return self._rebuild_config(reason=reason, preserve_view=preserve_view, base_error="")

    def _apply_timestamp_mirror_input(
        self,
        *,
        mirror_port: str,
        numeric_port: str,
        value: str,
        reason: str,
        preserve_view: bool,
    ) -> str | None:
        parsed = self._parse_iso_timestamp(value)
        if parsed is None:
            self._option_warnings[mirror_port] = f"invalid {mirror_port} '{value}'"
            self._publish_summary(reason, error=self._compose_error(self._validation_message()))
            return None
        self.inputs[mirror_port] = value
        self.inputs[numeric_port] = parsed
        self._option_warnings[mirror_port] = ""
        return self._rebuild_config(reason=reason, preserve_view=preserve_view, base_error="")

    def _rebuild_config(
        self,
        *,
        reason: str,
        preserve_view: bool,
        base_error: str,
    ) -> str:
        compression_warnings: list[str] = []
        for axis in ("x", "y"):
            _, _, warning = self._normalized_compression_pair(axis)
            if warning:
                compression_warnings.append(warning)
        self._sync_config_controls()

        error = base_error
        if compression_warnings:
            joined = "; ".join(compression_warnings)
            error = joined if not error else f"{error}; {joined}"
        self._rebuild_plot(
            reason=reason,
            preserve_view=preserve_view,
            error_override=error if error else None,
        )
        return error

    def on_input(self, port: str, value: Any) -> None:
        if port == "rows":
            self._row_buffer = list(value) if isinstance(value, list) else []
            trimmed = self._trim_rows_to_max_points()
            reason = "rows replaced" if trimmed == 0 else f"rows replaced (trimmed {trimmed})"
            self._rebuild_plot(reason=reason, preserve_view=False)
            return

        if port == "row":
            if isinstance(value, dict):
                self._pending_row = {str(key): payload for key, payload in value.items()}
                self._publish_summary(
                    "row cached",
                    error=self._compose_error(self._validation_message()),
                )
            else:
                self._pending_row = None
                self._publish_summary(
                    "row rejected",
                    error=self._compose_error("row must be a JSON object"),
                )
            return

        if port == "append" and is_truthy(value):
            if self._pending_row is None:
                self._publish_summary("append ignored", error=self._compose_error("no pending row"))
                return
            self._row_buffer.append(dict(self._pending_row))
            trimmed = self._trim_rows_to_max_points()
            reason = "row appended" if trimmed == 0 else f"row appended (trimmed {trimmed})"
            preserve_view = not bool(self.inputs["follow_latest"])
            self._rebuild_plot(reason=reason, preserve_view=preserve_view)
            return

        if port == "clear" and is_truthy(value):
            self._row_buffer = []
            self._pending_row = None
            self._source_series_data = {}
            self._series_data = {}
            self._display_series_data = {}
            self._display_series_items = ()
            self._invalid_count = 0
            self._range_applied = "all"
            self._visible_x_bounds = None
            self._x_transform = _AxisTransform.identity()
            self._y_transform = _AxisTransform.identity()
            self._cached_view_range = None
            self._sync_auto_range_x_max_display(0.0)
            self._hover_locked = False
            self._cursor_view = None
            self._sync_config_controls()
            self._clear_hover(force_emit=True)
            self._render_series()
            self.emit("path", "")
            self.emit("exported", 0)
            self._publish_summary("cleared", error="")
            return

        if port == "x_key":
            token = self._normalized_x_key(str(value))
            self.inputs["x_key"] = token
            self._sync_line_edit(self._x_key_edit, token)
            self._rebuild_plot(reason="x_key updated", preserve_view=True)
            return

        if port == "y_key":
            token = self._normalized_y_key(str(value))
            self.inputs["y_key"] = token
            self._sync_line_edit(self._y_key_edit, token)
            self._rebuild_plot(reason="y_key updated", preserve_view=True)
            return

        if port == "series_key":
            token = str(value).strip()
            self.inputs["series_key"] = token
            self._sync_line_edit(self._series_key_edit, token)
            self._rebuild_plot(reason="series_key updated", preserve_view=True)
            return

        if port == "x_mode":
            token, warning = self._normalized_x_mode(str(value))
            self.inputs["x_mode"] = token
            self._option_warnings["x_mode"] = warning
            self._sync_combo(self._x_mode_combo, token)
            self._rebuild_plot(reason="x_mode updated", preserve_view=False)
            return

        if port == "epoch_unit":
            token, warning = self._normalized_epoch_unit(str(value))
            self.inputs["epoch_unit"] = token
            self._option_warnings["epoch_unit"] = warning
            self._sync_combo(self._epoch_unit_combo, token)
            self._rebuild_plot(reason="epoch_unit updated", preserve_view=True)
            return

        if port == "max_points":
            requested = int(value)
            normalized = self._normalized_max_points(requested)
            self.inputs["max_points"] = normalized
            self._sync_spin(self._max_points_spin, normalized)
            trimmed = self._trim_rows_to_max_points()
            error = self._validation_message()
            if requested != normalized:
                clamp_message = "max_points clamped to [1, 1000000]"
                error = clamp_message if not error else f"{clamp_message}; {error}"
            reason = (
                "max_points updated" if trimmed == 0 else f"max_points updated (trimmed {trimmed})"
            )
            self._rebuild_plot(reason=reason, preserve_view=True, error_override=error)
            return

        if port == "range_mode":
            token, warning = self._normalized_range_mode(str(value))
            self.inputs["range_mode"] = token
            self._option_warnings["range_mode"] = warning
            self._sync_combo(self._range_mode_combo, token)
            self._rebuild_plot(reason="range_mode updated", preserve_view=False)
            return

        if port == "range_points":
            requested = int(value)
            normalized = self._normalized_range_points(requested)
            self.inputs["range_points"] = normalized
            self._sync_spin(self._range_points_spin, normalized)
            error = self._validation_message()
            if requested != normalized:
                clamp_message = "range_points clamped to [1, 1000000]"
                error = clamp_message if not error else f"{clamp_message}; {error}"
            self._rebuild_plot(
                reason="range_points updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
                error_override=error,
            )
            return

        if port == "range_seconds":
            rebuild_error = self._apply_numeric_seconds_input(
                port="range_seconds",
                value=value,
                reason="range_seconds updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            if rebuild_error is not None:
                self._sync_config_controls()
            return

        if port == "range_seconds_iso":
            self._apply_duration_mirror_input(
                mirror_port="range_seconds_iso",
                numeric_port="range_seconds",
                value=str(value),
                reason="range_seconds_iso updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            self._sync_config_controls()
            return

        if port == "range_x_min":
            parsed = coerce_finite_float(value)
            if parsed is None:
                self._publish_summary(
                    "range_x_min ignored",
                    error=self._compose_error("range_x_min must be a finite number"),
                )
                return
            self.inputs["range_x_min"] = parsed
            self._option_warnings["range_x_min_iso"] = ""
            self._sync_config_controls()
            self._rebuild_plot(
                reason="range_x_min updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            return

        if port == "range_x_min_iso":
            self._apply_timestamp_mirror_input(
                mirror_port="range_x_min_iso",
                numeric_port="range_x_min",
                value=str(value),
                reason="range_x_min_iso updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            self._sync_config_controls()
            return

        if port == "x_compression_threshold":
            self._apply_numeric_seconds_input(
                port="x_compression_threshold",
                value=value,
                reason="x_compression_threshold updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            self._sync_config_controls()
            return

        if port == "x_compression_span":
            self._apply_numeric_seconds_input(
                port="x_compression_span",
                value=value,
                reason="x_compression_span updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            self._sync_config_controls()
            return

        if port == "x_compression_threshold_iso":
            self._apply_duration_mirror_input(
                mirror_port="x_compression_threshold_iso",
                numeric_port="x_compression_threshold",
                value=str(value),
                reason="x_compression_threshold_iso updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            self._sync_config_controls()
            return

        if port == "x_compression_span_iso":
            self._apply_duration_mirror_input(
                mirror_port="x_compression_span_iso",
                numeric_port="x_compression_span",
                value=str(value),
                reason="x_compression_span_iso updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            self._sync_config_controls()
            return

        if port == "y_compression_threshold":
            self._apply_numeric_seconds_input(
                port="y_compression_threshold",
                value=value,
                reason="y_compression_threshold updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            self._sync_config_controls()
            return

        if port == "y_compression_span":
            self._apply_numeric_seconds_input(
                port="y_compression_span",
                value=value,
                reason="y_compression_span updated",
                preserve_view=not bool(self.inputs["follow_latest"]),
            )
            self._sync_config_controls()
            return

        if port == "follow_latest":
            enabled = bool(value)
            self.inputs["follow_latest"] = enabled
            self._sync_checkbox(self._follow_latest_check, enabled)
            self._publish_summary(
                "follow_latest updated",
                error=self._compose_error(self._validation_message()),
            )
            return

        if port == "show_points":
            enabled = bool(value)
            self.inputs["show_points"] = enabled
            self._sync_checkbox(self._show_points_check, enabled)
            self._render_series()
            self._publish_summary(
                "show_points updated",
                error=self._compose_error(self._validation_message()),
            )
            return

        if port == "antialias":
            enabled = bool(value)
            self.inputs["antialias"] = enabled
            self._sync_checkbox(self._antialias_check, enabled)
            self._render_series()
            self._publish_summary(
                "antialias updated",
                error=self._compose_error(self._validation_message()),
            )
            return

        if port == "lock_on_click":
            enabled = bool(value)
            self.inputs["lock_on_click"] = enabled
            self._sync_checkbox(self._lock_check, enabled)
            if not enabled and self._hover_locked:
                self._hover_locked = False
                self._clear_hover(force_emit=True)
            self._publish_summary(
                "lock_on_click updated",
                error=self._compose_error(self._validation_message()),
            )
            return

        if port == "show_legend":
            enabled = bool(value)
            self.inputs["show_legend"] = enabled
            self._sync_checkbox(self._legend_check, enabled)
            self._sync_plot_display_state()
            self._publish_summary(
                "show_legend updated",
                error=self._compose_error(self._validation_message()),
            )
            return

        if port == "show_grid":
            enabled = bool(value)
            self.inputs["show_grid"] = enabled
            self._sync_checkbox(self._grid_check, enabled)
            self._sync_plot_display_state()
            self._publish_summary(
                "show_grid updated",
                error=self._compose_error(self._validation_message()),
            )
            return

        if port == "local_time":
            enabled = bool(value)
            self.inputs["local_time"] = enabled
            self._sync_checkbox(self._local_time_check, enabled)
            self._rebuild_plot(reason="local_time updated", preserve_view=True)
            return

        if port == "reset_view" and is_truthy(value):
            self._rebuild_plot(reason="view reset", preserve_view=False)
            return

        if port == "export_folder":
            text = str(value)
            self.inputs["export_folder"] = text
            self._sync_line_edit(self._export_folder_edit, text)
            self._publish_summary(
                "export_folder updated",
                error=self._compose_error(self._validation_message()),
            )
            return

        if port == "file_name":
            text = str(value).strip() or _DEFAULT_FILE_STEM
            self.inputs["file_name"] = text
            self._sync_line_edit(self._file_name_edit, text)
            self._publish_summary(
                "file_name updated",
                error=self._compose_error(self._validation_message()),
            )
            return

        if port == "tag":
            text = str(value)
            self.inputs["tag"] = text
            self._sync_line_edit(self._tag_edit, text)
            self._publish_summary(
                "tag updated",
                error=self._compose_error(self._validation_message()),
            )
            return

        if port == "export_png" and is_truthy(value):
            self._export_plot("png")
            return

        if port == "export_svg" and is_truthy(value):
            self._export_plot("svg")

    def _rebuild_plot(
        self,
        *,
        reason: str,
        preserve_view: bool,
        error_override: str | None = None,
    ) -> None:
        previous_range = self._view_range() if preserve_view else None
        previous_y_bounds = self._target_y_view_bounds() if preserve_view else None

        parsed = self._parse_rows()
        self._source_series_data = parsed.series
        self._invalid_count = parsed.invalid_count
        self._sync_auto_range_x_max_display(self._auto_range_x_max())

        (
            self._series_data,
            self._range_applied,
            self._visible_x_bounds,
        ) = self._apply_range_to_series(self._source_series_data)
        self._x_transform = self._build_axis_transform("x", self._series_data)
        self._y_transform = self._build_axis_transform("y", self._series_data)
        self._display_series_data = self._build_display_series(self._series_data)
        self._display_series_items = tuple(self._display_series_data.items())
        self._data_x_span, self._data_y_span = self._compute_display_spans(
            self._display_series_data
        )
        self._cached_view_range = None
        self._configure_axes(force=False)
        self._sync_config_controls()

        self._hover_locked = False
        self._clear_hover(force_emit=True)

        self._render_series()

        x_bounds = self._target_x_view_bounds()
        y_bounds = self._target_y_view_bounds()
        self._apply_x_limits(x_bounds)
        self._apply_y_limits(y_bounds)
        self._apply_target_view(
            previous_range=previous_range,
            previous_y_bounds=previous_y_bounds,
            x_bounds=x_bounds,
            y_bounds=y_bounds,
        )
        self._enforce_view_bounds()

        if self._plot_item is not None:
            self._plot_item.setLabel("bottom", text=self._x_axis_label())
            self._plot_item.setLabel("left", text=self._y_axis_label())

        self._sync_plot_display_state()

        base_error = error_override if error_override is not None else self._validation_message()
        error = self._compose_error(base_error)
        self._publish_summary(reason, error=error)

    def _build_axis_transform(
        self,
        axis: str,
        series: dict[str, _SeriesData],
    ) -> _AxisTransform:
        threshold, span, _ = self._normalized_compression_pair(axis)
        if threshold <= 0.0 or not series:
            return _AxisTransform.identity()

        values: list[NDArray[np.float64]] = []
        for bucket in series.values():
            values.append(bucket.x_sorted if axis == "x" else bucket.y_sorted)
        if not values:
            return _AxisTransform.identity()
        merged = np.concatenate(values)
        return _AxisTransform.from_values(merged, threshold=threshold, span=span)

    def _build_display_series(
        self,
        series: dict[str, _SeriesData],
    ) -> dict[str, _DisplaySeriesData]:
        display_series: dict[str, _DisplaySeriesData] = {}
        for label, bucket in series.items():
            display_series[label] = _DisplaySeriesData(
                label=label,
                raw_x_sorted=bucket.x_sorted,
                raw_y_sorted=bucket.y_sorted,
                display_x_sorted=self._x_transform.raw_to_display_array(bucket.x_sorted),
                display_y_sorted=self._y_transform.raw_to_display_array(bucket.y_sorted),
                row_indices_sorted=bucket.row_indices_sorted,
                is_datetime_sorted=bucket.is_datetime_sorted,
            )
        return display_series

    def _parse_rows(self) -> _ParseResult:
        grouped: dict[str, _SeriesBuilder] = {}
        invalid_count = 0

        x_key = self._normalized_x_key(str(self.inputs["x_key"]))
        y_key = self._normalized_y_key(str(self.inputs["y_key"]))
        series_key = str(self.inputs["series_key"]).strip()
        x_mode, _ = self._normalized_x_mode(str(self.inputs["x_mode"]))
        epoch_unit, _ = self._normalized_epoch_unit(str(self.inputs["epoch_unit"]))

        for row_index, row in enumerate(self._row_buffer):
            if not isinstance(row, dict):
                invalid_count += 1
                continue

            y_value = coerce_finite_float(row.get(y_key))
            if y_value is None:
                invalid_count += 1
                continue

            x_parsed = self._parse_x_value(
                row=row,
                row_index=row_index,
                x_key=x_key,
                x_mode=x_mode,
                epoch_unit=epoch_unit,
            )
            if x_parsed is None:
                invalid_count += 1
                continue

            x_value, is_datetime = x_parsed
            label = self._resolve_series_label(row, series_key)
            bucket = grouped.get(label)
            if bucket is None:
                bucket = _SeriesBuilder(x=[], y=[], row_index=[], is_datetime=[])
                grouped[label] = bucket

            bucket.x.append(x_value)
            bucket.y.append(y_value)
            bucket.row_index.append(row_index)
            bucket.is_datetime.append(is_datetime)

        series: dict[str, _SeriesData] = {}
        for label in sorted(grouped):
            bucket = grouped[label]
            x_array = np.asarray(bucket.x, dtype=np.float64)
            if x_array.size == 0:
                continue
            y_array = np.asarray(bucket.y, dtype=np.float64)
            row_indices = np.asarray(bucket.row_index, dtype=np.int64)
            dt_flags = np.asarray(bucket.is_datetime, dtype=np.bool_)
            order = np.argsort(x_array, kind="mergesort")
            series[label] = _SeriesData(
                label=label,
                x_sorted=x_array[order],
                y_sorted=y_array[order],
                row_indices_sorted=row_indices[order],
                is_datetime_sorted=dt_flags[order],
            )

        return _ParseResult(series=series, invalid_count=invalid_count)

    def _apply_range_to_series(
        self,
        source: dict[str, _SeriesData],
    ) -> tuple[dict[str, _SeriesData], str, tuple[float, float] | None]:
        mode, _ = self._normalized_range_mode(str(self.inputs["range_mode"]))
        if not source:
            return ({}, mode, None)

        visible: dict[str, _SeriesData] = {}

        if mode == "all":
            visible = dict(source)
            return visible, "all", self._x_bounds_for_series(visible)

        if mode == "last_n":
            count = self._normalized_range_points(int(self.inputs["range_points"]))
            for label, series in source.items():
                size = int(series.x_sorted.size)
                if size <= 0:
                    continue
                start = max(0, size - count)
                visible[label] = _SeriesData(
                    label=series.label,
                    x_sorted=series.x_sorted[start:],
                    y_sorted=series.y_sorted[start:],
                    row_indices_sorted=series.row_indices_sorted[start:],
                    is_datetime_sorted=series.is_datetime_sorted[start:],
                )
            return visible, f"last_n({count})", self._x_bounds_for_series(visible)

        if mode == "last_seconds":
            seconds = self._normalized_range_seconds(self.inputs["range_seconds"])
            source_bounds = self._x_bounds_for_series(source)
            if source_bounds is None:
                return ({}, f"last_seconds({self._format_duration_text(seconds)})", None)
            lower = source_bounds[1] - seconds
            for label, series in source.items():
                mask = series.x_sorted >= lower
                if not bool(np.any(mask)):
                    continue
                visible[label] = _SeriesData(
                    label=series.label,
                    x_sorted=series.x_sorted[mask],
                    y_sorted=series.y_sorted[mask],
                    row_indices_sorted=series.row_indices_sorted[mask],
                    is_datetime_sorted=series.is_datetime_sorted[mask],
                )
            return (
                visible,
                f"last_seconds({self._format_duration_text(seconds)})",
                self._x_bounds_for_series(visible),
            )

        between = self._x_between_bounds()
        if between is None:
            return ({}, "x_between(none)", None)
        lower, upper = between
        for label, series in source.items():
            mask = (series.x_sorted >= lower) & (series.x_sorted <= upper)
            if not bool(np.any(mask)):
                continue
            visible[label] = _SeriesData(
                label=series.label,
                x_sorted=series.x_sorted[mask],
                y_sorted=series.y_sorted[mask],
                row_indices_sorted=series.row_indices_sorted[mask],
                is_datetime_sorted=series.is_datetime_sorted[mask],
            )
        use_datetime = self._series_are_datetime(visible or source)
        use_local_time = self._uses_local_datetime_display()
        applied = (
            "x_between("
            f"{self._format_x_bound_text(lower, is_datetime=use_datetime, use_local_time=use_local_time)}.."
            f"{self._format_x_bound_text(upper, is_datetime=use_datetime, use_local_time=use_local_time)})"
        )
        return visible, applied, self._x_bounds_for_series(visible)

    @staticmethod
    def _compute_display_spans(series: dict[str, _DisplaySeriesData]) -> tuple[float, float]:
        x_bounds = LinePlotterModule._x_bounds_for_display_series(series)
        y_bounds = LinePlotterModule._y_bounds_for_display_series(series)

        x_span = 1.0
        y_span = 1.0
        if x_bounds is not None:
            x_span = max(1e-9, abs(x_bounds[1] - x_bounds[0]))
        if y_bounds is not None:
            y_span = max(1e-9, abs(y_bounds[1] - y_bounds[0]))
        return x_span, y_span

    @staticmethod
    def _x_bounds_for_series(series: dict[str, _SeriesData]) -> tuple[float, float] | None:
        x_min = float("inf")
        x_max = float("-inf")
        for bucket in series.values():
            if bucket.x_sorted.size <= 0:
                continue
            x_min = min(x_min, float(bucket.x_sorted[0]))
            x_max = max(x_max, float(bucket.x_sorted[-1]))
        if not (np.isfinite(x_min) and np.isfinite(x_max)):
            return None
        return x_min, x_max

    @staticmethod
    def _x_bounds_for_display_series(
        series: dict[str, _DisplaySeriesData],
    ) -> tuple[float, float] | None:
        x_min = float("inf")
        x_max = float("-inf")
        for bucket in series.values():
            if bucket.display_x_sorted.size <= 0:
                continue
            x_min = min(x_min, float(bucket.display_x_sorted[0]))
            x_max = max(x_max, float(bucket.display_x_sorted[-1]))
        if not (np.isfinite(x_min) and np.isfinite(x_max)):
            return None
        return x_min, x_max

    @staticmethod
    def _y_bounds_for_series(series: dict[str, _SeriesData]) -> tuple[float, float] | None:
        y_min = float("inf")
        y_max = float("-inf")
        for bucket in series.values():
            if bucket.y_sorted.size <= 0:
                continue
            y_min = min(y_min, float(np.min(bucket.y_sorted)))
            y_max = max(y_max, float(np.max(bucket.y_sorted)))
        if not (np.isfinite(y_min) and np.isfinite(y_max)):
            return None
        if abs(y_max - y_min) < 1e-9:
            y_min = y_max - max(abs(y_max) * 0.01, 1.0)
        return y_min, y_max

    @staticmethod
    def _y_bounds_for_display_series(
        series: dict[str, _DisplaySeriesData],
    ) -> tuple[float, float] | None:
        y_min = float("inf")
        y_max = float("-inf")
        for bucket in series.values():
            if bucket.display_y_sorted.size <= 0:
                continue
            y_min = min(y_min, float(np.min(bucket.display_y_sorted)))
            y_max = max(y_max, float(np.max(bucket.display_y_sorted)))
        if not (np.isfinite(y_min) and np.isfinite(y_max)):
            return None
        if abs(y_max - y_min) < 1e-9:
            y_min = y_max - max(abs(y_max) * 0.01, 1.0)
        return y_min, y_max

    def _target_x_view_bounds(self) -> tuple[float, float] | None:
        mode, _ = self._normalized_range_mode(str(self.inputs["range_mode"]))
        raw_bounds: tuple[float, float] | None

        if mode == "all":
            if self._visible_x_bounds is None:
                return None
            raw_bounds = self._normalized_bounds(
                self._visible_x_bounds[0], self._visible_x_bounds[1]
            )
            return self._display_bounds(raw_bounds, self._x_transform)

        if mode == "last_n":
            if self._visible_x_bounds is None:
                return None
            raw_bounds = self._normalized_bounds(
                self._visible_x_bounds[0], self._visible_x_bounds[1]
            )
            return self._display_bounds(raw_bounds, self._x_transform)

        if mode == "last_seconds":
            source_bounds = self._x_bounds_for_series(self._source_series_data)
            if source_bounds is None:
                return None
            seconds = self._normalized_range_seconds(self.inputs["range_seconds"])
            raw_bounds = self._normalized_bounds(source_bounds[1] - seconds, source_bounds[1])
            return self._display_bounds(raw_bounds, self._x_transform)

        raw_bounds = self._x_between_bounds()
        return self._display_bounds(raw_bounds, self._x_transform)

    def _target_y_view_bounds(self) -> tuple[float, float] | None:
        display_bounds = self._y_bounds_for_display_series(self._display_series_data)
        if display_bounds is None:
            return None
        low, high = display_bounds
        span = max(high - low, 1e-9)
        pad = max(span * _Y_VIEW_PADDING_RATIO, self._minimum_resolvable_span(low, high))
        return low - pad, high + pad

    def _x_between_bounds(self) -> tuple[float, float] | None:
        x_min = self._normalized_range_bound(self.inputs["range_x_min"], default=0.0)
        source_bounds = self._x_bounds_for_series(self._source_series_data)
        if (
            source_bounds is not None
            and abs(x_min) < 1e-12
            and self._should_auto_anchor_x_min(source_bounds)
        ):
            x_min = float(source_bounds[0])
            self.inputs["range_x_min"] = x_min
            self._sync_config_controls()

        x_max = self._auto_range_x_max()
        if x_max is None:
            x_max = x_min

        lower = x_min
        upper = x_max
        if lower > upper:
            lower = upper

        return self._normalized_bounds(lower, upper)

    def _should_auto_anchor_x_min(self, source_bounds: tuple[float, float]) -> bool:
        x_mode, _ = self._normalized_x_mode(str(self.inputs["x_mode"]))
        if x_mode not in {"auto", "datetime"}:
            return False

        source_min = float(source_bounds[0])
        source_max = float(source_bounds[1])
        if not (np.isfinite(source_min) and np.isfinite(source_max)):
            return False

        return source_min > 100_000_000.0 and source_max > 100_000_000.0

    def _auto_range_x_max(self) -> float | None:
        source_bounds = self._x_bounds_for_series(self._source_series_data)
        if source_bounds is None:
            return None
        x_max = float(source_bounds[1])
        if not np.isfinite(x_max):
            return None
        return x_max

    @staticmethod
    def _display_bounds(
        bounds: tuple[float, float] | None,
        transform: _AxisTransform,
    ) -> tuple[float, float] | None:
        if bounds is None:
            return None
        left = transform.raw_to_display(float(bounds[0]))
        right = transform.raw_to_display(float(bounds[1]))
        return LinePlotterModule._normalized_bounds(left, right)

    @staticmethod
    def _normalized_bounds(lower: float, upper: float) -> tuple[float, float] | None:
        if not (np.isfinite(lower) and np.isfinite(upper)):
            return None
        left = min(lower, upper)
        right = max(lower, upper)
        span = right - left
        if span < 1e-9:
            center = (left + right) / 2.0
            min_span = LinePlotterModule._minimum_resolvable_span(left, right)
            half = min_span / 2.0
            left = center - half
            right = center + half
            if not (np.isfinite(left) and np.isfinite(right)):
                return None
        return left, right

    @staticmethod
    def _minimum_resolvable_span(lower: float, upper: float) -> float:
        magnitude = max(abs(lower), abs(upper), 1.0)
        try:
            ulp = float(np.spacing(magnitude))
        except Exception:
            ulp = 0.0
        if not np.isfinite(ulp) or ulp <= 0.0:
            ulp = 1e-9
        return max(1e-9, ulp * 2048.0)

    @staticmethod
    def _bounds_close(
        lhs: tuple[float, float],
        rhs: tuple[float, float],
        *,
        atol: float = 1e-9,
        rtol: float = 1e-9,
    ) -> bool:
        scale = max(abs(lhs[0]), abs(lhs[1]), abs(rhs[0]), abs(rhs[1]), 1.0)
        tolerance = max(atol, scale * rtol)
        return abs(lhs[0] - rhs[0]) <= tolerance and abs(lhs[1] - rhs[1]) <= tolerance

    @staticmethod
    def _clamp_window_to_bounds(
        x0: float,
        x1: float,
        bounds: tuple[float, float],
    ) -> tuple[float, float]:
        low, high = bounds
        left = min(x0, x1)
        right = max(x0, x1)
        span = right - left
        bound_span = high - low

        if span <= 1e-9 or span >= bound_span:
            return low, high

        if left < low:
            right += low - left
            left = low
        if right > high:
            left -= right - high
            right = high

        left = max(left, low)
        right = min(right, high)
        if abs(right - left) < 1e-9:
            return low, high
        return left, right

    def _apply_x_limits(self, bounds: tuple[float, float] | None) -> None:
        if self._plot_item is None:
            return
        view_box = self._plot_item.getViewBox()
        if view_box is None:
            return
        try:
            if bounds is None:
                view_box.setLimits(xMin=None, xMax=None, minXRange=None, maxXRange=None)
            else:
                span = max(bounds[1] - bounds[0], 1e-9)
                view_box.setLimits(
                    xMin=bounds[0],
                    xMax=bounds[1],
                    minXRange=span,
                    maxXRange=span,
                )
        except Exception:
            return

    def _apply_y_limits(self, bounds: tuple[float, float] | None) -> None:
        if self._plot_item is None:
            return
        view_box = self._plot_item.getViewBox()
        if view_box is None:
            return
        try:
            if bounds is None:
                view_box.setLimits(yMin=None, yMax=None, maxYRange=None)
            else:
                span = max(bounds[1] - bounds[0], 1e-9)
                view_box.setLimits(yMin=bounds[0], yMax=bounds[1], maxYRange=span)
        except Exception:
            return

    def _apply_target_view(
        self,
        *,
        previous_range: tuple[float, float, float, float] | None,
        previous_y_bounds: tuple[float, float] | None,
        x_bounds: tuple[float, float] | None,
        y_bounds: tuple[float, float] | None,
    ) -> None:
        if self._plot_item is None:
            return

        self._enforcing_view = True
        try:
            if x_bounds is not None:
                self._plot_item.setXRange(x_bounds[0], x_bounds[1], padding=0.0)
            elif previous_range is None and y_bounds is None:
                self._plot_item.enableAutoRange()

            if y_bounds is not None:
                if previous_range is None:
                    self._plot_item.setYRange(y_bounds[0], y_bounds[1], padding=0.0)
                else:
                    previous_view_y = self._normalized_bounds(
                        previous_range[2],
                        previous_range[3],
                    )
                    use_full_y_bounds = (
                        previous_view_y is not None
                        and previous_y_bounds is not None
                        and self._bounds_close(previous_view_y, previous_y_bounds)
                    )
                    if use_full_y_bounds:
                        y0, y1 = y_bounds
                    else:
                        y0, y1 = self._clamp_window_to_bounds(
                            previous_range[2],
                            previous_range[3],
                            y_bounds,
                        )
                    self._plot_item.setYRange(y0, y1, padding=0.0)
        finally:
            self._enforcing_view = False

    def _on_view_range_changed(self, *_: object) -> None:
        self._cached_view_range = self._read_view_range()
        self._enforce_view_bounds()
        self._position_locked_badge()

    def _enforce_view_bounds(self) -> None:
        if self._plot_item is None or self._enforcing_view:
            return

        current = self._view_range()
        if current is None:
            return

        x_bounds = self._target_x_view_bounds()
        y_bounds = self._target_y_view_bounds()

        enforce_x = False
        enforce_y = False
        target_y0 = current[2]
        target_y1 = current[3]

        if x_bounds is not None and (
            abs(current[0] - x_bounds[0]) > 1e-9 or abs(current[1] - x_bounds[1]) > 1e-9
        ):
            enforce_x = True

        if y_bounds is not None:
            clamp_y0, clamp_y1 = self._clamp_window_to_bounds(current[2], current[3], y_bounds)
            target_y0, target_y1 = clamp_y0, clamp_y1
            if abs(current[2] - clamp_y0) > 1e-9 or abs(current[3] - clamp_y1) > 1e-9:
                enforce_y = True

        if not (enforce_x or enforce_y):
            return

        self._enforcing_view = True
        try:
            if enforce_x and x_bounds is not None:
                self._plot_item.setXRange(x_bounds[0], x_bounds[1], padding=0.0)
            if enforce_y:
                self._plot_item.setYRange(target_y0, target_y1, padding=0.0)
        finally:
            self._enforcing_view = False

    def _parse_x_value(
        self,
        *,
        row: dict[str, Any],
        row_index: int,
        x_key: str,
        x_mode: str,
        epoch_unit: str,
    ) -> tuple[float, bool] | None:
        if x_mode == "index":
            return float(row_index), False

        raw = row.get(x_key)

        if x_mode == "number":
            parsed = coerce_finite_float(raw)
            return (parsed, False) if parsed is not None else None

        if x_mode == "datetime":
            return self._parse_datetime_value(raw, epoch_unit=epoch_unit)

        if isinstance(raw, str):
            token = raw.strip()
            if not token:
                return None
            maybe_dt = self._parse_iso_timestamp(token)
            if maybe_dt is not None:
                return maybe_dt, True
            maybe_number = coerce_finite_float(token)
            if maybe_number is not None:
                return maybe_number, False
            return None

        maybe_number = coerce_finite_float(raw)
        if maybe_number is not None:
            return maybe_number, False
        return None

    def _parse_datetime_value(self, value: Any, *, epoch_unit: str) -> tuple[float, bool] | None:
        parsed_number = coerce_finite_float(value)
        if parsed_number is not None:
            unit = epoch_unit
            if unit == "auto":
                unit = "ms" if abs(parsed_number) >= 100_000_000_000.0 else "s"
            seconds = parsed_number / 1000.0 if unit == "ms" else parsed_number
            return seconds, True

        if isinstance(value, str):
            maybe_iso = self._parse_iso_timestamp(value)
            if maybe_iso is not None:
                return maybe_iso, True

        return None

    @staticmethod
    def _parse_iso_timestamp(value: str) -> float | None:
        token = value.strip()
        if not token:
            return None
        iso_token = token[:-1] + "+00:00" if token.endswith("Z") else token
        try:
            parsed = datetime.fromisoformat(iso_token)
        except ValueError:
            return None

        parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        try:
            return float(parsed.timestamp())
        except (OverflowError, OSError, ValueError):
            return None

    def _render_series(self) -> None:
        if self._plot_item is None:
            return

        for curve in self._curve_items.values():
            self._plot_item.removeItem(curve)
        self._curve_items.clear()

        if self._legend is not None:
            self._legend.clear()

        show_points = bool(self.inputs["show_points"])
        antialias = bool(self.inputs["antialias"])

        for index, label in enumerate(sorted(self._display_series_data)):
            series = self._display_series_data[label]
            color = _COLOR_PALETTE[index % len(_COLOR_PALETTE)]
            size = int(series.display_x_sorted.size)
            degenerate_x = (
                size <= 1
                or abs(float(series.display_x_sorted[-1]) - float(series.display_x_sorted[0]))
                < 1e-9
            )
            render_points = show_points or degenerate_x

            curve = self._plot_item.plot(
                x=series.display_x_sorted,
                y=series.display_y_sorted,
                pen=pg.mkPen(color=color, width=1.8),
                antialias=antialias,
                symbol="o" if render_points else None,
                symbolPen=pg.mkPen(color=color),
                symbolBrush=pg.mkBrush(color),
                symbolSize=6 if render_points else 0,
                name=label,
            )
            try:
                curve.setClipToView(True)
                if degenerate_x:
                    curve.setDownsampling(auto=False)
                else:
                    curve.setDownsampling(auto=True, method="peak")
            except Exception:
                pass
            self._curve_items[label] = curve

        self._sync_plot_display_state()

    def _on_scene_mouse_moved(self, scene_position: object) -> None:
        if self._plot_item is None:
            return
        if not isinstance(scene_position, QPointF):
            return

        if not self._plot_item.sceneBoundingRect().contains(scene_position):
            self._cursor_view = None
            if not self._hover_locked:
                self._clear_hover(force_emit=False)
            else:
                self._sync_crosshair()
            return

        mapped = self._plot_item.vb.mapSceneToView(scene_position)
        view_x = float(mapped.x())
        view_y = float(mapped.y())
        self._cursor_view = (view_x, view_y)

        if self._hover_locked:
            self._sync_crosshair()
            return

        self._update_hover_from_view(view_x, view_y, force_emit=False)

    def _on_scene_mouse_clicked(self, event: object) -> None:
        if self._plot_item is None:
            return
        if not bool(self.inputs["lock_on_click"]):
            return

        button = getattr(event, "button", None)
        if not callable(button) or button() != Qt.MouseButton.LeftButton:
            return

        scene_pos_getter = getattr(event, "scenePos", None)
        if not callable(scene_pos_getter):
            return
        scene_position = scene_pos_getter()
        if not isinstance(scene_position, QPointF):
            return
        if not self._plot_item.sceneBoundingRect().contains(scene_position):
            return

        mapped = self._plot_item.vb.mapSceneToView(scene_position)
        self._toggle_lock(float(mapped.x()), float(mapped.y()))
        event_accept = getattr(event, "accept", None)
        if callable(event_accept):
            event_accept()

    def _toggle_lock(self, view_x: float, view_y: float) -> None:
        if self._hover_locked:
            self._hover_locked = False
            self._cursor_view = (view_x, view_y)
            self._update_hover_from_view(view_x, view_y, force_emit=True)
            self._sync_crosshair()
            return

        point = self._nearest_point_lock(view_x, view_y)
        if point is None:
            self._hover_locked = False
            self._cursor_view = (view_x, view_y)
            self._clear_hover(force_emit=True)
            self._sync_crosshair()
            return

        self._hover_locked = True
        self._set_active_point(point, force_emit=True)

    def _update_hover_from_view(self, view_x: float, view_y: float, *, force_emit: bool) -> None:
        if self._hover_locked and not force_emit:
            return

        point = self._nearest_point(view_x, view_y)
        if point is None:
            self._clear_hover(force_emit=force_emit)
            return

        self._set_active_point(point, force_emit=force_emit)

    def _nearest_point(self, view_x: float, view_y: float) -> _ActivePoint | None:
        if not self._display_series_items:
            return None

        x_scale, y_scale = self._distance_scales()
        best_key = (float("inf"), float("inf"), float("inf"))
        best: _ActivePoint | None = None

        for label, series in self._display_series_items:
            x_values = series.display_x_sorted
            y_values = series.display_y_sorted
            idx = self._nearest_index_x_then_y(x_values, y_values, view_x, view_y)
            if idx is None:
                continue

            snap_view_x = float(x_values[idx])
            snap_view_y = float(y_values[idx])
            display_dx = abs(snap_view_x - view_x)
            display_dy = abs(snap_view_y - view_y)
            if not (np.isfinite(display_dx) and np.isfinite(display_dy)):
                continue

            norm_dx = display_dx / x_scale
            norm_dy = display_dy / y_scale
            score = (norm_dx * norm_dx) + (norm_dy * norm_dy)
            key = (display_dx, display_dy, score)
            if key >= best_key:
                continue

            best_key = key
            best = _ActivePoint(
                series=label,
                row_index=int(series.row_indices_sorted[idx]),
                x=float(series.raw_x_sorted[idx]),
                y=float(series.raw_y_sorted[idx]),
                view_x=snap_view_x,
                view_y=snap_view_y,
                is_datetime=bool(series.is_datetime_sorted[idx]),
            )

        return best

    def _nearest_point_lock(self, view_x: float, view_y: float) -> _ActivePoint | None:
        if not self._display_series_items:
            return None

        view_box = None if self._plot_item is None else self._plot_item.getViewBox()
        click_scene: QPointF | None = None
        if view_box is not None:
            with suppress(Exception):
                mapped = view_box.mapViewToScene(QPointF(view_x, view_y))
                mapped_x = float(mapped.x())
                mapped_y = float(mapped.y())
                if np.isfinite(mapped_x) and np.isfinite(mapped_y):
                    click_scene = QPointF(mapped_x, mapped_y)

        x_scale, y_scale = self._lock_distance_scales()
        x_candidate = self._nearest_lock_axis_candidate(
            view_x=view_x,
            view_y=view_y,
            axis="x",
            view_box=view_box,
            click_scene=click_scene,
            x_scale=x_scale,
            y_scale=y_scale,
        )
        y_candidate = self._nearest_lock_axis_candidate(
            view_x=view_x,
            view_y=view_y,
            axis="y",
            view_box=view_box,
            click_scene=click_scene,
            x_scale=x_scale,
            y_scale=y_scale,
        )

        if x_candidate is None and y_candidate is None:
            return None
        if x_candidate is None and y_candidate is not None:
            return y_candidate[3]
        if y_candidate is None and x_candidate is not None:
            return x_candidate[3]
        if x_candidate is None or y_candidate is None:
            return None

        x_primary, x_secondary, x_score = x_candidate[:3]
        y_primary, y_secondary, y_score = y_candidate[:3]
        axis_eps = _LOCK_AXIS_TIE_EPS_SCENE

        if abs(x_primary - y_primary) > axis_eps:
            return x_candidate[3] if x_primary < y_primary else y_candidate[3]
        if abs(x_secondary - y_secondary) > axis_eps:
            return x_candidate[3] if x_secondary < y_secondary else y_candidate[3]
        if x_score <= y_score:
            return x_candidate[3]
        return y_candidate[3]

    def _nearest_lock_axis_candidate(
        self,
        *,
        view_x: float,
        view_y: float,
        axis: str,
        view_box: Any | None,
        click_scene: QPointF | None,
        x_scale: float,
        y_scale: float,
    ) -> tuple[float, float, float, _ActivePoint] | None:
        best_key = (float("inf"), float("inf"), float("inf"))
        best: _ActivePoint | None = None

        for label, series in self._display_series_items:
            x_values = series.display_x_sorted
            y_values = series.display_y_sorted
            size = int(x_values.size)
            if size <= 0 or int(y_values.size) != size:
                continue

            projected = (
                self._project_vertical_axis_point(x_values, y_values, view_x, view_y)
                if axis == "x"
                else self._project_horizontal_axis_point(x_values, y_values, view_x, view_y)
            )
            if projected is None:
                continue

            candidate_x, candidate_y, idx = projected

            dx, dy = self._lock_candidate_scene_delta(
                candidate_x=candidate_x,
                candidate_y=candidate_y,
                view_x=view_x,
                view_y=view_y,
                view_box=view_box,
                click_scene=click_scene,
                x_scale=x_scale,
                y_scale=y_scale,
            )

            if not (np.isfinite(dx) and np.isfinite(dy)):
                continue

            primary = dx if axis == "x" else dy
            secondary = dy if axis == "x" else dx
            score = (dx * dx) + (dy * dy)
            key = (primary, secondary, score)
            if key >= best_key:
                continue

            best_key = key
            best = _ActivePoint(
                series=label,
                row_index=int(series.row_indices_sorted[idx]),
                x=self._x_transform.display_to_raw(candidate_x),
                y=self._y_transform.display_to_raw(candidate_y),
                view_x=candidate_x,
                view_y=candidate_y,
                is_datetime=bool(series.is_datetime_sorted[idx]),
            )

        if best is None:
            return None
        return best_key[0], best_key[1], best_key[2], best

    @staticmethod
    def _project_vertical_axis_point(
        x_values: NDArray[np.float64],
        y_values: NDArray[np.float64],
        target_x: float,
        target_y: float,
    ) -> tuple[float, float, int] | None:
        size = int(x_values.size)
        if size <= 0 or int(y_values.size) != size:
            return None

        fallback_idx = LinePlotterModule._nearest_index_x_then_y(
            x_values,
            y_values,
            target_x,
            target_y,
        )
        if fallback_idx is None:
            return None

        left = int(np.searchsorted(x_values, target_x, side="left"))
        right = int(np.searchsorted(x_values, target_x, side="right"))
        if left < right:
            y_window = y_values[left:right]
            nearest_offset = int(np.argmin(np.abs(y_window - target_y)))
            idx = left + nearest_offset
            return float(target_x), float(y_values[idx]), idx

        if 0 < left < size:
            i0 = left - 1
            i1 = left
            x0 = float(x_values[i0])
            x1 = float(x_values[i1])
            y0 = float(y_values[i0])
            y1 = float(y_values[i1])
            if (
                np.isfinite(x0)
                and np.isfinite(x1)
                and np.isfinite(y0)
                and np.isfinite(y1)
                and x1 != x0
            ):
                t = (target_x - x0) / (x1 - x0)
                if 0.0 <= t <= 1.0:
                    y_interp = y0 + (t * (y1 - y0))
                    if np.isfinite(y_interp):
                        idx = i0 if abs(y0 - target_y) <= abs(y1 - target_y) else i1
                        return float(target_x), float(y_interp), idx

        return float(x_values[fallback_idx]), float(y_values[fallback_idx]), fallback_idx

    @staticmethod
    def _project_horizontal_axis_point(
        x_values: NDArray[np.float64],
        y_values: NDArray[np.float64],
        target_x: float,
        target_y: float,
    ) -> tuple[float, float, int] | None:
        size = int(x_values.size)
        if size <= 0 or int(y_values.size) != size:
            return None

        best_key = (float("inf"), float("inf"))
        best: tuple[float, float, int] | None = None
        tol = 1e-12

        for idx in range(size - 1):
            x0 = float(x_values[idx])
            y0 = float(y_values[idx])
            x1 = float(x_values[idx + 1])
            y1 = float(y_values[idx + 1])
            if not (np.isfinite(x0) and np.isfinite(y0) and np.isfinite(x1) and np.isfinite(y1)):
                continue

            if y0 == y1:
                if abs(y0 - target_y) > tol:
                    continue
                low = min(x0, x1)
                high = max(x0, x1)
                x_proj = float(min(max(target_x, low), high))
                secondary = abs(x_proj - target_x)
                src_idx = idx if abs(x0 - x_proj) <= abs(x1 - x_proj) else idx + 1
                key = (0.0, secondary)
                if key < best_key:
                    best_key = key
                    best = (x_proj, float(target_y), src_idx)
                continue

            min_y = min(y0, y1)
            max_y = max(y0, y1)
            if target_y < min_y or target_y > max_y:
                continue

            t = (target_y - y0) / (y1 - y0)
            if t < 0.0 or t > 1.0:
                continue

            x_proj = x0 + (t * (x1 - x0))
            if not np.isfinite(x_proj):
                continue

            secondary = abs(float(x_proj) - target_x)
            src_idx = idx if abs(t) <= 0.5 else idx + 1
            key = (0.0, secondary)
            if key < best_key:
                best_key = key
                best = (float(x_proj), float(target_y), src_idx)

        if best is not None:
            return best

        fallback_idx = LinePlotterModule._nearest_index_y_then_x(
            x_values,
            y_values,
            target_x,
            target_y,
        )
        if fallback_idx is None:
            return None
        return float(x_values[fallback_idx]), float(y_values[fallback_idx]), fallback_idx

    @staticmethod
    def _lock_candidate_scene_delta(
        *,
        candidate_x: float,
        candidate_y: float,
        view_x: float,
        view_y: float,
        view_box: Any | None,
        click_scene: QPointF | None,
        x_scale: float,
        y_scale: float,
    ) -> tuple[float, float]:
        if view_box is not None and click_scene is not None:
            with suppress(Exception):
                candidate_scene = view_box.mapViewToScene(QPointF(candidate_x, candidate_y))
                dx = abs(float(candidate_scene.x()) - float(click_scene.x()))
                dy = abs(float(candidate_scene.y()) - float(click_scene.y()))
                if np.isfinite(dx) and np.isfinite(dy):
                    return dx, dy
        return abs(candidate_x - view_x) / x_scale, abs(candidate_y - view_y) / y_scale

    def _lock_distance_scales(self) -> tuple[float, float]:
        if self._plot_item is not None:
            view_box = self._plot_item.getViewBox()
            if view_box is not None:
                with suppress(Exception):
                    pixel_size = view_box.viewPixelSize()
                    if (
                        isinstance(pixel_size, tuple)
                        and len(pixel_size) == 2
                        and np.isfinite(float(pixel_size[0]))
                        and np.isfinite(float(pixel_size[1]))
                        and abs(float(pixel_size[0])) > 1e-12
                        and abs(float(pixel_size[1])) > 1e-12
                    ):
                        return abs(float(pixel_size[0])), abs(float(pixel_size[1]))
        return self._distance_scales()

    @staticmethod
    def _nearest_index_x_then_y(
        x_values: NDArray[np.float64],
        y_values: NDArray[np.float64],
        target_x: float,
        target_y: float,
    ) -> int | None:
        size = int(x_values.size)
        if size <= 0 or int(y_values.size) != size:
            return None

        pos = int(np.searchsorted(x_values, target_x, side="left"))
        if pos <= 0:
            if size == 1 or float(x_values[0]) != float(x_values[1]):
                return 0
        elif pos >= size:
            if size == 1 or float(x_values[-1]) != float(x_values[-2]):
                return size - 1
        else:
            left_idx = pos - 1
            right_idx = pos
            left_x = float(x_values[left_idx])
            right_x = float(x_values[right_idx])
            if left_x != right_x:
                left_key = (abs(left_x - target_x), abs(float(y_values[left_idx]) - target_y))
                right_key = (
                    abs(right_x - target_x),
                    abs(float(y_values[right_idx]) - target_y),
                )
                return left_idx if left_key <= right_key else right_idx

        candidate_x_values: list[float] = []
        if pos > 0:
            candidate_x_values.append(float(x_values[pos - 1]))
        if pos < size:
            x_at_pos = float(x_values[pos])
            if not candidate_x_values or x_at_pos != candidate_x_values[-1]:
                candidate_x_values.append(x_at_pos)
        if not candidate_x_values:
            return None

        best_idx: int | None = None
        best_key = (float("inf"), float("inf"))
        for candidate_x in candidate_x_values:
            left = int(np.searchsorted(x_values, candidate_x, side="left"))
            right = int(np.searchsorted(x_values, candidate_x, side="right"))
            if left >= right:
                continue
            y_window = y_values[left:right]
            nearest_offset = int(np.argmin(np.abs(y_window - target_y)))
            idx = left + nearest_offset
            key = (abs(candidate_x - target_x), abs(float(y_values[idx]) - target_y))
            if key >= best_key:
                continue
            best_key = key
            best_idx = idx

        return best_idx

    @staticmethod
    def _nearest_index_y_then_x(
        x_values: NDArray[np.float64],
        y_values: NDArray[np.float64],
        target_x: float,
        target_y: float,
    ) -> int | None:
        size = int(y_values.size)
        if size <= 0 or int(x_values.size) != size:
            return None

        dy_values = np.abs(y_values - target_y)
        min_dy = float(np.min(dy_values))
        if not np.isfinite(min_dy):
            return None

        candidate_indices = np.flatnonzero(dy_values == min_dy)
        if candidate_indices.size <= 0:
            return None

        x_candidates = np.abs(x_values[candidate_indices] - target_x)
        nearest_local = int(np.argmin(x_candidates))
        return int(candidate_indices[nearest_local])

    def _set_active_point(self, point: _ActivePoint, *, force_emit: bool) -> None:
        prior = self._active_point
        changed = (
            prior is None
            or prior.series != point.series
            or prior.row_index != point.row_index
            or abs(prior.x - point.x) > 1e-9
            or abs(prior.y - point.y) > 1e-9
            or force_emit
        )

        self._active_point = point
        self._sync_crosshair()
        self._sync_hover_label()

        if not changed:
            return

        self.emit("hover_active", True)
        self.emit("hover_series", point.series)
        self.emit("hover_index", point.row_index)
        self.emit("hover_x", point.x)
        self.emit("hover_y", point.y)
        self.emit(
            "hover_x_text",
            self._format_x_text(
                point.x,
                is_datetime=point.is_datetime,
                use_local_time=self._uses_local_datetime_display(),
            ),
        )
        self.emit("hover_y_text", self._format_number(point.y))

    def _clear_hover(self, *, force_emit: bool) -> None:
        if self._active_point is None and not force_emit:
            self._sync_crosshair()
            return

        self._active_point = None
        self._sync_crosshair()
        self._sync_hover_label()

        self.emit("hover_active", False)
        self.emit("hover_series", "")
        self.emit("hover_index", -1)
        self.emit("hover_x", 0.0)
        self.emit("hover_y", 0.0)
        self.emit("hover_x_text", "")
        self.emit("hover_y_text", "")

    def _sync_crosshair(self) -> None:
        if self._crosshair_x is None or self._crosshair_y is None:
            return

        if self._hover_locked and self._active_point is not None:
            view_x = self._active_point.view_x
            view_y = self._active_point.view_y
        elif self._cursor_view is not None:
            view_x, view_y = self._cursor_view
        else:
            self._crosshair_x.setVisible(False)
            self._crosshair_y.setVisible(False)
            return

        self._crosshair_x.setVisible(True)
        self._crosshair_y.setVisible(True)
        self._crosshair_x.setPos(view_x)
        self._crosshair_y.setPos(view_y)

    def _sync_hover_label(self) -> None:
        if self._hover_label is None:
            return

        if not self._hover_locked:
            self._hover_label.setText("")
            self._sync_locked_badge()
            return

        if self._active_point is None:
            self._hover_label.setText("")
            self._sync_locked_badge()
            return

        self._hover_label.setText("")
        self._sync_locked_badge()

    def _sync_locked_badge(self) -> None:
        if self._locked_badge_item is None:
            return

        point = self._active_point if self._hover_locked else None
        if point is None:
            if self._locked_badge_bg_item is not None:
                self._locked_badge_bg_item.setVisible(False)
            self._locked_badge_item.setVisible(False)
            self._locked_badge_item.setText("")
            return

        self._locked_badge_item.setText(
            f"locked {point.series} #{point.row_index} "
            f"x={self._format_x_text(point.x, is_datetime=point.is_datetime, use_local_time=self._uses_local_datetime_display())} "
            f"y={self._format_number(point.y)}"
        )
        self._position_locked_badge()
        if self._locked_badge_bg_item is not None:
            self._locked_badge_bg_item.setVisible(True)
        self._locked_badge_item.setVisible(True)

    def _position_locked_badge(self) -> None:
        if self._locked_badge_item is None or self._plot_item is None:
            return

        with suppress(Exception):
            bounds = self._plot_item.boundingRect()
            text_bounds = self._locked_badge_item.boundingRect()
            pad_x = 6.0
            pad_y = 3.0
            outer_x = float(bounds.left() + 6.0)
            outer_y = float(bounds.bottom() - (text_bounds.height() + (2.0 * pad_y)) - 4.0)
            if self._locked_badge_bg_item is not None:
                self._locked_badge_bg_item.setRect(
                    outer_x,
                    outer_y,
                    float(text_bounds.width() + (2.0 * pad_x)),
                    float(text_bounds.height() + (2.0 * pad_y)),
                )
            self._locked_badge_item.setPos(float(outer_x + pad_x), float(outer_y + pad_y))

    def _distance_scales(self) -> tuple[float, float]:
        x_scale = self._data_x_span
        y_scale = self._data_y_span

        current = self._view_range()
        if current is not None:
            span_x = abs(current[1] - current[0])
            span_y = abs(current[3] - current[2])
            if np.isfinite(span_x) and span_x > 1e-9:
                x_scale = span_x
            if np.isfinite(span_y) and span_y > 1e-9:
                y_scale = span_y

        return x_scale, y_scale

    def _view_range(self) -> tuple[float, float, float, float] | None:
        if self._cached_view_range is not None:
            return self._cached_view_range
        current = self._read_view_range()
        self._cached_view_range = current
        return current

    def _read_view_range(self) -> tuple[float, float, float, float] | None:
        if self._plot_item is None:
            return None

        view_range = self._plot_item.viewRange()
        if (
            not isinstance(view_range, list)
            or len(view_range) < 2
            or not isinstance(view_range[0], list)
            or not isinstance(view_range[1], list)
            or len(view_range[0]) < 2
            or len(view_range[1]) < 2
        ):
            return None

        x0 = float(view_range[0][0])
        x1 = float(view_range[0][1])
        y0 = float(view_range[1][0])
        y1 = float(view_range[1][1])
        if not (np.isfinite(x0) and np.isfinite(x1) and np.isfinite(y0) and np.isfinite(y1)):
            return None
        return x0, x1, y0, y1

    def _trim_rows_to_max_points(self) -> int:
        max_points = self._normalized_max_points(int(self.inputs["max_points"]))
        self.inputs["max_points"] = max_points
        overflow = len(self._row_buffer) - max_points
        if overflow <= 0:
            return 0
        self._row_buffer = self._row_buffer[overflow:]
        return overflow

    def _publish_summary(self, reason: str, *, error: str) -> None:
        source_point_count = sum(
            int(series.x_sorted.size) for series in self._source_series_data.values()
        )
        point_count = sum(int(series.x_sorted.size) for series in self._series_data.values())
        series_count = len(self._series_data)

        visible_x_min = (
            float(self._visible_x_bounds[0]) if self._visible_x_bounds is not None else 0.0
        )
        visible_x_max = (
            float(self._visible_x_bounds[1]) if self._visible_x_bounds is not None else 0.0
        )

        summary = (
            f"{reason}: points={point_count}/{source_point_count}, series={series_count}, "
            f"invalid={self._invalid_count}, mode={self.inputs['x_mode']}, "
            f"range={self._range_applied}"
        )

        self.emit("point_count", point_count)
        self.emit("source_point_count", source_point_count)
        self.emit("series_count", series_count)
        self.emit("invalid_count", self._invalid_count)
        self.emit("visible_x_min", visible_x_min)
        self.emit("visible_x_max", visible_x_max)
        self.emit("range_mode", str(self.inputs["range_mode"]))
        self.emit("range_applied", self._range_applied)
        if not reason.startswith("exported "):
            self.emit("exported", 0)
        self.emit("text", summary)
        self.emit("error", error)

        if self._summary_label is not None:
            rendered = summary if not error else f"{summary}; error: {error}"
            self._summary_label.setText(rendered)

    def _validation_message(self) -> str:
        if self._invalid_count <= 0:
            return ""
        return f"skipped {self._invalid_count} invalid row(s)"

    def _export_plot(self, extension: str) -> None:
        if self._plot_item is None:
            message = "plot widget is not initialized"
            self.emit("path", "")
            self.emit("exported", 0)
            self.emit("error", message)
            self._publish_summary("export failed", error=self._compose_error(message))
            return

        target = build_export_path(
            file_name=str(self.inputs["file_name"]),
            export_folder=str(self.inputs["export_folder"]),
            extension=extension,
            default_stem=_DEFAULT_FILE_STEM,
            tag=str(self.inputs["tag"]),
        )

        restore_crosshair: tuple[bool, bool] | None = None
        if (
            extension == "png"
            and not self._hover_locked
            and self._crosshair_x is not None
            and self._crosshair_y is not None
        ):
            restore_crosshair = (self._crosshair_x.isVisible(), self._crosshair_y.isVisible())
            self._crosshair_x.setVisible(False)
            self._crosshair_y.setVisible(False)

        try:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            if extension == "png":
                exporter = pg.exporters.ImageExporter(self._plot_item)
                self._configure_png_export(exporter)
            elif extension == "svg":
                exporter = pg.exporters.SVGExporter(self._plot_item)
            else:
                raise ValueError(f"unsupported export extension '{extension}'")
            exporter.export(str(target))
        except Exception as exc:
            message = f"export failed: {exc}"
            self.emit("path", "")
            self.emit("exported", 0)
            self.emit("error", message)
            self._publish_summary("export failed", error=self._compose_error(message))
            return
        finally:
            if (
                restore_crosshair is not None
                and self._crosshair_x is not None
                and self._crosshair_y is not None
            ):
                self._crosshair_x.setVisible(bool(restore_crosshair[0]))
                self._crosshair_y.setVisible(bool(restore_crosshair[1]))
                if restore_crosshair[0] or restore_crosshair[1]:
                    self._sync_crosshair()

        self.emit("path", str(target))
        self.emit("exported", 1)
        self.emit("error", self._compose_error(""))
        self._publish_summary(f"exported {extension} -> {target}", error=self._compose_error(""))

    def _configure_png_export(self, exporter: Any) -> None:
        if self._plot_item is None:
            return

        with suppress(Exception):
            params = exporter.parameters()
            source_width = int(max(1.0, float(self._plot_item.sceneBoundingRect().width())))
            target_width = source_width * _PNG_EXPORT_SCALE
            target_width = max(_PNG_EXPORT_MIN_WIDTH, target_width)
            target_width = min(_PNG_EXPORT_MAX_WIDTH, target_width)
            params["width"] = int(target_width)
            params["antialias"] = True

    def _apply_plot_display_state(self) -> None:
        if self._legend is not None:
            self._legend.setVisible(bool(self.inputs["show_legend"]))
        if self._plot_item is not None:
            visible = bool(self.inputs["show_grid"])
            grid_value: int | bool = _GRID_ALPHA if visible else False
            for axis_name in ("bottom", "left"):
                axis = self._plot_item.getAxis(axis_name)
                set_grid = getattr(axis, "setGrid", None)
                if callable(set_grid):
                    with suppress(Exception):
                        set_grid(grid_value)

    def _sync_plot_display_state(self) -> None:
        self._apply_plot_display_state()

    @staticmethod
    def _format_number(value: float) -> str:
        if not np.isfinite(value):
            return "nan"
        absolute = abs(value)
        if absolute == 0.0:
            return "0"
        if absolute >= 1_000_000.0 or absolute < 1e-4:
            return f"{value:.12g}"
        return f"{value:.10g}"

    @classmethod
    def _format_x_text(
        cls,
        value: float,
        *,
        is_datetime: bool,
        use_local_time: bool,
    ) -> str:
        if not is_datetime:
            return cls._format_number(value)
        try:
            utc_value = datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return cls._format_number(value)
        if use_local_time:
            return utc_value.astimezone().isoformat(sep=" ", timespec="milliseconds")
        rendered = utc_value.isoformat(sep=" ", timespec="milliseconds")
        return rendered[:-6] + "Z" if rendered.endswith("+00:00") else rendered

    @classmethod
    def _format_x_bound_text(
        cls,
        value: float,
        *,
        is_datetime: bool,
        use_local_time: bool,
    ) -> str:
        if not is_datetime:
            return cls._format_number(value)
        return cls._format_x_text(
            value,
            is_datetime=True,
            use_local_time=use_local_time,
        )

    @classmethod
    def _format_duration_text(cls, seconds: float) -> str:
        return cls._format_duration_iso(seconds)

    def _x_axis_label(self) -> str:
        mode, _ = self._normalized_x_mode(str(self.inputs["x_mode"]))
        x_key = self._normalized_x_key(str(self.inputs["x_key"]))
        if mode == "index":
            return "row index"
        if self._uses_datetime_axis():
            return f"{x_key} ({self._datetime_axis_time_label()})"
        return x_key

    def _uses_local_datetime_display(self) -> bool:
        return bool(self.inputs.get("local_time", _DEFAULT_LOCAL_TIME))

    def _datetime_axis_time_label(self) -> str:
        if self._uses_local_datetime_display():
            zone = self._local_timezone_symbol()
            return f"time {zone}"
        return "time UTC"

    @staticmethod
    def _local_timezone_symbol() -> str:
        try:
            zone = datetime.now().astimezone().tzname()
        except Exception:
            zone = None
        token = str(zone).strip() if zone is not None else ""
        return token or "LOCAL"

    def _uses_datetime_axis(self) -> bool:
        mode, _ = self._normalized_x_mode(str(self.inputs["x_mode"]))
        if mode == "datetime":
            return True
        if mode in {"number", "index"}:
            return False

        return self._series_are_datetime(self._series_data)

    @staticmethod
    def _series_are_datetime(series_map: dict[str, _SeriesData]) -> bool:
        total_points = 0
        datetime_points = 0
        for series in series_map.values():
            flags = series.is_datetime_sorted
            total_points += int(flags.size)
            datetime_points += int(np.count_nonzero(flags))
        return total_points > 0 and datetime_points == total_points

    def _configure_axes(self, *, force: bool) -> None:
        if self._plot_item is None:
            return

        use_datetime_axis = self._uses_datetime_axis()
        use_local_time = self._uses_local_datetime_display()
        bottom_axis: Any
        if use_datetime_axis:
            bottom_axis = _CompressedDateAxisItem(
                orientation="bottom",
                transform=self._x_transform,
                use_local_time=use_local_time,
            )
        else:
            bottom_axis = _CompressedAxisItem(
                orientation="bottom",
                transform=self._x_transform,
            )
        left_axis = _CompressedAxisItem(orientation="left", transform=self._y_transform)

        if not force and use_datetime_axis == self._using_datetime_axis:
            existing_bottom = self._plot_item.getAxis("bottom")
            existing_left = self._plot_item.getAxis("left")
            if isinstance(existing_bottom, (_CompressedAxisItem, _CompressedDateAxisItem)):
                existing_bottom.set_transform(self._x_transform)
            if isinstance(existing_bottom, _CompressedDateAxisItem):
                existing_bottom.set_timezone_mode(use_local_time=use_local_time)
            if isinstance(existing_left, _CompressedAxisItem):
                existing_left.set_transform(self._y_transform)
            return

        with suppress(Exception):
            bottom_axis.enableAutoSIPrefix(False)
        with suppress(Exception):
            bottom_axis.setStyle(autoExpandTextSpace=True)
        with suppress(Exception):
            left_axis.enableAutoSIPrefix(False)
        with suppress(Exception):
            left_axis.setStyle(autoExpandTextSpace=True)

        try:
            self._plot_item.setAxisItems({"bottom": bottom_axis, "left": left_axis})
        except Exception:
            return

        self._using_datetime_axis = use_datetime_axis

    def _y_axis_label(self) -> str:
        return self._normalized_y_key(str(self.inputs["y_key"]))

    @staticmethod
    def _resolve_series_label(row: dict[str, Any], series_key: str) -> str:
        if not series_key:
            return _DEFAULT_SERIES
        raw = row.get(series_key)
        if raw is None:
            return _DEFAULT_SERIES
        token = str(raw).strip()
        return token or _DEFAULT_SERIES

    @staticmethod
    def _normalized_x_mode(value: str) -> tuple[str, str]:
        token = value.strip().lower()
        if token in _X_MODES:
            return token, ""
        return _DEFAULT_X_MODE, f"invalid x_mode '{value}'; using '{_DEFAULT_X_MODE}'"

    @staticmethod
    def _normalized_epoch_unit(value: str) -> tuple[str, str]:
        token = value.strip().lower()
        if token in _EPOCH_UNITS:
            return token, ""
        return _DEFAULT_EPOCH_UNIT, (
            f"invalid epoch_unit '{value}'; using '{_DEFAULT_EPOCH_UNIT}'"
        )

    @staticmethod
    def _normalized_range_mode(value: str) -> tuple[str, str]:
        token = value.strip().lower()
        if token in _RANGE_MODES:
            return token, ""
        return _DEFAULT_RANGE_MODE, (
            f"invalid range_mode '{value}'; using '{_DEFAULT_RANGE_MODE}'"
        )

    @staticmethod
    def _normalized_max_points(value: int) -> int:
        return max(1, min(1_000_000, int(value)))

    @staticmethod
    def _normalized_range_points(value: int) -> int:
        return max(1, min(1_000_000, int(value)))

    @staticmethod
    def _normalized_range_seconds(value: Any) -> float:
        parsed = coerce_finite_float(value)
        if parsed is None:
            return 0.0
        return max(0.0, parsed)

    @staticmethod
    def _normalized_range_bound(value: Any, *, default: float) -> float:
        parsed = coerce_finite_float(value)
        if parsed is None:
            return default
        return parsed

    @staticmethod
    def _normalized_x_key(value: str) -> str:
        token = value.strip()
        return token or _DEFAULT_X_KEY

    @staticmethod
    def _normalized_y_key(value: str) -> str:
        token = value.strip()
        return token or _DEFAULT_Y_KEY

    def _compose_error(self, base: str) -> str:
        parts = [warning for warning in self._option_warnings.values() if warning]
        if base:
            parts.append(base)
        return "; ".join(parts)

    def _set_core_options_expanded(self, expanded: bool) -> None:
        self._core_options_expanded = bool(expanded)

        if self._core_options_bar is not None:
            expected = "[-] Options" if self._core_options_expanded else "[+] Options"
            if self._core_options_bar.text() != expected:
                self._core_options_bar.setText(expected)
            if self._core_options_bar.isChecked() != self._core_options_expanded:
                self._core_options_bar.blockSignals(True)
                self._core_options_bar.setChecked(self._core_options_expanded)
                self._core_options_bar.blockSignals(False)

        if self._core_options_container is not None:
            self._core_options_container.setVisible(self._core_options_expanded)

    def _set_options_expanded(self, expanded: bool) -> None:
        self._options_expanded = bool(expanded)

        if self._options_bar is not None:
            expected = "[-] Advanced" if self._options_expanded else "[+] Advanced"
            if self._options_bar.text() != expected:
                self._options_bar.setText(expected)
            if self._options_bar.isChecked() != self._options_expanded:
                self._options_bar.blockSignals(True)
                self._options_bar.setChecked(self._options_expanded)
                self._options_bar.blockSignals(False)

        if self._options_container is not None:
            self._options_container.setVisible(self._options_expanded)

    @staticmethod
    def _sync_line_edit(widget: QLineEdit | None, value: str) -> None:
        if widget is None or widget.text() == value:
            return
        widget.blockSignals(True)
        widget.setText(value)
        widget.blockSignals(False)

    @staticmethod
    def _sync_combo(widget: QComboBox | None, value: str) -> None:
        if widget is None or widget.currentText() == value:
            return
        widget.blockSignals(True)
        widget.setCurrentText(value)
        widget.blockSignals(False)

    @staticmethod
    def _sync_spin(widget: QSpinBox | None, value: int) -> None:
        if widget is None or widget.value() == value:
            return
        widget.blockSignals(True)
        widget.setValue(value)
        widget.blockSignals(False)

    @staticmethod
    def _sync_double_spin(widget: QDoubleSpinBox | None, value: float) -> None:
        if widget is None or widget.value() == value:
            return
        widget.blockSignals(True)
        widget.setValue(value)
        widget.blockSignals(False)

    @staticmethod
    def _sync_checkbox(widget: QCheckBox | None, value: bool) -> None:
        if widget is None or widget.isChecked() == value:
            return
        widget.blockSignals(True)
        widget.setChecked(value)
        widget.blockSignals(False)

    def on_close(self) -> None:
        if self._plot_widget is None:
            return

        if self._plot_item is not None:
            with suppress(Exception):
                self._plot_item.getViewBox().sigRangeChanged.disconnect(self._on_view_range_changed)

        scene = self._plot_widget.scene()
        with suppress(Exception):
            scene.sigMouseMoved.disconnect(self._on_scene_mouse_moved)
        with suppress(Exception):
            scene.sigMouseClicked.disconnect(self._on_scene_mouse_clicked)
