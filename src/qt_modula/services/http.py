"""HTTP service abstractions with retry, pacing, and timeout policy."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from qt_modula.services.errors import ServiceError
from qt_modula.services.settings_state import current_provider_network


@dataclass(frozen=True, slots=True)
class HttpRequest:
    """Typed HTTP request model."""

    method: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    json_body: Any | None = None
    timeout_s: float = 10.0
    retries: int = 2
    min_gap_s: float = 0.0
    backoff_s: float = 0.15


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Normalized HTTP response payload."""

    status_code: int
    headers: dict[str, str]
    text: str
    elapsed_ms: int


class HttpClient(Protocol):
    """Provider-agnostic HTTP client interface."""

    def request(self, request: HttpRequest) -> HttpResponse:
        """Execute one request with policy-controlled retries."""

    def close(self) -> None:
        """Release underlying transport resources."""


class DefaultHttpClient:
    """High-throughput HTTP client with deterministic retry behavior."""

    def __init__(self, *, proxy_url: str | None = None) -> None:
        resolved_proxy = proxy_url
        if resolved_proxy is None:
            resolved_proxy = current_provider_network().http.proxy_url.strip() or None
        self._client = httpx.Client(follow_redirects=True, proxy=resolved_proxy)
        self._lock = threading.Lock()
        self._last_request_ts = 0.0

    def request(self, request: HttpRequest) -> HttpResponse:
        last_error: ServiceError | None = None
        for attempt in range(request.retries + 1):
            self._apply_pacing(request.min_gap_s)
            started = time.monotonic()
            try:
                response = self._client.request(
                    request.method.upper(),
                    request.url,
                    params=request.params,
                    headers=request.headers,
                    json=request.json_body,
                    timeout=request.timeout_s,
                )
                elapsed_ms = round((time.monotonic() - started) * 1000.0)
                error = self._status_error(response.status_code)
                if error is not None:
                    last_error = error
                    if error.retryable and attempt < request.retries:
                        self._sleep_backoff(request.backoff_s, attempt)
                        continue
                    raise error

                return HttpResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers.items()),
                    text=response.text,
                    elapsed_ms=elapsed_ms,
                )
            except httpx.TimeoutException as exc:
                last_error = ServiceError(
                    kind="timeout",
                    message=str(exc),
                    provider="httpx",
                    retryable=attempt < request.retries,
                )
                if attempt < request.retries:
                    self._sleep_backoff(request.backoff_s, attempt)
                    continue
                raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = ServiceError(
                    kind="network",
                    message=str(exc),
                    provider="httpx",
                    retryable=attempt < request.retries,
                )
                if attempt < request.retries:
                    self._sleep_backoff(request.backoff_s, attempt)
                    continue
                raise last_error from exc
            except ServiceError:
                raise
            except Exception as exc:
                raise ServiceError(
                    kind="unknown",
                    message=str(exc),
                    provider="httpx",
                ) from exc

        if last_error is not None:
            raise last_error
        raise ServiceError(kind="unknown", message="Request failed without explicit error.")

    def close(self) -> None:
        self._client.close()

    def _apply_pacing(self, min_gap_s: float) -> None:
        if min_gap_s <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = min_gap_s - (now - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.monotonic()

    @staticmethod
    def _sleep_backoff(base: float, attempt: int) -> None:
        delay = max(0.0, base * float(attempt + 1))
        if delay > 0:
            time.sleep(delay)

    @staticmethod
    def _status_error(status_code: int) -> ServiceError | None:
        if status_code == 429:
            return ServiceError(
                kind="rate_limit",
                message="HTTP 429: rate limit",
                retryable=True,
                provider="http",
                details={"status_code": status_code},
            )
        if status_code in {401, 403}:
            return ServiceError(
                kind="auth",
                message=f"HTTP {status_code}: authentication/authorization failed",
                retryable=False,
                provider="http",
                details={"status_code": status_code},
            )
        if status_code == 404:
            return ServiceError(
                kind="not_found",
                message="HTTP 404: resource not found",
                retryable=False,
                provider="http",
                details={"status_code": status_code},
            )
        if status_code >= 500:
            return ServiceError(
                kind="network",
                message=f"HTTP {status_code}: server error",
                retryable=True,
                provider="http",
                details={"status_code": status_code},
            )
        if status_code >= 400:
            return ServiceError(
                kind="validation",
                message=f"HTTP {status_code}: request rejected",
                retryable=False,
                provider="http",
                details={"status_code": status_code},
            )
        return None
