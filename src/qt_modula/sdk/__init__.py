"""Public SDK surface."""

from qt_modula.sdk.async_services import AsyncServiceRunner, apply_async_error_policy
from qt_modula.sdk.background import BackgroundTaskRunner
from qt_modula.sdk.contracts import (
    BindingDiagnostic,
    BindingEdge,
    CapabilityTag,
    EmitResult,
    ModuleDescriptor,
    ModuleLifecycle,
    PayloadKind,
    Plane,
    PortSpec,
    PortUiGroup,
    PortVisibility,
    RuntimeBatch,
    RuntimeFailure,
    RuntimeFailureInfo,
    RuntimePolicy,
)
from qt_modula.sdk.module import ModuleBase
from qt_modula.sdk.validation import coerce_finite_float, coerce_port_value, is_truthy

BaseModule = ModuleBase

__all__ = [
    "AsyncServiceRunner",
    "BackgroundTaskRunner",
    "BaseModule",
    "BindingDiagnostic",
    "BindingEdge",
    "CapabilityTag",
    "EmitResult",
    "ModuleBase",
    "ModuleDescriptor",
    "ModuleLifecycle",
    "PayloadKind",
    "Plane",
    "PortSpec",
    "PortUiGroup",
    "PortVisibility",
    "RuntimeBatch",
    "RuntimeFailure",
    "RuntimeFailureInfo",
    "RuntimePolicy",
    "apply_async_error_policy",
    "coerce_finite_float",
    "coerce_port_value",
    "is_truthy",
]
