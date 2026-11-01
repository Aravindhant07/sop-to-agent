"""Analysis must find planted issues and stay quiet otherwise."""

from sop_to_agent.analyze import analyze
from sop_to_agent.bench.loan import C, PLANTS, build_variant
from sop_to_agent.spec import Citation, Rule
from sop_to_agent.testgen import generate_tests

PLANT_RULES = {  # what a perfect extractor returns for planted rule sentences
    PLANTS["contradiction"][1]: (C(("credit_score", ">=", 700)), "approve"),
    PLANTS["boundary_mismatch"][1]: (C(("loan_amount", ">=", 250000)), "refer"),
    PLANTS["unreachable"][1]: (C(("credit_score", "<", 500)), "decline"),
}


def perfect_spec(name):
    v = build_variant(name)
    spec = v.truth.model_copy(deep=True)
    by_text = {s.text: s for s in v.document.sentences}
    for text, (cond, outcome) in PLANT_RULES.items():
        if text in by_text:
            s = by_text[text]
            spec.rules.append(Rule(id="P" + s.id.split(":")[1], condition=cond, outcome=outcome,
                                   citation=Citation(doc=name, sentence_id=s.id, quote=text, section=s.section)))
    order = {s.id: i for i, s in enumerate(v.document.sentences)}
    spec.rules.sort(key=lambda r: (r.priority == "default", order[r.citation.sentence_id]))
    return v, spec


def matches(issue, planted):
    return issue.kind == planted.kind and (planted.sentence_id is None or planted.sentence_id in issue.sentence_ids)


def test_perfect_extraction_finds_exactly_the_planted_issues():
    for name in ("loan_sop_a", "loan_sop_b", "loan_sop_c", "loan_sop_d"):
        v, spec = perfect_spec(name)
        issues = analyze(spec, [v.document])
        for p in v.planted:
            assert any(matches(i, p) for i in issues), f"{name}: missed {p.kind}"
        for i in issues:
            assert any(matches(i, p) for p in v.planted), f"{name}: false alarm {i.kind}: {i.title}"


def test_clean_procedure_has_no_issues():
    v = build_variant("loan_sop_a")
    spec = v.truth.model_copy(deep=True)  # true rules only, no planted sentences
    assert [i.kind for i in analyze(spec, [])] == []


def test_same_condition_different_outcome_is_a_contradiction():
    v = build_variant("loan_sop_a")
    spec = v.truth.model_copy(deep=True)
    r = spec.rules[2].model_copy(deep=True)
    r.id, r.outcome = "DUP", "approve"
    spec.rules.insert(3, r)
    assert any(i.kind == "contradiction" and "DUP" in i.rule_ids for i in analyze(spec, []))


def test_tests_cover_every_reachable_rule_and_flag_open_issues():
    v, spec = perfect_spec("loan_sop_b")
    issues = analyze(spec, [v.document])
    tests = generate_tests(spec, issues)
    covered = {t.rule_id for t in tests if t.kind == "rule"}
    assert {r.id for r in spec.rules} <= covered
    assert any(t.depends_on for t in tests)  # gap and boundary cases are flagged
    assert any(t.expected is None for t in tests)  # the gap shows up as "no rule"
