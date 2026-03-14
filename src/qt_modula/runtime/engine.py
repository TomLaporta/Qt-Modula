"""Deterministic single-threaded runtime engine."""

from __future__ import annotations

import heapq
import itertools
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from qt_modula.sdk.contracts import (
    BindingDiagnostic,
    BindingEdge,
    EmitResult,
    ModuleLifecycle,
    PortSpec,
    RuntimeBatch,
    RuntimeErrorCode,
    RuntimeFailure,
    RuntimeFailureInfo,
    RuntimePolicy,
)


@dataclass(frozen=True, slots=True)
class _PendingDelivery:
    """Queued delivery payload."""

    serial: int
    dst_module_id: str
    dst_port: str
    value: Any


class RuntimeEngine:
    """Bounded deterministic scheduler with strict cycle rejection."""

    def __init__(self, policy: RuntimePolicy | None = None) -> None:
        active_policy = policy or RuntimePolicy()
        self._policy = active_policy

        self._modules: dict[str, ModuleLifecycle] = {}
        self._inputs: dict[str, dict[str, PortSpec]] = {}
        self._outputs: dict[str, dict[str, PortSpec]] = {}

        self._bindings: list[BindingEdge] = []
        self._bindings_by_source: dict[tuple[str, str], list[BindingEdge]] = {}

        self._rank_cache: dict[str, int] = {}
        self._pending_heap: list[tuple[tuple[int, int, int, int], int]] = []
        self._pending_keys: dict[tuple[str, str], int] = {}
        self._pending_payloads: dict[int, _PendingDelivery] = {}

        self._sequence = itertools.count(1)
        self._edge_order = itertools.count(1)
        self._delivery_serial = itertools.count(1)

        self._contract_listeners: list[Callable[[str], None]] = []
        self._persistent_input_listeners: list[Callable[[str, str, Any], None]] = []

        self._dropped_events = 0
        self._processing = False
        now = time.time_ns()
        self._last_batch = RuntimeBatch(now, now, 0, 0)

    @property
    def policy(self) -> RuntimePolicy:
        return self._policy

    @property
    def last_batch(self) -> RuntimeBatch:
        return self._last_batch

    def register_module(self, module: ModuleLifecycle) -> None:
        if module.module_id in self._modules:
            raise self._failure("invalid_binding", f"Duplicate module id '{module.module_id}'.")

        self._modules[module.module_id] = module
        self._inputs[module.module_id] = {spec.key: spec for spec in module.descriptor.inputs}
        self._outputs[module.module_id] = {spec.key: spec for spec in module.descriptor.outputs}

        module.attach_execution_context(self)
        self._rebuild_ranks()

    def unregister_module(self, module_id: str) -> None:
        module = self._modules.pop(module_id, None)
        if module is None:
            return

        module.on_close()
        self._inputs.pop(module_id, None)
        self._outputs.pop(module_id, None)

        self._bindings = [
            edge
            for edge in self._bindings
            if edge.src_module_id != module_id and edge.dst_module_id != module_id
        ]
        self._reindex_bindings()
        self._rebuild_ranks()

    def get_module(self, module_id: str) -> ModuleLifecycle | None:
        return self._modules.get(module_id)

    def list_bindings(self) -> list[BindingEdge]:
        return list(self._bindings)

    def clear_bindings(self) -> None:
        self._bindings.clear()
        self._bindings_by_source.clear()
        self._rebuild_ranks()

    def module_ids_in_order(self) -> list[str]:
        return [
            module_id
            for module_id, _rank in sorted(
                self._rank_cache.items(), key=lambda item: (item[1], item[0])
            )
        ]

    def add_module_contract_listener(self, listener: Callable[[str], None]) -> None:
        if listener not in self._contract_listeners:
            self._contract_listeners.append(listener)

    def remove_module_contract_listener(self, listener: Callable[[str], None]) -> None:
        if listener in self._contract_listeners:
            self._contract_listeners.remove(listener)

    def add_persistent_input_listener(self, listener: Callable[[str, str, Any], None]) -> None:
        if listener not in self._persistent_input_listeners:
            self._persistent_input_listeners.append(listener)

    def remove_persistent_input_listener(self, listener: Callable[[str, str, Any], None]) -> None:
        if listener in self._persistent_input_listeners:
            self._persistent_input_listeners.remove(listener)

    def notify_persistent_input_changed(self, module_id: str, key: str, value: Any) -> None:
        for listener in tuple(self._persistent_input_listeners):
            try:
                listener(module_id, key, value)
            except Exception:
                continue

    def refresh_module_contract(self, module_id: str) -> None:
        module = self._modules.get(module_id)
        if module is None:
            return

        next_inputs = {spec.key: spec for spec in module.descriptor.inputs}
        next_outputs = {spec.key: spec for spec in module.descriptor.outputs}
        self._inputs[module_id] = next_inputs
        self._outputs[module_id] = next_outputs

        valid_input_keys = set(next_inputs)
        next_bindings: list[BindingEdge] = []
        bindings_changed = False
        for edge in self._bindings:
            if edge.src_module_id == module_id and edge.src_port not in next_outputs:
                bindings_changed = True
                continue
            if edge.dst_module_id == module_id and edge.dst_port not in valid_input_keys:
                bindings_changed = True
                continue
            next_bindings.append(edge)

        invalid_serials = [
            serial
            for serial, pending in self._pending_payloads.items()
            if pending.dst_module_id == module_id and pending.dst_port not in valid_input_keys
        ]
        for serial in invalid_serials:
            self._pending_payloads.pop(serial, None)

        invalid_keys = [
            pending_key
            for pending_key in self._pending_keys
            if pending_key[0] == module_id and pending_key[1] not in valid_input_keys
        ]
        for pending_key in invalid_keys:
            self._pending_keys.pop(pending_key, None)

        if bindings_changed:
            self._bindings = next_bindings
            self._reindex_bindings()

        self._rebuild_ranks()
        for listener in tuple(self._contract_listeners):
            try:
                listener(module_id)
            except Exception:
                continue

    def diagnostics_for_edge(self, edge: BindingEdge) -> list[BindingDiagnostic]:
        diagnostics: list[BindingDiagnostic] = []

        src_out = self._outputs.get(edge.src_module_id, {}).get(edge.src_port)
        dst_in = self._inputs.get(edge.dst_module_id, {}).get(edge.dst_port)

        if edge.src_module_id not in self._modules:
            diagnostics.append(
                BindingDiagnostic(
                    "error",
                    f"Unknown source module '{edge.src_module_id}'.",
                )
            )
        if edge.dst_module_id not in self._modules:
            diagnostics.append(
                BindingDiagnostic("error", f"Unknown destination module '{edge.dst_module_id}'.")
            )
        if src_out is None and edge.src_module_id in self._modules:
            diagnostics.append(
                BindingDiagnostic(
                    "error",
                    f"Unknown source output '{edge.src_module_id}.{edge.src_port}'.",
                )
            )
        if dst_in is None and edge.dst_module_id in self._modules:
            diagnostics.append(
                BindingDiagnostic(
                    "error",
                    f"Unknown destination input '{edge.dst_module_id}.{edge.dst_port}'.",
                )
            )

        if src_out is not None and dst_in is not None:
            if src_out.plane != dst_in.plane:
                diagnostics.append(
                    BindingDiagnostic(
                        "warning",
                        "Plane mismatch between source output and destination input.",
                    )
                )
            if src_out.kind != "any" and dst_in.kind != "any" and src_out.kind != dst_in.kind:
                diagnostics.append(
                    BindingDiagnostic(
                        "warning",
                        f"Payload kind mismatch: {src_out.kind} -> {dst_in.kind}.",
                    )
                )

        if (
            edge.src_module_id in self._modules
            and edge.dst_module_id in self._modules
            and self._would_create_cycle(edge.src_module_id, edge.dst_module_id)
        ):
            diagnostics.append(
                BindingDiagnostic("error", "Binding would create a cycle (strict cycle policy).")
            )

        if not diagnostics:
            diagnostics.append(BindingDiagnostic("info", "Binding is valid."))
        return diagnostics

    def add_binding(
        self,
        src_module_id: str,
        src_port: str,
        dst_module_id: str,
        dst_port: str,
    ) -> BindingEdge:
        candidate = BindingEdge(
            src_module_id=src_module_id,
            src_port=src_port,
            dst_module_id=dst_module_id,
            dst_port=dst_port,
        )

        for diagnostic in self.diagnostics_for_edge(candidate):
            if diagnostic.level == "error":
                raise self._failure("invalid_binding", diagnostic.message)

        for edge in self._bindings:
            if (
                edge.src_module_id == src_module_id
                and edge.src_port == src_port
                and edge.dst_module_id == dst_module_id
                and edge.dst_port == dst_port
            ):
                return edge

        edge = BindingEdge(
            src_module_id=src_module_id,
            src_port=src_port,
            dst_module_id=dst_module_id,
            dst_port=dst_port,
            order=next(self._edge_order),
        )
        self._bindings.append(edge)
        self._bindings_by_source.setdefault((src_module_id, src_port), []).append(edge)
        self._bindings_by_source[(src_module_id, src_port)].sort(key=lambda item: item.order)
        self._rebuild_ranks()
        return edge

    def remove_binding(self, edge: BindingEdge) -> bool:
        before = len(self._bindings)
        self._bindings = [
            item
            for item in self._bindings
            if not (
                item.src_module_id == edge.src_module_id
                and item.src_port == edge.src_port
                and item.dst_module_id == edge.dst_module_id
                and item.dst_port == edge.dst_port
            )
        ]
        if len(self._bindings) == before:
            return False
        self._reindex_bindings()
        self._rebuild_ranks()
        return True

    def emit(self, module_id: str, port: str, value: Any) -> EmitResult:
        if module_id not in self._modules:
            return EmitResult(
                ok=False,
                delivered_events=0,
                dropped_events=self._dropped_events,
                error=RuntimeFailure(
                    code="unknown_module",
                    message=f"Unknown source module '{module_id}'.",
                ),
            )

        out_spec = self._outputs.get(module_id, {}).get(port)
        if out_spec is None:
            return EmitResult(
                ok=False,
                delivered_events=0,
                dropped_events=self._dropped_events,
                error=RuntimeFailure(
                    code="unknown_port",
                    message=f"Unknown output '{module_id}.{port}'.",
                ),
            )

        sequence = next(self._sequence)
        try:
            self._enqueue_event(
                source_module_id=module_id,
                source_port=out_spec.key,
                value=value,
                sequence=sequence,
            )
            batch = self._process_if_idle()
            return EmitResult(
                ok=True,
                delivered_events=batch.delivered_events,
                dropped_events=self._dropped_events,
            )
        except RuntimeFailureInfo as exc:
            self._reset_pending_deliveries()
            return EmitResult(
                ok=False,
                delivered_events=0,
                dropped_events=self._dropped_events,
                error=exc.failure,
            )
        except Exception as exc:
            self._reset_pending_deliveries()
            return EmitResult(
                ok=False,
                delivered_events=0,
                dropped_events=self._dropped_events,
                error=RuntimeFailure(
                    code="internal_error",
                    message="Unexpected runtime failure.",
                    details={"exception": str(exc)},
                ),
            )

    def _enqueue_event(
        self,
        *,
        source_module_id: str,
        source_port: str,
        value: Any,
        sequence: int,
    ) -> None:
        edges = self._bindings_by_source.get((source_module_id, source_port), [])
        for edge in edges:
            self._enqueue_delivery(
                src_sequence=sequence,
                edge_order=edge.order,
                dst_module_id=edge.dst_module_id,
                dst_port=edge.dst_port,
                value=value,
            )

    def _enqueue_delivery(
        self,
        *,
        src_sequence: int,
        edge_order: int,
        dst_module_id: str,
        dst_port: str,
        value: Any,
    ) -> None:
        delivery_key = (dst_module_id, dst_port)
        replaced_serial: int | None = None

        if self._policy.coalesce_pending_inputs:
            previous = self._pending_keys.get(delivery_key)
            if previous is not None and previous in self._pending_payloads:
                replaced_serial = previous

        active_pending = len(self._pending_payloads)
        if replaced_serial is not None:
            active_pending -= 1
        if active_pending >= self._policy.max_queue_size:
            self._dropped_events += 1
            raise self._failure(
                "queue_overflow",
                f"Runtime queue overflow ({self._policy.max_queue_size}).",
            )

        if replaced_serial is not None:
            self._pending_payloads.pop(replaced_serial, None)

        rank = self._rank_cache.get(dst_module_id, 0)
        serial = next(self._delivery_serial)
        pending = _PendingDelivery(
            serial=serial,
            dst_module_id=dst_module_id,
            dst_port=dst_port,
            value=value,
        )

        if self._policy.coalesce_pending_inputs:
            self._pending_keys[delivery_key] = serial

        self._pending_payloads[serial] = pending
        heapq.heappush(self._pending_heap, ((rank, src_sequence, edge_order, serial), serial))

    def _process_if_idle(self) -> RuntimeBatch:
        if self._processing:
            now = time.time_ns()
            return RuntimeBatch(now, now, 0, 0)

        self._processing = True
        started = time.time_ns()
        delivered = 0
        dropped_before = self._dropped_events

        try:
            while self._pending_heap:
                if delivered >= self._policy.max_deliveries_per_batch:
                    raise self._failure(
                        "cycle_detected",
                        "Delivery budget exceeded; probable cycle or runaway pulse.",
                        details={"budget": self._policy.max_deliveries_per_batch},
                    )

                _, serial = heapq.heappop(self._pending_heap)
                pending = self._pending_payloads.pop(serial, None)
                if pending is None:
                    continue

                key = (pending.dst_module_id, pending.dst_port)
                if self._policy.coalesce_pending_inputs:
                    current = self._pending_keys.get(key)
                    if current is not None and current != pending.serial:
                        continue
                    self._pending_keys.pop(key, None)

                module = self._modules.get(pending.dst_module_id)
                if module is None:
                    continue

                try:
                    module.receive_binding(pending.dst_port, pending.value)
                except RuntimeFailureInfo:
                    raise
                except Exception as exc:
                    raise self._failure(
                        "module_failure",
                        "Module receive failed: "
                        f"{pending.dst_module_id}.{pending.dst_port}",
                        details={"exception": str(exc)},
                    ) from exc

                delivered += 1

            ended = time.time_ns()
            self._last_batch = RuntimeBatch(
                started_ns=started,
                ended_ns=ended,
                delivered_events=delivered,
                dropped_events=self._dropped_events - dropped_before,
            )
            return self._last_batch
        finally:
            self._processing = False

    def _reindex_bindings(self) -> None:
        self._bindings_by_source.clear()
        for edge in sorted(self._bindings, key=lambda item: item.order):
            self._bindings_by_source.setdefault(
                (edge.src_module_id, edge.src_port),
                [],
            ).append(edge)

    def _rebuild_ranks(self) -> None:
        nodes = set(self._modules)
        indegree = dict.fromkeys(nodes, 0)
        adjacency: dict[str, set[str]] = {node: set() for node in nodes}

        for edge in self._bindings:
            if (
                edge.src_module_id in nodes
                and edge.dst_module_id in nodes
                and edge.dst_module_id not in adjacency[edge.src_module_id]
            ):
                adjacency[edge.src_module_id].add(edge.dst_module_id)
                indegree[edge.dst_module_id] = indegree[edge.dst_module_id] + 1

        queue = deque(node for node, degree in sorted(indegree.items()) if degree == 0)
        rank: dict[str, int] = {}
        index = 0

        while queue:
            node = queue.popleft()
            rank[node] = index
            index += 1
            for nxt in sorted(adjacency[node]):
                indegree[nxt] = indegree[nxt] - 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        for node in sorted(nodes):
            if node not in rank:
                rank[node] = index
                index += 1

        self._rank_cache = rank

    def _would_create_cycle(self, src: str, dst: str) -> bool:
        adjacency: dict[str, set[str]] = {module_id: set() for module_id in self._modules}
        for edge in self._bindings:
            adjacency.setdefault(edge.src_module_id, set()).add(edge.dst_module_id)
        adjacency.setdefault(src, set()).add(dst)

        stack = [dst]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == src:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(sorted(adjacency.get(current, ())))
        return False

    def _reset_pending_deliveries(self) -> None:
        dropped = len(self._pending_payloads)
        if dropped:
            self._dropped_events += dropped
        self._pending_heap.clear()
        self._pending_keys.clear()
        self._pending_payloads.clear()

    @staticmethod
    def _failure(
        code: RuntimeErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> RuntimeFailureInfo:
        return RuntimeFailureInfo(RuntimeFailure(code=code, message=message, details=details or {}))
