"""Provider-backed market history fetcher module."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk import (
    AsyncServiceRunner,
    BaseModule,
    ModuleDescriptor,
    PortSpec,
    apply_async_error_policy,
    is_truthy,
)
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height
from qt_modula.services import (
    MarketHistoryProfile,
    MarketHistoryProfileRequest,
    MarketHistoryRequest,
    ServiceFailure,
    YFinanceMarketHistoryProvider,
    capture_service_result,
)

_MONTH_VALUES = tuple(range(12))
_WEEK_VALUES = tuple(range(53))
_DAY_VALUES = tuple(range(32))
_RANGE_CATEGORY_ITEMS = (
    ("years", "Years"),
    ("months", "Months"),
    ("weeks", "Weeks"),
    ("days", "Days"),
)
_RANGE_CATEGORY_KEYS = tuple(key for key, _ in _RANGE_CATEGORY_ITEMS)
_INTERVAL_VALUES = ("auto", "1m", "2m", "5m", "15m", "30m", "1h", "1d")
_INTERVAL_ALIASES = {"60m": "1h"}


@dataclass(slots=True)
class _RangeSelection:
    years: int
    months: int
    weeks: int
    days: int
    interval: str
    extended_hours: bool
    filter_zero_volume_outliers: bool
    selected_start: str
    selected_end: str
    full_max: bool


class MarketFetcherModule(BaseModule):
    """Fetch OHLCV history from yfinance with commit-gated range selection."""

    persistent_inputs = (
        "symbol",
        "years",
        "months",
        "weeks",
        "days",
        "interval",
        "extended_hours",
        "filter_zero_volume_outliers",
        "auto_fetch",
    )

    descriptor = ModuleDescriptor(
        module_type="market_fetcher",
        display_name="Market Fetcher",
        family="Providers",
        description="Fetches market OHLCV history from yfinance with commit-gated date ranges.",
        inputs=(
            PortSpec("symbol", "string", default="AAPL"),
            PortSpec("years", "integer", default=0),
            PortSpec("months", "integer", default=0),
            PortSpec("weeks", "integer", default=0),
            PortSpec("days", "integer", default=0),
            PortSpec("interval", "string", default="auto"),
            PortSpec("extended_hours", "boolean", default=True),
            PortSpec("filter_zero_volume_outliers", "boolean", default=False),
            PortSpec("auto_fetch", "boolean", default=False),
            PortSpec("commit", "trigger", default=0, control_plane=True),
            PortSpec("fetch", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("history", "json", default=[]),
            PortSpec("rows", "table", default=[]),
            PortSpec("row_count", "integer", default=0),
            PortSpec("symbol", "string", default=""),
            PortSpec("provider", "string", default=""),
            PortSpec("source_symbol", "string", default=""),
            PortSpec("extended_trading", "boolean", default=True),
            PortSpec("outliers", "boolean", default=False),
            PortSpec("auto_fetch", "boolean", default=False),
            PortSpec("range_ready", "boolean", default=False),
            PortSpec("max_years", "integer", default=0),
            PortSpec("available_start", "string", default=""),
            PortSpec("available_end", "string", default=""),
            PortSpec("selected_start", "string", default=""),
            PortSpec("selected_end", "string", default=""),
            PortSpec("effective_interval", "string", default=""),
            PortSpec("latest_timestamp", "string", default=""),
            PortSpec("latest_open", "number", default=0.0),
            PortSpec("latest_high", "number", default=0.0),
            PortSpec("latest_low", "number", default=0.0),
            PortSpec("latest_close", "number", default=0.0),
            PortSpec("latest_adj_close", "number", default=0.0),
            PortSpec("latest_volume", "integer", default=0),
            PortSpec("busy", "boolean", default=False, control_plane=True),
            PortSpec("committed", "trigger", default=0, control_plane=True),
            PortSpec("fetched", "trigger", default=0, control_plane=True),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._runner = AsyncServiceRunner()
        self._runner.completed.connect(self._on_done)
        self._runner.failed.connect(self._on_failed)

        self._active_operation: str = ""
        self._queued_commit = False
        self._queued_fetch = False
        self._drain_scheduled = False

        self._profile: MarketHistoryProfile | None = None

        self._symbol_edit: QLineEdit | None = None
        self._range_category_combo: QComboBox | None = None
        self._range_value_combo: QComboBox | None = None
        self._interval_combo: QComboBox | None = None
        self._extended_hours_check: QCheckBox | None = None
        self._filter_outliers_check: QCheckBox | None = None
        self._auto_fetch_check: QCheckBox | None = None
        self._fetch_button: QPushButton | None = None
        self._status: QLabel | None = None
        self._active_range_key = "years"

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        symbol_row = QHBoxLayout()

        self._symbol_edit = QLineEdit(str(self.inputs["symbol"]).strip().upper())
        self._symbol_edit.textChanged.connect(
            lambda text: self.receive_binding("symbol", text.strip().upper())
        )
        set_control_height(self._symbol_edit)
        symbol_row.addWidget(self._symbol_edit, 1)

        commit_button = QPushButton("Commit")
        commit_button.clicked.connect(lambda: self.receive_binding("commit", 1))
        set_control_height(commit_button)
        symbol_row.addWidget(commit_button)

        form.addRow("Symbol", symbol_row)

        self._range_category_combo = QComboBox()
        self._range_category_combo.currentIndexChanged.connect(self._on_range_category_changed)
        set_control_height(self._range_category_combo)
        form.addRow("Range", self._range_category_combo)

        self._range_value_combo = QComboBox()
        self._range_value_combo.currentIndexChanged.connect(self._on_range_value_changed)
        set_control_height(self._range_value_combo)
        form.addRow("Value", self._range_value_combo)

        self._interval_combo = QComboBox()
        self._interval_combo.addItems(list(_INTERVAL_VALUES))
        interval_token = self._normalized_interval(str(self.inputs["interval"]))
        self.inputs["interval"] = interval_token
        self._interval_combo.setCurrentText(interval_token)
        self._interval_combo.currentTextChanged.connect(self._on_interval_changed)
        set_control_height(self._interval_combo)
        form.addRow("Interval", self._interval_combo)

        self._extended_hours_check = QCheckBox("Include Pre/Post Market")
        self._extended_hours_check.setChecked(is_truthy(self.inputs["extended_hours"]))
        self._extended_hours_check.toggled.connect(
            lambda checked: self.receive_binding("extended_hours", checked)
        )
        form.addRow("Extended Hours", self._extended_hours_check)

        self._filter_outliers_check = QCheckBox("Filter Zero-Volume Outliers")
        self._filter_outliers_check.setChecked(
            is_truthy(self.inputs["filter_zero_volume_outliers"])
        )
        self._filter_outliers_check.toggled.connect(
            lambda checked: self.receive_binding("filter_zero_volume_outliers", checked)
        )
        form.addRow("Filter Outliers", self._filter_outliers_check)

        self._auto_fetch_check = QCheckBox("Auto-Fetch")
        self._auto_fetch_check.setChecked(is_truthy(self.inputs["auto_fetch"]))
        self._auto_fetch_check.toggled.connect(
            lambda checked: self.receive_binding("auto_fetch", checked)
        )
        form.addRow("Auto-Fetch", self._auto_fetch_check)

        fetch_button = QPushButton("Fetch")
        fetch_button.clicked.connect(lambda: self.receive_binding("fetch", 1))
        set_control_height(fetch_button)
        form.addRow("", fetch_button)
        self._fetch_button = fetch_button

        layout.addLayout(form)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._render_range_controls(max_years=0)
        self._update_extended_hours_enabled()
        self._update_fetch_enabled()
        self._publish_status("ready", error="")
        self._emit_toggle_outputs()
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "symbol":
            token = str(value).strip().upper()
            self.inputs["symbol"] = token
            self._sync_line_edit(self._symbol_edit, token)
            return

        if port == "years":
            normalized = max(0, int(value))
            self._set_exclusive_range("years", normalized)
            self._render_range_controls(max_years=self._current_max_years())
            self._publish_status("years updated", error="")
            return

        if port == "months":
            normalized = max(0, int(value))
            self._set_exclusive_range("months", normalized)
            self._render_range_controls(max_years=self._current_max_years())
            self._publish_status("months updated", error="")
            return

        if port == "weeks":
            normalized = max(0, int(value))
            self._set_exclusive_range("weeks", normalized)
            self._render_range_controls(max_years=self._current_max_years())
            self._publish_status("weeks updated", error="")
            return

        if port == "days":
            normalized = max(0, int(value))
            self._set_exclusive_range("days", normalized)
            self._render_range_controls(max_years=self._current_max_years())
            self._publish_status("days updated", error="")
            return

        if port == "interval":
            interval_token = self._normalized_interval(str(value))
            self.inputs["interval"] = interval_token
            self._sync_combo(self._interval_combo, interval_token)
            self._update_extended_hours_enabled()
            self._publish_status("interval updated", error="")
            return

        if port == "extended_hours":
            enabled = is_truthy(value)
            self.inputs["extended_hours"] = enabled
            self._sync_checkbox(self._extended_hours_check, enabled)
            self._emit_toggle_outputs()
            self._publish_status("extended hours updated", error="")
            return

        if port == "filter_zero_volume_outliers":
            enabled = is_truthy(value)
            self.inputs["filter_zero_volume_outliers"] = enabled
            self._sync_checkbox(self._filter_outliers_check, enabled)
            self._emit_toggle_outputs()
            self._publish_status("outlier filter updated", error="")
            return

        if port == "auto_fetch":
            enabled = is_truthy(value)
            self.inputs["auto_fetch"] = enabled
            self._sync_checkbox(self._auto_fetch_check, enabled)
            self._emit_toggle_outputs()
            self._publish_status("auto-fetch updated", error="")
            return

        if port == "commit" and is_truthy(value):
            self._queued_commit = True
            self._schedule_drain()
            return

        if port == "fetch" and is_truthy(value):
            self._queued_fetch = True
            self._publish_status("fetch queued", error="")
            self._schedule_drain()

    def _schedule_drain(self) -> None:
        if self._drain_scheduled:
            return
        self._drain_scheduled = True
        QTimer.singleShot(0, self._drain_queued_operations)

    def _drain_queued_operations(self) -> None:
        self._drain_scheduled = False

        if self._runner.running():
            return

        if self._queued_commit:
            self._queued_commit = False
            self._start_commit()
            return

        if self._queued_fetch:
            if self._profile is None:
                self._publish_status(
                    "fetch queued",
                    error="commit required before fetch",
                )
                return
            self._queued_fetch = False
            self._start_fetch()

    def _start_commit(self) -> None:
        if self._runner.running():
            self._queued_commit = True
            return

        symbol = str(self.inputs["symbol"]).strip().upper()
        if not symbol:
            self._on_operation_failed(
                "commit",
                ServiceFailure(message="symbol is required", kind="validation"),
            )
            return

        self.emit("busy", True)
        self._active_operation = "commit"

        def call() -> dict[str, Any]:
            provider = YFinanceMarketHistoryProvider()
            profile = provider.profile(MarketHistoryProfileRequest(symbol=symbol))
            return {
                "symbol": profile.symbol,
                "provider": profile.provider,
                "source_symbol": profile.source_symbol,
                "available_start": profile.available_start,
                "available_end": profile.available_end,
                "max_years": profile.max_years,
            }

        self._runner.submit(lambda: capture_service_result(call))

    def _start_fetch(self) -> None:
        if self._runner.running():
            self._queued_fetch = True
            return

        profile = self._profile
        if profile is None:
            self._queued_fetch = True
            self._publish_status("fetch queued", error="commit required before fetch")
            return

        selection = self._build_selection(profile)

        self.emit("busy", True)
        self._active_operation = "fetch"

        def call() -> dict[str, Any]:
            provider = YFinanceMarketHistoryProvider()
            history = provider.history(
                MarketHistoryRequest(
                    symbol=profile.symbol,
                    selected_start=selection.selected_start,
                    selected_end=selection.selected_end,
                    interval=selection.interval,
                    full_max=selection.full_max,
                    extended_hours=selection.extended_hours,
                    filter_zero_volume_outliers=selection.filter_zero_volume_outliers,
                )
            )
            return {
                "symbol": history.symbol,
                "provider": history.provider,
                "source_symbol": history.source_symbol,
                "rows": history.rows,
                "selected_start": history.selected_start,
                "selected_end": history.selected_end,
                "requested_interval": selection.interval,
                "effective_interval": history.effective_interval,
            }

        self._runner.submit(lambda: capture_service_result(call))

    def _on_done(self, payload: object) -> None:
        operation = self._active_operation
        self._active_operation = ""
        self.emit("busy", False)

        if not isinstance(payload, dict):
            self._on_operation_failed(
                operation,
                ServiceFailure(message="unexpected provider payload", kind="provider_payload"),
            )
            self._schedule_drain()
            return

        if operation == "commit":
            self._on_commit_done(payload)
        elif operation == "fetch":
            self._on_fetch_done(payload)
        else:
            self._on_operation_failed(
                operation,
                ServiceFailure(message="unknown operation completion", kind="unknown"),
            )

        self._schedule_drain()

    def _on_failed(self, failure: object) -> None:
        operation = self._active_operation
        self._active_operation = ""
        self.emit("busy", False)

        normalized = (
            failure
            if isinstance(failure, ServiceFailure)
            else ServiceFailure(message="Unknown async failure", kind="unknown")
        )
        self._on_operation_failed(operation, normalized)
        self._schedule_drain()

    def _on_commit_done(self, payload: dict[str, Any]) -> None:
        try:
            symbol = str(payload.get("symbol", "")).strip().upper()
            provider = str(payload.get("provider", "")).strip()
            source_symbol = str(payload.get("source_symbol", "")).strip().upper()
            available_start = str(payload.get("available_start", "")).strip()
            available_end = str(payload.get("available_end", "")).strip()
            max_years = int(payload.get("max_years", 0))
            if not symbol:
                raise ValueError("symbol is required")
            if not provider:
                raise ValueError("provider is required")
            if not source_symbol:
                source_symbol = symbol
            if not available_start or not available_end:
                raise ValueError("available_start and available_end are required")
            if max_years <= 0:
                raise ValueError("max_years must be > 0")
        except (TypeError, ValueError) as exc:
            self._on_operation_failed(
                "commit",
                ServiceFailure(message=f"Invalid commit payload: {exc}", kind="provider_payload"),
            )
            return

        self._profile = MarketHistoryProfile(
            symbol=symbol,
            provider=provider,
            source_symbol=source_symbol,
            available_start=available_start,
            available_end=available_end,
            max_years=max_years,
        )

        self.inputs["symbol"] = symbol
        self.inputs["years"] = 0
        self.inputs["months"] = 0
        self.inputs["weeks"] = 0
        self.inputs["days"] = 0
        self._active_range_key = "days"

        self._sync_line_edit(self._symbol_edit, symbol)
        self._render_range_controls(max_years=max_years)
        self._update_fetch_enabled()

        self.emit("symbol", symbol)
        self.emit("provider", provider)
        self.emit("source_symbol", source_symbol)
        self.emit("range_ready", True)
        self.emit("max_years", max_years)
        self.emit("available_start", available_start)
        self.emit("available_end", available_end)
        self.emit("selected_start", available_end)
        self.emit("selected_end", available_end)
        self.emit("effective_interval", "")
        self.emit("committed", 1)
        self.emit("fetched", 0)
        self.emit("error", "")
        self._publish_status(
            (
                "commit ok: "
                f"symbol={symbol}, available={available_start}..{available_end}, "
                f"max_years={max_years}"
            ),
            error="",
        )
        if is_truthy(self.inputs.get("auto_fetch", False)):
            self._queued_fetch = True

    def _on_fetch_done(self, payload: dict[str, Any]) -> None:
        try:
            symbol = str(payload.get("symbol", "")).strip().upper()
            provider = str(payload.get("provider", "")).strip()
            source_symbol = str(payload.get("source_symbol", "")).strip().upper()
            selected_start = str(payload.get("selected_start", "")).strip()
            selected_end = str(payload.get("selected_end", "")).strip()
            requested_interval = self._normalized_interval(
                str(payload.get("requested_interval", self.inputs["interval"]))
            )
            effective_raw = str(payload.get("effective_interval", "")).strip()
            effective_interval = self._normalized_interval(effective_raw)
            rows = payload.get("rows", [])
            if not isinstance(rows, list):
                raise ValueError("rows must be a list")
            if not rows:
                raise ValueError("rows is empty")
            latest = rows[-1]
            if not isinstance(latest, dict):
                raise ValueError("latest row is invalid")
            latest_timestamp = str(latest.get("timestamp", "")).strip()
            latest_open = float(latest.get("open", 0.0))
            latest_high = float(latest.get("high", 0.0))
            latest_low = float(latest.get("low", 0.0))
            latest_close = float(latest.get("close", 0.0))
            latest_adj_close = float(latest.get("adj_close", 0.0))
            latest_volume = int(latest.get("volume", 0))
            if not latest_timestamp:
                raise ValueError("latest timestamp is required")
            if (
                not math.isfinite(latest_open)
                or not math.isfinite(latest_high)
                or not math.isfinite(latest_low)
                or not math.isfinite(latest_close)
                or not math.isfinite(latest_adj_close)
            ):
                raise ValueError("latest OHLC values must be finite numbers")
            if not symbol:
                raise ValueError("symbol is required")
            if not provider:
                raise ValueError("provider is required")
            if not source_symbol:
                source_symbol = symbol
            if not selected_start or not selected_end:
                raise ValueError("selected_start and selected_end are required")
            if not effective_raw or effective_interval == "auto":
                raise ValueError("effective_interval is required")
        except (TypeError, ValueError) as exc:
            self._on_operation_failed(
                "fetch",
                ServiceFailure(message=f"Invalid history payload: {exc}", kind="provider_payload"),
            )
            return

        self.emit("history", rows)
        self.emit("rows", rows)
        self.emit("row_count", len(rows))
        self.emit("symbol", symbol)
        self.emit("provider", provider)
        self.emit("source_symbol", source_symbol)
        self.emit("range_ready", True)
        self.emit("selected_start", selected_start)
        self.emit("selected_end", selected_end)
        self.emit("effective_interval", effective_interval)
        self.emit("latest_timestamp", latest_timestamp)
        self.emit("latest_open", latest_open)
        self.emit("latest_high", latest_high)
        self.emit("latest_low", latest_low)
        self.emit("latest_close", latest_close)
        self.emit("latest_adj_close", latest_adj_close)
        self.emit("latest_volume", latest_volume)
        self.emit("committed", 0)
        self.emit("fetched", 1)
        self.emit("error", "")
        interval_note = (
            f"interval=requested:{requested_interval} effective:{effective_interval}"
        )
        if requested_interval != "auto" and requested_interval != effective_interval:
            interval_note = f"{interval_note} downgraded to {effective_interval}"
        self._publish_status(
            (
                f"fetch ok: symbol={symbol}, rows={len(rows)}, "
                f"range={selected_start}..{selected_end}, {interval_note}"
            ),
            error="",
        )

    def _build_selection(self, profile: MarketHistoryProfile) -> _RangeSelection:
        provider = YFinanceMarketHistoryProvider()

        years = max(0, min(int(self.inputs["years"]), profile.max_years))
        months = max(0, int(self.inputs["months"]))
        weeks = max(0, int(self.inputs["weeks"]))
        days = max(0, int(self.inputs["days"]))
        interval_token = self._normalized_interval(str(self.inputs["interval"]))
        extended_hours = is_truthy(self.inputs["extended_hours"])
        filter_zero_volume_outliers = is_truthy(self.inputs["filter_zero_volume_outliers"])

        full_max = years >= profile.max_years
        if full_max:
            months = 0
            weeks = 0
            days = 0
            selected_start = profile.available_start
        else:
            months = min(months, _MONTH_VALUES[-1])
            weeks = min(weeks, _WEEK_VALUES[-1])
            days = min(days, _DAY_VALUES[-1])
            selected_start = provider.compute_selected_start(
                profile=profile,
                years=years,
                months=months,
                weeks=weeks,
                days=days,
            )

        selected_end = profile.available_end
        if not full_max:
            selected_end = max(
                selected_end,
                datetime.now(tz=UTC).replace(microsecond=0).isoformat(),
            )

        self.inputs["years"] = years
        self.inputs["months"] = months
        self.inputs["weeks"] = weeks
        self.inputs["days"] = days
        request_interval = interval_token
        if (
            not full_max
            and interval_token == "auto"
            and years == 0
            and months == 0
            and weeks == 0
            and days == 0
        ):
            request_interval = "1m"

        self.inputs["interval"] = interval_token
        self.inputs["extended_hours"] = extended_hours
        self.inputs["filter_zero_volume_outliers"] = filter_zero_volume_outliers
        self._render_range_controls(max_years=profile.max_years)
        self._sync_combo(self._interval_combo, interval_token)
        self._sync_checkbox(self._extended_hours_check, extended_hours)
        self._sync_checkbox(self._filter_outliers_check, filter_zero_volume_outliers)
        self._update_extended_hours_enabled()
        self._emit_toggle_outputs()

        return _RangeSelection(
            years=years,
            months=months,
            weeks=weeks,
            days=days,
            interval=request_interval,
            extended_hours=extended_hours,
            filter_zero_volume_outliers=filter_zero_volume_outliers,
            selected_start=selected_start,
            selected_end=selected_end,
            full_max=full_max,
        )

    def _on_operation_failed(self, operation: str, failure: ServiceFailure) -> None:
        if operation == "commit":
            self._profile = None
            self._render_range_controls(max_years=0)
            self._update_fetch_enabled()
            apply_async_error_policy(
                self,
                failure,
                reset_outputs={
                    "history": [],
                    "rows": [],
                    "row_count": 0,
                    "symbol": "",
                    "provider": "",
                    "source_symbol": "",
                    "range_ready": False,
                    "max_years": 0,
                    "available_start": "",
                    "available_end": "",
                    "selected_start": "",
                    "selected_end": "",
                    "effective_interval": "",
                    "latest_timestamp": "",
                    "latest_open": 0.0,
                    "latest_high": 0.0,
                    "latest_low": 0.0,
                    "latest_close": 0.0,
                    "latest_adj_close": 0.0,
                    "latest_volume": 0,
                    "committed": 0,
                    "fetched": 0,
                },
                status_sink=self._status,
            )
            return

        if operation == "fetch":
            apply_async_error_policy(
                self,
                failure,
                reset_outputs={
                    "history": [],
                    "rows": [],
                    "row_count": 0,
                    "selected_start": "",
                    "selected_end": "",
                    "effective_interval": "",
                    "latest_timestamp": "",
                    "latest_open": 0.0,
                    "latest_high": 0.0,
                    "latest_low": 0.0,
                    "latest_close": 0.0,
                    "latest_adj_close": 0.0,
                    "latest_volume": 0,
                    "committed": 0,
                    "fetched": 0,
                },
                status_sink=self._status,
            )
            return

        apply_async_error_policy(
            self,
            failure,
            reset_outputs={
                "history": [],
                "rows": [],
                "row_count": 0,
                "symbol": "",
                "provider": "",
                "source_symbol": "",
                "range_ready": False,
                "max_years": 0,
                "available_start": "",
                "available_end": "",
                "selected_start": "",
                "selected_end": "",
                "effective_interval": "",
                "latest_timestamp": "",
                "latest_open": 0.0,
                "latest_high": 0.0,
                "latest_low": 0.0,
                "latest_close": 0.0,
                "latest_adj_close": 0.0,
                "latest_volume": 0,
                "committed": 0,
                "fetched": 0,
            },
            status_sink=self._status,
        )

    def _publish_status(self, text: str, *, error: str) -> None:
        self.emit("text", text)
        self.emit("error", error)
        if self._status is not None:
            self._status.setText(text if not error else f"{text}; error: {error}")

    def replay_state(self) -> None:
        self._emit_toggle_outputs()

    def _emit_toggle_outputs(self) -> None:
        self.emit("extended_trading", is_truthy(self.inputs.get("extended_hours", True)))
        self.emit(
            "outliers",
            is_truthy(self.inputs.get("filter_zero_volume_outliers", False)),
        )
        self.emit("auto_fetch", is_truthy(self.inputs.get("auto_fetch", False)))

    def _current_max_years(self) -> int:
        if self._profile is None:
            return 0
        return max(0, int(self._profile.max_years))

    def _render_range_controls(self, *, max_years: int) -> None:
        max_years = max(0, int(max_years))

        years = max(0, min(int(self.inputs["years"]), max_years)) if max_years > 0 else 0
        full_max_selected = max_years > 0 and years >= max_years

        months_values = (0,) if full_max_selected else _MONTH_VALUES
        weeks_values = (0,) if full_max_selected else _WEEK_VALUES
        days_values = (0,) if full_max_selected else _DAY_VALUES

        months = max(0, int(self.inputs["months"]))
        weeks = max(0, int(self.inputs["weeks"]))
        days = max(0, int(self.inputs["days"]))

        months = min(months, months_values[-1])
        weeks = min(weeks, weeks_values[-1])
        days = min(days, days_values[-1])

        if full_max_selected:
            months = 0
            weeks = 0
            days = 0

        year_values = tuple(range(max_years + 1)) if max_years > 0 else (0,)

        self.inputs["years"] = years
        self.inputs["months"] = months
        self.inputs["weeks"] = weeks
        self.inputs["days"] = days

        category = (
            self._active_range_key
            if self._active_range_key in _RANGE_CATEGORY_KEYS
            else "years"
        )
        self._active_range_key = category
        self._set_combo_items(
            self._range_category_combo,
            tuple((label, key) for key, label in _RANGE_CATEGORY_ITEMS),
            category,
        )

        value_map = {
            "years": year_values,
            "months": months_values,
            "weeks": weeks_values,
            "days": days_values,
        }
        selected_map = {
            "years": years,
            "months": months,
            "weeks": weeks,
            "days": days,
        }
        value_items = tuple(
            (self._range_value_label(category, value), value) for value in value_map[category]
        )
        self._set_combo_items(
            self._range_value_combo,
            value_items,
            selected_map[category],
        )

    def _update_fetch_enabled(self) -> None:
        if self._fetch_button is not None:
            self._fetch_button.setEnabled(self._profile is not None)

    def _update_extended_hours_enabled(self) -> None:
        if self._extended_hours_check is None:
            return
        interval = self._normalized_interval(str(self.inputs.get("interval", "auto")))
        self._extended_hours_check.setEnabled(interval != "1d")

    def _on_range_category_changed(self, _index: int) -> None:
        category = str(
            self._combo_current_data(
                self._range_category_combo,
                fallback=self._active_range_key,
            )
        )
        if category not in _RANGE_CATEGORY_KEYS:
            return
        selected_value = max(0, int(self.inputs.get(category, 0)))
        self._set_exclusive_range(category, selected_value)
        self._render_range_controls(max_years=self._current_max_years())

    def _on_range_value_changed(self, _index: int) -> None:
        category = (
            self._active_range_key
            if self._active_range_key in _RANGE_CATEGORY_KEYS
            else "years"
        )
        fallback = max(0, int(self.inputs.get(category, 0)))
        raw_value = self._combo_current_data(self._range_value_combo, fallback=fallback)
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float, str)):
            value = fallback
        else:
            try:
                value = max(0, int(raw_value))
            except (TypeError, ValueError):
                value = fallback
        if value != int(self.inputs[category]):
            self.receive_binding(category, value)

    def _set_exclusive_range(self, category: str, value: int) -> None:
        if category not in _RANGE_CATEGORY_KEYS:
            return
        normalized = max(0, int(value))
        for key in _RANGE_CATEGORY_KEYS:
            self.inputs[key] = normalized if key == category else 0
        self._active_range_key = category

    def _on_interval_changed(self, text: str) -> None:
        parsed = self._normalized_interval(text)
        if parsed != str(self.inputs["interval"]):
            self.receive_binding("interval", parsed)

    @staticmethod
    def _range_value_label(category: str, value: int) -> str:
        if category == "days" and value == 0:
            return "Today"
        return str(value)

    @staticmethod
    def _normalized_interval(value: str) -> str:
        token = value.strip().lower()
        token = _INTERVAL_ALIASES.get(token, token)
        if token in _INTERVAL_VALUES:
            return token
        return "auto"

    @staticmethod
    def _sync_line_edit(widget: QLineEdit | None, value: str) -> None:
        if widget is None or widget.text() == value:
            return
        widget.blockSignals(True)
        widget.setText(value)
        widget.blockSignals(False)

    @staticmethod
    def _set_combo_items(
        widget: QComboBox | None,
        items: tuple[tuple[str, object], ...],
        selected_data: object,
    ) -> None:
        if widget is None:
            return
        current_items = tuple(
            (widget.itemText(index), widget.itemData(index)) for index in range(widget.count())
        )
        if current_items != items:
            widget.blockSignals(True)
            widget.clear()
            for label, data in items:
                widget.addItem(label, userData=data)
            widget.blockSignals(False)

        selected_index = 0
        for index, (_, data) in enumerate(items):
            if data == selected_data:
                selected_index = index
                break
        if widget.currentIndex() != selected_index:
            widget.blockSignals(True)
            widget.setCurrentIndex(selected_index)
            widget.blockSignals(False)

    @staticmethod
    def _combo_current_data(widget: QComboBox | None, *, fallback: object) -> object:
        if widget is None:
            return fallback
        data = widget.currentData()
        if data is None:
            return fallback
        return data

    @staticmethod
    def _sync_combo(widget: QComboBox | None, value: str) -> None:
        if widget is None or widget.currentText() == value:
            return
        widget.blockSignals(True)
        widget.setCurrentText(value)
        widget.blockSignals(False)

    @staticmethod
    def _sync_checkbox(widget: QCheckBox | None, value: bool) -> None:
        if widget is None or widget.isChecked() == value:
            return
        widget.blockSignals(True)
        widget.setChecked(value)
        widget.blockSignals(False)

    def on_close(self) -> None:
        self._runner.shutdown()
