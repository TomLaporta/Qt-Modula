"""Thread-safe runtime settings shared by service and module layers."""

from __future__ import annotations

from pathlib import Path
from threading import RLock

from qt_modula.paths import exports_root, resolve_app_relative
from qt_modula.persistence.schemas import AppConfig, ProviderNetworkPolicy

_LOCK = RLock()
_PROVIDER_NETWORK_POLICY = ProviderNetworkPolicy()
_EXPORT_ROOT = exports_root()


def configure_provider_network(policy: ProviderNetworkPolicy) -> None:
    """Update shared provider/network defaults."""
    global _PROVIDER_NETWORK_POLICY
    with _LOCK:
        _PROVIDER_NETWORK_POLICY = policy.model_copy(deep=True)


def current_provider_network() -> ProviderNetworkPolicy:
    """Return a copy of active provider/network defaults."""
    with _LOCK:
        return _PROVIDER_NETWORK_POLICY.model_copy(deep=True)


def configure_export_root(path: Path | str) -> None:
    """Update shared default export root."""
    global _EXPORT_ROOT
    normalized = resolve_app_relative(path)
    with _LOCK:
        _EXPORT_ROOT = normalized


def current_export_root() -> Path:
    """Return active export root."""
    with _LOCK:
        return Path(_EXPORT_ROOT)


def configure_from_app_config(config: AppConfig) -> None:
    """Apply all service-relevant settings from app config."""
    configure_provider_network(config.provider_network)
    configure_export_root(config.paths.resolved_export_directory())
