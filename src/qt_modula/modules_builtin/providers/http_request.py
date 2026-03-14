"""Provider-backed HTTP request module."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from qt_modula.sdk import (
    AsyncServiceRunner,
    BaseModule,
    ModuleDescriptor,
    PortSpec,
    apply_async_error_policy,
    is_truthy,
)
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height
from qt_modula.services import (
    DefaultHttpClient,
    HttpRequest,
    ServiceFailure,
    capture_service_result,
    current_provider_network,
)


class HttpRequestModule(BaseModule):
    """Issue HTTP requests via service abstraction and emit normalized payloads."""

    persistent_inputs = (
        "url",
        "method",
        "params",
        "headers",
        "body",
        "timeout_s",
        "retries",
    )

    descriptor = ModuleDescriptor(
        module_type="http_request",
        display_name="HTTP Request",
        family="Providers",
        description="Background HTTP request module with retries/timeouts and normalized errors.",
        inputs=(
            PortSpec("url", "string", default="https://httpbin.org/get"),
            PortSpec("method", "string", default="GET"),
            PortSpec("params", "json", default={}),
            PortSpec("headers", "json", default={}),
            PortSpec("body", "json", default={}),
            PortSpec("timeout_s", "number", default=10.0),
            PortSpec("retries", "integer", default=2),
            PortSpec("fetch", "trigger", default=0, control_plane=True),
        ),
        outputs=(
            PortSpec("status_code", "integer", default=0),
            PortSpec("elapsed_ms", "integer", default=0),
            PortSpec("text", "string", default=""),
            PortSpec("json", "json", default={}),
            PortSpec("busy", "boolean", default=False, control_plane=True),
            PortSpec("fetched", "trigger", default=0, control_plane=True),
            PortSpec("error", "string", default=""),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._apply_global_defaults()
        self._runner = AsyncServiceRunner()
        self._runner.completed.connect(self._on_done)
        self._runner.failed.connect(self._on_failed)

        self._url_edit: QLineEdit | None = None
        self._status: QLabel | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()
        self._url_edit = QLineEdit(str(self.inputs["url"]))
        self._url_edit.textChanged.connect(
            lambda text: self._set_input_value("url", text.strip())
        )
        set_control_height(self._url_edit)
        form.addRow("URL", self._url_edit)

        method_edit = QLineEdit(str(self.inputs["method"]))
        method_edit.textChanged.connect(
            lambda text: self._set_input_value("method", text.strip().upper() or "GET")
        )
        set_control_height(method_edit)
        form.addRow("Method", method_edit)

        fetch_btn = QPushButton("Fetch")
        fetch_btn.clicked.connect(self._start_fetch)
        set_control_height(fetch_btn)
        form.addRow("", fetch_btn)

        layout.addLayout(form)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "url":
            url = str(value).strip()
            self._set_input_value("url", url)
            if self._url_edit is not None and self._url_edit.text() != url:
                self._url_edit.blockSignals(True)
                self._url_edit.setText(url)
                self._url_edit.blockSignals(False)
            return
        if port == "fetch" and is_truthy(value):
            self._start_fetch()

    def _start_fetch(self) -> None:
        if self._runner.running():
            return

        network_defaults = current_provider_network().http
        url = str(self.inputs["url"]).strip()
        if not url:
            self._on_failed(ServiceFailure(message="url is required", kind="validation"))
            return

        method = str(self.inputs["method"]).strip().upper() or "GET"
        params = self._coerce_dict(self.inputs.get("params", {}))
        headers = self._coerce_str_dict(self.inputs.get("headers", {}))
        body = self.inputs.get("body", {})
        timeout_s = max(0.1, float(self.inputs["timeout_s"]))
        retries = max(0, int(self.inputs["retries"]))
        backoff_s = max(0.0, float(network_defaults.backoff_s))
        min_gap_s = max(0.0, float(network_defaults.min_gap_s))
        proxy_url = network_defaults.proxy_url.strip() or None

        self.emit("busy", True)

        def call() -> dict[str, Any]:
            client = DefaultHttpClient(proxy_url=proxy_url)
            try:
                response = client.request(
                    HttpRequest(
                        method=method,
                        url=url,
                        params=params,
                        headers=headers,
                        json_body=body,
                        timeout_s=timeout_s,
                        retries=retries,
                        min_gap_s=min_gap_s,
                        backoff_s=backoff_s,
                    )
                )
            finally:
                client.close()

            return {
                "status_code": response.status_code,
                "elapsed_ms": response.elapsed_ms,
                "text": response.text,
                "json": self._parse_response_json(response.text),
            }

        self._runner.submit(lambda: capture_service_result(call))

    def _on_done(self, payload: object) -> None:
        self.emit("busy", False)
        if not isinstance(payload, dict):
            self._on_failed(ServiceFailure(message="Unexpected response payload", kind="unknown"))
            return

        status_code = int(payload.get("status_code", 0))
        elapsed_ms = int(payload.get("elapsed_ms", 0))
        text = str(payload.get("text", ""))
        json_obj = payload.get("json", {})
        if not isinstance(json_obj, (dict, list)):
            json_obj = {}

        self.emit("status_code", status_code)
        self.emit("elapsed_ms", elapsed_ms)
        self.emit("text", text)
        self.emit("json", json_obj)
        self.emit("fetched", 1)
        self.emit("error", "")

        summary = f"HTTP {status_code} in {elapsed_ms}ms"
        if self._status is not None:
            self._status.setText(summary)

    def _on_failed(self, failure: object) -> None:
        self.emit("busy", False)
        normalized = (
            failure
            if isinstance(failure, ServiceFailure)
            else ServiceFailure(message="Unknown async failure", kind="unknown")
        )
        apply_async_error_policy(
            self,
            normalized,
            reset_outputs={
                "status_code": 0,
                "elapsed_ms": 0,
                "json": {},
                "fetched": 0,
            },
            status_sink=self._status,
        )

    @staticmethod
    def _coerce_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {str(key): item for key, item in value.items()}
        return {}

    @staticmethod
    def _parse_response_json(text: str) -> dict[str, Any] | list[Any]:
        stripped = text.strip()
        if not stripped.startswith(("{", "[")):
            return {}
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, (dict, list)) else {}

    @staticmethod
    def _coerce_str_dict(value: Any) -> dict[str, str]:
        if isinstance(value, dict):
            result: dict[str, str] = {}
            for key, item in value.items():
                result[str(key)] = str(item)
            return result
        return {}

    def _apply_global_defaults(self) -> None:
        defaults = current_provider_network().http
        self.inputs["timeout_s"] = float(defaults.timeout_s)
        self.inputs["retries"] = int(defaults.retries)

    def on_close(self) -> None:
        self._runner.shutdown()
