"""Reusable single-file picker and drop widget."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_modula.sdk.ui import set_control_height, set_expand


class SingleFileDropTarget(QFrame):
    """Visible drop target that accepts exactly one local file."""

    fileDropped = Signal(str)
    dropRejected = Signal(str)

    def __init__(self, prompt: str = "Drop a file here") -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        label = QLabel(prompt)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        _path, error = self._extract_single_local_file(event.mimeData().urls())
        if error is None:
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        _path, error = self._extract_single_local_file(event.mimeData().urls())
        if error is None:
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        path, error = self._extract_single_local_file(event.mimeData().urls())
        if error:
            self.dropRejected.emit(error)
            event.ignore()
            return
        if path is None:
            self.dropRejected.emit("Drop exactly one local file.")
            event.ignore()
            return
        self.fileDropped.emit(path)
        event.acceptProposedAction()

    @staticmethod
    def _extract_single_local_file(urls: list[object]) -> tuple[str | None, str | None]:
        if len(urls) != 1:
            return None, "Drop exactly one local file."
        url = urls[0]
        if not hasattr(url, "isLocalFile") or not url.isLocalFile():
            return None, "Only local files are supported."
        if not hasattr(url, "toLocalFile"):
            return None, "Only local files are supported."
        path = str(url.toLocalFile()).strip()
        if not path:
            return None, "Only local files are supported."
        return path, None


class SingleFileSelector(QWidget):
    """Path field, browse button, drop target, auto toggle, and action button."""

    pathCommitted = Signal(str)
    autoImportChanged = Signal(bool)
    importRequested = Signal()
    selectionRejected = Signal(str)

    def __init__(
        self,
        *,
        dialog_title: str,
        file_filter: str = "All Files (*)",
        drop_prompt: str = "Drop a file here",
        action_text: str = "Import",
    ) -> None:
        super().__init__()
        self._dialog_title = dialog_title
        self._file_filter = file_filter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(6)

        self._line_edit = QLineEdit()
        self._line_edit.setPlaceholderText("Type a file path")
        self._line_edit.editingFinished.connect(self._commit_line_edit)
        set_control_height(self._line_edit)
        set_expand(self._line_edit)
        path_row.addWidget(self._line_edit, 1)

        self._browse_button = QPushButton("Browse")
        self._browse_button.clicked.connect(self._browse)
        set_control_height(self._browse_button)
        path_row.addWidget(self._browse_button)

        layout.addLayout(path_row)

        self._drop_target = SingleFileDropTarget(drop_prompt)
        self._drop_target.fileDropped.connect(self._commit_external_path)
        self._drop_target.dropRejected.connect(self.selectionRejected)
        layout.addWidget(self._drop_target)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)

        self._auto_checkbox = QCheckBox("Auto Import")
        self._auto_checkbox.toggled.connect(self.autoImportChanged)
        controls.addWidget(self._auto_checkbox)
        controls.addStretch(1)

        self._action_button = QPushButton(action_text)
        self._action_button.clicked.connect(self.importRequested)
        set_control_height(self._action_button)
        controls.addWidget(self._action_button)

        layout.addLayout(controls)

    @property
    def drop_target(self) -> SingleFileDropTarget:
        return self._drop_target

    def path(self) -> str:
        return self._line_edit.text().strip()

    def set_path(self, value: str) -> None:
        text = value.strip()
        if self._line_edit.text() == text:
            return
        self._line_edit.blockSignals(True)
        self._line_edit.setText(text)
        self._line_edit.blockSignals(False)

    def auto_import(self) -> bool:
        return self._auto_checkbox.isChecked()

    def set_auto_import(self, enabled: bool) -> None:
        if self._auto_checkbox.isChecked() == enabled:
            return
        self._auto_checkbox.blockSignals(True)
        self._auto_checkbox.setChecked(enabled)
        self._auto_checkbox.blockSignals(False)

    def _browse(self) -> None:
        start = self.path() or str(Path.home())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self._dialog_title,
            start,
            self._file_filter,
        )
        if selected:
            self._commit_external_path(selected)

    def _commit_line_edit(self) -> None:
        self._commit_external_path(self._line_edit.text())

    def _commit_external_path(self, value: str) -> None:
        text = value.strip()
        self.set_path(text)
        self.pathCommitted.emit(text)
