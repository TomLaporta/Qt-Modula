"""Shared async module framework and error-output policy."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from PySide6.QtCore import QObject, Signal, Slot

from qt_modula.sdk.background import BackgroundTaskRunner
from qt_modula.sdk.module import BaseModule
from qt_modula.services.results import (
    ServiceFailure,
    ServiceResult,
    ServiceSuccess,
    service_failure,
)


class _StatusSink(Protocol):
    def setText(self, text: str) -> None:  # noqa: N802
        """Set status text."""


class AsyncServiceRunner(QObject):
    """Shared async task runner for modules using service-result envelopes."""

    completed = Signal(object)
    failed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._runner = BackgroundTaskRunner()
        self._runner.completed.connect(self._on_completed)
        self._runner.failed.connect(self._on_failed)

    def running(self) -> bool:
        return self._runner.running()

    def submit(self, fn: Callable[[], ServiceResult[Any]]) -> bool:
        return self._runner.submit(fn)

    def shutdown(self) -> None:
        self._runner.shutdown()

    @Slot(object)
    def _on_completed(self, payload: object) -> None:
        if isinstance(payload, ServiceSuccess):
            self.completed.emit(payload.value)
            return
        if isinstance(payload, ServiceFailure):
            self.failed.emit(payload)
            return
        self.failed.emit(
            service_failure(
                message="Unexpected async payload envelope.",
                kind="unknown",
            )
        )

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.failed.emit(service_failure(message=message, kind="unknown"))


def apply_async_error_policy(
    module: BaseModule,
    failure: ServiceFailure,
    *,
    reset_outputs: Mapping[str, Any],
    status_sink: _StatusSink | None = None,
    text_port: str = "text",
    error_port: str = "error",
) -> None:
    """Clear stale success outputs and emit deterministic error outputs."""

    for port, value in reset_outputs.items():
        module.emit(port, value)

    if error_port in module.outputs:
        module.emit(error_port, failure.message)

    if text_port in module.outputs and text_port not in reset_outputs:
        module.emit(text_port, f"error: {failure.message}")

    if status_sink is not None:
        status_sink.setText(f"error: {failure.message}")
