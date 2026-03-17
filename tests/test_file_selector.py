from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog

from qt_modula.ui.file_selector import SingleFileDropTarget, SingleFileSelector


def test_single_file_selector_browse_commits_selected_path(
    monkeypatch, qapp, tmp_path: Path
) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")

    selector = SingleFileSelector(dialog_title="Select File")
    committed: list[str] = []
    selector.pathCommitted.connect(committed.append)

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(target), ""),
    )

    selector._browse_button.click()
    qapp.processEvents()

    assert committed == [str(target)]
    assert selector.path() == str(target)


def test_drop_target_accepts_single_local_file(qapp, tmp_path: Path) -> None:
    target = SingleFileDropTarget()
    file_path = tmp_path / "data.txt"
    file_path.write_text("ok", encoding="utf-8")

    dropped: list[str] = []
    target.fileDropped.connect(dropped.append)

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(file_path))])

    drag_event = QDragEnterEvent(
        QPoint(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    target.dragEnterEvent(drag_event)

    drop_event = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    target.dropEvent(drop_event)
    qapp.processEvents()

    assert drag_event.isAccepted()
    assert dropped == [str(file_path)]


def test_drop_target_rejects_multiple_or_non_local_files(qapp, tmp_path: Path) -> None:
    target = SingleFileDropTarget()
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")

    rejected: list[str] = []
    target.dropRejected.connect(rejected.append)

    multi_mime = QMimeData()
    multi_mime.setUrls(
        [QUrl.fromLocalFile(str(first)), QUrl.fromLocalFile(str(second))]
    )
    multi_drop = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        multi_mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    target.dropEvent(multi_drop)

    remote_mime = QMimeData()
    remote_mime.setUrls([QUrl("https://example.com/file.txt")])
    remote_drop = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        remote_mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    target.dropEvent(remote_drop)
    qapp.processEvents()

    assert rejected == [
        "Drop exactly one local file.",
        "Only local files are supported.",
    ]
