"""Qt Modula desktop entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QComboBox

from qt_modula.paths import app_icon_path, settings_path as runtime_settings_path
from qt_modula.persistence import AppConfig, PersistenceError, load_app_config, save_app_config
from qt_modula.services import configure_from_app_config
from qt_modula.ui.main_window import MainWindow
from qt_modula.ui.sizing import UI_SCALE_FACTOR, base_em_px, configure_em_base


class _ComboBoxWheelBlocker(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Wheel and isinstance(watched, QComboBox):
            event.ignore()
            return True
        return super().eventFilter(watched, event)


def _settings_path() -> Path:
    return runtime_settings_path()


def load_or_create_app_config(path: Path) -> AppConfig:
    config = load_app_config(path) if path.exists() else AppConfig()
    save_app_config(path, config)
    return config


def _save_app_config(path: Path, config: AppConfig) -> None:
    save_app_config(path, config)


def _resolve_font(app: QApplication) -> None:
    font = app.font()
    base_px = base_em_px(app.primaryScreen())
    target_px = max(10.0, float(base_px) * UI_SCALE_FACTOR)
    metrics = app.fontMetrics()
    ratio = target_px / max(1.0, float(metrics.height()))
    point = font.pointSizeF()
    if point <= 0:
        point = 12.0
    font.setPointSizeF(max(8.0, min(64.0, point * ratio)))
    app.setFont(font)


def _configure_app_icon(app: QApplication) -> None:
    icon_path = app_icon_path()
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))


def main() -> int:
    """Run Qt Modula desktop app."""
    QApplication.setDesktopSettingsAware(False)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.RoundPreferFloor
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    _configure_app_icon(app)
    combo_box_wheel_blocker = _ComboBoxWheelBlocker(app)
    app.installEventFilter(combo_box_wheel_blocker)
    configure_em_base(app.primaryScreen())
    _resolve_font(app)

    settings_path = _settings_path()
    try:
        config = load_or_create_app_config(settings_path)
    except PersistenceError as exc:
        raise SystemExit(f"Invalid app settings file: {exc}") from exc

    configure_from_app_config(config)

    window = MainWindow(
        config,
        on_app_config_saved=lambda cfg: _save_app_config(settings_path, cfg),
    )
    window.show()
    return app.exec()
