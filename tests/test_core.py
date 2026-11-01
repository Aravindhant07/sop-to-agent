import pytest

from sop_to_agent.engine import Engine
from sop_to_agent.expr import compare, holds, normalize, validate_condition
from sop_to_agent.ingest import split_document
from sop_to_agent.spec import Comparison, Condition, Rule, Spec

from sop_to_agent.bench.loan import C, base_spec


def test_sentence_split_keeps_offsets_and_sections():
    text = "# Rules\n\nLoans over $250,000 are referred, e.g. to an underwriter. Scores below 580 are declined.\n- If DTI exceeds 45%, decline.\n"
    d = split_document("t", text)
    assert [s.text for s in d.sentences] == [
        "Loans over $250,000 are referred, e.g. to an underwriter.", "Scores below 580 are declined.", "If DTI exceeds 45%, decline."]
    for s in d.sentences:
        assert text[s.start:s.end].strip() == s.text and s.section == "Rules"


def test_compare_ops():
    assert compare(Comparison(field="x", op="<", value=5), {"x": 4})
    assert not compare(Comparison(field="x", op="<", value=5), {"x": 5})
    assert compare(Comparison(field="s", op="==", value="Self_Employed"), {"s": "self_employed"})
    assert compare(Comparison(field="b", op="==", value=True), {"b": True})
    assert compare(Comparison(field="s", op="in", value=["a", "b"]), {"s": "B"})
    assert not compare(Comparison(field="x", op=">", value=1), {})  # missing input never matches
    assert holds(Condition(), {})  # empty condition = always


def test_validation_and_normalization():
    spec = base_spec()
    bad = C(("nope", "<", 1), ("credit_score", "in", [1]), ("employment_status", "==", "astronaut"), ("has_bankruptcy", ">", 1))
    errs = validate_condition(bad, spec)
    assert len(errs) == 4
    good = normalize(C(("credit_score", "<", "580"), ("employment_status", "==", "SELF_EMPLOYED"), ("has_bankruptcy", "==", "yes")), spec)
    assert [c.value for c in good.comparisons] == [580.0, "self_employed", True]


def test_engine_order_override_normal_default():
    spec = Spec(name="t", outcomes=["a", "b", "c"], inputs=base_spec().inputs, rules=[
        Rule(id="D", condition=Condition(), outcome="c", priority="default"),
        Rule(id="N", condition=C(("credit_score", "<", 600)), outcome="b"),
        Rule(id="O", condition=C(("credit_score", "<", 500)), outcome="a", priority="override"),
        Rule(id="X", condition=C(("credit_score", "<", 900)), outcome="a", status="rejected"),
    ])
    e = Engine(spec)
    assert e.decide({"credit_score": 450}).rule.id == "O"
    assert e.decide({"credit_score": 550}).rule.id == "N"
    assert e.decide({"credit_score": 700}).rule.id == "D"


def test_spec_roundtrip(tmp_path):
    spec = base_spec()
    spec.rules.append(Rule(id="R1", condition=C(("credit_score", "<", 580)), outcome="decline"))
    spec.save(tmp_path / "s.yaml")
    assert Spec.load(tmp_path / "s.yaml") == spec


def test_enum_field_needs_values():
    with pytest.raises(ValueError):
        Spec(name="x", outcomes=["a"], inputs=[{"name": "e", "type": "enum"}])
