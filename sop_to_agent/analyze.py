"""Deterministic analysis: contradictions, gaps, boundary mismatches, unreachable
rules and vague terms. No model involved: the compiled rules are evaluated over a
grid of boundary values for every input."""

from __future__ import annotations

import itertools
import random
import re
from dataclasses import dataclass, field
from typing import Any

from .engine import Engine
from .expr import describe, holds
from .ingest import Document, looks_like_rule
from .spec import InputField, Rule, Spec

INFORMAL_SECTIONS = re.compile(r"\b(faq|q&a|questions|notes?|appendix|examples?|guidance|tips|memo|update)\b", re.IGNORECASE)

VAGUE_TERMS = [
    "unstable", "high-risk", "high risk", "low-risk", "adequate", "sufficient", "reasonable", "significant",
    "good standing", "satisfactory", "promptly", "recent", "recently", "excessive", "strong", "weak", "poor",
    "acceptable", "appropriate", "as needed", "case-by-case", "case by case", "discretion", "with caution",
    "unusual", "suspicious", "material", "substantial", "timely",
]
_VAGUE = re.compile(r"\b(" + "|".join(re.escape(t) for t in VAGUE_TERMS) + r")\b", re.IGNORECASE)

QUESTIONS = {
    "contradiction": "These rules give different outcomes for the same applicant and the procedure does not say which wins. Which outcome is correct?",
    "boundary_mismatch": "The documents disagree on whether the exact threshold value is included. What should happen at exactly this value?",
    "gap": "No rule covers these cases. What should happen to them?",
    "unreachable_rule": "This rule can never apply because earlier rules always decide first. Is it still needed, or should it take priority?",
    "vague_term": "This term is not defined precisely enough to automate. What measurable criterion should be used?",
    "unparsed_requirement": "This sentence looks like a requirement but could not be turned into a rule. What exactly should happen?",
}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Issue:
    id: str
    kind: str
    severity: str
    title: str
    question: str
    rule_ids: list[str] = field(default_factory=list)
    sentence_ids: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""


# -- input grid -----------------------------------------------------------

def boundary_values(spec: Spec) -> dict[str, list[Any]]:
    """Per field: every threshold t that appears in a rule, with t−δ and t+δ, plus the field's range."""
    vals: dict[str, set] = {f.name: set() for f in spec.inputs}
    for r in spec.active_rules():
        for c in r.condition.comparisons:
            if c.field not in vals:
                continue
            f = spec.field(c.field)
            if f.type in ("number", "integer"):
                t = float(c.value)
                d = 1.0 if (f.type == "integer" or t.is_integer()) else 0.01
                vals[f.name].update({t - d, t, t + d})
    out: dict[str, list[Any]] = {}
    for f in spec.inputs:
        if f.type == "enum":
            out[f.name] = list(f.values or [])
        elif f.type == "boolean":
            out[f.name] = [True, False]
        else:
            s = set(vals[f.name])
            if f.minimum is not None:
                s.add(float(f.minimum))
            if f.maximum is not None:
                s.add(float(f.maximum))
            if not s:
                s = {0.0}
            lo, hi = f.minimum, f.maximum
            s = {x for x in s if (lo is None or x >= lo) and (hi is None or x <= hi)}
            out[f.name] = sorted(int(x) if f.type == "integer" else x for x in s)
    return out


def input_grid(spec: Spec, limit: int = 30000, seed: int = 0) -> list[dict[str, Any]]:
    bv = boundary_values(spec)
    names = list(bv)
    total = 1
    for n in names:
        total *= max(1, len(bv[n]))
    if total <= limit:
        return [dict(zip(names, combo)) for combo in itertools.product(*(bv[n] for n in names))]
    rng = random.Random(seed)
    seen, pts = set(), []
    while len(pts) < limit:
        p = tuple(rng.choice(bv[n]) for n in names)
        if p not in seen:
            seen.add(p)
            pts.append(dict(zip(names, p)))
    return pts


# -- checks ---------------------------------------------------------------

def _informal(r: Rule) -> bool:
    return bool(r.citation and INFORMAL_SECTIONS.search(r.citation.section or ""))


def _side(op: str) -> str | None:
    """Which band the threshold value itself belongs to, for a comparison against it."""
    return {">": "lower", "<=": "lower", ">=": "upper", "<": "upper"}.get(op)


def analyze(spec: Spec, documents: list[Document] | None = None, rejected: list[dict] | None = None) -> list[Issue]:
    issues: list[Issue] = []
    engine = Engine(spec)
    rules = engine.rules
    grid = input_grid(spec)

    def add(kind, severity, title, **kw):
        issues.append(Issue(id="", kind=kind, severity=severity, title=title, question=QUESTIONS[kind], **kw))

    # 1. Contradictions: overlapping rules with different outcomes where nothing settles the order.
    #    Document order inside the main procedure is treated as an intended cascade; a rule from an
    #    informal section (FAQ, notes, appendix) or another document that disagrees is a contradiction.
    def fields(r: Rule) -> set[str]:
        return {c.field for c in r.condition.comparisons}

    def restates(x: Rule, others: list[Rule]) -> bool:
        """x repeats a main rule (same outcome, same inputs); differences are boundary issues, not conflicts."""
        return any(o.outcome == x.outcome and fields(o) == fields(x) and fields(x) for o in others)

    reported: set[frozenset] = set()
    for i, r1 in enumerate(rules):
        for r2 in rules[i + 1:]:
            if r1.outcome != r2.outcome and r1.condition == r2.condition and r1.condition.comparisons:
                reported.add(frozenset((r1.id, r2.id)))
                add("contradiction", "high", f"Same condition, different outcomes: '{r1.outcome}' vs '{r2.outcome}'",
                    rule_ids=[r1.id, r2.id],
                    sentence_ids=[r.citation.sentence_id for r in (r1, r2) if r.citation],
                    detail=f"{describe(r1.condition)} → {r1.outcome} ({r1.id}) and → {r2.outcome} ({r2.id}).")

    main = [r for r in rules if not _informal(r)]
    docs = {r.citation.doc for r in main if r.citation}
    primary_doc = max(docs, key=lambda d: sum(1 for r in main if r.citation and r.citation.doc == d)) if docs else None
    side_rules = [r for r in rules if r.priority == "normal" and (_informal(r) or (r.citation and r.citation.doc != primary_doc))]
    for x in side_rules:
        if restates(x, [r for r in main if r is not x]):
            continue
        clashes = []
        for m in rules:
            if m is x or m.outcome == x.outcome or m.priority != "normal" or m in side_rules:
                continue
            if frozenset((m.id, x.id)) in reported:
                continue
            ex = next((p for p in grid if holds(m.condition, p) and holds(x.condition, p)), None)
            if ex:
                clashes.append((m, ex))
        if clashes:
            where = x.citation.section if x.citation and x.citation.section else (x.citation.doc if x.citation else "")
            add("contradiction", "high",
                f"'{describe(x.condition)} → {x.outcome}' ({where}) conflicts with {len(clashes)} rule(s)",
                rule_ids=[x.id] + [m.id for m, _ in clashes],
                sentence_ids=[r.citation.sentence_id for r in [x] + [m for m, _ in clashes] if r.citation],
                examples=[ex for _, ex in clashes[:2]],
                detail="; ".join(f"{m.id}: {describe(m.condition)} → {m.outcome}" for m, _ in clashes))

    # 2. Boundary mismatches: the same threshold treated as inclusive in one rule and exclusive in another.
    sides: dict[tuple[str, float], dict[str, list[Rule]]] = {}
    for r in rules:
        for c in r.condition.comparisons:
            s = _side(c.op)
            if s and isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
                sides.setdefault((c.field, float(c.value)), {}).setdefault(s, []).append(r)
    for (fname, t), by in sides.items():
        if "lower" in by and "upper" in by:
            rs = by["lower"] + by["upper"]
            add("boundary_mismatch", "medium", f"{fname} = {t:g}: included in one rule, excluded in another",
                rule_ids=[r.id for r in rs],
                sentence_ids=[r.citation.sentence_id for r in rs if r.citation],
                examples=[{fname: t}],
                detail="; ".join(f"{r.id}: {describe(r.condition)}" for r in rs))

    # 3. Gaps: inputs no rule decides.
    gaps = [p for p in grid if engine.decide(p).outcome is None]
    if gaps:
        add("gap", "high", f"{len(gaps)} of {len(grid)} test inputs are not covered by any rule",
            examples=gaps[:3], detail="Add a default rule or rules for these cases.")

    # 4. Unreachable rules: never the first rule to fire.
    first = {engine.decide(p).rule.id for p in grid if engine.decide(p).rule}
    for r in rules:
        if r.id in first:
            continue
        sat = [p for p in grid if holds(r.condition, p)]
        why = "its condition can never hold" if not sat else "earlier rules always decide first"
        blockers = sorted({engine.decide(p).rule.id for p in sat[:200] if engine.decide(p).rule}) if sat else []
        add("unreachable_rule", "low", f"Rule {r.id} never applies ({why})",
            rule_ids=[r.id] + blockers, sentence_ids=[r.citation.sentence_id] if r.citation else [],
            detail=f"{r.id}: {describe(r.condition)} → {r.outcome}" + (f"; blocked by {', '.join(blockers)}" if blockers else ""))

    # 5. Vague terms in requirement-like sentences.
    for doc in documents or []:
        for s in doc.sentences:
            m = _VAGUE.search(s.text)
            if m and (looks_like_rule(s) or re.search(r"\b(must|should|shall)\b", s.text, re.I)):
                add("vague_term", "medium", f"Vague term '{m.group(1)}'", sentence_ids=[s.id], detail=s.text)

    # 6. Requirement-like sentences that could not be turned into a valid rule.
    vague_ids = {sid for i in issues if i.kind == "vague_term" for sid in i.sentence_ids}
    for rej in rejected or []:
        if rej.get("sentence_id") in vague_ids:
            continue
        add("unparsed_requirement", "low", "Requirement could not be turned into a rule",
            sentence_ids=[rej["sentence_id"]], detail=f"{rej.get('text', '')} ({rej.get('reason', '')})")

    issues.sort(key=lambda i: (SEVERITY_ORDER[i.severity], i.kind))
    for n, i in enumerate(issues, 1):
        i.id = f"I{n}"
    return issues
