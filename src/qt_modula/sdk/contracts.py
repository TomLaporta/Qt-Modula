"""Public SDK contracts for Qt Modula v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

CapabilityTag = Literal[
    "source",
    "gate",
    "transform",
    "sink",
    "provider",
    "scheduler",
]

PayloadKind = Literal[
    "any",
    "number",
    "integer",
    "string",
    "boolean",
    "json",
    "table",
    "trigger",
    "pulse",
]

Plane = Literal["data", "control"]
PortVisibility = Literal["normal", "advanced", "hidden"]
PortUiGroup = Literal["basic", "advanced"]


@dataclass(frozen=True, slots=True)
class PortSpec:
    """Typed input/output port declaration."""

    key: str
    kind: PayloadKind = "any"
    default: Any = None
    required: bool = False
    description: str = ""
    display_name: str = ""
    plane: Plane = "data"
    control_plane: bool = False
    bind_visibility: PortVisibility = "normal"
    ui_group: PortUiGroup = "basic"

    def __post_init__(self) -> None:
        if self.control_plane:
            object.__setattr__(self, "plane", "control")


@dataclass(frozen=True, slots=True)
class ModuleDescriptor:
    """Module identity and I/O contract."""

    module_type: str
    display_name: str
    family: str
    description: str
    inputs: tuple[PortSpec, ...]
    outputs: tuple[PortSpec, ...]
    capabilities: tuple[CapabilityTag, ...] = ()


@dataclass(frozen=True, slots=True)
class BindingEdge:
    """Directed edge from one output to one input."""

    src_module_id: str
    src_port: str
    dst_module_id: str
    dst_port: str
    order: int = 0


@dataclass(frozen=True, slots=True)
class BindingDiagnostic:
    """Binding candidate validation output."""

    level: Literal["error", "warning", "info"]
    message: str


RuntimeErrorCode = Literal[
    "unknown_module",
    "unknown_port",
    "invalid_binding",
    "cycle_detected",
    "queue_overflow",
    "module_failure",
    "internal_error",
]


@dataclass(frozen=True, slots=True)
class RuntimeFailure:
    """Normalized runtime failure payload."""

    code: RuntimeErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmitResult:
    """Emit call result."""

    ok: bool
    delivered_events: int
    dropped_events: int
    error: RuntimeFailure | None = None


@dataclass(frozen=True, slots=True)
class RuntimeBatch:
    """Single runtime drain statistics."""

    started_ns: int
    ended_ns: int
    delivered_events: int
    dropped_events: int


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """Runtime scheduler bounds."""

    max_queue_size: int = 100_000
    coalesce_pending_inputs: bool = True
    max_deliveries_per_batch: int = 250_000


class RuntimeFailureInfo(Exception):  # noqa: N818
    """Exception that carries a RuntimeFailure payload."""

    def __init__(self, failure: RuntimeFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


class ExecutionContext(Protocol):
    """Runtime API exposed to modules."""

    def emit(self, module_id: str, port: str, value: Any) -> EmitResult:
        """Emit one output payload."""

    def list_bindings(self) -> list[BindingEdge]:
        """Return current bindings in deterministic order."""

    def refresh_module_contract(self, module_id: str) -> None:
        """Refresh runtime contract indexes for a module."""

    def notify_persistent_input_changed(self, module_id: str, key: str, value: Any) -> None:
        """Notify runtime listeners that a persistent input changed."""


class ModuleLifecycle(Protocol):
    """Runtime lifecycle contract implemented by modules."""

    descriptor: ModuleDescriptor

    @property
    def module_id(self) -> str:
        """Stable module identifier."""

    def attach_execution_context(self, context: ExecutionContext) -> None:
        """Attach runtime context."""

    def widget(self) -> Any:
        """Return module root widget."""

    def receive_binding(self, port: str, value: Any) -> None:
        """Receive one bound input payload."""

    def snapshot_inputs(self) -> dict[str, Any]:
        """Return persisted user-intent inputs."""

    def restore_inputs(self, inputs: dict[str, Any]) -> None:
        """Restore persisted user-intent inputs."""

    def replay_state(self) -> None:
        """Republish current outputs after load."""

    def on_close(self) -> None:
        """Release owned resources."""
