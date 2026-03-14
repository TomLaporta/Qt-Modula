"""Unified async service result envelopes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from qt_modula.services.errors import ServiceError, ServiceErrorKind

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ServiceSuccess(Generic[T]):
    """Explicit successful async service result envelope."""

    value: T
    ok: Literal[True] = True


@dataclass(frozen=True, slots=True)
class ServiceFailure:
    """Explicit failed async service result envelope."""

    message: str
    kind: ServiceErrorKind = "unknown"
    provider: str = ""
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    ok: Literal[False] = False


ServiceResult = ServiceSuccess[T] | ServiceFailure


def service_success(value: T) -> ServiceSuccess[T]:
    return ServiceSuccess(value=value)


def service_failure(
    *,
    message: str,
    kind: ServiceErrorKind = "unknown",
    provider: str = "",
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> ServiceFailure:
    return ServiceFailure(
        message=message,
        kind=kind,
        provider=provider,
        retryable=retryable,
        details=details or {},
    )


def capture_service_result(fn: Callable[[], T]) -> ServiceResult[T]:
    """Run one service call and normalize all exceptions into explicit envelopes."""

    try:
        return service_success(fn())
    except ServiceError as exc:
        return service_failure(
            message=exc.message,
            kind=exc.kind,
            provider=exc.provider,
            retryable=exc.retryable,
            details=exc.details,
        )
    except Exception as exc:
        return service_failure(message=str(exc))
