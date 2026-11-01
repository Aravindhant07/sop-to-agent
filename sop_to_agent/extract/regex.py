"""Pattern-matching baseline extractor. No model: fast, free, brittle on paraphrase.

Uses the spec's field aliases, enum/boolean value phrases and outcome phrases.
"""

from __future__ import annotations

import re
from typing import Any

from ..ingest import Sentence
from ..spec import Comparison, Condition, Spec

WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
NUM = r"\$?\s*(\d[\d,]*(?:\.\d+)?|" + "|".join(WORD_NUMBERS) + r")\s*(?:%|percent)?"
PREFIX_OPS = [  # phrase before the number
    (r"falls? short of|below|under|less than|lower than|fewer than", "<"),
    (r"no more than|at most|up to|not more than", "<="),
    (r"above|over|more than|exceeds?|greater than|higher than", ">"),
    (r"at least|no less than|minimum of|not less than", ">="),
]
SUFFIX_OPS = [  # phrase after the number
    (r"or more|or higher|or above|or greater", ">="),
    (r"or less|or lower|or below|or fewer", "<="),
]
DEFAULT_PHRASES = re.compile(r"\b(all other|otherwise|every check above|any remaining|in all other cases)\b", re.I)


def _num(s: str) -> float:
    s = s.lower().strip()
    return float(WORD_NUMBERS[s]) if s in WORD_NUMBERS else float(s.replace(",", ""))


def _phrase_re(phrases: list[str]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + r")\b", re.I)


def find_outcome(spec: Spec, text: str) -> str | None:
    """Earliest-listed outcome whose phrase appears (spec order puts negative phrases first)."""
    best: tuple[int, str] | None = None
    for outcome, phrases in spec.outcome_aliases.items():
        m = _phrase_re(phrases).search(text) if phrases else None
        if m:
            # prefer the longest matching phrase, so "cannot be approved" beats "approved"
            score = -len(m.group(1))
            if best is None or score < best[0]:
                best = (score, outcome)
    return best[1] if best else None


def numeric_comparisons(text: str, fname: str, alias_pos: int) -> list[Comparison]:
    """Comparisons for a numeric field mentioned at alias_pos: the closest number phrases after it."""
    out: list[Comparison] = []
    tail = text[alias_pos:]
    m = re.search(rf"between\s+{NUM}\s+and\s+{NUM}", tail, re.I)
    if m:
        return [Comparison(field=fname, op=">=", value=_num(m.group(1))), Comparison(field=fname, op="<=", value=_num(m.group(2)))]
    for phrase, op in PREFIX_OPS:
        m = re.search(rf"\b(?:{phrase})\s+(?:the\s+)?{NUM}", tail, re.I)
        if m:
            out.append((m.start(), Comparison(field=fname, op=op, value=_num(m.group(1)))))
    for phrase, op in SUFFIX_OPS:
        m = re.search(rf"{NUM}\s+(?:{phrase})\b", tail, re.I)
        if m:
            out.append((m.start(), Comparison(field=fname, op=op, value=_num(m.group(1)))))
    out.sort(key=lambda x: x[0])
    return [out[0][1]] if out else []


def extract_rule(spec: Spec, s: Sentence) -> dict[str, Any] | None:
    text = s.text
    outcome = find_outcome(spec, text)
    if outcome is None:
        return None
    comps: list[Comparison] = []
    used_spans: list[tuple[int, int]] = []
    for f in spec.inputs:
        if f.type in ("number", "integer") and f.aliases:
            m = _phrase_re(f.aliases).search(text)
            if m and not any(a <= m.start() < b for a, b in used_spans):
                c = numeric_comparisons(text, f.name, m.start())
                if c:
                    comps += c
                    used_spans.append((m.start(), m.end()))
        elif f.type in ("enum", "boolean"):
            for value, phrases in f.value_aliases.items():
                if phrases and _phrase_re(phrases).search(text):
                    v: Any = value
                    if f.type == "boolean":
                        v = value == "true"
                    comps.append(Comparison(field=f.name, op="==", value=v))
                    break
    if comps:
        return {"condition": Condition(combine="all", comparisons=comps), "outcome": outcome, "priority": "normal"}
    if DEFAULT_PHRASES.search(text):
        return {"condition": Condition(), "outcome": outcome, "priority": "default"}
    return None


class RegexExtractor:
    name = "regex"

    def extract(self, spec: Spec, s: Sentence) -> dict[str, Any] | None:
        return extract_rule(spec, s)
