"""Score an extractor on the synthetic loan SOPs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..analyze import input_grid
from ..engine import Engine
from ..expr import holds
from ..pipeline import Extractor, compile_documents
from ..spec import Spec
from .loan import PLANTS, Variant, all_variants, base_spec

RULE_SENTENCE_PLANTS = {"contradiction", "boundary_mismatch", "unreachable"}  # planted sentences that ARE rules


def _merged_grid(truth: Spec, extracted: Spec) -> list[dict[str, Any]]:
    merged = truth.model_copy(deep=True)
    merged.rules = truth.rules + extracted.rules
    return input_grid(merged)


def score_variant(v: Variant, extractor: Extractor, on_progress: Callable | None = None) -> dict[str, Any]:
    res = compile_documents(base_spec(v.name), [v.document], extractor, on_progress)
    ext = res.spec
    grid = _merged_grid(v.truth, ext)
    te, ee = Engine(v.truth), Engine(ext)
    agree = sum(1 for p in grid if te.decide(p).outcome == ee.decide(p).outcome) / len(grid)

    # Rule recall: a true rule counts as recovered if an extracted rule cites its sentence
    # and behaves identically (same outcome, condition true on exactly the same inputs).
    by_sid = {r.citation.sentence_id: r for r in ext.rules if r.citation}
    recovered = []
    for tr in v.truth.rules:
        er = by_sid.get(tr.citation.sentence_id)
        ok = bool(er and er.outcome == tr.outcome and er.priority == tr.priority
                  and all(holds(er.condition, p) == holds(tr.condition, p) for p in grid))
        recovered.append({"rule": tr.id, "sentence": tr.citation.quote, "recovered": ok,
                          "extracted": None if not er else {"outcome": er.outcome, "condition": er.condition.model_dump()}})

    # Citation precision: extracted rules should come from rule sentences, not filler.
    rule_sids = {r.citation.sentence_id for r in v.truth.rules}
    planted_rule_texts = {PLANTS[k][1] for k in RULE_SENTENCE_PLANTS}
    rule_sids |= {s.id for s in v.document.sentences if s.text in planted_rule_texts}
    false_rules = [r.citation.quote for r in ext.rules if r.citation and r.citation.sentence_id not in rule_sids]

    # Issue detection.
    found = []
    for p in v.planted:
        hit = any(i.kind == p.kind and (p.sentence_id is None or p.sentence_id in i.sentence_ids) for i in res.issues)
        found.append({"kind": p.kind, "text": p.text, "detected": hit})
    scored = [i for i in res.issues if i.kind != "unparsed_requirement"]
    matched = [i for i in scored if any(i.kind == p.kind and (p.sentence_id is None or p.sentence_id in i.sentence_ids) for p in v.planted)]
    return {
        "variant": v.name,
        "decision_agreement": agree,
        "rule_recall": sum(r["recovered"] for r in recovered) / len(recovered),
        "rules": recovered,
        "false_rules": false_rules,
        "issue_recall": sum(f["detected"] for f in found) / len(found) if found else 1.0,
        "issue_precision": len(matched) / len(scored) if scored else 1.0,
        "issues_found": found,
        "unparsed_flags": sum(1 for i in res.issues if i.kind == "unparsed_requirement"),
        "stats": res.stats,
    }


def run_benchmark(extractor: Extractor, out_dir: str | Path | None = None, on_progress: Callable | None = None) -> dict[str, Any]:
    results = [score_variant(v, extractor, on_progress) for v in all_variants()]
    n = len(results)
    summary = {
        "extractor": extractor.name,
        "decision_agreement": sum(r["decision_agreement"] for r in results) / n,
        "rule_recall": sum(r["rule_recall"] for r in results) / n,
        "issue_recall": sum(r["issue_recall"] for r in results) / n,
        "issue_precision": sum(r["issue_precision"] for r in results) / n,
        "false_rules": sum(len(r["false_rules"]) for r in results),
        "seconds": round(sum(r["stats"].get("seconds", 0) for r in results), 1),
        "variants": results,
    }
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        slug = extractor.name.replace("/", "_").replace(":", "_")
        (out / f"benchmark_{slug}.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def format_summary(s: dict[str, Any]) -> str:
    lines = [f"Extractor: {s['extractor']}",
             f"  decision agreement {s['decision_agreement']:.1%} · rule recall {s['rule_recall']:.1%} · "
             f"issue recall {s['issue_recall']:.1%} · issue precision {s['issue_precision']:.1%} · "
             f"false rules {s['false_rules']} · {s['seconds']}s"]
    for r in s["variants"]:
        lines.append(f"  {r['variant']}: agreement {r['decision_agreement']:.1%}, rules {r['rule_recall']:.0%}, "
                     f"issues {sum(f['detected'] for f in r['issues_found'])}/{len(r['issues_found'])}")
    return "\n".join(lines)
