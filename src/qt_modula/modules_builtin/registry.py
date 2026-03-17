"""Built-in module registry and plugin integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from qt_modula.modules_builtin.analytics import (
    LinePlotterModule,
    RollingStatsModule,
    TableMetricsModule,
)
from qt_modula.modules_builtin.control import (
    IntervalPulseModule,
    LogNotesModule,
    NumberInputModule,
    OptionsModule,
    TextInputModule,
    TriggerButtonModule,
    TriggerDebounceModule,
    TriggerDelayModule,
    TriggerMapperModule,
    TriggerRateLimitModule,
    ValueViewModule,
)
from qt_modula.modules_builtin.export import TableExportModule, TextExportModule
from qt_modula.modules_builtin.importers import (
    JsonImportModule,
    TableImportModule,
    TextImportModule,
)
from qt_modula.modules_builtin.logic import (
    CircuitBreakerModule,
    ConditionGateModule,
    LogicCombinatorModule,
    RetryControllerModule,
    TriggerJoinModule,
    TriggerJoinNModule,
    ValueChangeGateModule,
    ValueLatchModule,
    ValueRouterModule,
    ValueSelectorModule,
)
from qt_modula.modules_builtin.math import ArithmeticModule, FormulaCalculatorModule
from qt_modula.modules_builtin.providers import (
    FxQuoteModule,
    HttpRequestModule,
    MarketFetcherModule,
)
from qt_modula.modules_builtin.research import ParameterSweepModule, TableBufferModule
from qt_modula.modules_builtin.transform import (
    DatetimeConvertModule,
    JsonProjectModule,
    JsonTransformModule,
    TableTransformModule,
    TemplateFormatterModule,
    ValueScannerModule,
    ValueWrapperModule,
)
from qt_modula.plugins import PluginLoadIssue, load_plugins
from qt_modula.sdk import BaseModule, CapabilityTag, ModuleDescriptor, PortSpec

ModuleConstructor = Callable[[str], BaseModule]

_FAMILY_ORDER: tuple[str, ...] = (
    "Control",
    "Providers",
    "Import",
    "Transform",
    "Logic",
    "Math",
    "Research",
    "Analytics",
    "Export",
)
_FAMILY_RANK: dict[str, int] = {family.lower(): index for index, family in enumerate(_FAMILY_ORDER)}

_MODULE_CAPABILITIES: dict[str, tuple[CapabilityTag, ...]] = {
    "trigger_button": ("source", "scheduler"),
    "trigger_debounce": ("transform", "scheduler"),
    "trigger_delay": ("transform", "scheduler"),
    "trigger_mapper": ("transform", "scheduler"),
    "trigger_rate_limit": ("gate", "transform"),
    "interval_pulse": ("source", "scheduler"),
    "number_input": ("source", "scheduler"),
    "options": ("source", "scheduler"),
    "text_input": ("source", "scheduler"),
    "value_view": ("sink",),
    "log_notes": ("sink",),
    "condition_gate": ("gate", "transform"),
    "logic_combinator": ("gate", "transform"),
    "trigger_join": ("gate", "transform"),
    "trigger_join_n": ("gate", "transform"),
    "value_router": ("gate", "transform"),
    "value_selector": ("gate", "transform"),
    "value_latch": ("gate", "transform"),
    "value_change_gate": ("gate", "transform"),
    "retry_controller": ("gate", "transform"),
    "circuit_breaker": ("gate", "transform"),
    "json_project": ("transform",),
    "datetime_convert": ("transform",),
    "json_transform": ("transform",),
    "table_transform": ("transform",),
    "template_formatter": ("transform",),
    "value_scanner": ("transform",),
    "value_wrapper": ("transform",),
    "line_plotter": ("sink", "transform"),
    "rolling_stats": ("transform", "sink"),
    "table_metrics": ("transform",),
    "arithmetic": ("transform",),
    "formula_calculator": ("transform",),
    "table_export": ("sink",),
    "text_export": ("sink",),
    "text_import": ("source",),
    "json_import": ("source",),
    "table_import": ("source",),
    "parameter_sweep": ("transform", "source"),
    "table_buffer": ("transform",),
    "http_request": ("provider", "source"),
    "fx_quote": ("provider", "source"),
    "market_fetcher": ("provider", "source"),
}

_CORE_BIND_PORTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "interval_pulse": (
        frozenset({"enabled", "interval_ms", "start", "stop", "pulse"}),
        frozenset({"pulse", "running"}),
    ),
    "log_notes": (
        frozenset({"append", "text", "clear"}),
        frozenset({"text"}),
    ),
    "trigger_debounce": (
        frozenset({"trigger", "window_ms"}),
        frozenset({"pulse"}),
    ),
    "trigger_delay": (
        frozenset({"trigger", "delay_ms", "cancel"}),
        frozenset({"pulse"}),
    ),
    "trigger_mapper": (
        frozenset({"trigger", "channel"}),
        frozenset({"pulse", "evaluate", "refresh", "fetch", "run", "flush", "emit"}),
    ),
    "trigger_rate_limit": (
        frozenset({"trigger", "max_events", "window_ms", "reset"}),
        frozenset({"pulse", "blocked"}),
    ),
    "fx_quote": (
        frozenset({"from_currency", "to_currency", "fetch"}),
        frozenset(
            {
                "rate",
                "inverse_rate",
                "from_currency",
                "to_currency",
                "pair",
                "quote",
                "fetched",
            }
        ),
    ),
    "http_request": (
        frozenset({"url", "method", "params", "headers", "body", "fetch"}),
        frozenset({"status_code", "text", "json", "fetched"}),
    ),
    "market_fetcher": (
        frozenset(
            {
                "symbol",
                "years",
                "months",
                "weeks",
                "days",
                "interval",
                "auto_fetch",
                "commit",
                "fetch",
            }
        ),
        frozenset(
            {
                "history",
                "rows",
                "row_count",
                "symbol",
                "effective_interval",
                "committed",
                "fetched",
            }
        ),
    ),
    "datetime_convert": (
        frozenset({"value", "auto", "output_timezone", "emit"}),
        frozenset({"datetime", "date", "time", "iso", "epoch_seconds", "converted"}),
    ),
    "json_project": (
        frozenset({"json", "mapping", "auto", "emit"}),
        frozenset({"record", "keys", "projected"}),
    ),
    "json_transform": (
        frozenset({"json", "mode", "path", "key", "match", "auto", "emit"}),
        frozenset({"json", "count", "transformed"}),
    ),
    "table_transform": (
        frozenset(
            {
                "rows",
                "filter_key",
                "filter_value",
                "sort_key",
                "descending",
                "limit",
                "columns",
                "auto",
                "emit",
            }
        ),
        frozenset({"rows", "row_count", "transformed"}),
    ),
    "template_formatter": (
        frozenset({"template", "context", "value", "auto", "emit"}),
        frozenset({"value", "fields", "rendered"}),
    ),
    "value_scanner": (
        frozenset({"value", "entry", "auto", "emit"}),
        frozenset({"in_value", "text"}),
    ),
    "value_wrapper": (
        frozenset({"value", "key", "entry", "auto", "emit"}),
        frozenset({"value", "text"}),
    ),
    "circuit_breaker": (
        frozenset(
            {
                "request",
                "success",
                "failure",
                "failure_threshold",
                "cooldown_ms",
                "half_open_budget",
                "reset",
            }
        ),
        frozenset({"allow", "blocked", "state"}),
    ),
    "logic_combinator": (
        frozenset({"values", "operator", "auto", "emit"}),
        frozenset({"matched", "on_true", "on_false"}),
    ),
    "retry_controller": (
        frozenset({"request", "success", "failure", "max_attempts", "backoff_ms", "reset"}),
        frozenset({"attempt", "exhausted", "done"}),
    ),
    "trigger_join": (
        frozenset({"left", "right", "auto_reset", "clear"}),
        frozenset({"joined"}),
    ),
    "trigger_join_n": (
        frozenset(
            {
                "in_0",
                "in_1",
                "in_2",
                "in_3",
                "in_4",
                "in_5",
                "in_6",
                "in_7",
                "input_count",
                "auto_reset",
                "clear",
            }
        ),
        frozenset({"joined"}),
    ),
    "value_change_gate": (
        frozenset({"value", "epsilon", "emit_initial", "auto", "emit", "clear"}),
        frozenset({"value", "changed", "unchanged"}),
    ),
    "value_latch": (
        frozenset({"value", "release", "transparent", "clear"}),
        frozenset({"value", "held", "released"}),
    ),
    "value_router": (
        frozenset(
            {
                "v0",
                "v1",
                "v2",
                "v3",
                "v4",
                "v5",
                "v6",
                "v7",
                "selector",
                "input_count",
                "auto",
                "emit",
            }
        ),
        frozenset({"value", "selected", "in_range", "changed"}),
    ),
    "value_selector": (
        frozenset({"a", "b", "selector", "auto", "emit"}),
        frozenset({"value", "selected", "changed"}),
    ),
    "formula_calculator": (
        frozenset({"formula", "solve_for", "variables", "evaluate", "auto_evaluate"}),
        frozenset(
            {
                "value",
                "text",
                "error",
                "formula",
                "variables",
                "roots",
                "root_count",
                "solved",
            }
        ),
    ),
    "parameter_sweep": (
        frozenset({"start", "stop", "step", "variable", "formula", "run"}),
        frozenset({"rows", "count", "done"}),
    ),
    "table_buffer": (
        frozenset({"row", "append", "emit", "clear"}),
        frozenset({"rows", "row_count", "appended"}),
    ),
    "line_plotter": (
        frozenset(
            {
                "rows",
                "row",
                "append",
                "clear",
                "x_key",
                "y_key",
                "series_key",
                "x_mode",
                "range_mode",
                "range_points",
                "follow_latest",
                "reset_view",
                "export_folder",
                "file_name",
                "tag",
                "export_png",
                "export_svg",
            }
        ),
        frozenset(
            {
                "point_count",
                "series_count",
                "range_applied",
                "hover_active",
                "hover_series",
                "hover_x",
                "hover_y",
                "hover_x_text",
                "hover_y_text",
                "path",
                "exported",
            }
        ),
    ),
    "rolling_stats": (
        frozenset({"value", "window", "reset", "emit"}),
        frozenset({"mean", "stddev", "min", "max", "count", "ready"}),
    ),
    "table_metrics": (
        frozenset({"rows", "emit"}),
        frozenset({"row_count", "column_count", "columns"}),
    ),
    "table_export": (
        frozenset({"rows", "file_name", "export_folder", "format", "mode", "write"}),
        frozenset({"path", "row_count", "total_row_count", "wrote"}),
    ),
    "text_export": (
        frozenset(
            {
                "text",
                "append_text",
                "file_name",
                "export_folder",
                "extension",
                "mode",
                "tag",
                "section_title",
                "auto_write",
                "write",
                "export",
            }
        ),
        frozenset({"path", "wrote", "char_count", "line_count"}),
    ),
    "text_import": (
        frozenset({"path", "auto_import", "import"}),
        frozenset({"content", "char_count", "line_count", "path", "imported"}),
    ),
    "json_import": (
        frozenset({"path", "auto_import", "import"}),
        frozenset({"json", "keys", "item_count", "path", "imported"}),
    ),
    "table_import": (
        frozenset({"path", "auto_import", "format", "sheet_name", "import"}),
        frozenset({"rows", "row_count", "column_count", "columns", "path", "imported"}),
    ),
}


def _default_capabilities(family: str) -> tuple[CapabilityTag, ...]:
    token = family.strip().lower()
    if token == "control":
        return ("source", "scheduler")
    if token == "import":
        return ("source",)
    if token == "logic":
        return ("gate", "transform")
    if token in {"transform", "research", "analytics", "math"}:
        return ("transform",)
    if token == "providers":
        return ("provider", "source")
    if token == "export":
        return ("sink",)
    return ("transform",)


def _normalize_bind_port(
    module_type: str,
    port: PortSpec,
    *,
    is_input: bool,
) -> PortSpec:
    visibility = port.bind_visibility
    ui_group = port.ui_group

    core = _CORE_BIND_PORTS.get(module_type)
    if core is not None:
        core_inputs, core_outputs = core
        core_ports = core_inputs if is_input else core_outputs
        if port.key not in core_ports and visibility == "normal":
            visibility = "advanced"

    if visibility == "advanced" and ui_group == "basic":
        ui_group = "advanced"
    elif visibility == "hidden" and ui_group == "advanced":
        ui_group = "basic"

    if visibility == port.bind_visibility and ui_group == port.ui_group:
        return port
    return replace(port, bind_visibility=visibility, ui_group=ui_group)


def _normalize_bind_metadata(descriptor: ModuleDescriptor) -> ModuleDescriptor:
    inputs = tuple(
        _normalize_bind_port(descriptor.module_type, port, is_input=True)
        for port in descriptor.inputs
    )
    outputs = tuple(
        _normalize_bind_port(descriptor.module_type, port, is_input=False)
        for port in descriptor.outputs
    )
    if inputs == descriptor.inputs and outputs == descriptor.outputs:
        return descriptor
    return replace(descriptor, inputs=inputs, outputs=outputs)


@dataclass(frozen=True, slots=True)
class ModuleRegistration:
    """Descriptor + constructor pair."""

    descriptor: ModuleDescriptor
    constructor: ModuleConstructor


class ModuleRegistry:
    """Registry for built-in and plugin modules."""

    def __init__(self) -> None:
        self._by_type: dict[str, ModuleRegistration] = {}

    def register_module(self, module_cls: type[BaseModule]) -> None:
        descriptor = module_cls.descriptor
        existing = self._by_type.get(descriptor.module_type)
        if existing is not None:
            raise ValueError(
                "Duplicate module_type registration "
                f"'{descriptor.module_type}' "
                f"({existing.constructor.__name__} -> {module_cls.__name__})."
            )

        if not descriptor.capabilities:
            explicit = _MODULE_CAPABILITIES.get(descriptor.module_type)
            capabilities = (
                explicit
                if explicit
                else tuple(_default_capabilities(descriptor.family))
            )
            descriptor = replace(
                descriptor,
                capabilities=capabilities,
            )
        descriptor = _normalize_bind_metadata(descriptor)
        module_cls.descriptor = descriptor

        self._by_type[descriptor.module_type] = ModuleRegistration(
            descriptor=descriptor,
            constructor=module_cls,
        )

    def has(self, module_type: str) -> bool:
        return module_type in self._by_type

    def create(self, module_type: str, module_id: str) -> BaseModule:
        record = self._by_type.get(module_type)
        if record is None:
            raise KeyError(f"Unknown module_type '{module_type}'.")
        return record.constructor(module_id)

    @staticmethod
    def _descriptor_sort_key(descriptor: ModuleDescriptor) -> tuple[int, str, str]:
        family_token = descriptor.family.strip().lower()
        rank = _FAMILY_RANK.get(family_token, len(_FAMILY_RANK))
        return (rank, descriptor.family, descriptor.display_name)

    def descriptors(self) -> list[ModuleDescriptor]:
        return sorted(
            [record.descriptor for record in self._by_type.values()],
            key=self._descriptor_sort_key,
        )


def register_builtin_modules(registry: ModuleRegistry) -> None:
    """Register all first-party built-ins in deterministic order."""
    registry.register_module(TriggerButtonModule)
    registry.register_module(TriggerDebounceModule)
    registry.register_module(TriggerDelayModule)
    registry.register_module(TriggerRateLimitModule)
    registry.register_module(TriggerMapperModule)
    registry.register_module(IntervalPulseModule)
    registry.register_module(NumberInputModule)
    registry.register_module(OptionsModule)
    registry.register_module(TextInputModule)
    registry.register_module(ValueViewModule)
    registry.register_module(LogNotesModule)

    registry.register_module(HttpRequestModule)
    registry.register_module(FxQuoteModule)
    registry.register_module(MarketFetcherModule)

    registry.register_module(TextImportModule)
    registry.register_module(JsonImportModule)
    registry.register_module(TableImportModule)

    registry.register_module(DatetimeConvertModule)
    registry.register_module(JsonProjectModule)
    registry.register_module(JsonTransformModule)
    registry.register_module(TableTransformModule)
    registry.register_module(TemplateFormatterModule)
    registry.register_module(ValueScannerModule)
    registry.register_module(ValueWrapperModule)

    registry.register_module(ConditionGateModule)
    registry.register_module(LogicCombinatorModule)
    registry.register_module(TriggerJoinModule)
    registry.register_module(TriggerJoinNModule)
    registry.register_module(ValueRouterModule)
    registry.register_module(ValueSelectorModule)
    registry.register_module(ValueLatchModule)
    registry.register_module(ValueChangeGateModule)
    registry.register_module(RetryControllerModule)
    registry.register_module(CircuitBreakerModule)

    registry.register_module(ArithmeticModule)
    registry.register_module(FormulaCalculatorModule)

    registry.register_module(ParameterSweepModule)
    registry.register_module(TableBufferModule)

    registry.register_module(LinePlotterModule)
    registry.register_module(RollingStatsModule)
    registry.register_module(TableMetricsModule)

    registry.register_module(TableExportModule)
    registry.register_module(TextExportModule)


def build_registry(plugin_root: Path | None = None) -> tuple[ModuleRegistry, list[PluginLoadIssue]]:
    """Build module registry with built-ins + local plugins."""
    registry = ModuleRegistry()
    register_builtin_modules(registry)

    issues: list[PluginLoadIssue] = []
    if plugin_root is not None:
        issues = load_plugins(root=plugin_root, registry=registry)
    return registry, issues
