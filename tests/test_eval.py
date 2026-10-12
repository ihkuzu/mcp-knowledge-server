from mcpkb.config import ROOT
from mcpkb.docs import DocIndex
from mcpkb.evaluate import evaluate


def test_eval_report_shape_and_keyword_quality():
    report = evaluate(DocIndex(ROOT / "data" / "docs"), ROOT / "data" / "eval" / "questions.json", min_score=5.0)
    groups = report["groups"]
    assert groups["keyword"]["n"] == 24 and groups["paraphrase"]["n"] == 16 and groups["unanswerable"]["n"] == 8
    # a guard against regressions in tokenizing or scoring
    assert groups["keyword"]["hit@1"] >= 0.9
