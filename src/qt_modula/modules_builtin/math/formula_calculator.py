"""Integrated formula calculator with embedded formula library window."""

from __future__ import annotations

import json
import keyword
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from qt_modula.modules_builtin.math.expression_engine import (
    ALLOWED_CONSTANTS,
    ALLOWED_FUNCTIONS,
    RESERVED_NAMES,
    ExpressionEngine,
)
from qt_modula.sdk import BaseModule, ModuleDescriptor, PortSpec, is_truthy
from qt_modula.sdk.ui import apply_layout_defaults, set_control_height

_MAX_PM_BRANCHES = 8
_SOLUTION_ABS_TOL = 1e-9
_SOLUTION_REL_TOL = 1e-8
_COMPLEX_TOL = 1e-9

_UNICODE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("−", "-"),
    ("×", "*"),
    ("·", "*"),
    ("÷", "/"),
    ("^", "**"),
    ("√", "sqrt"),
    ("π", "pi"),
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_IDENTIFIER_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_REFS_PREFIX_RE = re.compile(r"^\s*refs\{(?P<refs>[^{}]*)\}\s*;\s*(?P<body>.*)$", re.DOTALL)
_TOKEN_RE = re.compile(
    r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|"
    r"[A-Za-z_][A-Za-z0-9_]*|[()+\-*/^=,%]"
)
_SYMPY_IMPORT_ERROR: str | None = None


@dataclass(frozen=True, slots=True)
class FormulaRecord:
    id: str
    category: str
    name: str
    display: str
    expression: str
    notes: str
    professional_expression: str
    professional_notes: str
    professional_display: str


@dataclass(frozen=True, slots=True)
class _EvaluationResult:
    text: str
    value: float | None
    roots: list[complex]
    solved: bool
    target: str | None = None


# Optional symbolic backend for hard equation solving.
try:
    import sympy  # type: ignore[import-untyped]
    from sympy import Eq as _sym_eq
    from sympy import N as _sym_n
    from sympy import solve as _sym_solve
    from sympy import symbols as _sym_symbols
    from sympy.parsing.sympy_parser import (  # type: ignore[import-untyped]
        convert_xor as _sym_convert_xor,
    )
    from sympy.parsing.sympy_parser import (
        implicit_multiplication_application as _sym_implicit,
    )
    from sympy.parsing.sympy_parser import (
        parse_expr as _sym_parse,
    )
    from sympy.parsing.sympy_parser import (
        standard_transformations as _sym_std_t,
    )

    _SYMPY_AVAILABLE = True
    _SYMPY_TRANSFORMS = (*_sym_std_t, _sym_implicit, _sym_convert_xor)
except Exception as exc:
    _SYMPY_AVAILABLE = False
    _SYMPY_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


@lru_cache(maxsize=1)
def load_formula_catalog() -> tuple[FormulaRecord, ...]:
    """Load formula catalog from local JSON asset."""
    payload = json.loads(
        resources.files("qt_modula.modules_builtin.math")
        .joinpath("formula_catalog.json")
        .read_text(encoding="utf-8")
    )

    rows: list[FormulaRecord] = []
    for raw in payload.get("formulas", []):
        rows.append(
            FormulaRecord(
                id=str(raw.get("id", "")),
                category=str(raw.get("category", "")),
                name=str(raw.get("name", "")),
                display=str(raw.get("display", "")),
                expression=str(raw.get("expression", "")),
                notes=str(raw.get("notes", "")),
                professional_expression=str(raw.get("professional_expression", "")),
                professional_notes=str(raw.get("professional_notes", "")),
                professional_display=str(raw.get("professional_display", "")),
            )
        )

    expected = int(payload.get("formula_count", len(rows)))
    if expected != len(rows):
        raise ValueError("Formula catalog count mismatch.")
    return tuple(rows)


def _is_number_token(token: str) -> bool:
    return bool(re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", token))


def _is_identifier(name: str) -> bool:
    stripped = name.strip()
    if not _IDENTIFIER_RE.fullmatch(stripped):
        return False
    if keyword.iskeyword(stripped):
        return False
    return stripped.lower() not in RESERVED_NAMES


def _is_external_identifier(name: str) -> bool:
    stripped = name.strip()
    if not _IDENTIFIER_RE.fullmatch(stripped):
        return False
    return stripped.lower() not in RESERVED_NAMES


def _needs_implicit_multiply(prev: str, current: str) -> bool:
    if prev in {",", "="} or current in {",", "="}:
        return False

    prev_is_name = bool(_IDENTIFIER_RE.fullmatch(prev))
    current_is_name = bool(_IDENTIFIER_RE.fullmatch(current))
    prev_lower = prev.lower()

    left_is_value = (
        prev == ")"
        or _is_number_token(prev)
        or (prev_is_name and prev_lower in ALLOWED_CONSTANTS)
        or (prev_is_name and prev_lower not in ALLOWED_FUNCTIONS)
    )
    right_is_value = current == "(" or _is_number_token(current) or current_is_name

    if prev_is_name and current == "(" and prev_lower in ALLOWED_FUNCTIONS:
        return False

    return left_is_value and right_is_value


def _normalize_formula(text: str) -> str:
    normalized = "" if text is None else str(text)

    for raw, replacement in _UNICODE_REPLACEMENTS:
        normalized = normalized.replace(raw, replacement)

    normalized = normalized.replace("±", "+/-")
    normalized = normalized.strip()
    if not normalized:
        return ""

    normalized = re.sub(r"\s+", " ", normalized)
    tokens = _TOKEN_RE.findall(normalized)
    if not tokens:
        return ""

    out: list[str] = []
    for token in tokens:
        if out and _needs_implicit_multiply(out[-1], token):
            out.append("*")
        out.append(token)
    return "".join(out)


def _infer_variables(expression: str) -> list[str]:
    tokens = _IDENTIFIER_TOKEN_RE.findall(expression)
    seen: set[str] = set()
    variables: list[str] = []
    for token in tokens:
        lowered = token.lower()
        if lowered in RESERVED_NAMES:
            continue
        if token in seen:
            continue
        seen.add(token)
        variables.append(token)
    return variables


def _split_reference_formula(text: str, *, strict: bool) -> tuple[dict[str, str], str]:
    raw = "" if text is None else str(text).strip()
    if not raw:
        return {}, ""

    if not raw.lstrip().lower().startswith("refs"):
        return {}, raw

    match = _REFS_PREFIX_RE.match(raw)
    if match is None:
        if strict:
            raise ValueError("Invalid refs prefix. Use: refs{external=internal}; expression")
        return {}, raw

    refs_raw = match.group("refs").strip()
    body = match.group("body").strip()
    if not body and strict:
        raise ValueError("Formula body is empty after refs prefix.")

    refs: dict[str, str] = {}
    internals_seen: set[str] = set()

    if refs_raw:
        for raw_pair in refs_raw.split(","):
            pair = raw_pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                if strict:
                    raise ValueError(f"Invalid refs mapping '{pair}'.")
                continue
            external_raw, internal_raw = pair.split("=", 1)
            external = external_raw.strip()
            internal = internal_raw.strip()

            if not _is_external_identifier(external):
                raise ValueError(f"Invalid refs external name '{external}'.")
            if not _is_identifier(internal):
                raise ValueError(f"Invalid refs internal name '{internal}'.")
            if external in refs:
                raise ValueError(f"Duplicate refs external name '{external}'.")
            if internal in internals_seen:
                raise ValueError(f"Duplicate refs internal name '{internal}'.")

            refs[external] = internal
            internals_seen.add(internal)

    if strict and refs and (set(refs) & set(refs.values())):
        raise ValueError("refs external/internal names may not overlap.")

    return refs, body


def _canonical_reference_formula(body: str, refs: dict[str, str]) -> str:
    if not refs:
        return body
    pairs = ", ".join(f"{external}={internal}" for external, internal in refs.items())
    return f"refs{{{pairs}}}; {body}"


def _rewrite_identifiers(expression: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return expression

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        return mapping.get(token, token)

    return _IDENTIFIER_TOKEN_RE.sub(repl, expression)


def _require_reference_coverage(expression: str, refs: dict[str, str]) -> None:
    variables = _infer_variables(expression)
    if not variables:
        return

    externals = set(variables)
    missing = sorted(name for name in externals if keyword.iskeyword(name) and name not in refs)
    if missing:
        missing_csv = ", ".join(missing)
        raise ValueError(
            f"Formula uses parser-unsafe identifier(s): {missing_csv}. Add refs mapping."
        )

    unused_refs = sorted(name for name in refs if name not in externals)
    if unused_refs:
        unused_csv = ", ".join(unused_refs)
        raise ValueError(f"refs contains unused name(s): {unused_csv}.")

    internal_overlap = sorted(set(refs.values()) & externals)
    if internal_overlap:
        overlap_csv = ", ".join(internal_overlap)
        raise ValueError(f"refs internal name(s) overlap variables: {overlap_csv}.")


def _map_env_identifiers(env: dict[str, float], refs: dict[str, str]) -> dict[str, float]:
    mapped: dict[str, float] = {}
    for external, value in env.items():
        internal = refs.get(external, external)
        if not _is_identifier(internal):
            raise ValueError(f"Invalid mapped identifier '{internal}'.")
        if internal in mapped and not math.isclose(
            mapped[internal], value, rel_tol=_SOLUTION_REL_TOL, abs_tol=_SOLUTION_ABS_TOL
        ):
            raise ValueError(f"Identifier mapping conflict for '{internal}'.")
        mapped[internal] = value
    return mapped


def _split_assignments(text: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    depth = 0

    for char in text:
        if char == "(":
            depth += 1
            current.append(char)
            continue
        if char == ")":
            depth = max(0, depth - 1)
            current.append(char)
            continue

        if depth == 0 and char in {",", ";", "\n"}:
            chunk = "".join(current).strip()
            if chunk:
                chunks.append(chunk)
            current = []
            continue

        current.append(char)

    tail = "".join(current).strip()
    if tail:
        chunks.append(tail)
    return chunks


def _expand_plus_minus(expression: str) -> list[str]:
    branches = [expression]
    operators = (
        ("+/-", ("+", "-")),
        ("-/+", ("-", "+")),
    )

    for marker, replacements in operators:
        while any(marker in branch for branch in branches):
            expanded: list[str] = []
            for branch in branches:
                idx = branch.find(marker)
                if idx < 0:
                    expanded.append(branch)
                    continue
                prefix = branch[:idx]
                suffix = branch[idx + len(marker) :]
                for replacement in replacements:
                    expanded.append(prefix + replacement + suffix)
            branches = expanded
            if len(branches) > _MAX_PM_BRANCHES:
                raise ValueError(
                    f"Too many +/- branches ({len(branches)}). Limit is {_MAX_PM_BRANCHES}."
                )

    return branches


def _dedupe_solutions(values: list[float]) -> list[float]:
    unique: list[float] = []
    for value in values:
        if not math.isfinite(value):
            raise ValueError("Expression produced a non-finite value.")

        normalized = 0.0 if math.isclose(value, 0.0, abs_tol=_SOLUTION_ABS_TOL) else value
        if any(
            math.isclose(
                normalized,
                existing,
                rel_tol=_SOLUTION_REL_TOL,
                abs_tol=_SOLUTION_ABS_TOL,
            )
            for existing in unique
        ):
            continue
        unique.append(normalized)

    if not unique:
        raise ValueError("No valid solutions found.")
    return unique


def _dedupe_complex_solutions(values: list[complex]) -> list[complex]:
    unique: list[complex] = []
    for value in values:
        if not (math.isfinite(value.real) and math.isfinite(value.imag)):
            continue
        normalized = complex(
            0.0 if abs(value.real) < _COMPLEX_TOL else value.real,
            0.0 if abs(value.imag) < _COMPLEX_TOL else value.imag,
        )
        if any(
            abs(normalized.real - existing.real) <= _COMPLEX_TOL
            and abs(normalized.imag - existing.imag) <= _COMPLEX_TOL
            for existing in unique
        ):
            continue
        unique.append(normalized)
    if not unique:
        raise ValueError("No valid solutions found.")
    return unique


def _format_complex(value: complex) -> str:
    real = value.real
    imag = value.imag
    if abs(imag) < _COMPLEX_TOL:
        return f"{real:g}"
    if abs(real) < _COMPLEX_TOL:
        return f"{imag:g}i"
    sign = "+" if imag >= 0 else "-"
    return f"{real:g} {sign} {abs(imag):g}i"


def _roots_to_text(roots: list[complex]) -> str:
    parts = [_format_complex(root) for root in roots]
    if len(parts) == 1:
        return parts[0]
    return "[" + ", ".join(parts) + "]"


def _roots_to_json(roots: list[complex]) -> list[float | str]:
    payload: list[float | str] = []
    for root in roots:
        if abs(root.imag) < _COMPLEX_TOL:
            payload.append(float(root.real))
        else:
            payload.append(_format_complex(root))
    return payload


def _first_real_value(roots: list[complex]) -> float | None:
    for root in roots:
        if abs(root.imag) < _COMPLEX_TOL:
            return float(root.real)
    return None


def _format_variables(env: dict[str, float]) -> str:
    return ", ".join(f"{name}={value:g}" for name, value in env.items())


def _parse_assignments(text: str) -> dict[str, float]:
    assignments: dict[str, float] = {}
    if not text.strip():
        return assignments

    chunks = _split_assignments(text)
    for raw_chunk in chunks:
        chunk = raw_chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"Invalid assignment '{chunk}'. Expected name=value.")
        name_raw, value_raw = chunk.split("=", 1)
        name = name_raw.strip()
        if not _is_external_identifier(name):
            raise ValueError(f"Invalid variable name '{name}'.")
        value = ExpressionEngine.evaluate(value_raw.strip(), assignments)
        assignments[name] = value
    return assignments


def _symbolic_solve(formula: str, solve_for: str, env: dict[str, float]) -> list[complex]:
    if not _SYMPY_AVAILABLE:
        message = "sympy unavailable"
        if _SYMPY_IMPORT_ERROR:
            message = f"{message}: {_SYMPY_IMPORT_ERROR}"
        raise ValueError(message)
    if not _is_identifier(solve_for):
        raise ValueError(f"Invalid solve_for variable name: '{solve_for}'.")

    target_sym = _sym_symbols(solve_for)
    local_dict: dict[str, Any] = {solve_for: target_sym}
    for name, value in env.items():
        if name == solve_for:
            continue
        local_dict[name] = sympy.Float(value)

    try:
        if "=" in formula:
            lhs_text, rhs_text = formula.split("=", 1)
            lhs = _sym_parse(
                lhs_text.strip(),
                transformations=_SYMPY_TRANSFORMS,
                local_dict=local_dict,
            )
            rhs = _sym_parse(
                rhs_text.strip(),
                transformations=_SYMPY_TRANSFORMS,
                local_dict=local_dict,
            )
            equation = _sym_eq(lhs, rhs)
            raw_roots = _sym_solve(equation, target_sym)
        else:
            expr = _sym_parse(
                formula.strip(),
                transformations=_SYMPY_TRANSFORMS,
                local_dict=local_dict,
            )
            raw_roots = _sym_solve(expr, target_sym)
    except Exception as exc:
        raise ValueError(str(exc)) from exc

    if not raw_roots:
        raise ValueError(f"No solution found for '{solve_for}'.")

    roots: list[complex] = []
    for raw in raw_roots:
        try:
            roots.append(complex(_sym_n(raw, 15)))
        except Exception:
            continue
    return _dedupe_complex_solutions(roots)


def _newton_solve(func: Any, seed: float) -> float | None:
    x = float(seed)
    for _ in range(40):
        try:
            fx = float(func(x))
        except Exception:
            return None
        if abs(fx) <= _SOLUTION_ABS_TOL:
            return x

        step = max(1e-6, abs(x) * 1e-6)
        try:
            f_plus = float(func(x + step))
            f_minus = float(func(x - step))
        except Exception:
            return None
        derivative = (f_plus - f_minus) / (2.0 * step)
        if not math.isfinite(derivative) or abs(derivative) < 1e-12:
            return None

        next_x = x - (fx / derivative)
        if not math.isfinite(next_x):
            return None
        if abs(next_x - x) <= _SOLUTION_ABS_TOL:
            x = next_x
            break
        x = next_x

    try:
        if abs(float(func(x))) <= 1e-7:
            return x
    except Exception:
        return None
    return None


def _scan_and_bisect(func: Any, start: float, stop: float, *, segments: int) -> float | None:
    prev_x = start
    try:
        prev_f = float(func(prev_x))
    except Exception:
        return None

    step = (stop - start) / float(segments)
    for idx in range(1, segments + 1):
        x = start + (step * idx)
        try:
            fx = float(func(x))
        except Exception:
            prev_x, prev_f = x, math.nan
            continue

        if not math.isfinite(prev_f):
            prev_x, prev_f = x, fx
            continue

        if abs(fx) <= _SOLUTION_ABS_TOL:
            return x

        if prev_f == 0.0:
            return prev_x

        if prev_f * fx < 0.0:
            return _bisect(func, prev_x, x)

        prev_x, prev_f = x, fx

    return None


def _bisect(func: Any, lo: float, hi: float) -> float | None:
    try:
        flo = float(func(lo))
        fhi = float(func(hi))
    except Exception:
        return None

    if not (math.isfinite(flo) and math.isfinite(fhi)):
        return None

    if flo == 0.0:
        return lo
    if fhi == 0.0:
        return hi
    if flo * fhi > 0.0:
        return None

    for _ in range(80):
        mid = (lo + hi) / 2.0
        try:
            fmid = float(func(mid))
        except Exception:
            return None

        if not math.isfinite(fmid):
            return None
        if abs(fmid) <= _SOLUTION_ABS_TOL:
            return mid

        if flo * fmid <= 0.0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid

        if abs(hi - lo) <= _SOLUTION_ABS_TOL:
            return (hi + lo) / 2.0

    return (hi + lo) / 2.0


def _solve_numeric(lhs: str, rhs: str, target: str, env: dict[str, float]) -> float:
    def residual(value: float) -> float:
        local = dict(env)
        local[target] = value
        left = ExpressionEngine.evaluate(lhs, local)
        right = ExpressionEngine.evaluate(rhs, local)
        return left - right

    seeds = [env.get(target, 0.0), 1.0, -1.0, 10.0, -10.0, 100.0, -100.0]
    for seed in seeds:
        guess = _newton_solve(residual, seed)
        if guess is not None:
            return guess

    for span in (1.0, 10.0, 100.0, 1000.0, 10000.0):
        guess = _scan_and_bisect(residual, -span, span, segments=80)
        if guess is not None:
            return guess

    raise ValueError(f"Could not solve equation for '{target}'.")


class _FormulaLibraryDialog(QDialog):
    """Embedded formula browser dialog for formula calculator."""

    def __init__(
        self,
        *,
        formulas: tuple[FormulaRecord, ...],
        professional_enabled: bool,
        on_professional_changed: Any,
        on_formula_selected: Any,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Formula Library")
        self.resize(900, 620)

        self._formulas = formulas
        self._professional_enabled = professional_enabled
        self._on_professional_changed = on_professional_changed
        self._on_formula_selected = on_formula_selected
        self._visible: list[FormulaRecord] = []
        self._confirm_button: QPushButton | None = None

        root = QVBoxLayout(self)
        apply_layout_defaults(root)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search formulas by category/name/expression")
        self._search.textChanged.connect(self._populate)
        set_control_height(self._search)
        root.addWidget(self._search)

        self._professional = QCheckBox("Full Professional Generality")
        self._professional.setChecked(self._professional_enabled)
        self._professional.toggled.connect(self._on_professional_toggled)
        root.addWidget(self._professional)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection_changed)
        root.addWidget(self._list, stretch=2)

        self._details = QTextEdit()
        self._details.setReadOnly(True)
        root.addWidget(self._details, stretch=1)

        buttons = QDialogButtonBox()
        self._confirm_button = buttons.addButton("Confirm", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_button = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self._confirm_button.clicked.connect(self._confirm_selection)
        cancel_button.clicked.connect(self.reject)
        set_control_height(self._confirm_button)
        set_control_height(cancel_button)
        root.addWidget(buttons)

        self._populate("")

    def sync_professional(self, enabled: bool) -> None:
        self._professional_enabled = enabled
        self._professional.blockSignals(True)
        self._professional.setChecked(enabled)
        self._professional.blockSignals(False)
        self._on_selection_changed(self._list.currentItem(), None)

    def _populate(self, query: str) -> None:
        lowered = query.strip().lower()
        self._visible = []
        self._list.blockSignals(True)
        self._list.clear()

        for formula in self._formulas:
            searchable = " ".join(
                [
                    formula.category,
                    formula.name,
                    formula.display,
                    formula.expression,
                    formula.notes,
                    formula.professional_display,
                    formula.professional_expression,
                    formula.professional_notes,
                ]
            ).lower()
            if lowered and lowered not in searchable:
                continue
            self._visible.append(formula)
            text = f"{formula.category} :: {formula.name}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, formula.id)
            self._list.addItem(item)

        self._list.blockSignals(False)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
            self._on_selection_changed(self._list.currentItem(), None)
        else:
            self._details.setPlainText("No formulas match current search.")
            if self._confirm_button is not None:
                self._confirm_button.setEnabled(False)

    def _current_formula(self) -> FormulaRecord | None:
        item = self._list.currentItem()
        if item is None:
            return None
        formula_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(formula_id, str):
            return None
        for formula in self._visible:
            if formula.id == formula_id:
                return formula
        return None

    def _expression_for(self, formula: FormulaRecord) -> str:
        if self._professional_enabled and formula.professional_expression:
            return formula.professional_expression
        return formula.expression

    def _display_for(self, formula: FormulaRecord) -> str:
        if self._professional_enabled and formula.professional_expression:
            return formula.professional_display or formula.display
        return formula.display

    def _on_professional_toggled(self, checked: bool) -> None:
        self._professional_enabled = bool(checked)
        self._on_professional_changed(self._professional_enabled)
        self._on_selection_changed(self._list.currentItem(), None)

    def _on_selection_changed(self, current: QListWidgetItem | None, _: object) -> None:
        _ = current
        formula = self._current_formula()
        if formula is None:
            if self._confirm_button is not None:
                self._confirm_button.setEnabled(False)
            return

        expression = self._expression_for(formula)
        is_professional = bool(
            expression
            and expression == formula.professional_expression
        )
        variant = "professional" if is_professional else "standard"
        expression_body = _split_reference_formula(expression, strict=False)[1]
        vars_text = ", ".join(_infer_variables(expression_body))

        details = [
            f"Category: {formula.category}",
            f"Name: {formula.name}",
            f"Variant: {variant}",
            f"Display: {self._display_for(formula)}",
            f"Expression: {expression_body}",
            f"Variables: {vars_text or '(none inferred)'}",
        ]
        if formula.notes:
            details.append(f"Notes: {formula.notes}")
        if variant == "professional" and formula.professional_notes:
            details.append(f"Professional Notes: {formula.professional_notes}")
        self._details.setPlainText("\n".join(details))
        if self._confirm_button is not None:
            self._confirm_button.setEnabled(True)

    def _confirm_selection(self) -> None:
        formula = self._current_formula()
        if formula is None:
            return
        self._on_formula_selected(self._expression_for(formula))
        self.accept()


class FormulaCalculatorModule(BaseModule):
    """Integrated formula evaluator/solver with embedded formula library window."""

    persistent_inputs = (
        "formula",
        "solve_for",
        "variables",
        "auto_evaluate",
        "full_professional_generality",
    )

    descriptor = ModuleDescriptor(
        module_type="formula_calculator",
        display_name="Formula Calculator",
        family="Math",
        description="Integrated formula calculator with library + optional professional variants.",
        inputs=(
            PortSpec("formula", "string", default=""),
            PortSpec("solve_for", "string", default=""),
            PortSpec("variables", "string", default=""),
            PortSpec("evaluate", "trigger", default=0, control_plane=True),
            PortSpec("auto_evaluate", "boolean", default=False),
            PortSpec("clear", "trigger", default=0, control_plane=True),
            PortSpec("open_library", "trigger", default=0, control_plane=True),
            PortSpec("full_professional_generality", "boolean", default=False),
        ),
        outputs=(
            PortSpec("value", "number", default=0.0),
            PortSpec("text", "string", default=""),
            PortSpec("error", "string", default=""),
            PortSpec("formula", "string", default=""),
            PortSpec("variables", "string", default=""),
            PortSpec("roots", "json", default=[]),
            PortSpec("root_count", "integer", default=0),
            PortSpec("solved", "boolean", default=False),
        ),
    )

    def __init__(self, module_id: str) -> None:
        super().__init__(module_id)
        self._catalog = load_formula_catalog()
        self._formula_edit: QLineEdit | None = None
        self._solve_edit: QLineEdit | None = None
        self._vars_edit: QLineEdit | None = None
        self._auto_check: QCheckBox | None = None
        self._professional_check: QCheckBox | None = None
        self._result_view: QTextEdit | None = None
        self._error_label: QLabel | None = None
        self._library_dialog: _FormulaLibraryDialog | None = None

    def widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        apply_layout_defaults(layout)

        form = QFormLayout()

        self._formula_edit = QLineEdit(str(self.inputs["formula"]))
        self._formula_edit.setPlaceholderText(
            "e.g. F = m*a, x^2 - 4, refs{lambda=lam}; N=N0*exp(-lambda*t)"
        )
        self._formula_edit.textChanged.connect(self._on_formula_changed)
        set_control_height(self._formula_edit)
        form.addRow("Formula", self._formula_edit)

        self._solve_edit = QLineEdit(str(self.inputs["solve_for"]))
        self._solve_edit.setPlaceholderText("optional target variable")
        self._solve_edit.textChanged.connect(self._on_solve_for_changed)
        set_control_height(self._solve_edit)
        form.addRow("Solve For", self._solve_edit)

        self._vars_edit = QLineEdit(str(self.inputs["variables"]))
        self._vars_edit.setPlaceholderText("e.g. m=2, a=9.81")
        self._vars_edit.textChanged.connect(self._on_variables_changed)
        set_control_height(self._vars_edit)
        form.addRow("Variables", self._vars_edit)

        layout.addLayout(form)

        toggles = QHBoxLayout()

        self._auto_check = QCheckBox("Live Recompute")
        self._auto_check.setChecked(bool(self.inputs["auto_evaluate"]))
        self._auto_check.toggled.connect(self._on_auto_toggled)
        toggles.addWidget(self._auto_check)

        self._professional_check = QCheckBox("Full Professional Generality")
        self._professional_check.setChecked(bool(self.inputs["full_professional_generality"]))
        self._professional_check.toggled.connect(self._on_professional_toggled)
        toggles.addWidget(self._professional_check)
        toggles.addStretch(1)
        layout.addLayout(toggles)

        buttons = QHBoxLayout()

        evaluate_btn = QPushButton("Evaluate")
        evaluate_btn.clicked.connect(lambda: self._evaluate_now())
        set_control_height(evaluate_btn)
        buttons.addWidget(evaluate_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        set_control_height(clear_btn)
        buttons.addWidget(clear_btn)

        library_btn = QPushButton("Open Formula Library")
        library_btn.clicked.connect(self._open_library)
        set_control_height(library_btn)
        buttons.addWidget(library_btn)

        layout.addLayout(buttons)

        self._result_view = QTextEdit()
        self._result_view.setReadOnly(True)
        layout.addWidget(self._result_view, stretch=1)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        self._sync_output_views()
        return root

    def on_input(self, port: str, value: Any) -> None:
        if port == "formula":
            self._set_formula_text(str(value))
            self._evaluate_if_enabled()
            return

        if port == "solve_for":
            text = str(value).strip()
            self._set_input_value("solve_for", text)
            if self._solve_edit is not None and self._solve_edit.text() != text:
                self._solve_edit.blockSignals(True)
                self._solve_edit.setText(text)
                self._solve_edit.blockSignals(False)
            self._evaluate_if_enabled()
            return

        if port == "variables":
            text = str(value)
            self._set_input_value("variables", text)
            if self._vars_edit is not None and self._vars_edit.text() != text:
                self._vars_edit.blockSignals(True)
                self._vars_edit.setText(text)
                self._vars_edit.blockSignals(False)
            self._evaluate_if_enabled()
            return

        if port == "auto_evaluate":
            enabled = bool(value)
            self._set_input_value("auto_evaluate", enabled)
            if self._auto_check is not None and self._auto_check.isChecked() != enabled:
                self._auto_check.blockSignals(True)
                self._auto_check.setChecked(enabled)
                self._auto_check.blockSignals(False)
            if enabled:
                self._evaluate_now()
            return

        if port == "full_professional_generality":
            enabled = bool(value)
            self._set_input_value("full_professional_generality", enabled)
            if (
                self._professional_check is not None
                and self._professional_check.isChecked() != enabled
            ):
                self._professional_check.blockSignals(True)
                self._professional_check.setChecked(enabled)
                self._professional_check.blockSignals(False)
            if self._library_dialog is not None:
                self._library_dialog.sync_professional(enabled)
            return

        if port == "evaluate" and is_truthy(value):
            self._evaluate_now()
            return

        if port == "clear" and is_truthy(value):
            self._clear()
            return

        if port == "open_library" and is_truthy(value):
            self._open_library()

    def _on_formula_changed(self, text: str) -> None:
        self._set_input_value("formula", text)
        self._evaluate_if_enabled()

    def _on_solve_for_changed(self, text: str) -> None:
        self._set_input_value("solve_for", text.strip())
        self._evaluate_if_enabled()

    def _on_variables_changed(self, text: str) -> None:
        self._set_input_value("variables", text)
        self._evaluate_if_enabled()

    def _on_auto_toggled(self, checked: bool) -> None:
        self._set_input_value("auto_evaluate", bool(checked))
        if checked:
            self._evaluate_now()

    def _on_professional_toggled(self, checked: bool) -> None:
        enabled = bool(checked)
        self._set_input_value("full_professional_generality", enabled)
        if self._library_dialog is not None:
            self._library_dialog.sync_professional(enabled)

    def _set_formula_text(self, text: str) -> None:
        self._set_input_value("formula", text)
        if self._formula_edit is not None and self._formula_edit.text() != text:
            self._formula_edit.blockSignals(True)
            self._formula_edit.setText(text)
            self._formula_edit.blockSignals(False)

    def _select_formula_expression(self, expression: str) -> None:
        self._set_formula_text(expression)
        self._evaluate_if_enabled()

    def _open_library(self) -> None:
        if self._library_dialog is not None:
            self._library_dialog.show()
            self._library_dialog.raise_()
            self._library_dialog.activateWindow()
            return

        self._library_dialog = _FormulaLibraryDialog(
            formulas=self._catalog,
            professional_enabled=bool(self.inputs["full_professional_generality"]),
            on_professional_changed=self._on_professional_from_dialog,
            on_formula_selected=self._select_formula_expression,
        )
        self._library_dialog.finished.connect(self._on_library_closed)
        self._library_dialog.show()

    def _on_professional_from_dialog(self, enabled: bool) -> None:
        self._set_input_value("full_professional_generality", enabled)
        if self._professional_check is not None and self._professional_check.isChecked() != enabled:
            self._professional_check.blockSignals(True)
            self._professional_check.setChecked(enabled)
            self._professional_check.blockSignals(False)

    def _on_library_closed(self, _: int) -> None:
        self._library_dialog = None

    def _clear(self) -> None:
        self._set_input_value("formula", "")
        self._set_input_value("solve_for", "")
        self._set_input_value("variables", "")

        if self._formula_edit is not None:
            self._formula_edit.blockSignals(True)
            self._formula_edit.clear()
            self._formula_edit.blockSignals(False)
        if self._solve_edit is not None:
            self._solve_edit.blockSignals(True)
            self._solve_edit.clear()
            self._solve_edit.blockSignals(False)
        if self._vars_edit is not None:
            self._vars_edit.blockSignals(True)
            self._vars_edit.clear()
            self._vars_edit.blockSignals(False)

        self._emit_empty_state()

    def _evaluate_if_enabled(self) -> None:
        if bool(self.inputs["auto_evaluate"]):
            self._evaluate_now()

    def _emit_empty_state(self) -> None:
        self.emit("value", 0.0)
        self.emit("text", "")
        self.emit("error", "")
        self.emit("formula", "")
        self.emit("variables", "")
        self.emit("roots", [])
        self.emit("root_count", 0)
        self.emit("solved", False)
        if self._result_view is not None:
            self._result_view.setPlainText("")
        if self._error_label is not None:
            self._error_label.setText("")

    def _sync_output_views(self) -> None:
        if self._result_view is not None:
            self._result_view.setPlainText(str(self.outputs.get("text", "")))
        if self._error_label is not None:
            self._error_label.setText(str(self.outputs.get("error", "")))

    def replay_state(self) -> None:
        if bool(self.inputs["auto_evaluate"]):
            self._evaluate_now()
            return
        self._sync_output_views()

    def _evaluate_now(self) -> None:
        formula_raw = str(self.inputs["formula"])
        solve_for_external = str(self.inputs["solve_for"]).strip()
        variables_raw = str(self.inputs["variables"])

        formula_for_emit = ""
        env_external: dict[str, float] = {}

        try:
            refs, formula_body = _split_reference_formula(formula_raw, strict=True)
            formula_external = _normalize_formula(formula_body)
            if not formula_external:
                self._emit_empty_state()
                return

            _require_reference_coverage(formula_external, refs)
            formula_internal = _rewrite_identifiers(formula_external, refs)
            formula_for_emit = _canonical_reference_formula(formula_external, refs)

            env_external = _parse_assignments(variables_raw)
            env_internal = _map_env_identifiers(env_external, refs)

            if (
                solve_for_external
                and keyword.iskeyword(solve_for_external)
                and solve_for_external not in refs
            ):
                raise ValueError(
                    f"solve_for '{solve_for_external}' is parser-unsafe. Add refs mapping."
                )
            solve_for_internal = refs.get(solve_for_external, solve_for_external)

            explicit_assignments_internal = {
                refs.get(name, name) for name in env_external
            }

            if "=" in formula_internal:
                result = self._evaluate_equation(
                    formula=formula_internal,
                    solve_for=solve_for_internal,
                    env=env_internal,
                    explicit_assignments=explicit_assignments_internal,
                )
            else:
                result = self._evaluate_expression(formula_internal, env_internal)

            roots_json = _roots_to_json(result.roots)
            root_count = len(result.roots)
            value_out = float(result.value) if result.value is not None else 0.0
            vars_out = _format_variables(env_external)
            result_text = result.text
            if result.solved and result.target is not None:
                inverse_refs = {internal: external for external, internal in refs.items()}
                display_target = inverse_refs.get(result.target, result.target)
                result_text = f"{display_target} = {_roots_to_text(result.roots)}"

            self.emit("value", value_out)
            self.emit("text", result_text)
            self.emit("error", "")
            self.emit("formula", formula_for_emit)
            self.emit("variables", vars_out)
            self.emit("roots", roots_json)
            self.emit("root_count", root_count)
            self.emit("solved", bool(result.solved))

            if self._result_view is not None:
                self._result_view.setPlainText(result_text)
            if self._error_label is not None:
                self._error_label.setText("")

        except Exception as exc:
            message = str(exc)
            self.emit("value", 0.0)
            self.emit("text", "")
            self.emit("error", message)
            self.emit("formula", formula_for_emit or formula_raw.strip())
            self.emit("variables", _format_variables(env_external))
            self.emit("roots", [])
            self.emit("root_count", 0)
            self.emit("solved", False)

            if self._result_view is not None:
                self._result_view.setPlainText("")
            if self._error_label is not None:
                self._error_label.setText(message)

    def _evaluate_expression(self, formula: str, env: dict[str, float]) -> _EvaluationResult:
        branches = _expand_plus_minus(formula)
        values = [ExpressionEngine.evaluate(branch, env) for branch in branches]
        unique = _dedupe_solutions(values)

        if len(unique) == 1:
            value = unique[0]
            return _EvaluationResult(text=f"{value:g}", value=value, roots=[], solved=False)

        text = "[" + ", ".join(f"{value:g}" for value in unique) + "]"
        roots = [complex(item, 0.0) for item in unique]
        return _EvaluationResult(text=text, value=unique[0], roots=roots, solved=False)

    def _evaluate_equation(
        self,
        *,
        formula: str,
        solve_for: str,
        env: dict[str, float],
        explicit_assignments: set[str],
    ) -> _EvaluationResult:
        left_raw, right_raw = [part.strip() for part in formula.split("=", 1)]
        if not left_raw or not right_raw:
            raise ValueError("Equation must contain expressions on both sides.")

        left_name = _is_identifier(left_raw)
        right_name = _is_identifier(right_raw)

        target = solve_for
        if target and not _is_identifier(target):
            raise ValueError("solve_for must be a valid variable name.")

        if not target:
            if left_name and left_raw not in explicit_assignments:
                target = left_raw
            elif right_name and right_raw not in explicit_assignments:
                target = right_raw

        left_branches = _expand_plus_minus(left_raw)
        right_branches = _expand_plus_minus(right_raw)

        if target:
            if target == left_raw and left_name and target not in _infer_variables(right_raw):
                values = [ExpressionEngine.evaluate(expr, env) for expr in right_branches]
                roots = [complex(value, 0.0) for value in _dedupe_solutions(values)]
            elif target == right_raw and right_name and target not in _infer_variables(left_raw):
                values = [ExpressionEngine.evaluate(expr, env) for expr in left_branches]
                roots = [complex(value, 0.0) for value in _dedupe_solutions(values)]
            else:
                roots = self._solve_equation_roots(
                    left_branches=left_branches,
                    right_branches=right_branches,
                    target=target,
                    env=env,
                )

            first_real = _first_real_value(roots)
            return _EvaluationResult(
                text=f"{target} = {_roots_to_text(roots)}",
                value=first_real,
                roots=roots,
                solved=True,
                target=target,
            )

        left_value = ExpressionEngine.evaluate(left_branches[0], env)
        right_value = ExpressionEngine.evaluate(right_branches[0], env)
        residual = left_value - right_value
        text = f"lhs={left_value:g}, rhs={right_value:g}, residual={residual:g}"
        return _EvaluationResult(text=text, value=residual, roots=[], solved=False)

    def _solve_equation_roots(
        self,
        *,
        left_branches: list[str],
        right_branches: list[str],
        target: str,
        env: dict[str, float],
    ) -> list[complex]:
        roots: list[complex] = []
        last_error = f"Could not solve equation for '{target}'."

        for lhs in left_branches:
            for rhs in right_branches:
                try:
                    numeric = _solve_numeric(lhs, rhs, target, env)
                    roots.append(complex(numeric, 0.0))
                    continue
                except Exception as numeric_exc:
                    last_error = str(numeric_exc)

                if _SYMPY_AVAILABLE:
                    branch_formula = f"{lhs}={rhs}"
                    try:
                        roots.extend(_symbolic_solve(branch_formula, target, env))
                        continue
                    except Exception as symbolic_exc:
                        last_error = str(symbolic_exc)

        if not roots:
            raise ValueError(last_error)
        return _dedupe_complex_solutions(roots)
