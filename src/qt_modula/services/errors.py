"""Normalized service-layer error taxonomy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ServiceErrorKind = Literal[
    "timeout",
    "network",
    "rate_limit",
    "auth",
    "provider_payload",
    "not_found",
    "validation",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class ServiceError(Exception):
    """Typed service failure used across HTTP/providers/export workflows."""

    kind: ServiceErrorKind
    message: str
    provider: str = ""
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        provider = f" [{self.provider}]" if self.provider else ""
        return f"{self.kind}{provider}: {self.message}"
