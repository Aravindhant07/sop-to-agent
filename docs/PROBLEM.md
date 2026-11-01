# Problem Statement: SOP-to-Agent Compiler

## Context

When a Forward Deployed Engineer starts at a customer, the first weeks go into
**discovery**: reading the customer's standard operating procedures (SOPs), policy
PDFs and call transcripts, interviewing experts, and turning all of it into an agent
that follows the process correctly.

Today that work is manual and slow, and it goes wrong in predictable ways:

| What happens today | What goes wrong |
|---|---|
| The engineer reads a 40-page SOP and writes a prompt | Rules get missed or paraphrased wrongly; nobody can trace a decision back to the SOP |
| Gaps and contradictions in the SOP are found in production | "What if the customer has two policies?" Nobody asked, so the agent guesses |
| Test cases are written by hand, late, and few | The agent ships with no evidence it follows the process |
| Each customer starts from a blank page | The same discovery work is repeated every engagement |

## The gap

The open-source projects we found each do one piece. One converts SOP text into a
workflow spec (small dataset, simulated executors), and others generate evaluation
test sets. **None goes end to end** from messy customer documents to:

- an agent spec where every rule is traceable to the source,
- a list of gaps and contradictions to raise with the customer,
- and a test set that proves the agent follows the process.

## What we build

An open-source compiler that takes a customer's process documents and produces:

1. **A decision spec:** the decisions, inputs, rules and their order, each rule
   linked to the exact sentence of the SOP it came from.
2. **A discovery report:** ambiguities, contradictions and missing cases, written
   as questions the engineer can put to the customer.
3. **A test set:** cases with expected outcomes, including edge cases at every rule
   boundary.
4. **A ready-to-use Shadow Eval domain file**, so the agent can go straight into
   shadow mode with project 1.

## Why it fits the portfolio

Project 2 *understands* the customer's process, and project 1 *proves* the agent is
ready to go live. Together they cover the FDE journey from discovery to go-live.

## Success criteria (proposed)

- On benchmark SOPs with known rules, the compiler recovers ≥ 90% of the rules,
  each with a correct link to the source text.
- It finds ≥ 80% of deliberately planted ambiguities and contradictions.
- Generated tests catch a deliberately broken agent.
- The default path runs free, on open-source models.
