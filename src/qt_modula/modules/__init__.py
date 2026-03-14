"""Compatibility shim exporting built-in module registry APIs."""

from qt_modula.modules_builtin import ModuleRegistry, build_registry, register_builtin_modules

__all__ = ["ModuleRegistry", "build_registry", "register_builtin_modules"]
