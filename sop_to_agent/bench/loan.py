"""Synthetic loan-approval SOPs with known ground truth and planted issues.

Each variant renders the same true rule set in different wording (some easy for
pattern matching, some paraphrased), plus deliberately planted problems:
contradictions, boundary mismatches, vague terms, gaps and unreachable rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..ingest import Document, split_document
from ..spec import Citation, Comparison, Condition, InputField, Rule, Spec

INPUTS = [
    InputField(name="credit_score", type="integer", minimum=300, maximum=850,
               description="Applicant's credit (FICO) score", aliases=["credit score", "fico"]),
    InputField(name="dti_ratio", type="number", unit="%", minimum=0, maximum=100,
               description="Debt-to-income ratio in percent",
               aliases=["debt-to-income", "dti"]),
    InputField(name="loan_amount", type="number", unit="USD", minimum=1000, maximum=1000000,
               description="Requested loan amount in USD", aliases=["loan amount", "loans", "loan"]),
    InputField(name="employment_status", type="enum", values=["employed", "self_employed", "unemployed", "retired"],
               description="Current employment status", aliases=["employment"],
               value_aliases={"self_employed": ["self-employed", "self employed"], "unemployed": ["unemployed"],
                              "retired": ["retired"], "employed": ["employed"]}),
    InputField(name="years_employed", type="number", minimum=0, maximum=50,
               description="Years in current job or business",
               aliases=["years"]),
    InputField(name="has_bankruptcy", type="boolean", description="Any bankruptcy on record",
               value_aliases={"true": ["bankruptcy"]}),
    InputField(name="documents_complete", type="boolean", description="All required documents provided",
               value_aliases={"false": ["missing", "incomplete"]}),
]
OUTCOMES = ["approve", "decline", "refer", "request_documents"]
# Generic vocabulary an engineer would configure from the outcome names (not tuned to the benchmark wording).
OUTCOME_ALIASES = {
    "decline": ["cannot be approved", "not eligible", "ineligible", "declined", "decline", "rejected", "reject"],
    "request_documents": ["request documents", "request the documents"],
    "refer": ["referred", "refer", "manual review"],
    "approve": ["approved", "approve"],
}


def C(*comps: tuple, combine: str = "all") -> Condition:
    return Condition(combine=combine, comparisons=[Comparison(field=f, op=o, value=v) for f, o, v in comps])


@dataclass
class TrueRule:
    key: str
    condition: Condition
    outcome: str
    phrasings: tuple[str, str, str, str]
    priority: str = "normal"


TRUE_RULES = [
    TrueRule("docs", C(("documents_complete", "==", False)), "request_documents", (
        "If the application is missing required documents, request the documents from the applicant.",
        "Incomplete files must not be decided; ask the applicant for the outstanding paperwork first.",
        "When documentation is incomplete, request documents before any other review.",
        "Do not make a decision on a file until every required document has been received; chase the applicant for anything outstanding.")),
    TrueRule("bankruptcy", C(("has_bankruptcy", "==", True)), "decline", (
        "Applicants with a bankruptcy on record are declined.",
        "Any prior bankruptcy makes the applicant ineligible.",
        "Decline the application if the applicant has ever filed for bankruptcy.",
        "A history of bankruptcy rules the applicant out.")),
    TrueRule("score_low", C(("credit_score", "<", 580)), "decline", (
        "If the credit score is below 580, decline the application.",
        "Applicants whose FICO score falls short of 580 are not eligible.",
        "A credit score under 580 results in a decline.",
        "We turn away anyone scoring lower than 580 with the credit bureau.")),
    TrueRule("dti", C(("dti_ratio", ">", 45)), "decline", (
        "If the debt-to-income ratio exceeds 45%, decline the application.",
        "We do not lend when monthly debt payments take up more than 45% of income.",
        "A DTI above 45 percent is grounds for rejection.",
        "Where debts eat up more than 45% of monthly income, the answer is no.")),
    TrueRule("unemployed", C(("employment_status", "==", "unemployed")), "decline", (
        "Unemployed applicants are declined.",
        "Applicants without current employment cannot be approved.",
        "Decline applicants who are unemployed.",
        "People who are out of work are turned down.")),
    TrueRule("amount", C(("loan_amount", ">", 250000)), "refer", (
        "Loans over $250,000 are referred to a senior underwriter.",
        "Any request above $250,000 needs sign-off from a senior underwriter.",
        "Refer the application if the loan amount is more than $250,000.",
        "Requests north of $250,000 are escalated to a senior underwriter.")),
    TrueRule("self_employed", C(("employment_status", "==", "self_employed"), ("years_employed", "<", 2)), "refer", (
        "If the applicant is self-employed with less than 2 years in business, refer the application.",
        "Self-employed applicants trading for under two years go to manual review.",
        "Refer self-employed applicants with fewer than 2 years of history.",
        "Business owners with under 2 years of trading history go to an underwriter.")),
    TrueRule("score_mid", C(("credit_score", "<", 660)), "refer", (
        "If the credit score is below 660, refer the application for manual review.",
        "Scores between 580 and 659 are handled by an underwriter rather than automatically.",
        "Refer applicants with a credit score under 660.",
        "Bureau scores from 580 up to 659 need an underwriter's sign-off.")),
    TrueRule("default", C(), "approve", (
        "All other applications are approved.",
        "Otherwise, approve the application.",
        "Applications that pass every check above are approved.",
        "Everyone else gets approved."), priority="default"),
]

SECTIONS = [  # (heading, rule keys, filler sentences)
    ("1. Purpose", [], ["This procedure applies to unsecured personal loans up to $1,000,000.",
                        "It is used by the lending operations team."]),
    ("2. Document checks", ["docs"], ["Required documents are listed in the application checklist."]),
    ("3. Eligibility", ["bankruptcy", "score_low", "dti", "unemployed"], []),
    ("4. Referral rules", ["amount", "self_employed", "score_mid"], ["Referred applications are reviewed within two business days."]),
    ("5. Final decision", ["default"], ["Every decision is recorded in the loan system."]),
]

PLANTS = {
    "contradiction": ("FAQ", "Applicants with a credit score of 700 or higher are approved."),
    "boundary_mismatch": ("FAQ", "Loans of $250,000 or more require senior underwriter review."),
    "vague_unstable": ("4. Referral rules", "Applicants with unstable income should be treated with caution."),
    "vague_highrisk": ("4. Referral rules", "High-risk applicants must be referred."),
    "unreachable": ("3. Eligibility", "Applicants with a credit score below 500 are declined."),
}
PLANT_KIND = {"contradiction": "contradiction", "boundary_mismatch": "boundary_mismatch",
              "vague_unstable": "vague_term", "vague_highrisk": "vague_term", "unreachable": "unreachable_rule"}

VARIANTS = {
    # name: (phrasing index, planted issues, include default rule?)
    "loan_sop_a": (0, ["contradiction", "vague_unstable"], True),
    "loan_sop_b": (1, ["boundary_mismatch", "vague_highrisk"], False),  # no default rule: planted gap
    "loan_sop_c": (2, ["unreachable", "contradiction", "boundary_mismatch"], True),
    "loan_sop_d": (3, ["contradiction", "boundary_mismatch", "vague_highrisk"], True),  # held-out conversational wording
}


@dataclass
class PlantedIssue:
    kind: str  # contradiction | boundary_mismatch | vague_term | unreachable_rule | gap
    sentence_id: str | None
    text: str


@dataclass
class Variant:
    name: str
    markdown: str
    document: Document
    truth: Spec  # true rules only, with citations
    planted: list[PlantedIssue] = field(default_factory=list)


def base_spec(name: str = "loan_approval") -> Spec:
    return Spec(name=name, decision="decision", outcomes=list(OUTCOMES), inputs=[i.model_copy(deep=True) for i in INPUTS],
                outcome_aliases={k: list(v) for k, v in OUTCOME_ALIASES.items()})


def build_variant(name: str) -> Variant:
    idx, plants, with_default = VARIANTS[name]
    rules = {r.key: r for r in TRUE_RULES}
    lines = ["# Northwind Bank: Personal Loan Approval Procedure (fictional)", ""]
    by_section: dict[str, list[str]] = {}
    for p in plants:
        sec, text = PLANTS[p]
        by_section.setdefault(sec, []).append(text)
    used: list[tuple[str, str]] = []  # (rule key, sentence text)
    for heading, keys, filler in SECTIONS:
        lines += [f"## {heading}", ""]
        body = list(filler)
        for k in keys:
            if k == "default" and not with_default:
                continue
            body.append(rules[k].phrasings[idx])
            used.append((k, rules[k].phrasings[idx]))
        if heading == "3. Eligibility" and "unreachable" in plants:
            body.append(PLANTS["unreachable"][1])
        body += [t for t in by_section.get(heading, []) if t != PLANTS["unreachable"][1]]
        lines += [f"- {s}" for s in body] + [""]
    if by_section.get("FAQ"):
        lines += ["## FAQ", ""] + [f"- {s}" for s in by_section["FAQ"]] + [""]
    md = "\n".join(lines)
    doc = split_document(name, md)
    sid = {s.text: s for s in doc.sentences}
    truth = base_spec(name)
    truth.documents = [name]
    for k, text in used:
        tr, s = rules[k], sid[text]
        truth.rules.append(Rule(id=f"T-{k}", condition=tr.condition, outcome=tr.outcome, priority=tr.priority, source="truth",
                                citation=Citation(doc=name, sentence_id=s.id, quote=s.text, section=s.section)))
    planted = [PlantedIssue(PLANT_KIND[p], sid[PLANTS[p][1]].id, PLANTS[p][1]) for p in plants]
    if not with_default:
        planted.append(PlantedIssue("gap", None, "No rule covers applicants who pass every check (default rule missing)."))
    return Variant(name, md, doc, truth, planted)


def all_variants() -> list[Variant]:
    return [build_variant(n) for n in VARIANTS]
