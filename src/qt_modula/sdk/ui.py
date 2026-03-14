"""Shared UI helpers for module authoring."""

from __future__ import annotations

from PySide6.QtWidgets import QLayout, QSizePolicy, QWidget

from qt_modula.ui.sizing import em


def apply_layout_defaults(layout: QLayout) -> None:
    """Apply standard spacing and margins."""
    margin = em(0.6)
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(em(0.35))


def set_control_height(widget: QWidget, scale: float = 2.0) -> None:
    """Use deterministic em-based control height."""
    widget.setFixedHeight(em(scale))


def set_expand(widget: QWidget) -> None:
    """Mark a control as horizontally expanding."""
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
