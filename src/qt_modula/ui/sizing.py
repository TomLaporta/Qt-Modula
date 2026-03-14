"""UI sizing helpers."""

from __future__ import annotations

from PySide6.QtGui import QScreen

_BASE_EM_PX_DEFAULT = 16.0
_EM_PX_RUNTIME = _BASE_EM_PX_DEFAULT
UI_SCALE_FACTOR = 1.0


def base_em_px(screen: QScreen | None) -> float:
    """Resolve base font-relative unit."""
    if screen is None:
        return _BASE_EM_PX_DEFAULT
    dpi = float(screen.logicalDotsPerInch())
    return max(12.0, min(22.0, _BASE_EM_PX_DEFAULT * (dpi / 96.0)))


def configure_em_base(screen: QScreen | None) -> None:
    """Set the runtime em baseline from one screen's logical DPI."""
    global _EM_PX_RUNTIME
    _EM_PX_RUNTIME = base_em_px(screen)


def em(value: float) -> int:
    """Convert em unit to px integer."""
    return max(1, round(_EM_PX_RUNTIME * value))
