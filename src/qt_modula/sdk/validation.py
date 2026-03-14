"""Strict value coercion helpers."""

from __future__ import annotations

import json
import math
from typing import Any

from qt_modula.sdk.contracts import PayloadKind, PortSpec


def is_truthy(value: Any) -> bool:
    """Deterministic truthy parsing for control lanes."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def coerce_finite_float(value: Any, *, fallback: float | None = None) -> float | None:
    """Parse finite float or return fallback."""
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return parsed if math.isfinite(parsed) else fallback


def coerce_port_value(port: PortSpec, value: Any) -> Any:
    """Coerce a payload to a port's declared kind."""
    kind: PayloadKind = port.kind

    if kind == "any":
        return value

    if kind in {"trigger", "pulse"}:
        return 1 if is_truthy(value) else 0

    if kind == "boolean":
        return is_truthy(value)

    if kind == "number":
        parsed = coerce_finite_float(value)
        if parsed is None:
            raise ValueError(f"Port '{port.key}' expects a finite number.")
        return parsed

    if kind == "integer":
        parsed = coerce_finite_float(value)
        if parsed is None:
            raise ValueError(f"Port '{port.key}' expects a finite integer.")
        return round(parsed)

    if kind == "string":
        return "" if value is None else str(value)

    if kind == "json":
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            loaded = json.loads(text)
            if not isinstance(loaded, (dict, list)):
                raise ValueError(f"Port '{port.key}' expects JSON object or list.")
            return loaded
        raise ValueError(f"Port '{port.key}' expects JSON payload.")

    if kind == "table":
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            loaded = json.loads(text)
            if isinstance(loaded, list):
                return loaded
        raise ValueError(f"Port '{port.key}' expects table payload list.")

    raise ValueError(f"Unsupported kind '{kind}'.")
