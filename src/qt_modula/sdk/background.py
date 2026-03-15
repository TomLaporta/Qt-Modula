"""Reusable background-task runner for module SDK."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _Worker(QObject):
    finished = Signal(int)
    failed = Signal(int)

    def __init__(
        self,
        task_token: int,
        fn: Callable[[], Any],
        *,
        store_result: Callable[[int, Any], None],
        store_error: Callable[[int, str], None],
    ) -> None:
        super().__init__()
        self._task_token = task_token
        self._fn = fn
        self._store_result = store_result
        self._store_error = store_error

    @Slot()
    def run(self) -> None:
        try:
            self._store_result(self._task_token, self._fn())
            self.finished.emit(self._task_token)
        except Exception as exc:
            self._store_error(self._task_token, str(exc))
            self.failed.emit(self._task_token)


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
        self._results: dict[int, Any] = {}
        self._errors: dict[int, str] = {}
        self._result_lock = Lock()
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
        worker = _Worker(
            task_token,
            fn,
            store_result=self._store_result,
            store_error=self._store_error,
        )
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
        worker.finished.connect(self._emit_completed)
        worker.failed.connect(self._emit_failed)

        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda token=task_token: self._on_finished(token))

        self._thread = thread
        thread.start()
        return True

    def _store_result(self, task_token: int, payload: Any) -> None:
        with self._result_lock:
            self._results[task_token] = payload

    def _store_error(self, task_token: int, message: str) -> None:
        with self._result_lock:
            self._errors[task_token] = message

    @Slot(int)
    def _emit_completed(self, task_token: int) -> None:
        with self._result_lock:
            payload = self._results.pop(task_token, None)
        self.completed.emit(payload)

    @Slot(int)
    def _emit_failed(self, task_token: int) -> None:
        with self._result_lock:
            message = self._errors.pop(task_token, "Unknown background failure")
        self.failed.emit(message)

    def _on_task_complete(self, task_token: int) -> None:
        if task_token != self._task_token:
            return
        self._in_flight = False

    def _on_finished(self, task_token: int) -> None:
        self._live_workers.pop(task_token, None)
        self._live_threads.pop(task_token, None)
        with self._result_lock:
            self._results.pop(task_token, None)
            self._errors.pop(task_token, None)
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
        with self._result_lock:
            active_tokens = set(self._live_threads)
            self._results = {
                token: payload for token, payload in self._results.items() if token in active_tokens
            }
            self._errors = {
                token: message for token, message in self._errors.items() if token in active_tokens
            }
        self._worker = None
        self._thread = None
