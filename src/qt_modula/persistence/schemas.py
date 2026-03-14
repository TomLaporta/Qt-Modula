"""Strict persistence schemas (current contract only)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qt_modula.paths import autosnapshots_root, exports_root, projects_root

_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


def _resolve_path_override(value: str | None, default_factory: Callable[[], Path]) -> Path:
    if value is None:
        return default_factory()
    return Path(value).expanduser().resolve()


class _StrictModel(BaseModel):
    """Base strict schema model."""

    model_config = ConfigDict(extra="forbid")


class RuntimePolicyModel(_StrictModel):
    """Runtime scheduler policy schema."""

    max_queue_size: int = Field(default=100_000, ge=1, le=5_000_000)
    coalesce_pending_inputs: bool = True
    max_deliveries_per_batch: int = Field(default=250_000, ge=1, le=10_000_000)


class AutosnapshotPolicy(_StrictModel):
    """Autosnapshot behavior policy."""

    enabled: bool = True
    debounce_ms: int = Field(default=800, ge=100, le=30_000)
    max_history: int = Field(default=50, ge=1, le=500)


class CustomThemePolicy(_StrictModel):
    """Custom theme color policy."""

    primary_color: str = Field(default="#1F1F1F", pattern=_HEX_COLOR_PATTERN)
    secondary_color: str = Field(default="#DDD5EB", pattern=_HEX_COLOR_PATTERN)
    highlight_color: str = Field(default="#432475", pattern=_HEX_COLOR_PATTERN)
    canvas_color: str = Field(default="#141414", pattern=_HEX_COLOR_PATTERN)


class UiPolicy(_StrictModel):
    """UI-level settings."""

    theme: str = "default"
    custom_theme: CustomThemePolicy = Field(default_factory=CustomThemePolicy)


class HttpNetworkPolicy(_StrictModel):
    """Shared HTTP defaults."""

    timeout_s: float = Field(default=10.0, ge=0.1, le=300.0)
    retries: int = Field(default=2, ge=0, le=20)
    backoff_s: float = Field(default=0.15, ge=0.0, le=60.0)
    min_gap_s: float = Field(default=0.0, ge=0.0, le=60.0)
    proxy_url: str = Field(default="", max_length=2048)

    @field_validator("proxy_url", mode="before")
    @classmethod
    def _normalize_proxy_url(cls, value: Any) -> str:
        return str(value).strip() if value is not None else ""


class YFinanceNetworkPolicy(_StrictModel):
    """Shared yfinance defaults."""

    retries: int = Field(default=2, ge=0, le=20)
    backoff_s: float = Field(default=0.25, ge=0.0, le=60.0)


class ProviderNetworkPolicy(_StrictModel):
    """Provider/network defaults."""

    http: HttpNetworkPolicy = Field(default_factory=HttpNetworkPolicy)
    yfinance: YFinanceNetworkPolicy = Field(default_factory=YFinanceNetworkPolicy)


class PathPolicy(_StrictModel):
    """Default path policy."""

    project_directory: str | None = None
    autosnapshot_directory: str | None = None
    export_directory: str | None = None

    @field_validator(
        "project_directory",
        "autosnapshot_directory",
        "export_directory",
        mode="before",
    )
    @classmethod
    def _normalize_path_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        token = str(value).strip()
        return token or None

    @model_validator(mode="after")
    def _validate_absolute_paths(self) -> PathPolicy:
        for field_name in ("project_directory", "autosnapshot_directory", "export_directory"):
            token = getattr(self, field_name)
            if token is not None and not Path(token).is_absolute():
                raise ValueError(f"{field_name} must be an absolute path.")
        return self

    def resolved_project_directory(self) -> Path:
        return _resolve_path_override(self.project_directory, projects_root)

    def resolved_autosnapshot_directory(self) -> Path:
        return _resolve_path_override(self.autosnapshot_directory, autosnapshots_root)

    def resolved_export_directory(self) -> Path:
        return _resolve_path_override(self.export_directory, exports_root)


class SafetyPromptPolicy(_StrictModel):
    """Prompt policy for destructive operations."""

    confirm_module_remove: bool = True
    confirm_binding_remove: bool = True
    confirm_canvas_delete: bool = True
    confirm_workspace_reset: bool = True
    confirm_load_over_unsaved: bool = True


class AppConfig(_StrictModel):
    """App settings payload."""

    version: Literal["AppConfig"] = "AppConfig"
    runtime: RuntimePolicyModel = Field(default_factory=RuntimePolicyModel)
    ui: UiPolicy = Field(default_factory=UiPolicy)
    autosnapshot: AutosnapshotPolicy = Field(default_factory=AutosnapshotPolicy)
    provider_network: ProviderNetworkPolicy = Field(default_factory=ProviderNetworkPolicy)
    paths: PathPolicy = Field(default_factory=PathPolicy)
    safety_prompts: SafetyPromptPolicy = Field(default_factory=SafetyPromptPolicy)


class ModuleSnapshot(_StrictModel):
    """Persisted module record."""

    module_id: str = Field(min_length=1)
    module_type: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=32)
    inputs: dict[str, Any] = Field(default_factory=dict)


class CanvasSnapshot(_StrictModel):
    """Persisted canvas record."""

    canvas_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    modules: list[ModuleSnapshot] = Field(default_factory=list)


class BindingSnapshot(_StrictModel):
    """Persisted binding edge."""

    src_module_id: str = Field(min_length=1)
    src_port: str = Field(min_length=1)
    dst_module_id: str = Field(min_length=1)
    dst_port: str = Field(min_length=1)


class Project(_StrictModel):
    """Project payload schema."""

    version: Literal["ProjectV2"] = "ProjectV2"
    project_id: str = Field(default="workspace", min_length=1, max_length=64)
    runtime: RuntimePolicyModel = Field(default_factory=RuntimePolicyModel)
    canvases: list[CanvasSnapshot] = Field(default_factory=list)
    bindings: list[BindingSnapshot] = Field(default_factory=list)
