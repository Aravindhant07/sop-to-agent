"""The decision spec: inputs, outcomes and ordered rules, each traceable to its source."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

OPS = ("<", "<=", ">", ">=", "==", "!=", "in", "not_in")


class InputField(BaseModel):
    name: str
    type: Literal["number", "integer", "enum", "boolean"]
    description: str = ""
    values: list[str] | None = None  # enum values
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    aliases: list[str] = Field(default_factory=list)  # phrases that refer to this field
    value_aliases: dict[str, list[str]] = Field(default_factory=dict)  # enum value -> phrases

    @model_validator(mode="after")
    def _check(self) -> "InputField":
        if self.type == "enum" and not self.values:
            raise ValueError(f"enum field '{self.name}' needs values")
        return self


class Comparison(BaseModel):
    field: str
    op: Literal["<", "<=", ">", ">=", "==", "!=", "in", "not_in"]
    value: Any


class Condition(BaseModel):
    """A flat condition: comparisons combined with all (AND) or any (OR).

    Flat on purpose: small models produce it reliably, and SOP rules rarely need deeper nesting.
    An empty condition always holds (used for "otherwise" / default rules).
    """

    combine: Literal["all", "any"] = "all"
    comparisons: list[Comparison] = Field(default_factory=list)


class Citation(BaseModel):
    doc: str
    sentence_id: str
    quote: str
    section: str = ""


class Rule(BaseModel):
    id: str
    condition: Condition
    outcome: str
    citation: Citation | None = None
    priority: Literal["normal", "override", "default"] = "normal"
    source: str = "manual"  # regex | llm:<model> | manual | truth
    status: Literal["accepted", "pending", "rejected"] = "accepted"
    note: str = ""


class Spec(BaseModel):
    name: str
    decision: str = "decision"
    outcomes: list[str]
    inputs: list[InputField]
    rules: list[Rule] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    outcome_aliases: dict[str, list[str]] = Field(default_factory=dict)  # outcome -> phrases (regex extractor)

    def field(self, name: str) -> InputField:
        for f in self.inputs:
            if f.name == name:
                return f
        raise KeyError(name)

    def has_field(self, name: str) -> bool:
        return any(f.name == name for f in self.inputs)

    def active_rules(self) -> list[Rule]:
        return [r for r in self.rules if r.status == "accepted"]

    def save(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True))

    @classmethod
    def load(cls, path: str | Path) -> "Spec":
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))
