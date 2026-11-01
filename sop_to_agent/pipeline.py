"""End-to-end: documents → candidate rules → validated spec → issues → tests."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .analyze import Issue, analyze
from .expr import normalize, validate_condition
from .ingest import Document, looks_like_rule
from .spec import Citation, Rule, Spec
from .testgen import TestCase, generate_tests


class Extractor(Protocol):
    name: str

    def extract(self, spec: Spec, s) -> dict[str, Any] | None: ...


@dataclass
class CompileResult:
    spec: Spec
    issues: list[Issue]
    tests: list[TestCase]
    rejected: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def extract_rules(
    spec: Spec,
    documents: list[Document],
    extractor: Extractor,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[Rule], list[dict[str, Any]], dict[str, Any]]:
    """Run the extractor on every candidate sentence and validate each answer."""
    candidates = [s for d in documents for s in d.sentences if looks_like_rule(s)]
    rules: list[Rule] = []
    rejected: list[dict[str, Any]] = []
    t0, tok_in, tok_out = time.perf_counter(), 0, 0
    for n, s in enumerate(candidates, 1):
        out = extractor.extract(spec, s)
        if on_progress:
            on_progress(n, len(candidates))
        if out is None:
            continue
        if "error" in out:
            rejected.append({"sentence_id": s.id, "text": s.text, "reason": out["error"]})
            continue
        ti, to = out.get("tokens", (0, 0))
        tok_in, tok_out = tok_in + ti, tok_out + to
        problems = validate_condition(out["condition"], spec)
        if out["outcome"] not in spec.outcomes:
            problems.append(f"unknown outcome '{out['outcome']}'")
        if not out["condition"].comparisons and out["priority"] != "default":
            problems.append("rule has no condition")
        if problems:
            rejected.append({"sentence_id": s.id, "text": s.text, "reason": "; ".join(problems)})
            continue
        rules.append(Rule(
            id=f"R{len(rules) + 1}",
            condition=normalize(out["condition"], spec),
            outcome=out["outcome"],
            priority=out["priority"],
            source=extractor.name,
            citation=Citation(doc=s.doc, sentence_id=s.id, quote=s.text, section=s.section),
        ))
    stats = {"candidates": len(candidates), "rules": len(rules), "rejected": len(rejected),
             "seconds": round(time.perf_counter() - t0, 1), "input_tokens": tok_in, "output_tokens": tok_out}
    return rules, rejected, stats


def compile_documents(spec: Spec, documents: list[Document], extractor: Extractor, on_progress=None) -> CompileResult:
    spec = spec.model_copy(deep=True)
    rules, rejected, stats = extract_rules(spec, documents, extractor, on_progress)
    spec.rules = rules
    spec.documents = [d.name for d in documents]
    return finish(spec, documents, rejected, stats)


def finish(spec: Spec, documents: list[Document], rejected: list[dict[str, Any]] | None = None, stats: dict | None = None) -> CompileResult:
    issues = analyze(spec, documents, rejected or [])
    tests = generate_tests(spec, issues)
    return CompileResult(spec, issues, tests, rejected or [], stats or {})
