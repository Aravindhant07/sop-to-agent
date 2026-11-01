"""Safe condition evaluation and validation (no eval())."""

from __future__ import annotations

from typing import Any

from .spec import Comparison, Condition, InputField, Spec


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compare(c: Comparison, inputs: dict[str, Any]) -> bool:
    if c.field not in inputs:
        return False
    x, v = inputs[c.field], c.value
    if c.op in ("in", "not_in"):
        vals = v if isinstance(v, list) else [v]
        hit = str(x).lower() in {str(i).lower() for i in vals}
        return hit if c.op == "in" else not hit
    if c.op in ("==", "!="):
        if isinstance(x, bool) or isinstance(v, bool):
            eq = bool(x) == (v if isinstance(v, bool) else str(v).lower() in ("true", "yes", "1"))
        elif _num(x) is not None and _num(v) is not None:
            eq = _num(x) == _num(v)
        else:
            eq = str(x).lower() == str(v).lower()
        return eq if c.op == "==" else not eq
    fx, fv = _num(x), _num(v)
    if fx is None or fv is None:
        return False
    return {"<": fx < fv, "<=": fx <= fv, ">": fx > fv, ">=": fx >= fv}[c.op]


def holds(cond: Condition, inputs: dict[str, Any]) -> bool:
    if not cond.comparisons:
        return True
    results = (compare(c, inputs) for c in cond.comparisons)
    return all(results) if cond.combine == "all" else any(results)


def fields_in(cond: Condition) -> set[str]:
    return {c.field for c in cond.comparisons}


def validate_condition(cond: Condition, spec: Spec) -> list[str]:
    """Problems that make a condition unusable against this spec."""
    errors = []
    for c in cond.comparisons:
        if not spec.has_field(c.field):
            errors.append(f"unknown field '{c.field}'")
            continue
        f = spec.field(c.field)
        if f.type in ("number", "integer"):
            if c.op in ("in", "not_in"):
                errors.append(f"'{c.op}' is not valid for number field '{f.name}'")
            elif _num(c.value) is None:
                errors.append(f"'{c.value}' is not a number for '{f.name}'")
        elif f.type == "enum":
            vals = c.value if isinstance(c.value, list) else [c.value]
            bad = [v for v in vals if str(v).lower() not in {x.lower() for x in f.values or []}]
            if bad:
                errors.append(f"{bad} not allowed for '{f.name}' (allowed: {f.values})")
            if c.op in ("<", "<=", ">", ">="):
                errors.append(f"'{c.op}' is not valid for enum field '{f.name}'")
        elif f.type == "boolean":
            if c.op not in ("==", "!="):
                errors.append(f"'{c.op}' is not valid for boolean field '{f.name}'")
    return errors


def normalize(cond: Condition, spec: Spec) -> Condition:
    """Coerce values to the field types (numbers to float, enum values to canonical case)."""
    out = []
    for c in cond.comparisons:
        f: InputField = spec.field(c.field)
        v = c.value
        if f.type in ("number", "integer"):
            v = float(v)
        elif f.type == "boolean":
            v = v if isinstance(v, bool) else str(v).lower() in ("true", "yes", "1")
        elif f.type == "enum":
            canon = {x.lower(): x for x in f.values or []}
            v = [canon[str(i).lower()] for i in v] if isinstance(v, list) else canon[str(v).lower()]
        out.append(Comparison(field=c.field, op=c.op, value=v))
    return Condition(combine=cond.combine, comparisons=out)


def describe(cond: Condition) -> str:
    if not cond.comparisons:
        return "always"
    parts = []
    for c in cond.comparisons:
        v = c.value
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        parts.append(f"{c.field} {c.op} {v}")
    return f" {'and' if cond.combine == 'all' else 'or'} ".join(parts)
