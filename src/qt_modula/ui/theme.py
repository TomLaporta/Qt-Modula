"""Application stylesheet theming."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True, slots=True)
class Theme:
    primary_color: str
    secondary_color: str
    highlight_color: str
    canvas_color: str


def _blend_hex(color_a: str, color_b: str, ratio: float) -> str:
    """Return a deterministic blend between two #RRGGBB colors."""
    if not (_HEX_COLOR_RE.fullmatch(color_a) and _HEX_COLOR_RE.fullmatch(color_b)):
        return color_a

    clamped = max(0.0, min(1.0, ratio))
    a = tuple(int(color_a[index : index + 2], 16) for index in (1, 3, 5))
    b = tuple(int(color_b[index : index + 2], 16) for index in (1, 3, 5))
    mixed = tuple(
        round((base * (1.0 - clamped)) + (target * clamped))
        for base, target in zip(a, b, strict=True)
    )
    return f"#{mixed[0]:02X}{mixed[1]:02X}{mixed[2]:02X}"


def app_stylesheet(theme: Theme) -> str:
    """Generate application stylesheet."""
    border_color = _blend_hex(theme.secondary_color, theme.canvas_color, 0.72)
    panel_color = _blend_hex(theme.primary_color, theme.canvas_color, 0.4)
    input_bg = _blend_hex(theme.canvas_color, theme.primary_color, 0.12)
    hover_fill = _blend_hex(theme.highlight_color, theme.canvas_color, 0.24)
    selected_fill = _blend_hex(theme.highlight_color, theme.canvas_color, 0.38)
    pressed_fill = _blend_hex(theme.highlight_color, theme.canvas_color, 0.5)
    muted_text = _blend_hex(theme.secondary_color, theme.canvas_color, 0.55)

    return f"""
    QWidget {{
        background: {panel_color};
        color: {theme.secondary_color};
    }}
    QMainWindow {{
        background: {theme.primary_color};
    }}
    QSplitter::handle {{
        background: {border_color};
    }}
    QSplitter::handle:hover {{
        background: {theme.highlight_color};
    }}
    QScrollBar:vertical {{
        background: {input_bg};
        border: 1px solid {border_color};
        width: 12px;
        margin: 0;
    }}
    QScrollBar:horizontal {{
        background: {input_bg};
        border: 1px solid {border_color};
        height: 12px;
        margin: 0;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {theme.highlight_color};
        border: 1px solid {theme.highlight_color};
        border-radius: 4px;
        min-height: 20px;
        min-width: 20px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {hover_fill};
        border-color: {hover_fill};
    }}
    QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {{
        background: {pressed_fill};
        border-color: {pressed_fill};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        border: none;
        background: {input_bg};
        width: 0;
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}
    QListWidget, QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTabWidget::pane {{
        background: {input_bg};
        border: 1px solid {border_color};
        border-radius: 4px;
        padding: 3px;
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {theme.highlight_color};
        background: {theme.canvas_color};
    }}
    QListWidget::item {{
        border: 1px solid transparent;
        border-radius: 4px;
        margin: 1px;
        padding: 3px 4px;
        outline: none;
    }}
    QListWidget::item:focus,
    QListWidget::item:selected:active,
    QListWidget::item:selected:!active {{
        outline: none;
    }}
    QListWidget::item:hover {{
        background: {hover_fill};
        border-color: {theme.highlight_color};
    }}
    QListWidget::item:selected {{
        background: {selected_fill};
        border-color: {theme.highlight_color};
    }}
    QComboBox QAbstractItemView::item {{
        border: 1px solid transparent;
        border-radius: 3px;
        margin: 1px;
        padding: 3px 4px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background: {hover_fill};
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {selected_fill};
    }}
    QPushButton {{
        background: {input_bg};
        border: 1px solid {border_color};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QPushButton:hover {{
        background: {hover_fill};
        border-color: {theme.highlight_color};
    }}
    QPushButton:pressed {{
        background: {pressed_fill};
        border-color: {theme.highlight_color};
    }}
    QPushButton:checked {{
        background: {selected_fill};
        border-color: {theme.highlight_color};
    }}
    QTabBar::tab {{
        background: {input_bg};
        border: 1px solid {border_color};
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        padding: 4px 10px;
        margin-right: 2px;
    }}
    QTabBar::tab:hover {{
        background: {hover_fill};
        border-color: {theme.highlight_color};
    }}
    QTabBar::tab:selected {{
        background: {selected_fill};
        border-color: {theme.highlight_color};
    }}
    QLabel#module-card-title, QLabel#module-card-type {{
        background: transparent;
    }}
    QLabel#module-card-type {{
        color: {muted_text};
    }}
    QFrame#module-card {{
        border: 1px solid {border_color};
        border-radius: 7px;
        background: {theme.canvas_color};
    }}
    QFrame#module-card:focus {{
        background: {selected_fill};
        border-color: {theme.highlight_color};
    }}
    """
