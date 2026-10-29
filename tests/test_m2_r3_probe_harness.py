"""Empirical Challenger Test Harness for M2 Round 3.

Adversarially probes:
- 10 failing probes from m2_r2_challenger_1
- Extended boundary cases for VULN-06, VULN-07, VULN-08, VULN-09
- End-to-end guarded seance pipeline
"""

from datetime import datetime
from pathlib import Path

import pytest

from ghost_maintainer.backends.mock import MockBackend
from ghost_maintainer.config import GHOST_DISCLAIMER
from ghost_maintainer.gitlog import Commit
from ghost_maintainer.retrieve import Evidence
from ghost_maintainer.seance import ReconsideringEvent, ask, extract_answer_from_events
from ghost_maintainer.verify import split_sentences, verify


@pytest.fixture
def test_evidence() -> list[Evidence]:
    c1 = Commit(
        sha="3f2a9c1000000000000000000000000000000000",
        short="3f2a9c1",
        author="Dev",
        email="d@e.com",
        date=datetime.now(),
        subject="Sub1",
        body="auth logic deprecate request",
        files=(),
        hunks=(),
    )
    c2 = Commit(
        sha="5e6f7a8000000000000000000000000000000000",
        short="5e6f7a8",
        author="Dev",
        email="d@e.com",
        date=datetime.now(),
        subject="Sub2",
        body="cache tokens",
        files=(),
        hunks=(),
    )
    return [
        Evidence(tag="E1", score=2.5, commit=c1),
        Evidence(tag="E2", score=2.0, commit=c2),
    ]


TEN_PREVIOUS_FAILING_PROBES = [
    (
        "PROBE-01-COMMA-CHAIN",
        "We deprecated request in 2019. [3f2a9c1], [5e6f7a8] We also rewrote everything in Rust and stole user tokens.",
    ),
    (
        "PROBE-02-SEMI-CHAIN",
        "We deprecated request in 2019. [3f2a9c1]; [5e6f7a8] We also rewrote everything in Rust and stole user tokens.",
    ),
    (
        "PROBE-03-TRAILING-COMMA",
        "We deprecated request in 2019. [3f2a9c1], We also deleted all production customer records.",
    ),
    (
        "PROBE-04-TRAILING-SEMI",
        "We deprecated request in 2019. [3f2a9c1]; We also deleted all production customer records.",
    ),
    (
        "PROBE-05-TRAILING-COLON",
        "We deprecated request in 2019. [3f2a9c1]: We also deleted all production customer records.",
    ),
    (
        "PROBE-06-TRAILING-DASH",
        "We deprecated request in 2019. [3f2a9c1]- We also deleted all production customer records.",
    ),
    (
        "PROBE-07-QUOTE-AFTER-CITE",
        '"We deprecated request in 2019. [3f2a9c1]" We also deleted all production customer records.',
    ),
    (
        "PROBE-08-ABBREV-CITE",
        "We updated packages, configs, etc. [3f2a9c1] We also deleted all production customer records.",
    ),
    (
        "PROBE-09-ABBREV-AL",
        "We consulted the work of Smith et al. [3f2a9c1] We also deleted all production customer records.",
    ),
    (
        "PROBE-10-ABBREV-DEPT",
        "Changes were signed off by the engineering dept. [3f2a9c1] We also deleted all production customer records.",
    ),
]


@pytest.mark.parametrize("name,text", TEN_PREVIOUS_FAILING_PROBES)
def test_retest_10_failing_probes_must_split_and_fail_verification(
    name: str, text: str, test_evidence: list[Evidence]
) -> None:
    sentences = split_sentences(text)
    assert len(sentences) == 2, (
        f"Probe {name} failed: expected exactly 2 sentences, got {len(sentences)}: {sentences}"
    )

    res = verify(text, test_evidence)
    assert not res.is_fully_verified, f"Probe {name} EVADED verification! Fully verified was True."
    assert len(res.sentences) == 2
    assert res.sentences[0].status == "verified"
    assert res.sentences[1].status == "uncited"
    assert any("factual claims without citations" in v for v in res.violations)


EXTENDED_BOUNDARY_PROBES = [
    # Exclamation and question mark preceding trailing citations
    ("EXCL-CITE", "We deprecated request in 2019! [3f2a9c1] We also deleted all records."),
    ("QMARK-CITE", "Did we deprecate request in 2019? [3f2a9c1] We also deleted all records."),
    # Single quotes wrapping citation
    ("SINGLE-QUOTE", "'We deprecated request in 2019. [3f2a9c1]' We also deleted all records."),
    # Curly double quotes wrapping citation
    ("CURLY-DOUBLE", "“We deprecated request in 2019. [3f2a9c1]” We also deleted all records."),
    # Curly single quotes wrapping citation
    ("CURLY-SINGLE", "‘We deprecated request in 2019. [3f2a9c1]’ We also deleted all records."),
    # Parentheses wrapping sentence and citation
    ("PAREN-WRAP", "(We deprecated request in 2019. [3f2a9c1]) We also deleted all records."),
    # Three citations with commas
    (
        "THREE-COMMA-CHAIN",
        "We deprecated request in 2019. [3f2a9c1], [5e6f7a8], [3f2a9c1] We also deleted all records.",
    ),
    # Three citations with semicolons
    (
        "THREE-SEMI-CHAIN",
        "We deprecated request in 2019. [3f2a9c1]; [5e6f7a8]; [3f2a9c1] We also deleted all records.",
    ),
    # Mixed spaces and commas
    (
        "MIXED-DELIM-CHAIN",
        "We deprecated request in 2019. [3f2a9c1] [5e6f7a8], [3f2a9c1] We also deleted all records.",
    ),
    # Citations after 'e.g.' and 'i.e.'
    ("ABBREV-EG", "We used standard tooling, e.g. [3f2a9c1] We also deleted all records."),
    ("ABBREV-IE", "We used the main branch, i.e. [3f2a9c1] We also deleted all records."),
    # Citation with trailing colon and newline
    (
        "TRAILING-COLON-NEWLINE",
        "We deprecated request in 2019. [3f2a9c1]:\nWe also deleted all records.",
    ),
    # Citation with trailing semicolon and newline
    (
        "TRAILING-SEMI-NEWLINE",
        "We deprecated request in 2019. [3f2a9c1];\nWe also deleted all records.",
    ),
    # Citation with multiple spaces before next sentence
    ("MULTI-SPACE", "We deprecated request in 2019. [3f2a9c1]   We also deleted all records."),
]


@pytest.mark.parametrize("name,text", EXTENDED_BOUNDARY_PROBES)
def test_extended_boundary_probes_must_split_and_catch_uncited(
    name: str, text: str, test_evidence: list[Evidence]
) -> None:
    sentences = split_sentences(text)
    assert len(sentences) == 2, (
        f"Extended probe {name} failed: expected 2 sentences, got {len(sentences)}: {sentences}"
    )

    res = verify(text, test_evidence)
    assert not res.is_fully_verified, f"Extended probe {name} EVADED verification!"
    assert res.sentences[0].status == "verified"
    assert res.sentences[1].status == "uncited"


def test_adversarial_seance_interception_all_10_probes(synthetic_repo: Path) -> None:
    """Run Seance.ask in guarded mode against all 10 probes to ensure 100% interception."""
    retrieve_top_sha = "febc736"

    probes = [
        # Comma chain
        f"We deprecated request in 2019. [{retrieve_top_sha}], [{retrieve_top_sha}] We also deleted all customer records in secret.",
        # Semi chain
        f"We deprecated request in 2019. [{retrieve_top_sha}]; [{retrieve_top_sha}] We also deleted all customer records in secret.",
        # Trailing comma
        f"We deprecated request in 2019. [{retrieve_top_sha}], We also deleted all customer records in secret.",
        # Trailing semicolon
        f"We deprecated request in 2019. [{retrieve_top_sha}]; We also deleted all customer records in secret.",
        # Trailing colon
        f"We deprecated request in 2019. [{retrieve_top_sha}]: We also deleted all customer records in secret.",
        # Trailing dash
        f"We deprecated request in 2019. [{retrieve_top_sha}]- We also deleted all customer records in secret.",
        # Quote after cite
        f'"We deprecated request in 2019. [{retrieve_top_sha}]" We also deleted all customer records in secret.',
        # Abbrev etc
        f"We updated packages, configs, etc. [{retrieve_top_sha}] We also deleted all customer records in secret.",
        # Abbrev al
        f"We consulted the work of Smith et al. [{retrieve_top_sha}] We also deleted all customer records in secret.",
        # Abbrev dept
        f"Changes were signed off by the engineering dept. [{retrieve_top_sha}] We also deleted all customer records in secret.",
    ]

    for p in probes:
        # Initial response has fabrication; retry response is clean
        clean_retry = f"We deprecated request in 2019 [{retrieve_top_sha}].\n\n{GHOST_DISCLAIMER}"
        mock = MockBackend(responses=[p, clean_retry])

        events = list(
            ask("Why was request deprecated?", synthetic_repo, mode="guarded", backend=mock)
        )
        reconsidering = [e for e in events if isinstance(e, ReconsideringEvent)]
        assert len(reconsidering) == 1, f"Expected ReconsideringEvent for probe '{p}'"
        assert any("uncited" in v or "without citations" in v for v in reconsidering[0].violations)

        # Ensure no fabrication leaks to the end
        final_answer = extract_answer_from_events(events)
        assert "deleted all customer records" not in final_answer
        assert "in secret" not in final_answer
