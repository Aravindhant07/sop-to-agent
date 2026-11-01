"""Schema discovery: ask a model to propose the decision outcomes and input fields.

The proposal is a starting point; the engineer edits schema.yaml before extraction.
"""

from __future__ import annotations

import re

from ..ingest import Document
from ..llm import JSONBackend
from ..spec import InputField, Spec

SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string"},
        "outcomes": {"type": "array", "items": {"type": "string"}},
        "inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["number", "integer", "enum", "boolean"]},
                    "description": {"type": "string"},
                    "values": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "type", "description", "values"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decision", "outcomes", "inputs"],
    "additionalProperties": False,
}

SYSTEM = (
    "You read a business procedure and list what an automated decision needs.\n"
    "Return: decision (snake_case name), outcomes (snake_case verbs such as approve, decline, refer), and inputs: "
    "every fact about a case that a rule checks. For each input give a snake_case name, a type (number, integer, enum, "
    "boolean), a short description, and for enums the allowed snake_case values (else an empty list). "
    "Answer with only the JSON object."
)


def _snake(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")


def discover_schema(documents: list[Document], backend: JSONBackend, name: str = "process") -> Spec:
    text = "\n\n".join(d.text for d in documents)
    r = backend.complete(SYSTEM, f"Procedure:\n{text[:12000]}", SCHEMA)
    d = r.data
    inputs = []
    seen = set()
    for f in d.get("inputs") or []:
        try:
            n = _snake(str(f["name"]))
            if not n or n in seen:
                continue
            t = f.get("type") if f.get("type") in ("number", "integer", "enum", "boolean") else "number"
            vals = [_snake(v) for v in f.get("values") or []] or None
            if t == "enum" and not vals:
                t = "boolean"
            inputs.append(InputField(name=n, type=t, description=str(f.get("description", "")), values=vals if t == "enum" else None,
                                     aliases=[n.replace("_", " ")]))
            seen.add(n)
        except (KeyError, ValueError):
            continue
    outcomes = [_snake(o) for o in d.get("outcomes") or [] if _snake(o)] or ["approve", "decline"]
    return Spec(name=name, decision=_snake(d.get("decision") or "decision") or "decision", outcomes=outcomes, inputs=inputs,
                outcome_aliases={o: [o.replace("_", " ")] for o in outcomes})
