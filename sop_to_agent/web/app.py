"""Review UI: check every rule against its source sentence, edit or reject it, and
see issues and tests recomputed immediately."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..expr import describe, normalize, validate_condition
from ..export import write_outputs
from ..ingest import Document, split_document
from ..pipeline import finish
from ..spec import Comparison, Condition, Spec

TEMPLATES = Path(__file__).parent / "templates"


class Workspace:
    def __init__(self, out_dir: str | Path):
        self.dir = Path(out_dir)
        if not (self.dir / "spec.yaml").exists():
            raise FileNotFoundError(f"{self.dir}/spec.yaml not found: run `sop2agent compile` first")
        self.reload()

    def reload(self) -> None:
        self.spec = Spec.load(self.dir / "spec.yaml")
        self.documents: list[Document] = [
            split_document(p.stem, p.read_text()) for p in sorted((self.dir / "documents").glob("*.md"))
        ]
        rj = self.dir / "rejected.json"
        self.rejected: list[dict[str, Any]] = json.loads(rj.read_text()) if rj.exists() else []
        st = self.dir / "stats.json"
        self.stats = json.loads(st.read_text()) if st.exists() else {}
        self.result = finish(self.spec, self.documents, self.rejected, self.stats)

    def save(self) -> None:
        self.result = finish(self.spec, self.documents, self.rejected, self.stats)
        write_outputs(self.result, self.documents, self.dir)

    @property
    def sentences(self):
        return {s.id: s for d in self.documents for s in d.sentences}


def parse_comparisons(text: str) -> list[Comparison]:
    """One comparison per line: `field op value`, e.g. `credit_score < 580`."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) != 3 or parts[1] not in ("<", "<=", ">", ">=", "==", "!="):
            raise ValueError(f"cannot read '{line}': use `field op value`")
        v: Any = parts[2].strip().strip("'\"")
        if v.lower() in ("true", "false"):
            v = v.lower() == "true"
        out.append(Comparison(field=parts[0], op=parts[1], value=v))
    return out


def create_app(out_dir: str | Path) -> FastAPI:
    ws = Workspace(out_dir)
    app = FastAPI(title="sop-to-agent review", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(TEMPLATES))
    templates.env.filters["describe"] = describe

    def page(request: Request, name: str, **ctx: Any) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {"ws": ws, "spec": ws.spec, "res": ws.result, "sentences": ws.sentences, **ctx})

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request) -> HTMLResponse:
        return page(request, "overview.html")

    @app.get("/rules/{rule_id}", response_class=HTMLResponse)
    def rule(request: Request, rule_id: str, error: str = "") -> HTMLResponse:
        r = next((r for r in ws.spec.rules if r.id == rule_id), None)
        if r is None:
            raise HTTPException(404, "unknown rule")
        context = []
        if r.citation:
            doc = next((d for d in ws.documents if d.name == r.citation.doc), None)
            if doc:
                context = [s for s in doc.sentences if s.section == r.citation.section]
        issues = [i for i in ws.result.issues if rule_id in i.rule_ids]
        return page(request, "rule.html", rule=r, context=context, issues=issues, error=error)

    @app.post("/rules/{rule_id}")
    def save_rule(
        rule_id: str,
        status: str = Form(...),
        outcome: str = Form(...),
        priority: str = Form("normal"),
        combine: str = Form("all"),
        comparisons: str = Form(""),
        note: str = Form(""),
    ):
        r = next((r for r in ws.spec.rules if r.id == rule_id), None)
        if r is None:
            raise HTTPException(404, "unknown rule")
        try:
            cond = Condition(combine=combine, comparisons=parse_comparisons(comparisons))
            problems = validate_condition(cond, ws.spec)
            if outcome not in ws.spec.outcomes:
                problems.append(f"unknown outcome '{outcome}'")
            if problems:
                raise ValueError("; ".join(problems))
        except ValueError as e:
            return RedirectResponse(f"/rules/{rule_id}?error={e}", status_code=303)
        r.condition = normalize(cond, ws.spec)
        r.outcome, r.priority, r.status, r.note = outcome, priority, status, note
        r.source = r.source if r.source.endswith("+edited") else r.source + "+edited"
        ws.save()
        return RedirectResponse("/", status_code=303)

    @app.get("/documents/{name}", response_class=HTMLResponse)
    def document(request: Request, name: str) -> HTMLResponse:
        doc = next((d for d in ws.documents if d.name == name), None)
        if doc is None:
            raise HTTPException(404, "unknown document")
        rule_by_sid = {r.citation.sentence_id: r for r in ws.spec.rules if r.citation}
        issue_sids = {sid for i in ws.result.issues for sid in i.sentence_ids}
        return page(request, "document.html", doc=doc, rule_by_sid=rule_by_sid, issue_sids=issue_sids)

    @app.get("/report")
    def report() -> FileResponse:
        return FileResponse(ws.dir / "report.html")

    return app
