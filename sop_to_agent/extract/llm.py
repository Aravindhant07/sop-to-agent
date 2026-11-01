"""LLM extractor: one sentence in, one candidate rule out.

The model never sees more than one sentence and never chooses the citation:
the sentence ID is attached by code, so a citation cannot be hallucinated.
Every answer is validated against the spec before it becomes a rule.
"""

from __future__ import annotations

import json
from typing import Any

from ..ingest import Sentence
from ..llm import JSONBackend, LLMError
from ..spec import Comparison, Condition, Spec

EXAMPLES = [
    ("Applicants with a debt-to-income ratio of 50% or more are declined.",
     {"is_rule": True, "outcome": "decline", "priority": "normal", "combine": "all",
      "comparisons": [{"field": "dti_ratio", "op": ">=", "value": 50}]}),
    ("Retired applicants with a credit score under 600 must be referred.",
     {"is_rule": True, "outcome": "refer", "priority": "normal", "combine": "all",
      "comparisons": [{"field": "employment_status", "op": "==", "value": "retired"}, {"field": "credit_score", "op": "<", "value": 600}]}),
    ("In every remaining case the application is approved.",
     {"is_rule": True, "outcome": "approve", "priority": "default", "combine": "all", "comparisons": []}),
    ("The team reviews files every Monday.",
     {"is_rule": False, "outcome": "", "priority": "normal", "combine": "all", "comparisons": []}),
]


def _fields_text(spec: Spec) -> str:
    lines = []
    for f in spec.inputs:
        extra = f" values: {', '.join(f.values)}" if f.values else ""
        unit = f" ({f.unit})" if f.unit else ""
        lines.append(f"- {f.name}: {f.type}{unit}{extra}. {f.description}")
    return "\n".join(lines)


def system_prompt(spec: Spec) -> str:
    ex = "\n".join(f"Sentence: {s}\nJSON: {json.dumps(j)}" for s, j in EXAMPLES)
    return (
        "You convert ONE sentence from a business procedure into a decision rule.\n\n"
        f"Input fields:\n{_fields_text(spec)}\n\n"
        f"Outcomes: {', '.join(spec.outcomes)}\n\n"
        "Rules for your answer:\n"
        "- is_rule is false if the sentence does not decide an outcome.\n"
        "- Use only the field names and outcomes listed above. Use only these ops: <, <=, >, >=, ==, !=.\n"
        "- 'below/under/less than' is <, 'over/above/more than/exceeds' is >, 'at least/or more' is >=, 'at most/or less' is <=.\n"
        "- Percentages are plain numbers (45% -> 45). Write numbers without $ or commas.\n"
        "- priority is 'default' only for catch-all sentences such as 'otherwise' or 'all other applications'.\n"
        "- If the sentence uses a term that matches no field, set is_rule false.\n\n"
        f"Examples:\n{ex}\n\nAnswer with only the JSON object."
    )


def answer_schema(spec: Spec) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "is_rule": {"type": "boolean"},
            "outcome": {"type": "string", "enum": [*spec.outcomes, ""]},
            "priority": {"type": "string", "enum": ["normal", "default"]},
            "combine": {"type": "string", "enum": ["all", "any"]},
            "comparisons": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": [f.name for f in spec.inputs]},
                        "op": {"type": "string", "enum": ["<", "<=", ">", ">=", "==", "!="]},
                        "value": {"type": ["number", "string", "boolean"]},
                    },
                    "required": ["field", "op", "value"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["is_rule", "outcome", "priority", "combine", "comparisons"],
        "additionalProperties": False,
    }


class LLMExtractor:
    def __init__(self, backend: JSONBackend):
        self.backend = backend
        self.name = f"llm:{backend.name}"

    def extract(self, spec: Spec, s: Sentence) -> dict[str, Any] | None:
        try:
            r = self.backend.complete(system_prompt(spec), f"Sentence: {s.text}\nJSON:", answer_schema(spec))
        except LLMError as e:
            return {"error": str(e)}
        d = r.data
        if not d.get("is_rule"):
            return None
        comps = []
        for c in d.get("comparisons") or []:
            if not isinstance(c, dict) or not {"field", "op", "value"} <= set(c):
                return {"error": f"malformed comparison: {c}"}
            v = c["value"]
            if isinstance(v, str):
                vs = v.replace("$", "").replace(",", "").replace("%", "").strip()
                try:
                    v = float(vs)
                except ValueError:
                    v = {"true": True, "false": False}.get(vs.lower(), v)
            comps.append(Comparison(field=str(c["field"]), op=c["op"] if c["op"] in ("<", "<=", ">", ">=", "==", "!=") else "==", value=v))
        return {
            "condition": Condition(combine=d.get("combine") if d.get("combine") in ("all", "any") else "all", comparisons=comps),
            "outcome": str(d.get("outcome", "")).strip().lower(),
            "priority": "default" if d.get("priority") == "default" else "normal",
            "tokens": (r.input_tokens, r.output_tokens),
        }
