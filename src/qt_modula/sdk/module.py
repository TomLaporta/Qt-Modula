"""Canonical base module class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from qt_modula.sdk.contracts import (
    EmitResult,
    ExecutionContext,
    ModuleDescriptor,
    PortSpec,
    RuntimeFailureInfo,
)
from qt_modula.sdk.validation import coerce_port_value


class ModuleBase(ABC):
    """Base implementation for first-party and plugin modules."""

    descriptor: ModuleDescriptor
    persistent_inputs: tuple[str, ...] = ()

    def __init__(self, module_id: str) -> None:
        self._module_id = module_id
        self._context: ExecutionContext | None = None

        self._input_specs: dict[str, PortSpec] = {
            spec.key: spec for spec in self.descriptor.inputs
        }
        self._output_specs: dict[str, PortSpec] = {
            spec.key: spec for spec in self.descriptor.outputs
        }

        self.inputs: dict[str, Any] = {spec.key: spec.default for spec in self.descriptor.inputs}
        self.outputs: dict[str, Any] = {spec.key: spec.default for spec in self.descriptor.outputs}

    @property
    def module_id(self) -> str:
        return self._module_id

    def attach_execution_context(self, context: ExecutionContext) -> None:
        self._context = context

    def emit(self, port: str, value: Any) -> EmitResult:
        spec = self._output_specs.get(port)
        if spec is None:
            raise KeyError(f"Unknown output port '{port}' in {self.descriptor.module_type}.")

        coerced = coerce_port_value(spec, value)
        self.outputs[port] = coerced

        if self._context is None:
            return EmitResult(ok=True, delivered_events=0, dropped_events=0)

        result = self._context.emit(self._module_id, port, coerced)
        if not result.ok and result.error is not None:
            self._set_error_output(result.error.message)
            raise RuntimeFailureInfo(result.error)
        return result

    def receive_binding(self, port: str, value: Any) -> None:
        spec = self._input_specs.get(port)
        if spec is None:
            message = f"Unknown input port '{port}' in {self.descriptor.module_type}."
            self._publish_error(message)
            raise KeyError(message)

        previous = self.inputs.get(port)
        try:
            coerced = coerce_port_value(spec, value)
        except ValueError as exc:
            self._publish_error(str(exc))
            return

        self.inputs[port] = coerced
        if port in self.persistent_inputs and previous != coerced and self._context is not None:
            self._context.notify_persistent_input_changed(self._module_id, port, coerced)

        self.on_input(port, coerced)

    def _set_input_value(self, port: str, value: Any) -> None:
        previous = self.inputs.get(port)
        self.inputs[port] = value
        if port in self.persistent_inputs and previous != value and self._context is not None:
            self._context.notify_persistent_input_changed(self._module_id, port, value)

    def snapshot_inputs(self) -> dict[str, Any]:
        return {
            key: self.inputs[key]
            for key in self.persistent_inputs
            if key in self._input_specs and key in self.inputs
        }

    def restore_inputs(self, inputs: dict[str, Any]) -> None:
        if not isinstance(inputs, dict):
            raise ValueError("Persisted module inputs payload must be a mapping.")
        expected = set(self.persistent_inputs)
        actual = set(inputs)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing or unexpected:
            parts: list[str] = []
            if missing:
                parts.append(f"missing keys: {', '.join(missing)}")
            if unexpected:
                parts.append(f"unexpected keys: {', '.join(unexpected)}")
            detail = "; ".join(parts)
            raise ValueError(
                f"Persisted inputs for {self.descriptor.module_type} must match the current "
                f"contract exactly ({detail})."
            )
        for key in self.persistent_inputs:
            spec = self._input_specs.get(key)
            if spec is None:
                raise ValueError(
                    f"Persistent input '{key}' is not declared on {self.descriptor.module_type}."
                )
            coerced = coerce_port_value(spec, inputs[key])
            self.inputs[key] = coerced
            self.on_input(key, coerced)

    def replay_state(self) -> None:
        return None

    def on_close(self) -> None:
        return None

    def _publish_error(self, message: str) -> None:
        self._set_error_output(message)
        if self._context is None or "error" not in self._output_specs:
            return
        result = self._context.emit(self._module_id, "error", message)
        if not result.ok and result.error is not None:
            raise RuntimeFailureInfo(result.error)

    def _set_error_output(self, message: str) -> None:
        if "error" in self.outputs:
            self.outputs["error"] = message

    def _set_descriptor_inputs(self, inputs: tuple[PortSpec, ...]) -> None:
        self.descriptor = ModuleDescriptor(
            module_type=self.descriptor.module_type,
            display_name=self.descriptor.display_name,
            family=self.descriptor.family,
            description=self.descriptor.description,
            inputs=inputs,
            outputs=self.descriptor.outputs,
            capabilities=self.descriptor.capabilities,
        )
        self._input_specs = {spec.key: spec for spec in self.descriptor.inputs}
        previous = dict(self.inputs)
        self.inputs = {
            spec.key: previous.get(spec.key, spec.default)
            for spec in self.descriptor.inputs
        }
        if self._context is not None:
            self._context.refresh_module_contract(self.module_id)

    @abstractmethod
    def widget(self) -> Any:
        """Return root widget."""

    @abstractmethod
    def on_input(self, port: str, value: Any) -> None:
        """Handle one coerced input update."""


# Compatibility alias for legacy modules.
BaseModule = ModuleBase
