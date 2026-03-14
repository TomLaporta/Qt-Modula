"""Shared safe expression evaluator for math/research workflows."""

from __future__ import annotations

import ast
import math
from collections.abc import Callable
from typing import ClassVar


def _fact(value: float) -> float:
    if not math.isfinite(value) or value < 0:
        raise ValueError("fact() expects a finite non-negative value.")
    nearest = round(value)
    if math.isclose(value, nearest, rel_tol=0.0, abs_tol=1e-9):
        return float(math.factorial(int(nearest)))
    return float(math.gamma(value + 1.0))


ALLOWED_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "floor": math.floor,
    "ceil": math.ceil,
    "pow": pow,
    "fact": _fact,
}

ALLOWED_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
}

RESERVED_NAMES = set(ALLOWED_FUNCTIONS) | set(ALLOWED_CONSTANTS)


class ExpressionEngine:
    """AST-based numeric evaluator constrained to safe math operations."""

    _BIN_OPS: ClassVar[dict[type[ast.operator], Callable[[float, float], float]]] = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.Pow: lambda a, b: a**b,
        ast.Mod: lambda a, b: a % b,
    }
    _UNARY_OPS: ClassVar[dict[type[ast.unaryop], Callable[[float], float]]] = {
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }

    @classmethod
    def evaluate(cls, expression: str, env: dict[str, float] | None = None) -> float:
        text = expression.strip()
        if not text:
            raise ValueError("Expression is empty.")

        local_env: dict[str, float] = {}
        for key, raw in (env or {}).items():
            name = str(key)
            if not name:
                continue
            try:
                parsed = float(raw)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(parsed):
                continue
            local_env[name] = parsed

        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError as exc:
            raise ValueError("Invalid expression syntax.") from exc

        result = cls._eval_node(tree.body, local_env)
        if not math.isfinite(result):
            raise ValueError("Expression result is not finite.")
        return result

    @classmethod
    def _eval_node(cls, node: ast.AST, env: dict[str, float]) -> float:
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("Only numeric constants are allowed.")
            return float(value)

        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            lowered = node.id.lower()
            if lowered in ALLOWED_CONSTANTS:
                return float(ALLOWED_CONSTANTS[lowered])
            raise ValueError(f"Unknown variable '{node.id}'.")

        if isinstance(node, ast.BinOp):
            bin_operator = type(node.op)
            if bin_operator not in cls._BIN_OPS:
                raise ValueError("Unsupported operator.")
            left = cls._eval_node(node.left, env)
            right = cls._eval_node(node.right, env)
            try:
                value = cls._BIN_OPS[bin_operator](left, right)
            except Exception as exc:
                raise ValueError(str(exc)) from exc
            return float(value)

        if isinstance(node, ast.UnaryOp):
            unary_operator = type(node.op)
            if unary_operator not in cls._UNARY_OPS:
                raise ValueError("Unsupported unary operator.")
            operand = cls._eval_node(node.operand, env)
            return float(cls._UNARY_OPS[unary_operator](operand))

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct function calls are allowed.")
            fn = ALLOWED_FUNCTIONS.get(node.func.id)
            if fn is None:
                raise ValueError(f"Unsupported function '{node.func.id}'.")
            if node.keywords:
                raise ValueError("Keyword arguments are not supported.")
            args = [cls._eval_node(arg, env) for arg in node.args]
            try:
                value = fn(*args)
            except Exception as exc:
                raise ValueError(str(exc)) from exc
            return float(value)

        raise ValueError("Unsupported syntax in expression.")
