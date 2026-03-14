"""Provider abstractions for market and FX data."""

from __future__ import annotations

import calendar
import math
import time
from collections.abc import Sized
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

from qt_modula.services.errors import ServiceError
from qt_modula.services.http import HttpClient
from qt_modula.services.settings_state import current_provider_network

try:
    import yfinance as yf  # type: ignore[import-untyped]
except Exception:
    yf = None


@dataclass(frozen=True, slots=True)
class FxQuoteRequest:
    from_currency: str
    to_currency: str


@dataclass(frozen=True, slots=True)
class FxQuote:
    """Normalized FX quote."""

    from_currency: str
    to_currency: str
    rate: float
    provider: str
    change: float | None = None
    change_pct: float | None = None
    as_of: str = ""
    source_symbol: str = ""


@dataclass(frozen=True, slots=True)
class MarketHistoryProfileRequest:
    symbol: str


@dataclass(frozen=True, slots=True)
class MarketHistoryProfile:
    """Market history availability profile for one symbol."""

    symbol: str
    provider: str
    source_symbol: str
    available_start: str
    available_end: str
    max_years: int


@dataclass(frozen=True, slots=True)
class MarketHistoryRequest:
    symbol: str
    selected_start: str
    selected_end: str
    interval: str = "auto"
    full_max: bool = False
    extended_hours: bool = False
    filter_zero_volume_outliers: bool = False


@dataclass(frozen=True, slots=True)
class MarketHistory:
    """Normalized market history payload."""

    symbol: str
    provider: str
    source_symbol: str
    selected_start: str
    selected_end: str
    effective_interval: str
    rows: list[dict[str, Any]]


class FxProvider(Protocol):
    """FX provider interface."""

    def quote(self, request: FxQuoteRequest) -> FxQuote:
        """Fetch one FX quote."""


class MarketHistoryProvider(Protocol):
    """Market history provider interface."""

    def profile(self, request: MarketHistoryProfileRequest) -> MarketHistoryProfile:
        """Return the max history bounds available for one symbol."""

    def history(self, request: MarketHistoryRequest) -> MarketHistory:
        """Fetch OHLCV history for one symbol/range."""


@dataclass(frozen=True, slots=True)
class _TickerSnapshot:
    symbol: str
    price: float
    previous_close: float | None
    currency: str
    as_of: str


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return number


def _positive_number(value: object) -> float | None:
    number = _finite_number(value)
    if number is None or number <= 0.0:
        return None
    return number


def _value_from(source: object, key: str) -> object | None:
    getter = getattr(source, "get", None)
    if callable(getter):
        try:
            value = cast(object | None, getter(key))
        except Exception:
            value = None
        if value is not None:
            return value

    if isinstance(source, dict):
        return source.get(key)

    return None


def _first_from(source: object, keys: tuple[str, ...]) -> object | None:
    for key in keys:
        value = _value_from(source, key)
        if value is not None:
            return value
    return None


def _history_closes(history: object) -> tuple[float | None, float | None, str]:
    if history is None:
        return (None, None, "")
    if not isinstance(history, Sized):
        return (None, None, "")

    try:
        if len(history) == 0:
            return (None, None, "")
    except Exception:
        return (None, None, "")

    close_series: Any
    try:
        close_series = cast(Any, history)["Close"]
    except Exception:
        return (None, None, "")

    try:
        last_close = _positive_number(close_series.iloc[-1])
    except Exception:
        last_close = None

    previous_close: float | None = None
    try:
        if len(close_series) >= 2:
            previous_close = _positive_number(close_series.iloc[-2])
    except Exception:
        previous_close = None

    as_of = ""
    try:
        index = cast(Any, getattr(history, "index", []))
        if isinstance(index, Sized) and len(index) > 0:
            as_of = _timestamp_iso(index[-1])  # type: ignore[index]
    except Exception:
        as_of = ""

    return (last_close, previous_close, as_of)


def _timestamp_iso(value: object) -> str:
    if isinstance(value, datetime):
        stamp = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return stamp.astimezone(UTC).isoformat()

    epoch = _finite_number(value)
    if epoch is None:
        return ""
    try:
        return datetime.fromtimestamp(epoch, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def _parse_iso_timestamp(value: str) -> datetime | None:
    token = value.strip()
    if not token:
        return None
    iso_token = token[:-1] + "+00:00" if token.endswith("Z") else token
    try:
        parsed = datetime.fromisoformat(iso_token)
    except ValueError:
        return None
    stamp = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def _extract_market_time(info: object) -> str:
    market_time = _first_from(info, ("regularMarketTime",))
    return _timestamp_iso(market_time)


def _extract_string(source: object, keys: tuple[str, ...]) -> str:
    value = _first_from(source, keys)
    if value is None:
        return ""
    token = str(value).strip()
    return token


def _require_yfinance() -> Any:
    if yf is None:
        raise ServiceError(
            kind="unknown",
            message="yfinance dependency is unavailable.",
            provider="yfinance",
            retryable=False,
        )
    return yf


def _load_snapshot(symbol: str) -> _TickerSnapshot:
    yfinance = _require_yfinance()

    try:
        ticker = yfinance.Ticker(symbol)
    except Exception as exc:
        raise ServiceError(
            kind="network",
            message=f"Failed to initialize yfinance ticker for '{symbol}': {exc}",
            provider="yfinance",
            retryable=True,
        ) from exc

    try:
        fast_info = ticker.fast_info
    except Exception:
        fast_info = {}

    try:
        info = ticker.info
    except Exception:
        info = {}

    try:
        history = ticker.history(period="5d", interval="1d", auto_adjust=False, prepost=True)
    except Exception as exc:
        raise ServiceError(
            kind="network",
            message=f"yfinance history request failed for '{symbol}': {exc}",
            provider="yfinance",
            retryable=True,
        ) from exc

    history_close, history_previous_close, history_as_of = _history_closes(history)

    price = _positive_number(
        _first_from(
            fast_info,
            (
                "lastPrice",
                "regularMarketPrice",
            ),
        )
    )
    if price is None:
        price = _positive_number(
            _first_from(
                info,
                (
                    "regularMarketPrice",
                    "currentPrice",
                    "ask",
                    "bid",
                ),
            )
        )
    if price is None:
        price = history_close
    if price is None:
        raise ServiceError(
            kind="not_found",
            message=f"No quote found for symbol '{symbol}'.",
            provider="yfinance",
            retryable=False,
        )

    previous_close = _positive_number(
        _first_from(
            fast_info,
            (
                "previousClose",
                "regularMarketPreviousClose",
            ),
        )
    )
    if previous_close is None:
        previous_close = _positive_number(
            _first_from(
                info,
                (
                    "previousClose",
                    "regularMarketPreviousClose",
                ),
            )
        )
    if previous_close is None:
        previous_close = history_previous_close

    as_of = _extract_market_time(info)
    if not as_of:
        as_of = history_as_of
    if not as_of:
        as_of = datetime.now(tz=UTC).isoformat()

    currency = _extract_string(fast_info, ("currency",))
    if not currency:
        currency = _extract_string(info, ("currency", "financialCurrency"))

    return _TickerSnapshot(
        symbol=symbol,
        price=price,
        previous_close=previous_close,
        currency=currency,
        as_of=as_of,
    )


def _compute_change(
    price: float,
    previous_close: float | None,
) -> tuple[float | None, float | None]:
    if previous_close is None or previous_close <= 0.0:
        return (None, None)
    change = price - previous_close
    change_pct = (change / previous_close) * 100.0
    return (change, change_pct)


def _history_rows(history: object, *, symbol: str) -> list[dict[str, Any]]:
    if history is None or not isinstance(history, Sized):
        return []

    try:
        size = len(history)
    except Exception:
        return []

    if size <= 0:
        return []

    index = getattr(history, "index", None)
    rows: list[dict[str, Any]] = []

    for idx in range(size):
        try:
            row = cast(Any, history).iloc[idx]
        except Exception:
            continue

        timestamp_raw = None
        try:
            if isinstance(index, Sized) and idx < len(index):
                timestamp_raw = index[idx]  # type: ignore[index]
        except Exception:
            timestamp_raw = None

        timestamp = _timestamp_iso(timestamp_raw)
        if not timestamp:
            continue

        parsed_timestamp = _parse_iso_timestamp(timestamp)
        if parsed_timestamp is None:
            continue
        epoch_s = parsed_timestamp.timestamp()

        open_value = _finite_number(_first_from(row, ("Open", "open")))
        high_value = _finite_number(_first_from(row, ("High", "high")))
        low_value = _finite_number(_first_from(row, ("Low", "low")))
        close_value = _finite_number(_first_from(row, ("Close", "close")))
        adj_close_value = _finite_number(_first_from(row, ("Adj Close", "AdjClose", "adj_close")))
        volume_value = _finite_number(_first_from(row, ("Volume", "volume")))

        if (
            open_value is None
            or high_value is None
            or low_value is None
            or close_value is None
            or adj_close_value is None
            or volume_value is None
            or volume_value < 0.0
        ):
            continue

        rows.append(
            {
                "timestamp": parsed_timestamp.isoformat(),
                "epoch_s": epoch_s,
                "symbol": symbol,
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
                "adj_close": adj_close_value,
                "volume": round(volume_value),
                "x": parsed_timestamp.isoformat(),
                "y": close_value,
                "series": symbol,
            }
        )

    rows.sort(key=lambda row: float(row["epoch_s"]))
    return rows


def _max_years_from_bounds(start_iso: str, end_iso: str) -> int:
    start = _parse_iso_timestamp(start_iso)
    end = _parse_iso_timestamp(end_iso)
    if start is None or end is None:
        return 1
    span_days = max((end - start).days, 0)
    return max(1, math.ceil(span_days / 365.25))


def _shift_months(stamp: datetime, delta_months: int) -> datetime:
    month_index = (stamp.year * 12) + (stamp.month - 1) + delta_months
    year = month_index // 12
    month = (month_index % 12) + 1
    day = min(stamp.day, calendar.monthrange(year, month)[1])
    return stamp.replace(year=year, month=month, day=day)


_MARKET_INTERVAL_TOKENS = ("auto", "1m", "2m", "5m", "15m", "30m", "1h", "1d")
_MARKET_INTERVAL_ALIASES = {"60m": "1h"}
_MARKET_INTERVAL_ORDER = ("1m", "2m", "5m", "15m", "30m", "1h", "1d")
_MARKET_INTERVAL_CAP_DAYS: dict[str, float | None] = {
    "1m": 7.0,
    "2m": 60.0,
    "5m": 60.0,
    "15m": 60.0,
    "30m": 60.0,
    "1h": 730.0,
    "1d": None,
}


def _normalize_market_interval(value: str) -> str:
    token = value.strip().lower()
    token = _MARKET_INTERVAL_ALIASES.get(token, token)
    if token in _MARKET_INTERVAL_TOKENS:
        return token
    raise ServiceError(
        kind="validation",
        message=(
            "interval must be one of: "
            f"{', '.join(_MARKET_INTERVAL_TOKENS)}"
        ),
        provider="yfinance",
        retryable=False,
    )


def _market_range_days(start: datetime, end: datetime) -> float:
    span_days = max((end - start).total_seconds() / 86_400.0, 0.0)
    return span_days + 1.0


def _auto_market_interval(range_days: float) -> str:
    if range_days <= 7.0:
        return "2m"
    if range_days <= 30.0:
        return "5m"
    if range_days <= 60.0:
        return "15m"
    if range_days <= 730.0:
        return "1h"
    return "1d"


def _interval_allowed(interval: str, range_days: float) -> bool:
    cap_days = _MARKET_INTERVAL_CAP_DAYS[interval]
    if cap_days is None:
        return True
    return range_days <= (cap_days + 1e-9)


def _is_intraday_market_interval(interval: str) -> bool:
    return interval != "1d"


def _coarser_intervals(interval: str) -> tuple[str, ...]:
    start_index = _MARKET_INTERVAL_ORDER.index(interval)
    return _MARKET_INTERVAL_ORDER[start_index:]


def _resolve_market_interval(
    *,
    requested: str,
    range_days: float,
    full_max: bool,
) -> tuple[str, str, bool]:
    requested_token = _normalize_market_interval(requested)
    if full_max:
        return requested_token, "1d", requested_token != "1d"

    base_interval = (
        _auto_market_interval(range_days) if requested_token == "auto" else requested_token
    )
    effective_interval = base_interval
    if not _interval_allowed(base_interval, range_days):
        for candidate in _coarser_intervals(base_interval):
            if _interval_allowed(candidate, range_days):
                effective_interval = candidate
                break
        else:
            effective_interval = "1d"

    downgraded = requested_token != "auto" and effective_interval != requested_token
    return requested_token, effective_interval, downgraded


class YFinanceFxProvider:
    """FX provider backed by Yahoo Finance via yfinance."""

    def __init__(
        self,
        _http_client: HttpClient | None = None,
        *,
        retries: int | None = None,
        backoff_s: float | None = None,
    ) -> None:
        defaults = current_provider_network().yfinance
        resolved_retries = defaults.retries if retries is None else retries
        resolved_backoff = defaults.backoff_s if backoff_s is None else backoff_s
        self._retries = max(0, resolved_retries)
        self._backoff_s = max(0.0, resolved_backoff)

    def quote(self, request: FxQuoteRequest) -> FxQuote:
        from_currency = request.from_currency.strip().upper()
        to_currency = request.to_currency.strip().upper()
        if len(from_currency) != 3 or len(to_currency) != 3:
            raise ServiceError(
                kind="validation",
                message="Currencies must be 3-letter ISO codes.",
                provider="yfinance",
                retryable=False,
            )

        if from_currency == to_currency:
            return FxQuote(
                from_currency=from_currency,
                to_currency=to_currency,
                rate=1.0,
                provider="yfinance",
                change=0.0,
                change_pct=0.0,
                as_of=datetime.now(tz=UTC).isoformat(),
                source_symbol=f"{from_currency}{to_currency}=X",
            )

        direct_symbol = f"{from_currency}{to_currency}=X"
        inverse_symbol = f"{to_currency}{from_currency}=X"

        direct_error: ServiceError | None = None
        try:
            direct = self._load_with_retries(direct_symbol)
            rate = direct.price
            change, change_pct = _compute_change(rate, direct.previous_close)
            return FxQuote(
                from_currency=from_currency,
                to_currency=to_currency,
                rate=rate,
                provider="yfinance",
                change=change,
                change_pct=change_pct,
                as_of=direct.as_of,
                source_symbol=direct_symbol,
            )
        except ServiceError as exc:
            direct_error = exc

        if direct_error is None:
            raise ServiceError(
                kind="unknown",
                message="FX quote lookup failed without explicit error.",
                provider="yfinance",
                retryable=False,
            )

        if direct_error.kind not in {"not_found", "provider_payload"}:
            raise direct_error

        inverse = self._load_with_retries(inverse_symbol)
        rate = 1.0 / inverse.price
        previous_close = (
            1.0 / inverse.previous_close
            if inverse.previous_close is not None and inverse.previous_close > 0.0
            else None
        )
        change, change_pct = _compute_change(rate, previous_close)
        if not math.isfinite(rate) or rate <= 0.0:
            raise ServiceError(
                kind="provider_payload",
                message="FX provider returned non-positive rate.",
                provider="yfinance",
                retryable=False,
            )

        return FxQuote(
            from_currency=from_currency,
            to_currency=to_currency,
            rate=rate,
            provider="yfinance",
            change=change,
            change_pct=change_pct,
            as_of=inverse.as_of,
            source_symbol=inverse_symbol,
        )

    def _load_with_retries(self, symbol: str) -> _TickerSnapshot:
        last_error: ServiceError | None = None
        for attempt in range(self._retries + 1):
            try:
                return _load_snapshot(symbol)
            except ServiceError as exc:
                last_error = exc
                should_retry = exc.retryable and attempt < self._retries
                if should_retry:
                    time.sleep(self._backoff_s * float(attempt + 1))
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise ServiceError(
            kind="unknown",
            message=f"Failed to load FX symbol '{symbol}'.",
            provider="yfinance",
            retryable=False,
        )


class YFinanceMarketHistoryProvider:
    """Market history provider backed by Yahoo Finance via yfinance."""

    def __init__(
        self,
        _http_client: HttpClient | None = None,
        *,
        retries: int | None = None,
        backoff_s: float | None = None,
    ) -> None:
        defaults = current_provider_network().yfinance
        resolved_retries = defaults.retries if retries is None else retries
        resolved_backoff = defaults.backoff_s if backoff_s is None else backoff_s
        self._retries = max(0, resolved_retries)
        self._backoff_s = max(0.0, resolved_backoff)

    def profile(self, request: MarketHistoryProfileRequest) -> MarketHistoryProfile:
        symbol = request.symbol.strip().upper()
        if not symbol:
            raise ServiceError(
                kind="validation",
                message="symbol is required",
                provider="yfinance",
                retryable=False,
            )

        history = self._history_with_retries(symbol=symbol, period="max", interval="1d")
        rows = _history_rows(history, symbol=symbol)
        if not rows:
            raise ServiceError(
                kind="not_found",
                message=f"No history found for symbol '{symbol}'.",
                provider="yfinance",
                retryable=False,
            )

        available_start = str(rows[0]["timestamp"])
        available_end = str(rows[-1]["timestamp"])
        max_years = _max_years_from_bounds(available_start, available_end)
        return MarketHistoryProfile(
            symbol=symbol,
            provider="yfinance",
            source_symbol=symbol,
            available_start=available_start,
            available_end=available_end,
            max_years=max_years,
        )

    def history(self, request: MarketHistoryRequest) -> MarketHistory:
        symbol = request.symbol.strip().upper()
        if not symbol:
            raise ServiceError(
                kind="validation",
                message="symbol is required",
                provider="yfinance",
                retryable=False,
            )

        selected_start = _parse_iso_timestamp(request.selected_start)
        selected_end = _parse_iso_timestamp(request.selected_end)
        if selected_start is None or selected_end is None:
            raise ServiceError(
                kind="validation",
                message="selected_start and selected_end must be ISO timestamps",
                provider="yfinance",
                retryable=False,
            )

        if selected_start > selected_end:
            selected_start, selected_end = selected_end, selected_start

        range_days = _market_range_days(selected_start, selected_end)
        _, base_interval, _ = _resolve_market_interval(
            requested=request.interval,
            range_days=range_days,
            full_max=request.full_max,
        )

        last_not_found: ServiceError | None = None
        interval_candidates = _coarser_intervals(base_interval)
        for interval in interval_candidates:
            use_extended_hours = (
                request.extended_hours
                and not request.full_max
                and _is_intraday_market_interval(interval)
            )
            try:
                if request.full_max:
                    history = self._history_with_retries(
                        symbol=symbol,
                        period="max",
                        interval=interval,
                        prepost=use_extended_hours,
                    )
                else:
                    history = self._history_with_retries(
                        symbol=symbol,
                        start=selected_start,
                        end=selected_end + timedelta(days=1),
                        interval=interval,
                        prepost=use_extended_hours,
                    )
            except ServiceError as exc:
                if exc.kind == "not_found":
                    last_not_found = exc
                    continue
                raise

            rows = _history_rows(history, symbol=symbol)
            if not request.full_max:
                start_epoch = selected_start.timestamp()
                end_epoch = (selected_end + timedelta(days=1)).timestamp()
                rows = [
                    row
                    for row in rows
                    if start_epoch <= float(row.get("epoch_s", float("nan"))) < end_epoch
                ]

            if use_extended_hours and request.filter_zero_volume_outliers:
                # Yahoo can emit zero-volume after-hours quote bars with extreme highs/lows.
                rows = [row for row in rows if int(row.get("volume", 0)) > 0]

            if not rows:
                last_not_found = ServiceError(
                    kind="not_found",
                    message=(
                        f"No history rows available for symbol '{symbol}' "
                        f"in selected range for interval '{interval}'."
                    ),
                    provider="yfinance",
                    retryable=False,
                )
                continue

            return MarketHistory(
                symbol=symbol,
                provider="yfinance",
                source_symbol=symbol,
                selected_start=str(rows[0]["timestamp"]),
                selected_end=str(rows[-1]["timestamp"]),
                effective_interval=interval,
                rows=rows,
            )

        if last_not_found is not None:
            raise last_not_found

        raise ServiceError(
            kind="not_found",
            message=f"No history rows available for symbol '{symbol}' in selected range.",
            provider="yfinance",
            retryable=False,
        )

    def compute_selected_start(
        self,
        *,
        profile: MarketHistoryProfile,
        years: int,
        months: int,
        weeks: int,
        days: int,
    ) -> str:
        available_start = _parse_iso_timestamp(profile.available_start)
        available_end = _parse_iso_timestamp(profile.available_end)
        if available_start is None or available_end is None:
            raise ServiceError(
                kind="provider_payload",
                message="provider returned invalid profile timestamps",
                provider="yfinance",
                retryable=False,
            )

        if years >= profile.max_years:
            return available_start.isoformat()

        total_months = max(0, years) * 12 + max(0, months)
        start = _shift_months(available_end, -total_months)
        start = start - timedelta(weeks=max(0, weeks), days=max(0, days))
        if start < available_start:
            start = available_start
        return start.isoformat()

    def _history_with_retries(
        self,
        *,
        symbol: str,
        period: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
        prepost: bool = False,
    ) -> object:
        last_error: ServiceError | None = None

        for attempt in range(self._retries + 1):
            try:
                return self._request_history(
                    symbol=symbol,
                    period=period,
                    start=start,
                    end=end,
                    interval=interval,
                    prepost=prepost,
                )
            except ServiceError as exc:
                last_error = exc
                should_retry = exc.retryable and attempt < self._retries
                if should_retry:
                    time.sleep(self._backoff_s * float(attempt + 1))
                    continue
                raise

        if last_error is not None:
            raise last_error

        raise ServiceError(
            kind="unknown",
            message=f"Failed to load market history for symbol '{symbol}'.",
            provider="yfinance",
            retryable=False,
        )

    @staticmethod
    def _request_history(
        *,
        symbol: str,
        period: str | None,
        start: datetime | None,
        end: datetime | None,
        interval: str,
        prepost: bool,
    ) -> object:
        yfinance = _require_yfinance()

        try:
            ticker = yfinance.Ticker(symbol)
        except Exception as exc:
            raise ServiceError(
                kind="network",
                message=f"Failed to initialize yfinance ticker for '{symbol}': {exc}",
                provider="yfinance",
                retryable=True,
            ) from exc

        kwargs: dict[str, Any] = {
            "interval": interval,
            "auto_adjust": False,
            "actions": False,
            "prepost": prepost,
        }
        if period is not None:
            kwargs["period"] = period
        else:
            kwargs["start"] = start
            kwargs["end"] = end

        try:
            return ticker.history(**kwargs)
        except Exception as exc:
            raise ServiceError(
                kind="network",
                message=f"yfinance history request failed for '{symbol}': {exc}",
                provider="yfinance",
                retryable=True,
            ) from exc
