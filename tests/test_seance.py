"""Hermetic unit and integration tests for Seance orchestrator and honesty pipeline."""

from __future__ import annotations

from pathlib import Path

from ghost_maintainer.backends import MockBackend, MockMode
from ghost_maintainer.config import GHOST_DISCLAIMER, GHOST_REFUSAL_MESSAGE
from ghost_maintainer.retrieve import Evidence, retrieve
from ghost_maintainer.seance import (
    DoneEvent,
    ErrorEvent,
    EvidenceEvent,
    ReconsideringEvent,
    Seance,
    TokenEvent,
    VerdictEvent,
    ask,
    extract_answer_from_events,
)
from ghost_maintainer.verify import CitationVerdict, SentenceVerdict, VerificationResult


def test_seance_stage1_gate_refusal(synthetic_repo: Path) -> None:
    """Verify Stage 1 retrieval gate short-circuits on low-relevance query."""
    mock = MockBackend(mode=MockMode.HONEST)
    seance = Seance(backend=mock)
    events = list(
        seance.ask(
            "Why did the maintainers migrate to Haskell?",
            synthetic_repo,
            min_score=100.0,  # Unattainable threshold
        )
    )

    assert len(events) == 3
    assert isinstance(events[0], EvidenceEvent)
    assert isinstance(events[1], TokenEvent)
    assert events[1].token == GHOST_REFUSAL_MESSAGE
    assert isinstance(events[2], DoneEvent)
    assert events[2].retries == 0

    # Backend was never invoked
    assert mock.call_count == 0


def test_seance_stage1_empty_repo(empty_repo: Path) -> None:
    """Verify Stage 1 retrieval gate immediately refuses on empty repository."""
    mock = MockBackend(mode=MockMode.HONEST)
    events = list(
        ask(
            "What happened to the project?",
            empty_repo,
            backend=mock,
        )
    )

    assert any(isinstance(ev, TokenEvent) and ev.token == GHOST_REFUSAL_MESSAGE for ev in events)
    assert mock.call_count == 0


def test_seance_raw_mode_honest(synthetic_repo: Path) -> None:
    """Verify raw mode yields unmutated generation stream and verdict."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    mock = MockBackend(mode=MockMode.HONEST, default_hash=top_sha)
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="raw",
            backend=mock,
        )
    )

    types = [type(ev) for ev in events]
    assert EvidenceEvent in types
    assert TokenEvent in types
    assert VerdictEvent in types
    assert DoneEvent in types
    assert ReconsideringEvent not in types

    answer = extract_answer_from_events(events)
    assert f"[{top_sha}]" in answer

    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert verdict_ev.verdict.is_fully_verified is True

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.mode == "raw"
    assert done_ev.retries == 0


def test_seance_raw_mode_hallucinate(synthetic_repo: Path) -> None:
    """Verify raw mode permits hallucinated output without retry or repair."""
    mock = MockBackend(mode=MockMode.HALLUCINATE, fake_hash="deadbeef01")
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="raw",
            backend=mock,
        )
    )

    assert not any(isinstance(ev, ReconsideringEvent) for ev in events)
    answer = extract_answer_from_events(events)
    assert "[deadbeef01]" in answer

    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert verdict_ev.verdict.is_fully_verified is False

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 0


def test_seance_guarded_mode_clean(synthetic_repo: Path) -> None:
    """Verify clean response in guarded mode receives appended disclaimer."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    mock = MockBackend(mode=MockMode.HONEST, default_hash=top_sha)
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    assert not any(isinstance(ev, ReconsideringEvent) for ev in events)
    answer = extract_answer_from_events(events)
    assert f"[{top_sha}]" in answer
    assert GHOST_DISCLAIMER in answer

    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert verdict_ev.verdict.is_fully_verified is True

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 0


def test_seance_guarded_mode_retry_repair(synthetic_repo: Path) -> None:
    """Verify retry remediation when Pass 1 contains hallucinated hash."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    mock = MockBackend(
        mode=MockMode.RETRY_REPAIR,
        fake_hash="deadbeef01",
        default_hash=top_sha,
    )

    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    # ReconsideringEvent was emitted
    reconsidering_events = [ev for ev in events if isinstance(ev, ReconsideringEvent)]
    assert len(reconsidering_events) == 1
    assert any("deadbeef01" in v for v in reconsidering_events[0].violations)

    # Backend was invoked twice
    assert mock.call_count == 2

    # Final answer extracted cleanly discards pre-retry tokens
    answer = extract_answer_from_events(events)
    assert "[deadbeef01]" not in answer
    assert f"[{top_sha}]" in answer
    assert GHOST_DISCLAIMER in answer

    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert verdict_ev.verdict.is_fully_verified is True

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 1


def test_seance_guarded_mode_partial_strip_repair(synthetic_repo: Path) -> None:
    """Verify guarded repair strips unverified sentences on persistent retry violations."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    # Turn 0: hallucinated; Turn 1: 1 verified sentence + 1 uncited claim
    turn0 = "We overhauled everything in [deadbeef01]."
    turn1 = (
        f"We deprecated request in [{top_sha}]. We also rebuilt the server architecture completely."
    )

    mock = MockBackend(responses=[turn0, turn1])
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    assert any(isinstance(ev, ReconsideringEvent) for ev in events)
    answer = extract_answer_from_events(events)

    # Verified sentence retained
    assert f"[{top_sha}]" in answer
    assert GHOST_DISCLAIMER in answer

    # Uncited sentence stripped
    assert "rebuilt the server architecture" not in answer

    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert verdict_ev.verdict.is_fully_verified is True

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 1


def test_seance_guarded_mode_retry_fail_silence_fallback(synthetic_repo: Path) -> None:
    """Verify fallback to silence when all sentences fail verification across retry."""
    mock = MockBackend(mode=MockMode.RETRY_FAIL, fake_hash="fake0001")
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    assert any(isinstance(ev, ReconsideringEvent) for ev in events)
    answer = extract_answer_from_events(events)
    assert answer == GHOST_REFUSAL_MESSAGE

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 1


def test_seance_model_refusal_passthrough(synthetic_repo: Path) -> None:
    """Verify model-initiated refusal passes through without triggering retry."""
    mock = MockBackend(mode=MockMode.REFUSE)
    events = list(
        ask(
            "Why did the maintainers migrate from React to Vue?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    assert not any(isinstance(ev, ReconsideringEvent) for ev in events)
    answer = extract_answer_from_events(events)
    assert answer == GHOST_REFUSAL_MESSAGE

    done_ev = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done_ev.retries == 0


def test_seance_error_handling_invalid_repo(non_git_dir: Path) -> None:
    """Verify graceful ErrorEvent emission on non-git directory path."""
    mock = MockBackend()
    events = list(
        ask(
            "Any questions?",
            non_git_dir,
            backend=mock,
        )
    )

    assert any(isinstance(ev, ErrorEvent) for ev in events)
    assert any(isinstance(ev, DoneEvent) for ev in events)
    assert mock.call_count == 0


def test_seance_events_serialization() -> None:
    """Verify all 6 SeanceEvent classes serialize to JSON-compatible dictionaries."""
    # 1. EvidenceEvent
    ev_commit = Evidence(
        tag="E1",
        score=1.5,
        commit=retrieve("auth", Path("."))[0].commit if retrieve("auth", Path(".")) else None,  # type: ignore[arg-type]
    )
    if ev_commit.commit is not None:
        ev_event = EvidenceEvent(evidence=[ev_commit])
        assert ev_event.event == "evidence"
        assert "evidence" in ev_event.to_dict()

    # 2. TokenEvent
    tok = TokenEvent(token="hello")
    assert tok.event == "token"
    assert tok.to_dict() == {"token": "hello"}

    # 3. ReconsideringEvent
    recons = ReconsideringEvent(violations=("Violated citation [deadbeef].",))
    assert recons.event == "reconsidering"
    assert "violations" in recons.to_dict()
    assert recons.to_dict()["reason"] == "The spirits reconsider..."

    # 4. VerdictEvent
    v_res = VerificationResult(
        sentences=(
            SentenceVerdict(
                text="Text [3f2a9c1].",
                citations=(
                    CitationVerdict(
                        raw_hash="3f2a9c1", resolved_sha="3f2a9c1", exists=True, grounded=True
                    ),
                ),
                status="verified",
                support_hint=0.8,
            ),
        ),
        is_fully_verified=True,
        violations=(),
    )
    ve = VerdictEvent(verdict=v_res)
    assert ve.event == "verdict"
    assert ve.to_dict()["is_fully_verified"] is True

    # 5. DoneEvent
    de = DoneEvent(mode="guarded", retries=1)
    assert de.event == "done"
    assert de.to_dict() == {"mode": "guarded", "retries": 1, "disclaimer": GHOST_DISCLAIMER}

    # 6. ErrorEvent
    ee = ErrorEvent(message="Something failed")
    assert ee.event == "error"
    assert ee.to_dict() == {"message": "Something failed"}
