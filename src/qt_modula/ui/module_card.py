"""Canvas card host for modules."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.ui.sizing import em


class _TitleDragLabel(QLabel):
    """Module name label used as the reorder drag handle."""

    def __init__(self, text: str, card: ModuleCard) -> None:
        super().__init__(text)
        self._card = card
        self._press_pos: QPoint | None = None
        self._is_dragging = False
        self.setObjectName("module-card-title")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag to reorder module cards")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._card.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press_pos is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return

        global_pos = event.globalPosition().toPoint()
        if not self._is_dragging:
            if (global_pos - self._press_pos).manhattanLength() < QApplication.startDragDistance():
                super().mouseMoveEvent(event)
                return
            self._is_dragging = True
            self._card.start_live_reorder(global_pos)

        self._card.update_live_reorder(global_pos)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._is_dragging:
            self._card.end_live_reorder()
            self._is_dragging = False
        self._press_pos = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        event.accept()


class ModuleCard(QFrame):
    """Card host for a module widget."""

    remove_requested = Signal(str)
    reorder_started = Signal(str, QPoint)
    reorder_moved = Signal(str, QPoint)
    reorder_finished = Signal(str)

    def __init__(
        self,
        *,
        module_id: str,
        module_name: str,
        module_type_display: str,
        module_widget: QWidget,
    ) -> None:
        super().__init__()
        self.module_id = module_id
        self.setObjectName("module-card")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(em(0.4), em(0.4), em(0.4), em(0.4))
        layout.setSpacing(em(0.3))

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(em(0.3))

        title = _TitleDragLabel(module_name, self)
        type_label = QLabel(f"({module_type_display})")
        type_label.setObjectName("module-card-type")

        close_btn = QPushButton("Remove")
        close_btn.clicked.connect(lambda: self.remove_requested.emit(self.module_id))

        header.addWidget(title)
        header.addWidget(type_label)
        header.addStretch(1)
        header.addWidget(close_btn)

        layout.addLayout(header)
        layout.addWidget(module_widget)

    def start_live_reorder(self, global_pos: QPoint) -> None:
        self.reorder_started.emit(self.module_id, global_pos)

    def update_live_reorder(self, global_pos: QPoint) -> None:
        self.reorder_moved.emit(self.module_id, global_pos)

    def end_live_reorder(self) -> None:
        self.reorder_finished.emit(self.module_id)
