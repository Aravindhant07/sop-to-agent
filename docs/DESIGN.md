# Design: SOP-to-Agent Compiler

Approved choices: **loan approval** as the first domain · **CLI + review web page** ·
**free local open models from Hugging Face** as the default (Ollama and Claude optional).

## Key idea: small model jobs, verified by code

Small local models are unreliable at long reasoning. The Shadow Eval run showed Qwen2.5-1.5B
contradicting itself and hallucinating payouts. So the model never "writes the agent". It does
small, checkable jobs (one sentence → one candidate rule) and **deterministic code** does the
rest: it verifies citations, compiles the rules, finds contradictions and gaps, and generates tests.

```
 SOP docs (md/txt/pdf)
        │
   1 Ingest ──► sentences with IDs and character spans
        │
   2 Schema ──► decision outcomes + input fields      (LLM, then human-editable)
        │
   3 Extract ─► one candidate rule per sentence       (LLM, constrained JSON)
        │        condition · outcome · order cues · exceptions
        │        citation checked: quote must exist in the source
        │
   4 Compile ─► ordered rule list + safe evaluator    (code, no eval())
        │
   5 Analyse ─► contradictions · gaps · vague terms · boundary mismatches
        │        (code: boundary-value grid over input domains)
        │
   6 Tests ───► one case per rule + boundary cases, expected outcomes from the engine
        │
   7 Export ──► spec.yaml · discovery report · tests.jsonl · shadow-eval domain YAML
        │
   8 Review UI (web): each rule next to its highlighted source sentence; accept / edit / reject → recompile
```

## Components

**1. Ingest.** Markdown, text or PDF (`pypdf`) → normalized text → sentences, each with
`doc`, section path, index and character span. Lists and tables are kept as separate sentences.

**2. Schema discovery.** The LLM proposes the decision outcomes (e.g. approve, decline, refer,
request_documents) and the input fields (`credit_score: int`, `employment_status: enum`,
`loan_amount: number`, `dti_ratio: percent` …). This is written to `spec.yaml`, which the
engineer can edit. Every later step uses only these fields.

**3. Rule extraction.** For each sentence, the LLM answers in a strict JSON schema:
`is_rule`, `condition` (a small expression tree over the schema fields: `field op value`,
`all`/`any`/`not`), `outcome`, `order_cue` ("first", "unless", "otherwise"), `exception_of`, and an
exact `quote`. Code then validates it: unknown fields, unknown outcomes and quotes that are not
in the source are rejected and sent to review. They are never silently accepted.
A **regex baseline extractor** (patterns such as "if … then", "more than $X", "must be at least")
runs too, for comparison and as a fallback.

**4. Compile.** Rules are turned into an ordered first-match decision list with an explicit default.
Expressions are evaluated by a small interpreter, never with `eval`.

**5. Analysis.** This is the core differentiator, and it is deterministic. For each field, the code
collects the boundary values that appear in any condition (threshold −ε, exact, +ε; each enum
value). It then evaluates every rule over that grid:
- **Contradiction:** two rules that can both fire on the same input with different outcomes, and no
  stated order between them.
- **Gap:** inputs where no rule fires and no default exists.
- **Boundary mismatch:** "over $50,000" in one place and "$50,000 or more" in another, so the
  outcome at exactly $50,000 is unclear.
- **Vague or undefined terms:** "high-risk", "stable income", "promptly"; a lexicon plus an LLM
  check, and terms that reference no schema field.
- **Unreachable rule:** fully shadowed by earlier rules.

Each issue gets a severity, the evidence (example inputs plus the cited sentences), and a
customer question, e.g. *"At exactly $50,000, should the loan be referred or approved?
Section 3.2 and the FAQ disagree."*

**6. Test generation.** Boundary-value cases for every threshold, one case per rule that reaches it,
and random typical cases. Expected outcomes come from the compiled engine. Cases that depend on an
open issue are flagged and are not treated as truth.

**7. Exports.** `spec.yaml`, the discovery report (HTML and Markdown), `tests.jsonl`, and a
**Shadow Eval domain YAML** (decision field, inputs, segments, policy text). The extracted agent
can then go straight into shadow mode with project 1.

**8. Review UI.** FastAPI + Jinja (same style as Shadow Eval). It lists rules with their source
sentences highlighted, lets you accept, edit or reject each one, shows issues with evidence and
the customer questions, and has a recompile button.

## Benchmark (so quality is measured, not claimed)

A generator writes **synthetic loan-approval SOPs from a known rule set**, using varied phrasing,
and plants issues: a contradiction, a gap, a vague term, a boundary mismatch and an undefined term.
Metrics:
- **Rule recovery by behaviour:** run the extracted engine and the true engine over the boundary
  grid and report the % of inputs where they decide the same way. This avoids brittle text matching.
- **Citation accuracy:** % of rules linked to the correct source sentence.
- **Issue detection:** recall and precision per issue type.
- Every number is reported for each model (regex baseline, Qwen2.5-1.5B, Qwen2.5-3B …).

## Models

Same backend interface as Shadow Eval: `local` (Hugging Face transformers on CPU, the default),
`ollama`, `hf`, `claude`. The default local model will be picked from the benchmark results.
Small models are honestly limited: the review UI and the validation step exist for that reason.

## Tech

Python 3.11+, Pydantic, Typer, FastAPI, Jinja2, pypdf, PyYAML; torch + transformers as an
optional extra. Tests run offline with stubbed models.

## Milestones

1. Ingest, schema and spec model, safe expression evaluator, compiler
2. Synthetic loan-SOP benchmark generator (ground truth + planted issues)
3. Analysis engine (contradictions, gaps, boundaries, vague terms) + test generator
4. Regex baseline and LLM extraction with citation validation
5. Exports: discovery report and the Shadow Eval domain YAML
6. Review web UI
7. Benchmark across models, README with real results, push
