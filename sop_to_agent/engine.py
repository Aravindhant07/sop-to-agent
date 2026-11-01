"""Compile a spec into an executable first-match decision list."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .expr import holds
from .spec import Rule, Spec


@dataclass
class Result:
    outcome: str | None  # None = no rule applies (a gap)
    rule: Rule | None


class Engine:
    """Rules are tried in order: overrides first, then normal rules in document
    order, then default rules. The first rule whose condition holds decides."""

    def __init__(self, spec: Spec):
        self.spec = spec
        rules = spec.active_rules()
        rank = {"override": 0, "normal": 1, "default": 2}
        self.rules: list[Rule] = sorted(rules, key=lambda r: rank[r.priority])  # stable: keeps document order

    def decide(self, inputs: dict[str, Any]) -> Result:
        for r in self.rules:
            if holds(r.condition, inputs):
                return Result(r.outcome, r)
        return Result(None, None)

    def firing(self, inputs: dict[str, Any]) -> list[Rule]:
        """Every rule whose condition holds, not just the first."""
        return [r for r in self.rules if holds(r.condition, inputs)]
