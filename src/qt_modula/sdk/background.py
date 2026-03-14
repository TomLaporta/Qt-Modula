"""Reusable background-task runner for module SDK."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self._fn())
        except Exception as exc:
            self.failed.emit(str(exc))


class BackgroundTaskRunner(QObject):
    """Single-flight background task utility for module network/CPU tasks."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self._live_threads: dict[int, QThread] = {}
        self._live_workers: dict[int, _Worker] = {}
        self._task_token = 0
        self._in_flight = False

    def running(self) -> bool:
        return self._in_flight

    def submit(self, fn: Callable[[], Any]) -> bool:
        if self.running():
            return False

        self._task_token += 1
        task_token = self._task_token
        thread = QThread()
        worker = _Worker(fn)
        worker.moveToThread(thread)
        self._worker = worker
        self._live_threads[task_token] = thread
        self._live_workers[task_token] = worker
        self._in_flight = True

        thread.started.connect(worker.run)
        worker.finished.connect(
            lambda _payload, token=task_token: self._on_task_complete(token)
        )
        worker.failed.connect(
            lambda _message, token=task_token: self._on_task_complete(token)
        )
        worker.finished.connect(self.completed)
        worker.failed.connect(self.failed)

        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda token=task_token: self._on_finished(token))

        self._thread = thread
        thread.start()
        return True

    def _on_task_complete(self, task_token: int) -> None:
        if task_token != self._task_token:
            return
        self._in_flight = False

    def _on_finished(self, task_token: int) -> None:
        self._live_workers.pop(task_token, None)
        self._live_threads.pop(task_token, None)
        if task_token == self._task_token:
            self._worker = None
            self._thread = None

    def shutdown(self, timeout_ms: int = 2000) -> None:
        self._task_token += 1
        self._in_flight = False
        for thread in tuple(self._live_threads.values()):
            if thread.isRunning():
                thread.quit()
        for thread in tuple(self._live_threads.values()):
            if thread.isRunning():
                thread.wait(timeout_ms)
        self._live_workers = {
            token: worker
            for token, worker in self._live_workers.items()
            if token in self._live_threads and self._live_threads[token].isRunning()
        }
        self._live_threads = {
            token: thread for token, thread in self._live_threads.items() if thread.isRunning()
        }
        self._worker = None
        self._thread = None
