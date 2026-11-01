"""Read process documents and split them into addressable sentences."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Sentence:
    id: str  # "<doc>:<n>"
    doc: str
    section: str
    text: str
    start: int  # character offset in the document text
    end: int


@dataclass
class Document:
    name: str
    text: str
    sentences: list[Sentence]


_ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|vs|no|approx|Mr|Ms|Dr|Inc|Ltd|U\.S)\.$", re.IGNORECASE)
# Candidate boundaries: after . ! ? followed by whitespace and a capital, quote, bracket or digit.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[\"'(A-Z0-9])")


def split_sentences(body: str) -> list[tuple[int, str]]:
    """Return (offset, sentence) pairs; boundaries after abbreviations are merged back."""
    spans, start = [], 0
    for m in _BOUNDARY.finditer(body):
        if _ABBREV.search(body[start:m.start()]):
            continue
        spans.append((start, body[start:m.start()]))
        start = m.end()
    spans.append((start, body[start:]))
    return spans


_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def read_text(path: str | Path) -> str:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="replace")


def split_document(name: str, text: str) -> Document:
    sentences: list[Sentence] = []
    section = ""
    offset = 0
    n = 0
    for line in text.splitlines(keepends=True):
        line_start = offset
        offset += len(line)
        stripped = line.strip()
        if not stripped:
            continue
        m = _HEADING.match(line)
        if m:
            section = m.group(2).strip()
            continue
        body_start = line_start + (len(line) - len(line.lstrip()))
        bullet = _BULLET.match(line)
        if bullet:
            body_start = line_start + bullet.end()
        body = text[body_start:line_start + len(line.rstrip())]
        for idx, part in split_sentences(body):
            part_s = part.strip()
            if len(part_s) < 3:
                continue
            n += 1
            start = body_start + idx
            sentences.append(Sentence(f"{name}:{n}", name, section, part_s, start, start + len(part)))
    return Document(name, text, sentences)


def load_documents(paths: list[str | Path]) -> list[Document]:
    docs = []
    for p in paths:
        p = Path(p)
        docs.append(split_document(p.stem, read_text(p)))
    return docs


_RULEISH = re.compile(
    r"\b(?:if|unless|when|where|must|shall|should|may|cannot|can't|only|any(?:one)?|all|every(?:one)?|other(?:wise)?|"
    r"no|not|never|declin\w*|reject\w*|approv\w*|refer\w*|request\w*|escalat\w*|eligib\w*|ineligib\w*|"
    r"turn\w*|rul\w*|below|above|over|under|north|south|less|more|least|most|exceed\w*|requir\w*)\b"
    r"|\d",
    re.IGNORECASE,
)


def looks_like_rule(s: Sentence) -> bool:
    """Generous pre-filter so slow local models skip only obvious non-rules (headings, short fragments)."""
    return bool(_RULEISH.search(s.text)) and len(s.text.split()) >= 4
