# Requirements: SOP-to-Agent Compiler

## Users

| User | Needs |
|---|---|
| **FDE** | Turn customer documents into a correct, testable agent in days, not weeks |
| **Customer process owner** | See exactly which rule the agent follows and why; answer clear questions about gaps |
| **Reviewer / compliance** | Every rule traceable to the source document |

## Functional requirements (proposed)

| ID | Requirement |
|---|---|
| R1 | Accept documents as Markdown, plain text or PDF; multiple documents per process |
| R2 | Extract the decision(s), inputs (with types) and outcomes |
| R3 | Extract rules in order, each with **a citation to the source span** (document + quoted text) |
| R4 | Detect ambiguities (undefined terms, vague thresholds), contradictions between rules or documents, and missing cases (input combinations no rule covers) |
| R5 | Produce a discovery report: issues ranked by impact, phrased as customer questions |
| R6 | Generate a test set: typical cases, boundary cases for every threshold, and one case per rule |
| R7 | Compile the spec into an executable rule engine, so tests have checkable expected outcomes |
| R8 | Export a Shadow Eval domain YAML (decision schema, segments, policy text) |
| R9 | Human-in-the-loop: the engineer can edit the spec and recompile |
| R10 | Benchmark: synthetic SOPs with known rules and planted issues, to measure R3–R4 accuracy |

## Models

- **Default: free, open-source models**, run locally (Hugging Face `transformers` or Ollama).
- Claude is optional, through the same backend interface used in Shadow Eval.

## Out of scope (v1)

- Running the agent in production
- Scanned or handwritten documents (OCR)
- Multi-language documents

## Confirmed decisions

| Question | Decision |
|---|---|
| First domain | **Loan approval** |
| Interface | **CLI + review web page** |
| Default models | **Free local open models from Hugging Face** (transformers); Ollama and Claude optional |
