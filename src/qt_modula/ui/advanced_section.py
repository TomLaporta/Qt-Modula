"""Reusable collapsible advanced options section."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from qt_modula.sdk.ui import set_control_height


class AdvancedSection(QWidget):
    """Simple collapsible section with deterministic toggle text."""

    def __init__(self, title: str, *, expanded: bool = False) -> None:
        super().__init__()
        self._title = title
        self._expanded = expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.toggle_button = QPushButton()
        self.toggle_button.setCheckable(True)
        self.toggle_button.toggled.connect(self.set_expanded)
        set_control_height(self.toggle_button)
        layout.addWidget(self.toggle_button)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)
        layout.addWidget(self.content)

        self.set_expanded(expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        label = f"[-] {self._title}" if self._expanded else f"[+] {self._title}"
        if self.toggle_button.text() != label:
            self.toggle_button.setText(label)
        if self.toggle_button.isChecked() != self._expanded:
            self.toggle_button.blockSignals(True)
            self.toggle_button.setChecked(self._expanded)
            self.toggle_button.blockSignals(False)
        self.content.setVisible(self._expanded)

    @property
    def expanded(self) -> bool:
        return self._expanded
