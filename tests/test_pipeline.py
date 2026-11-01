import json

import yaml
from fastapi.testclient import TestClient

from sop_to_agent.bench.loan import base_spec, build_variant
from sop_to_agent.bench.run import run_benchmark
from sop_to_agent.export import write_outputs
from sop_to_agent.extract.llm import LLMExtractor, answer_schema, system_prompt
from sop_to_agent.extract.regex import RegexExtractor
from sop_to_agent.llm import LLMResult
from sop_to_agent.pipeline import compile_documents
from sop_to_agent.web.app import create_app, parse_comparisons


def test_regex_baseline_benchmark_is_reproducible():
    s = run_benchmark(RegexExtractor())
    by = {v["variant"]: v for v in s["variants"]}
    assert by["loan_sop_a"]["rule_recall"] >= 0.85  # plain wording
    assert by["loan_sop_d"]["rule_recall"] <= 0.2  # held-out conversational wording defeats patterns
    assert s["false_rules"] == 0


class ScriptedLLM:
    """Stands in for a model: answers from a lookup of sentence → JSON."""

    name = "scripted"

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def complete(self, system, user, schema):
        self.calls.append(user)
        sentence = user.removeprefix("Sentence: ").removesuffix("\nJSON:")
        return LLMResult(self.answers.get(sentence, {"is_rule": False, "outcome": "", "priority": "normal", "combine": "all", "comparisons": []}), "m", 10, 5)


def test_llm_extractor_validates_and_cites():
    v = build_variant("loan_sop_d")
    s = {x.text: x for x in v.document.sentences}
    answers = {
        "A history of bankruptcy rules the applicant out.":
            {"is_rule": True, "outcome": "decline", "priority": "normal", "combine": "all",
             "comparisons": [{"field": "has_bankruptcy", "op": "==", "value": "true"}]},
        "Requests north of $250,000 are escalated to a senior underwriter.":
            {"is_rule": True, "outcome": "refer", "priority": "normal", "combine": "all",
             "comparisons": [{"field": "loan_amount", "op": ">", "value": "$250,000"}]},
        "People who are out of work are turned down.":  # invalid enum value → rejected, not accepted
            {"is_rule": True, "outcome": "decline", "priority": "normal", "combine": "all",
             "comparisons": [{"field": "employment_status", "op": "==", "value": "jobless"}]},
        "Everyone else gets approved.":
            {"is_rule": True, "outcome": "approve", "priority": "default", "combine": "all", "comparisons": []},
    }
    llm = ScriptedLLM(answers)
    res = compile_documents(base_spec(), [v.document], LLMExtractor(llm))
    got = {r.citation.quote: r for r in res.spec.rules}
    assert got["Requests north of $250,000 are escalated to a senior underwriter."].condition.comparisons[0].value == 250000.0
    assert got["A history of bankruptcy rules the applicant out."].condition.comparisons[0].value is True
    assert got["Everyone else gets approved."].priority == "default"
    assert any("jobless" in x["reason"] for x in res.rejected)
    assert all(r.citation.sentence_id == s[r.citation.quote].id for r in res.spec.rules)  # citation set by code
    assert res.stats["input_tokens"] > 0


def test_prompt_and_schema_use_spec():
    spec = base_spec()
    p = system_prompt(spec)
    assert "credit_score" in p and "request_documents" in p and "Examples" in p
    assert answer_schema(spec)["properties"]["comparisons"]["items"]["properties"]["field"]["enum"][0] == "credit_score"


def test_outputs_and_shadow_eval_export(tmp_path):
    v = build_variant("loan_sop_c")
    res = compile_documents(base_spec(), [v.document], RegexExtractor())
    out = write_outputs(res, [v.document], tmp_path / "out")
    for f in ("spec.yaml", "issues.json", "tests.jsonl", "report.html", "report.md", "shadow_eval_domain.yaml"):
        assert (out / f).exists(), f
    dom = yaml.safe_load((out / "shadow_eval_domain.yaml").read_text())
    assert dom["decision"][0]["values"] == base_spec().outcomes and dom["primary_field"] == "decision"
    assert any(s["field"] == "employment_status" for s in dom["segments"])
    assert any(c["critical"] for c in dom["cost_matrix"])
    assert "Questions for the customer" in (out / "report.md").read_text()
    assert len((out / "tests.jsonl").read_text().splitlines()) == len(res.tests)
    assert json.loads((out / "issues.json").read_text())


def test_review_ui_edit_recomputes(tmp_path):
    v = build_variant("loan_sop_c")
    res = compile_documents(base_spec(), [v.document], RegexExtractor())
    write_outputs(res, [v.document], tmp_path / "ws")
    c = TestClient(create_app(tmp_path / "ws"))
    page = c.get("/")
    assert page.status_code == 200 and "Issues to raise" in page.text
    faq = next(r for r in res.spec.rules if r.citation.section == "FAQ" and r.outcome == "approve")
    assert c.get(f"/rules/{faq.id}").status_code == 200
    assert c.get("/documents/loan_sop_c").status_code == 200
    # Rejecting the FAQ rule removes the contradiction.
    r = c.post(f"/rules/{faq.id}", data={"status": "rejected", "outcome": "approve", "priority": "normal",
                                         "combine": "all", "comparisons": "credit_score >= 700"}, follow_redirects=False)
    assert r.status_code == 303
    assert "contradiction" not in c.get("/").text.split("Rules (in decision order)")[0]
    # Bad edits are refused with a message.
    bad = c.post(f"/rules/{faq.id}", data={"status": "accepted", "outcome": "approve", "comparisons": "nope >= 1"}, follow_redirects=False)
    assert "error=" in bad.headers["location"]
    assert parse_comparisons("credit_score < 580\nhas_bankruptcy == true")[1].value is True
