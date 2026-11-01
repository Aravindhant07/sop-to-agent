"""Generate test cases with expected outcomes from the compiled rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .analyze import Issue, boundary_values, input_grid
from .engine import Engine
from .expr import holds
from .spec import Spec


@dataclass
class TestCase:
    id: str
    kind: str  # rule | boundary | gap | contradiction
    inputs: dict[str, Any]
    expected: str | None
    rule_id: str | None
    note: str = ""
    depends_on: list[str] = field(default_factory=list)  # open issue ids that affect this case


def generate_tests(spec: Spec, issues: list[Issue] | None = None) -> list[TestCase]:
    engine = Engine(spec)
    grid = input_grid(spec)
    issues = issues or []
    tests: list[TestCase] = []
    seen: set[tuple] = set()

    def deps(point: dict[str, Any]) -> list[str]:
        out = []
        for i in issues:
            if i.kind == "contradiction":
                rs = [r for r in spec.rules if r.id in i.rule_ids]
                if len(rs) == 2 and all(holds(r.condition, point) for r in rs):
                    out.append(i.id)
            elif i.kind == "boundary_mismatch" and i.examples:
                (f, t), = i.examples[0].items()
                if point.get(f) == t:
                    out.append(i.id)
            elif i.kind == "gap" and engine.decide(point).outcome is None:
                out.append(i.id)
        return out

    def add(kind: str, p: dict[str, Any], note: str) -> None:
        key = tuple(sorted(p.items()))
        if key in seen:
            return
        seen.add(key)
        res = engine.decide(p)
        tests.append(TestCase(f"T{len(tests) + 1}", kind, dict(p), res.outcome, res.rule.id if res.rule else None, note, deps(p)))

    # One case per rule: an input where that rule is the one that decides.
    for r in engine.rules:
        p = next((p for p in grid if engine.decide(p).rule is r), None)
        if p:
            add("rule", p, f"exercises {r.id}")

    # Cases that illustrate open issues: until the customer answers, their expected outcome is provisional.
    for i in issues:
        if i.kind in ("gap", "contradiction"):
            for p in i.examples[:2]:
                if set(p) == {f.name for f in spec.inputs}:
                    add(i.kind, p, f"illustrates {i.id} ({i.kind})")

    # Boundary cases: vary one field across each threshold, everything else held at a base case.
    base = next((p for p in grid if (res := engine.decide(p)).rule and res.rule.priority == "default"), grid[0] if grid else {})
    bv = boundary_values(spec)
    for f in spec.inputs:
        if f.type not in ("number", "integer"):
            continue
        for v in bv[f.name]:
            p = dict(base)
            p[f.name] = v
            add("boundary", p, f"{f.name} = {v}")
    return tests
