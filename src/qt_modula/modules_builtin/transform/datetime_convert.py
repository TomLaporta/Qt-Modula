"""Datetime normalization module for deterministic bind chains."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height

_DATETIME_OUTPUT_FORMAT = "%Y-%m-%d %H:%M:%S"
_DATE_OUTPUT_FORMAT = "%Y-%m-%d"
_TIME_OUTPUT_FORMAT = "%H:%M:%S"
_TIME_12H_OUTPUT_FORMAT = "%I:%M:%S %p"
_DATE_MDY_OUTPUT_FORMAT = "%m/%d/%Y"
_DATE_DMY_OUTPUT_FORMAT = "%d/%m/%Y"
_ISO_DATETIME_OUTPUT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_DATETIME_MDY_OUTPUT_FORMAT = "%m/%d/%Y %I:%M:%S %p"
_DATETIME_DMY_OUTPUT_FORMAT = "%d/%m/%Y %I:%M:%S %p"
_NAMED_DATE_OUTPUT_FORMAT = "%B %d, %Y"
_NAMED_DATETIME_OUTPUT_FORMAT = "%B %d, %Y %I:%M:%S %p"

_EPOCH_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_ISO_TIME_RE = re.compile(r"[T\s]\d{1,2}:\d{2}")

_MDY_PATTERNS: tuple[tuple[str, bool], ...] = (
    ("%m/%d/%Y %I:%M:%S %p", True),
    ("%m/%d/%Y %I:%M %p", True),
    ("%m/%d/%Y %H:%M:%S", True),
    ("%m/%d/%Y %H:%M", True),
    ("%m/%d/%Y", False),
)
_DMY_PATTERNS: tuple[tuple[str, bool], ...] = (
    ("%d/%m/%Y %I:%M:%S %p", True),
    ("%d/%m/%Y %I:%M %p", True),
    ("%d/%m/%Y %H:%M:%S", True),
    ("%d/%m/%Y %H:%M", True),
    ("%d/%m/%Y", False),
)
_YMD_MERIDIAN_PATTERNS: tuple[str, ...] = (
    "%Y-%m-%d %I:%M:%S %p",
    "%Y-%m-%d %I:%M %p",
)
_TIME_ONLY_PATTERNS: tuple[str, ...] = (
    "%I:%M:%S %p",
    "%I:%M %p",
    "%H:%M:%S",
    "%H:%M",
)
_TIMEZONE_OPTIONS: tuple[str, str] = ("utc", "local")
_DEFAULT_INPUT_TIMEZONE = "utc"
_DEFAULT_OUTPUT_TIMEZONE = "utc"


@dataclass(frozen=True, slots=True)
class _ParsedDateTime:
    value: datetime
    has_date: bool
    has_time: bool


class DatetimeConvertModule(BaseModule):
    """Parse common datetime inputs and emit normalized date/time lanes."""

    persistent_inputs = (
        "value",
        "auto",
        "day_first",
        "input_timezone",
        "output_timezone",
    )

    descriptor = ModuleDescriptor(
        module_type="datetime_convert",
        display_name="Datetime Convert",
        family="Transform",
        description="Parses common datetime formats and emits normalized fields.",
        inputs=(
            PortSpec("value", "any", default=""),
            PortSpec("auto", "boolean", default=True),
            PortSpec("day_first", "boolean", default=False),
            PortSpec("input_timezone", "string", default=_DEFAULT_INPUT_TIMEZONE),
            PortSpec("output_timezone", "string", default=_DEFAULT_OUTPUT_TIMEZONE),
            PortSpec("emit", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("datetime", "string", default="", display_name="Datetime"),
            PortSpec("date", "string", default="", display_name="Date"),
            PortSpec("time", "string", default="", display_name="Time"),
            PortSpec("iso", "string", default="", display_name="ISO"),
            PortSpec(
                "epoch_seconds",
                "number",
                default=0.0,
                display_name="Epoch Seconds",
            ),
            PortSpec("date_mdy", "string", default="", display_name="MM/DD/YYYY"),
            PortSpec("date_dmy", "string", default="", display_name="DD/MM/YYYY"),
            PortSpec("time_12h", "string", default="", display_name="Time (12h)"),
            PortSpec(
                "datetime_mdy",
                "string",
                default="",
                display_name="Datetime (MM/DD/YYYY)",
            ),
            PortSpec(
                "datetime_dmy",
                "string",
                default="",
                display_name="Datetime (DD/MM/YYYY)",
            ),
            PortSpec("month_name", "string", default="", display_name="Month Name"),
            PortSpec("named_date", "string", default="", display_name="Named Date"),
            PortSpec(
                "named_datetime",
                "string",
                default="",
                display_name="Named Datetime",
            ),
            PortSpec("year", "integer", default=0, display_name="Year"),
            PortSpec("month", "integer", default=0, display_name="Month"),
            PortSpec("day", "integer", default=0, display_name="Day"),
            PortSpec("hours", "integer", default=0, display_name="Hours"),
            PortSpec("minutes", "integer", default=0, display_name="Minutes"),
            PortSpec("seconds", "number", default=0.0, display_name="Seconds"),
            PortSpec("converted", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._value_input: QLineEdit | None = None
        self._auto_check: QCheckBox | None = None
        self._date_order_group: QButtonGroup | None = None
        self._mdy_radio: QRadioButton | None = None
        self._dmy_radio: QRadioButton | None = None
        self._input_timezone_group: QButtonGroup | None = None
        self._input_utc_radio: QRadioButton | None = None
        self._input_local_radio: QRadioButton | None = None
        self._output_timezone_group: QButtonGroup | None = None
        self._output_utc_radio: QRadioButton | None = None
        self._output_local_radio: QRadioButton | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._value_input = QLineEdit(str(self.inputs["value"]))
        self._value_input.setPlaceholderText(
            "2026-03-10T18:30:00Z | 03/10/2026 6:30 PM | 1704067200"
        )
        self._value_input.textChanged.connect(
            lambda text: self.receive_binding("value", text)
        )
        set_control_height(self._value_input)
        form.addRow("Value", self._value_input)

        self._auto_check = QCheckBox("Auto Convert")
        self._auto_check.setChecked(bool(self.inputs["auto"]))
        self._auto_check.toggled.connect(
            lambda enabled: self.receive_binding("auto", enabled)
        )
        form.addRow("", self._auto_check)

        input_timezone = self._normalized_timezone(
            self.inputs.get("input_timezone"),
            default=_DEFAULT_INPUT_TIMEZONE,
        )
        output_timezone = self._normalized_timezone(
            self.inputs.get("output_timezone"),
            default=_DEFAULT_OUTPUT_TIMEZONE,
        )
        self.inputs["input_timezone"] = input_timezone
        self.inputs["output_timezone"] = output_timezone

        order_row = QWidget()
        order_layout = QHBoxLayout(order_row)
        order_layout.setContentsMargins(0, 0, 0, 0)
        order_layout.setSpacing(10)

        self._date_order_group = QButtonGroup(order_row)
        self._date_order_group.setExclusive(True)

        self._mdy_radio = QRadioButton("MM/DD/YYYY")
        self._dmy_radio = QRadioButton("DD/MM/YYYY")

        self._date_order_group.addButton(self._mdy_radio)
        self._date_order_group.addButton(self._dmy_radio)
        self._mdy_radio.toggled.connect(
            lambda checked: self.receive_binding("day_first", False) if checked else None
        )
        self._dmy_radio.toggled.connect(
            lambda checked: self.receive_binding("day_first", True) if checked else None
        )
        self._sync_date_order_controls(day_first=bool(self.inputs["day_first"]))

        order_layout.addWidget(self._mdy_radio)
        order_layout.addWidget(self._dmy_radio)
        order_layout.addStretch(1)
        form.addRow("Date Input", order_row)

        input_timezone_row = QWidget()
        input_timezone_layout = QHBoxLayout(input_timezone_row)
        input_timezone_layout.setContentsMargins(0, 0, 0, 0)
        input_timezone_layout.setSpacing(10)
        self._input_timezone_group = QButtonGroup(input_timezone_row)
        self._input_timezone_group.setExclusive(True)
        self._input_utc_radio = QRadioButton("UTC")
        self._input_local_radio = QRadioButton("Local")
        self._input_timezone_group.addButton(self._input_utc_radio)
        self._input_timezone_group.addButton(self._input_local_radio)
        self._input_utc_radio.toggled.connect(
            lambda checked: (
                self.receive_binding("input_timezone", "utc") if checked else None
            )
        )
        self._input_local_radio.toggled.connect(
            lambda checked: (
                self.receive_binding("input_timezone", "local") if checked else None
            )
        )
        self._sync_input_timezone_controls(input_timezone=input_timezone)
        input_timezone_layout.addWidget(self._input_utc_radio)
        input_timezone_layout.addWidget(self._input_local_radio)
        input_timezone_layout.addStretch(1)
        form.addRow("Input", input_timezone_row)

        output_timezone_row = QWidget()
        output_timezone_layout = QHBoxLayout(output_timezone_row)
        output_timezone_layout.setContentsMargins(0, 0, 0, 0)
        output_timezone_layout.setSpacing(10)
        self._output_timezone_group = QButtonGroup(output_timezone_row)
        self._output_timezone_group.setExclusive(True)
        self._output_utc_radio = QRadioButton("UTC")
        self._output_local_radio = QRadioButton("Local")
        self._output_timezone_group.addButton(self._output_utc_radio)
        self._output_timezone_group.addButton(self._output_local_radio)
        self._output_utc_radio.toggled.connect(
            lambda checked: (
                self.receive_binding("output_timezone", "utc") if checked else None
            )
        )
        self._output_local_radio.toggled.connect(
            lambda checked: (
                self.receive_binding("output_timezone", "local") if checked else None
            )
        )
        self._sync_output_timezone_controls(output_timezone=output_timezone)
        output_timezone_layout.addWidget(self._output_utc_radio)
        output_timezone_layout.addWidget(self._output_local_radio)
        output_timezone_layout.addStretch(1)
        form.addRow("Output", output_timezone_row)

        emit_btn = QPushButton("Convert")
        emit_btn.clicked.connect(lambda: self.receive_binding("emit", 1))
        set_control_height(emit_btn)
        form.addRow("", emit_btn)

        layout.addLayout(form)
        self._status = QLabel("ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._clear_outputs(reason="ready")
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "value":
            display = "" if value is None else str(value)
            if self._value_input is not None and self._value_input.text() != display:
                self._value_input.blockSignals(True)
                self._value_input.setText(display)
                self._value_input.blockSignals(False)

            if bool(self.inputs["auto"]):
                self._convert(reason="value")
            else:
                self._publish_cached(reason="value updated")
            return

        if port == "auto":
            enabled = bool(value)
            self.inputs["auto"] = enabled
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)

            if enabled:
                self._convert(reason="auto")
            else:
                self._publish_cached(reason="auto updated")
            return

        if port == "day_first":
            enabled = bool(value)
            self.inputs["day_first"] = enabled
            self._sync_date_order_controls(day_first=enabled)

            if bool(self.inputs["auto"]):
                self._convert(reason="day_first")
            else:
                self._publish_cached(reason="day_first updated")
            return

        if port == "input_timezone":
            token = self._normalized_timezone(
                value,
                default=_DEFAULT_INPUT_TIMEZONE,
            )
            self.inputs["input_timezone"] = token
            self._sync_input_timezone_controls(input_timezone=token)

            if bool(self.inputs["auto"]):
                self._convert(reason="input_timezone")
            else:
                self._publish_cached(reason="input_timezone updated")
            return

        if port == "output_timezone":
            token = self._normalized_timezone(
                value,
                default=_DEFAULT_OUTPUT_TIMEZONE,
            )
            self.inputs["output_timezone"] = token
            self._sync_output_timezone_controls(output_timezone=token)

            if bool(self.inputs["auto"]):
                self._convert(reason="output_timezone")
            else:
                self._publish_cached(reason="output_timezone updated")
            return

        if port == "emit" and is_truthy(value):
            self._convert(reason="emit")

    def replay_state(self) -> None:
        if bool(self.inputs["auto"]):
            self._convert(reason="replay")
        else:
            self._publish_cached(reason="replay")

    def _convert(self, *, reason: str) -> None:
        raw = self.inputs.get("value")
        if self._is_empty(raw):
            self._clear_outputs(reason=f"{reason}: empty input")
            return

        try:
            input_timezone = self._normalized_timezone(
                self.inputs.get("input_timezone"),
                default=_DEFAULT_INPUT_TIMEZONE,
            )
            output_timezone = self._normalized_timezone(
                self.inputs.get("output_timezone"),
                default=_DEFAULT_OUTPUT_TIMEZONE,
            )
            self.inputs["input_timezone"] = input_timezone
            self.inputs["output_timezone"] = output_timezone
            self._sync_input_timezone_controls(input_timezone=input_timezone)
            self._sync_output_timezone_controls(output_timezone=output_timezone)
            parsed = self._parse_value(
                raw,
                day_first=bool(self.inputs["day_first"]),
                input_timezone=input_timezone,
            )
        except ValueError as exc:
            self._publish(
                datetime_text="",
                date_text="",
                time_text="",
                iso_text="",
                epoch_seconds=0.0,
                date_mdy_text="",
                date_dmy_text="",
                time_12h_text="",
                datetime_mdy_text="",
                datetime_dmy_text="",
                month_name_text="",
                named_date_text="",
                named_datetime_text="",
                year=0,
                month=0,
                day=0,
                hours=0,
                minutes=0,
                seconds=0.0,
                converted=0,
                error=str(exc),
                reason=f"{reason}: error",
            )
            return

        (
            datetime_text,
            date_text,
            time_text,
            iso_text,
            epoch_seconds,
            date_mdy_text,
            date_dmy_text,
            time_12h_text,
            datetime_mdy_text,
            datetime_dmy_text,
            month_name_text,
            named_date_text,
            named_datetime_text,
            year,
            month,
            day,
            hours,
            minutes,
            seconds,
        ) = self._render_outputs(
            parsed,
            output_timezone=output_timezone,
        )
        summary = self._conversion_summary(
            parsed,
            input_timezone=input_timezone,
            output_timezone=output_timezone,
        )
        self._publish(
            datetime_text=datetime_text,
            date_text=date_text,
            time_text=time_text,
            iso_text=iso_text,
            epoch_seconds=epoch_seconds,
            date_mdy_text=date_mdy_text,
            date_dmy_text=date_dmy_text,
            time_12h_text=time_12h_text,
            datetime_mdy_text=datetime_mdy_text,
            datetime_dmy_text=datetime_dmy_text,
            month_name_text=month_name_text,
            named_date_text=named_date_text,
            named_datetime_text=named_datetime_text,
            year=year,
            month=month,
            day=day,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            converted=1,
            error="",
            reason=f"{reason}: {summary}",
        )

    def _publish_cached(self, *, reason: str) -> None:
        self._publish(
            datetime_text=str(self.outputs.get("datetime", "")),
            date_text=str(self.outputs.get("date", "")),
            time_text=str(self.outputs.get("time", "")),
            iso_text=str(self.outputs.get("iso", "")),
            epoch_seconds=float(self.outputs.get("epoch_seconds", 0.0)),
            date_mdy_text=str(self.outputs.get("date_mdy", "")),
            date_dmy_text=str(self.outputs.get("date_dmy", "")),
            time_12h_text=str(self.outputs.get("time_12h", "")),
            datetime_mdy_text=str(self.outputs.get("datetime_mdy", "")),
            datetime_dmy_text=str(self.outputs.get("datetime_dmy", "")),
            month_name_text=str(self.outputs.get("month_name", "")),
            named_date_text=str(self.outputs.get("named_date", "")),
            named_datetime_text=str(self.outputs.get("named_datetime", "")),
            year=int(self.outputs.get("year", 0)),
            month=int(self.outputs.get("month", 0)),
            day=int(self.outputs.get("day", 0)),
            hours=int(self.outputs.get("hours", 0)),
            minutes=int(self.outputs.get("minutes", 0)),
            seconds=float(self.outputs.get("seconds", 0.0)),
            converted=0,
            error="",
            reason=reason,
        )

    def _clear_outputs(self, *, reason: str) -> None:
        self._publish(
            datetime_text="",
            date_text="",
            time_text="",
            iso_text="",
            epoch_seconds=0.0,
            date_mdy_text="",
            date_dmy_text="",
            time_12h_text="",
            datetime_mdy_text="",
            datetime_dmy_text="",
            month_name_text="",
            named_date_text="",
            named_datetime_text="",
            year=0,
            month=0,
            day=0,
            hours=0,
            minutes=0,
            seconds=0.0,
            converted=0,
            error="",
            reason=reason,
        )

    def _publish(
        self,
        *,
        datetime_text: str,
        date_text: str,
        time_text: str,
        iso_text: str,
        epoch_seconds: float,
        date_mdy_text: str,
        date_dmy_text: str,
        time_12h_text: str,
        datetime_mdy_text: str,
        datetime_dmy_text: str,
        month_name_text: str,
        named_date_text: str,
        named_datetime_text: str,
        year: int,
        month: int,
        day: int,
        hours: int,
        minutes: int,
        seconds: float,
        converted: int,
        error: str,
        reason: str,
    ) -> None:
        self.emit("datetime", datetime_text)
        self.emit("date", date_text)
        self.emit("time", time_text)
        self.emit("iso", iso_text)
        self.emit("epoch_seconds", epoch_seconds)
        self.emit("date_mdy", date_mdy_text)
        self.emit("date_dmy", date_dmy_text)
        self.emit("time_12h", time_12h_text)
        self.emit("datetime_mdy", datetime_mdy_text)
        self.emit("datetime_dmy", datetime_dmy_text)
        self.emit("month_name", month_name_text)
        self.emit("named_date", named_date_text)
        self.emit("named_datetime", named_datetime_text)
        self.emit("year", year)
        self.emit("month", month)
        self.emit("day", day)
        self.emit("hours", hours)
        self.emit("minutes", minutes)
        self.emit("seconds", seconds)
        self.emit("converted", converted)
        self.emit("text", reason)
        self.emit("error", error)
        if self._status is not None:
            self._status.setText(reason)

    def _sync_date_order_controls(self, *, day_first: bool) -> None:
        if self._mdy_radio is None or self._dmy_radio is None:
            return
        self._mdy_radio.blockSignals(True)
        self._dmy_radio.blockSignals(True)
        self._mdy_radio.setChecked(not day_first)
        self._dmy_radio.setChecked(day_first)
        self._mdy_radio.blockSignals(False)
        self._dmy_radio.blockSignals(False)

    def _sync_input_timezone_controls(self, *, input_timezone: str) -> None:
        if self._input_utc_radio is None or self._input_local_radio is None:
            return
        self._input_utc_radio.blockSignals(True)
        self._input_local_radio.blockSignals(True)
        self._input_utc_radio.setChecked(input_timezone == "utc")
        self._input_local_radio.setChecked(input_timezone == "local")
        self._input_utc_radio.blockSignals(False)
        self._input_local_radio.blockSignals(False)

    def _sync_output_timezone_controls(self, *, output_timezone: str) -> None:
        if self._output_utc_radio is None or self._output_local_radio is None:
            return
        self._output_utc_radio.blockSignals(True)
        self._output_local_radio.blockSignals(True)
        self._output_utc_radio.setChecked(output_timezone == "utc")
        self._output_local_radio.setChecked(output_timezone == "local")
        self._output_utc_radio.blockSignals(False)
        self._output_local_radio.blockSignals(False)

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    @staticmethod
    def _normalized_timezone(value: Any, *, default: str) -> str:
        token = str(value).strip().lower()
        if token in _TIMEZONE_OPTIONS:
            return token
        return default

    @staticmethod
    def _parse_value(
        value: Any,
        *,
        day_first: bool,
        input_timezone: str,
    ) -> _ParsedDateTime:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return DatetimeConvertModule._from_epoch_seconds(float(value))

        token = str(value).strip()
        if not token:
            raise ValueError("input is empty")

        if _EPOCH_RE.fullmatch(token):
            return DatetimeConvertModule._from_epoch_seconds(float(token))

        normalized = " ".join(token.split())

        parsed_iso = DatetimeConvertModule._parse_iso(
            normalized,
            input_timezone=input_timezone,
        )
        if parsed_iso is not None:
            return parsed_iso

        slash_patterns = (
            (_DMY_PATTERNS + _MDY_PATTERNS)
            if day_first
            else (_MDY_PATTERNS + _DMY_PATTERNS)
        )
        for pattern, has_time in slash_patterns:
            try:
                parsed = datetime.strptime(normalized, pattern)
            except ValueError:
                continue
            zoned = DatetimeConvertModule._with_timezone(
                parsed,
                timezone=input_timezone,
            )
            return _ParsedDateTime(
                value=zoned.astimezone(UTC),
                has_date=True,
                has_time=has_time,
            )

        for pattern in _YMD_MERIDIAN_PATTERNS:
            try:
                parsed = datetime.strptime(normalized, pattern)
            except ValueError:
                continue
            zoned = DatetimeConvertModule._with_timezone(
                parsed,
                timezone=input_timezone,
            )
            return _ParsedDateTime(
                value=zoned.astimezone(UTC),
                has_date=True,
                has_time=True,
            )

        for pattern in _TIME_ONLY_PATTERNS:
            try:
                parsed = datetime.strptime(normalized, pattern)
            except ValueError:
                continue
            time_value = parsed.time()
            anchored = datetime(
                1970,
                1,
                1,
                time_value.hour,
                time_value.minute,
                time_value.second,
                time_value.microsecond,
            )
            zoned = DatetimeConvertModule._with_timezone(
                anchored,
                timezone=input_timezone,
            )
            return _ParsedDateTime(
                value=zoned.astimezone(UTC),
                has_date=False,
                has_time=True,
            )

        raise ValueError("unsupported datetime format")

    @staticmethod
    def _from_epoch_seconds(value: float) -> _ParsedDateTime:
        if not math.isfinite(value):
            raise ValueError("epoch seconds must be finite")
        try:
            parsed = datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            raise ValueError("epoch seconds out of range") from None
        return _ParsedDateTime(value=parsed, has_date=True, has_time=True)

    @staticmethod
    def _parse_iso(token: str, *, input_timezone: str) -> _ParsedDateTime | None:
        iso_token = token[:-1] + "+00:00" if token.endswith(("Z", "z")) else token
        try:
            parsed = datetime.fromisoformat(iso_token)
        except ValueError:
            return None

        has_time = bool(_ISO_TIME_RE.search(token))
        if not has_time:
            parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
        if parsed.tzinfo is None:
            parsed = DatetimeConvertModule._with_timezone(
                parsed,
                timezone=input_timezone,
            )
        return _ParsedDateTime(
            value=parsed.astimezone(UTC),
            has_date=True,
            has_time=has_time,
        )

    @staticmethod
    def _with_timezone(value: datetime, *, timezone: str) -> datetime:
        if value.tzinfo is not None:
            return value
        if timezone == "utc":
            return value.replace(tzinfo=UTC)
        return value.astimezone()

    @staticmethod
    def _in_output_timezone(value: datetime, *, output_timezone: str) -> datetime:
        if output_timezone == "local":
            return value.astimezone()
        return value.astimezone(UTC)

    @staticmethod
    def _render_outputs(
        parsed: _ParsedDateTime,
        *,
        output_timezone: str,
    ) -> tuple[
        str,
        str,
        str,
        str,
        float,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        int,
        int,
        int,
        int,
        int,
        float,
    ]:
        rendered = DatetimeConvertModule._in_output_timezone(
            parsed.value,
            output_timezone=output_timezone,
        )
        datetime_text = (
            rendered.strftime(_DATETIME_OUTPUT_FORMAT) if parsed.has_date else ""
        )
        date_text = rendered.strftime(_DATE_OUTPUT_FORMAT) if parsed.has_date else ""
        time_text = rendered.strftime(_TIME_OUTPUT_FORMAT) if parsed.has_time else ""
        if parsed.has_date and parsed.has_time:
            if output_timezone == "local":
                iso_text = rendered.isoformat(timespec="seconds")
            else:
                iso_text = rendered.strftime(_ISO_DATETIME_OUTPUT_FORMAT)
        else:
            iso_text = date_text if parsed.has_date else ""
        epoch_seconds = DatetimeConvertModule._to_epoch_seconds(parsed.value)
        date_mdy_text = (
            rendered.strftime(_DATE_MDY_OUTPUT_FORMAT) if parsed.has_date else ""
        )
        date_dmy_text = (
            rendered.strftime(_DATE_DMY_OUTPUT_FORMAT) if parsed.has_date else ""
        )
        time_12h_text = (
            rendered.strftime(_TIME_12H_OUTPUT_FORMAT) if parsed.has_time else ""
        )
        datetime_mdy_text = (
            rendered.strftime(_DATETIME_MDY_OUTPUT_FORMAT)
            if parsed.has_date and parsed.has_time
            else date_mdy_text
        )
        datetime_dmy_text = (
            rendered.strftime(_DATETIME_DMY_OUTPUT_FORMAT)
            if parsed.has_date and parsed.has_time
            else date_dmy_text
        )
        month_name_text = rendered.strftime("%B") if parsed.has_date else ""
        named_date_text = (
            rendered.strftime(_NAMED_DATE_OUTPUT_FORMAT) if parsed.has_date else ""
        )
        named_datetime_text = (
            rendered.strftime(_NAMED_DATETIME_OUTPUT_FORMAT)
            if parsed.has_date and parsed.has_time
            else named_date_text
        )
        year = rendered.year if parsed.has_date else 0
        month = rendered.month if parsed.has_date else 0
        day = rendered.day if parsed.has_date else 0
        hours = rendered.hour if parsed.has_time else 0
        minutes = rendered.minute if parsed.has_time else 0
        seconds = (
            float(rendered.second) + (float(rendered.microsecond) / 1_000_000.0)
            if parsed.has_time
            else 0.0
        )
        return (
            datetime_text,
            date_text,
            time_text,
            iso_text,
            epoch_seconds,
            date_mdy_text,
            date_dmy_text,
            time_12h_text,
            datetime_mdy_text,
            datetime_dmy_text,
            month_name_text,
            named_date_text,
            named_datetime_text,
            year,
            month,
            day,
            hours,
            minutes,
            seconds,
        )

    @staticmethod
    def _to_epoch_seconds(value: datetime) -> float:
        if value.tzinfo is None:
            return float(value.replace(tzinfo=UTC).timestamp())
        return float(value.astimezone(UTC).timestamp())

    @staticmethod
    def _conversion_summary(
        parsed: _ParsedDateTime,
        *,
        input_timezone: str,
        output_timezone: str,
    ) -> str:
        mode_text = f"input={input_timezone}, output={output_timezone}"
        if parsed.has_date and parsed.has_time:
            return f"parsed datetime ({mode_text})"
        if parsed.has_date:
            return f"parsed date ({mode_text})"
        return f"parsed time ({mode_text})"
