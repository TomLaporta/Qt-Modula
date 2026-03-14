"""Provider-backed FX quote module."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from qt_modula.sdk import (
    AsyncServiceRunner,
    BaseModule,
    ModuleDescriptor,
    PortSpec,
    apply_async_error_policy,
    coerce_finite_float,
    is_truthy,
)
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height
from qt_modula.services import (
    FxQuoteRequest,
    ServiceFailure,
    YFinanceFxProvider,
    capture_service_result,
)


class FxQuoteModule(BaseModule):
    """Fetch FX rates from configured provider backends."""

    persistent_inputs = ("from_currency", "to_currency")

    descriptor = ModuleDescriptor(
        module_type="fx_quote",
        display_name="FX Quote",
        family="Providers",
        description="Fetches FX quotes from yfinance with normalized workflow outputs.",
        inputs=(
            PortSpec("from_currency", "string", default="USD"),
            PortSpec("to_currency", "string", default="EUR"),
            PortSpec("fetch", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("rate", "number", default=0.0),
            PortSpec("inverse_rate", "number", default=0.0),
            PortSpec("from_currency", "string", default=""),
            PortSpec("to_currency", "string", default=""),
            PortSpec("pair", "string", default=""),
            PortSpec("change", "number", default=0.0),
            PortSpec("change_pct", "number", default=0.0),
            PortSpec("as_of", "string", default=""),
            PortSpec("source_symbol", "string", default=""),
            PortSpec("quote", "json", default={}),
            PortSpec("provider", "string", default=""),
            PortSpec("text", "string", default=""),
            PortSpec("busy", "boolean", default=False, control_plane=True),
            PortSpec("fetched", "trigger", default=0, control_plane=True),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._runner = AsyncServiceRunner()
        self._runner.completed.connect(self._on_done)
        self._runner.failed.connect(self._on_failed)

        self._from_edit: QLineEdit | None = None
        self._to_edit: QLineEdit | None = None
        self._status: QLabel | None = None

    @staticmethod
    def _normalize_currency_token(value: object) -> str:
        return str(value).strip().upper()

    @staticmethod
    def _sync_currency_edit(edit: QLineEdit | None, token: str) -> None:
        if edit is None or edit.text() == token:
            return
        edit.blockSignals(True)
        edit.setText(token)
        edit.blockSignals(False)

    def _effective_currency(self, *, port: str, edit: QLineEdit | None) -> str:
        raw = edit.text() if edit is not None else self.inputs.get(port, "")
        token = self._normalize_currency_token(raw)
        self._set_input_value(port, token)
        self._sync_currency_edit(edit, token)
        return token

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()
        self._from_edit = QLineEdit(str(self.inputs["from_currency"]))
        self._from_edit.textChanged.connect(
            lambda text: self._set_input_value(
                "from_currency", self._normalize_currency_token(text)
            )
        )
        self._from_edit.setMaxLength(3)
        set_control_height(self._from_edit)
        form.addRow("From", self._from_edit)

        self._to_edit = QLineEdit(str(self.inputs["to_currency"]))
        self._to_edit.textChanged.connect(
            lambda text: self._set_input_value("to_currency", self._normalize_currency_token(text))
        )
        self._to_edit.setMaxLength(3)
        set_control_height(self._to_edit)
        form.addRow("To", self._to_edit)

        fetch_btn = QPushButton("Fetch")
        fetch_btn.clicked.connect(self._start_fetch)
        set_control_height(fetch_btn)
        form.addRow("", fetch_btn)

        layout.addLayout(form)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "from_currency":
            token = self._normalize_currency_token(value)
            self._set_input_value("from_currency", token)
            self._sync_currency_edit(self._from_edit, token)
            return

        if port == "to_currency":
            token = self._normalize_currency_token(value)
            self._set_input_value("to_currency", token)
            self._sync_currency_edit(self._to_edit, token)
            return

        if port == "fetch" and is_truthy(value):
            self._start_fetch()

    def _start_fetch(self) -> None:
        if self._runner.running():
            return

        from_currency = self._effective_currency(port="from_currency", edit=self._from_edit)
        to_currency = self._effective_currency(port="to_currency", edit=self._to_edit)
        if len(from_currency) != 3 or len(to_currency) != 3:
            self._on_failed(
                ServiceFailure(
                    message="currencies must be 3-letter ISO codes",
                    kind="validation",
                )
            )
            return

        self.emit("busy", True)

        def call() -> dict[str, Any]:
            provider = YFinanceFxProvider()
            quote = provider.quote(
                FxQuoteRequest(from_currency=from_currency, to_currency=to_currency)
            )
            quote_from = str(getattr(quote, "from_currency", from_currency)).upper()
            quote_to = str(getattr(quote, "to_currency", to_currency)).upper()
            pair = f"{quote_from}/{quote_to}"
            rate = float(getattr(quote, "rate", float("nan")))
            try:
                inverse_rate = 1.0 / rate
            except ZeroDivisionError:
                inverse_rate = float("nan")

            raw_change = getattr(quote, "change", None)
            raw_change_pct = getattr(quote, "change_pct", None)
            change = raw_change if isinstance(raw_change, (int, float)) else 0.0
            change_pct = raw_change_pct if isinstance(raw_change_pct, (int, float)) else 0.0
            delta_text = ""
            if isinstance(raw_change, (int, float)) and isinstance(
                raw_change_pct, (int, float)
            ):
                delta_text = f" delta {raw_change:+.6g} ({raw_change_pct:+.4g}%)"
            as_of = str(getattr(quote, "as_of", ""))
            source_symbol = str(getattr(quote, "source_symbol", ""))
            provider_name = str(getattr(quote, "provider", ""))
            as_of_value = as_of or datetime.now(tz=UTC).isoformat()
            sampled_at = datetime.now(tz=UTC).isoformat()
            as_of_text = f" @ {as_of}" if as_of else ""
            quote_payload = {
                "x": sampled_at,
                "y": rate,
                "series": pair,
                "pair": pair,
                "sampled_at": sampled_at,
                "as_of": as_of_value,
                "rate": rate,
                "inverse_rate": inverse_rate,
                "change": change,
                "change_pct": change_pct,
                "from_currency": quote_from,
                "to_currency": quote_to,
                "provider": provider_name,
                "source_symbol": source_symbol,
            }
            return {
                "rate": rate,
                "inverse_rate": inverse_rate,
                "from_currency": quote_from,
                "to_currency": quote_to,
                "pair": pair,
                "change": change,
                "change_pct": change_pct,
                "as_of": as_of_value,
                "source_symbol": source_symbol,
                "quote": quote_payload,
                "provider": provider_name,
                "text": (
                    f"{pair} {rate:.8g}{delta_text} "
                    f"({provider_name}){as_of_text}"
                ),
            }

        self._runner.submit(lambda: capture_service_result(call))

    def _on_done(self, payload: object) -> None:
        self.emit("busy", False)
        if not isinstance(payload, dict):
            self._on_failed(ServiceFailure(message="Unexpected FX payload", kind="unknown"))
            return

        try:
            from_currency = str(payload.get("from_currency", ""))
            to_currency = str(payload.get("to_currency", ""))
            pair = str(payload.get("pair", ""))
            as_of = str(payload.get("as_of", ""))
            source_symbol = str(payload.get("source_symbol", ""))
            provider = str(payload.get("provider", ""))
            text = str(payload.get("text", ""))
            quote = payload.get("quote", {})
            if not isinstance(quote, dict):
                raise ValueError("quote must be a JSON object")
            rate = coerce_finite_float(payload.get("rate", 0.0))
            inverse_rate = coerce_finite_float(payload.get("inverse_rate", 0.0))
            change = coerce_finite_float(payload.get("change", 0.0))
            change_pct = coerce_finite_float(payload.get("change_pct", 0.0))
            if rate is None:
                raise ValueError("rate must be a finite number")
            if inverse_rate is None:
                raise ValueError("inverse_rate must be a finite number")
            if change is None:
                raise ValueError("change must be a finite number")
            if change_pct is None:
                raise ValueError("change_pct must be a finite number")
        except (TypeError, ValueError) as exc:
            self._on_failed(
                ServiceFailure(
                    message=f"Invalid FX payload: {exc}",
                    kind="provider_payload",
                )
            )
            return

        self.emit("rate", rate)
        self.emit("inverse_rate", inverse_rate)
        self.emit("from_currency", from_currency)
        self.emit("to_currency", to_currency)
        self.emit("pair", pair)
        self.emit("change", change)
        self.emit("change_pct", change_pct)
        self.emit("as_of", as_of)
        self.emit("source_symbol", source_symbol)
        self.emit("quote", quote)
        self.emit("provider", provider)
        self.emit("text", text)
        self.emit("error", "")
        self.emit("fetched", 1)
        if self._status is not None:
            self._status.setText(text)

    def _on_failed(self, failure: object) -> None:
        self.emit("busy", False)
        normalized = (
            failure
            if isinstance(failure, ServiceFailure)
            else ServiceFailure(message="Unknown async failure", kind="unknown")
        )
        apply_async_error_policy(
            self,
            normalized,
            reset_outputs={
                "rate": 0.0,
                "inverse_rate": 0.0,
                "from_currency": "",
                "to_currency": "",
                "pair": "",
                "change": 0.0,
                "change_pct": 0.0,
                "as_of": "",
                "source_symbol": "",
                "quote": {},
                "provider": "",
                "fetched": 0,
            },
            status_sink=self._status,
        )

    def on_close(self) -> None:
        self._runner.shutdown()
