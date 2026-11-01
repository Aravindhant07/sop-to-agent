"""`sop2agent` command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Turn process documents into a traceable agent spec, a discovery report and tests.")

EXTRACTORS = "regex | local | ollama | hf | claude"


def make_extractor(kind: str, model: Optional[str] = None):
    from .extract.llm import LLMExtractor
    from .extract.regex import RegexExtractor
    from .llm import make_backend

    if kind == "regex":
        return RegexExtractor()
    kwargs = {"max_new_tokens": 200} if kind in ("local", "transformers") else {}
    return LLMExtractor(make_backend(kind, model, **kwargs))


def _progress(done: int, total: int) -> None:
    if done == total or done % max(1, total // 4) == 0:
        typer.echo(f"  {done}/{total} sentences")


@app.command()
def schema(
    documents: list[Path] = typer.Argument(..., help="Procedure documents (.md, .txt, .pdf)."),
    provider: str = typer.Option("local", "--provider", help="local | ollama | hf | claude"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    out: Path = typer.Option(Path("schema.yaml"), "--out", "-o"),
    name: str = typer.Option("process", "--name"),
) -> None:
    """Ask a model to propose outcomes and input fields. Edit the result before compiling."""
    from .extract.schema import discover_schema
    from .ingest import load_documents
    from .llm import make_backend

    spec = discover_schema(load_documents(documents), make_backend(provider, model), name=name)
    spec.save(out)
    typer.echo(f"Proposed {len(spec.outcomes)} outcomes and {len(spec.inputs)} inputs → {out}. Review it, then run compile.")


@app.command("compile")
def compile_cmd(
    documents: list[Path] = typer.Argument(..., help="Procedure documents (.md, .txt, .pdf)."),
    schema_file: Path = typer.Option(..., "--schema", "-s", help="schema.yaml with outcomes and inputs."),
    extractor: str = typer.Option("regex", "--extractor", "-e", help=EXTRACTORS),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model for LLM extractors."),
    out: Path = typer.Option(Path("out"), "--out", "-o"),
) -> None:
    """Extract rules, analyse them, generate tests and write every output."""
    from .export import write_outputs
    from .ingest import load_documents
    from .pipeline import compile_documents
    from .spec import Spec

    docs = load_documents(documents)
    ex = make_extractor(extractor, model)
    typer.echo(f"Extracting rules with {ex.name}…")
    res = compile_documents(Spec.load(schema_file), docs, ex, _progress)
    write_outputs(res, docs, out)
    hi = sum(1 for i in res.issues if i.severity == "high")
    typer.echo(f"{len(res.spec.rules)} rules · {len(res.issues)} issues ({hi} high) · {len(res.tests)} tests · "
               f"{len(res.rejected)} sentences rejected")
    typer.echo(f"Outputs in {out}/: spec.yaml, report.html, report.md, tests.jsonl, shadow_eval_domain.yaml")
    typer.echo(f"Review in the browser: sop2agent serve --out {out}")


@app.command()
def analyze(out: Path = typer.Option(Path("out"), "--out", "-o")) -> None:
    """Re-run analysis and tests after editing spec.yaml by hand."""
    from .web.app import Workspace

    ws = Workspace(out)
    ws.save()
    typer.echo(f"{len(ws.result.issues)} issues · {len(ws.result.tests)} tests · outputs refreshed in {out}/")


@app.command()
def serve(out: Path = typer.Option(Path("out"), "--out", "-o"), port: int = typer.Option(8100, "--port"),
          host: str = typer.Option("127.0.0.1", "--host")) -> None:
    """Open the review UI for a compiled workspace."""
    import uvicorn

    from .web.app import create_app

    typer.echo(f"Open http://{host}:{port}")
    uvicorn.run(create_app(out), host=host, port=port, log_level="warning")


@app.command()
def demo(out: Path = typer.Option(Path("demo_out"), "--out", "-o"), serve_ui: bool = typer.Option(False, "--serve")) -> None:
    """Compile the bundled example loan procedure with the free regex extractor (instant, offline)."""
    root = Path(__file__).resolve().parents[1] / "examples" / "loan"
    compile_cmd([root / "loan_procedure.md"], root / "schema.yaml", "regex", None, out)
    if serve_ui:
        serve(out)


@app.command()
def benchmark(
    extractor: str = typer.Option("regex", "--extractor", "-e", help=EXTRACTORS),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    out: Path = typer.Option(Path("docs/results"), "--out", "-o"),
) -> None:
    """Score an extractor on the synthetic loan SOPs (known rules, planted issues)."""
    from .bench.run import format_summary, run_benchmark

    s = run_benchmark(make_extractor(extractor, model), out, _progress)
    typer.echo(format_summary(s))


if __name__ == "__main__":
    app()
