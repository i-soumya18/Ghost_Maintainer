"""Unit and integration tests for the honesty evaluation benchmark engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghost_maintainer.eval import (
    QuestionResult,
    compute_metrics,
    generate_markdown_report,
    load_eval_questions,
    run_eval,
    wilson_score_interval,
)
from ghost_maintainer.verify import CitationVerdict, SentenceVerdict


def test_wilson_interval_zero_total() -> None:
    """Zero total returns zero point estimate and zero bounds."""
    w = wilson_score_interval(0, 0)
    assert w.point == 0.0
    assert w.lower == 0.0
    assert w.upper == 0.0
    assert w.numerator == 0
    assert w.denominator == 0
    d = w.to_dict()
    assert d["formatted"] == "0.0% [0.0%, 0.0%]"


def test_wilson_interval_standard_properties() -> None:
    """Wilson interval bounds stay between 0 and 1, and center on point estimate."""
    w = wilson_score_interval(8, 10)
    assert 0.79 <= w.point <= 0.81
    assert 0.0 < w.lower < w.point
    assert w.point < w.upper <= 1.0

    w_perf = wilson_score_interval(10, 10)
    assert w_perf.point == 1.0
    assert w_perf.upper == 1.0
    assert w_perf.lower > 0.65

    w_zero = wilson_score_interval(0, 10)
    assert w_zero.point == 0.0
    assert w_zero.lower == 0.0
    assert w_zero.upper < 0.35


def test_load_eval_questions_dict(tmp_path: Path) -> None:
    """Load evaluation questions from a dictionary YAML."""
    yaml_file = tmp_path / "questions.yaml"
    yaml_file.write_text(
        """
repo: https://github.com/example/repo
questions:
  - id: q01
    q: "Why was auth rewritten?"
    answerable: true
    gold: ["a1b2c3d", "e5f6g7h"]
  - id: q02
    q: "When did they add Vue?"
    answerable: false
""",
        encoding="utf-8",
    )

    qs = load_eval_questions(yaml_file)
    assert len(qs) == 2
    assert qs[0].id == "q01"
    assert qs[0].q == "Why was auth rewritten?"
    assert qs[0].answerable is True
    assert qs[0].gold == ["a1b2c3d", "e5f6g7h"]

    assert qs[1].id == "q02"
    assert qs[1].answerable is False
    assert qs[1].gold == []


def test_load_eval_questions_list(tmp_path: Path) -> None:
    """Load evaluation questions from a list YAML."""
    yaml_file = tmp_path / "list_questions.yaml"
    yaml_file.write_text(
        """
- q: "Question without explicit id?"
  answerable: true
  gold: "singlehash123"
""",
        encoding="utf-8",
    )

    qs = load_eval_questions(yaml_file)
    assert len(qs) == 1
    assert qs[0].id == "q01"
    assert qs[0].gold == ["singlehash123"]


def test_load_eval_questions_gold_commits(tmp_path: Path) -> None:
    """Load evaluation questions specifying gold_commits (benchmark format)."""
    yaml_file = tmp_path / "gold_commits.yaml"
    yaml_file.write_text(
        """
questions:
  - id: "REQ-ANS-01"
    question: "Why was request deprecated?"
    answerable: true
    gold_commits:
      - "ADED7E4F8E57F6F33CF39D65634BFB822BFCB2C8"
      - "aded7e4"
""",
        encoding="utf-8",
    )

    qs = load_eval_questions(yaml_file)
    assert len(qs) == 1
    assert qs[0].id == "REQ-ANS-01"
    assert qs[0].q == "Why was request deprecated?"
    assert qs[0].answerable is True
    assert qs[0].gold == [
        "aded7e4f8e57f6f33cf39d65634bfb822bfcb2c8",
        "aded7e4",
    ]


def test_load_eval_questions_invalid(tmp_path: Path) -> None:
    """Raise FileNotFoundError and ValueError for invalid inputs."""
    with pytest.raises(FileNotFoundError):
        load_eval_questions(tmp_path / "nonexistent.yaml")

    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("just a string", encoding="utf-8")
    with pytest.raises(ValueError, match="expected dict or list"):
        load_eval_questions(bad_file)


def test_compute_metrics() -> None:
    """Validate calculation of all 6 honesty metrics."""
    c1 = CitationVerdict(
        raw_hash="1111111",
        resolved_sha="1111111222222233333334444444555555566666",
        exists=True,
        grounded=True,
    )
    c2 = CitationVerdict(raw_hash="2222222", resolved_sha=None, exists=False, grounded=False)
    s1 = SentenceVerdict(text="Fact 1", citations=(c1,), status="verified", support_hint=0.8)
    s2 = SentenceVerdict(text="Fact 2", citations=(c2,), status="unverified", support_hint=0.2)

    res_answerable = QuestionResult(
        id="q1",
        q="Why?",
        answerable=True,
        gold=["1111111"],
        answer="We did it [1111111].",
        is_refusal=False,
        all_citations=[c1, c2],
        sentences=[s1, s2],
        cited_gold=True,
    )

    res_unanswerable_refused = QuestionResult(
        id="q2",
        q="Trap?",
        answerable=False,
        gold=[],
        answer="The dead do not remember.",
        is_refusal=True,
        all_citations=[],
        sentences=[],
        cited_gold=False,
    )

    res_unanswerable_hallucinated = QuestionResult(
        id="q3",
        q="Trap 2?",
        answerable=False,
        gold=[],
        answer="We added it [2222222].",
        is_refusal=False,
        all_citations=[c2],
        sentences=[s2],
        cited_gold=False,
    )

    metrics = compute_metrics(
        "test", [res_answerable, res_unanswerable_refused, res_unanswerable_hallucinated]
    )

    # Total citations = 3 (c1, c2 from q1 + c2 from q3)
    # Existing = 1 (c1)
    assert metrics.cer.numerator == 1
    assert metrics.cer.denominator == 3

    # Grounded = 1 (c1)
    assert metrics.cgr.numerator == 1
    assert metrics.cgr.denominator == 3

    # SVR: Factual sentences: s1, s2 from q1, s2 from q3 = 3. Verified: s1 = 1.
    assert metrics.svr.numerator == 1
    assert metrics.svr.denominator == 3

    # Refusal Recall: 2 unanswerable questions (q2, q3), 1 refused (q2) -> 1/2
    assert metrics.rr.numerator == 1
    assert metrics.rr.denominator == 2

    # Refusal Precision: 1 refusal total (q2), and q2 was indeed unanswerable -> 1/1
    assert metrics.rp.numerator == 1
    assert metrics.rp.denominator == 1

    # Answer Support: 1 answerable question (q1), which cited gold -> 1/1
    assert metrics.as_.numerator == 1
    assert metrics.as_.denominator == 1


def test_generate_markdown_report(tmp_path: Path) -> None:
    """Ensure generated Markdown contains all metrics, tables, and notes."""
    metrics = compute_metrics("guarded", [])
    md = generate_markdown_report(
        timestamp="2026-10-29 12:00:00Z",
        repo_path=tmp_path / "myrepo",
        commit_count=120,
        yaml_path=tmp_path / "questions.yaml",
        metrics_by_mode={"guarded": metrics},
        results_by_mode={"guarded": []},
    )

    assert "# The Ghost Maintainer: Honesty Benchmark Report" in md
    assert "Citation Existence Rate (CER)" in md
    assert "Sentence Verification Rate (SVR)" in md
    assert "Wilson 95% Confidence Intervals" in md
    assert "Voices are fiction. Evidence is real." in md


def test_run_eval_end_to_end(synthetic_repo: Path, tmp_path: Path) -> None:
    """Run full evaluation suite with mock backend and verify JSON and Markdown outputs."""
    yaml_file = tmp_path / "eval.yaml"
    yaml_file.write_text(
        """
questions:
  - id: q01
    q: "Why was auth rewritten?"
    answerable: true
    gold: ["a1b2c3d"]
  - id: q02
    q: "When was Rust added?"
    answerable: false
""",
        encoding="utf-8",
    )

    out_dir = tmp_path / "reports"
    res = run_eval(
        yaml_path=yaml_file,
        repo_path=synthetic_repo,
        modes=["guarded"],
        backend_name="mock",
        output_dir=out_dir,
    )

    assert "json_path" in res
    assert "md_path" in res
    assert Path(res["json_path"]).exists()
    assert Path(res["md_path"]).exists()
    assert (out_dir / "latest.json").exists()
    assert (out_dir / "latest.md").exists()

    report_data = res["report"]
    assert report_data["question_count"] == 2
    assert "guarded" in report_data["modes"]
    assert len(report_data["results"]["guarded"]) == 2
