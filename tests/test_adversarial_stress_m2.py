"""Comprehensive empirical stress harness for Milestone 2 honesty pipeline.

Stress-tests:
1. High Citation Volume: massive responses with 50-200 citations across dozens of sentences.
2. Mixed Citations: hallucinated hashes mixed with legitimate hashes across multi-sentence responses.
3. Empty Responses & Refusal Triggers: empty, whitespace-only, partial refusal, and disclaimer variants.
4. Edge-Case Hashes: case normalization, boundary punctuation, English hex word collision resistance.
5. Streaming & HTTP Error Handling: fragmented think tags, prefix-only stripping boundary, and simulated OpenAICompat HTTP failures.
6. Concurrency: multi-threaded simultaneous queries against the same repository.
7. Evidence Formatting Stress: massive evidence blocks with dozens of files, long commit bodies, and Unicode characters.
"""

from __future__ import annotations

import concurrent.futures
from datetime import UTC
from pathlib import Path
from typing import Any

import httpx
import pytest

from ghost_maintainer.backends import (
    BackendError,
    MockBackend,
    MockMode,
    OpenAICompatBackend,
    strip_think_tags_stream,
)
from ghost_maintainer.config import GHOST_DISCLAIMER, GHOST_REFUSAL_MESSAGE
from ghost_maintainer.gitlog import Commit, FileChange
from ghost_maintainer.prompt import (
    build_seance_prompt,
    format_evidence_block,
)
from ghost_maintainer.retrieve import Evidence, retrieve
from ghost_maintainer.seance import (
    DoneEvent,
    ErrorEvent,
    ReconsideringEvent,
    VerdictEvent,
    ask,
    extract_answer_from_events,
)
from ghost_maintainer.verify import (
    audit_bare_hex,
    extract_citations,
    split_sentences,
    verify,
)

# ==============================================================================
# 1. HIGH CITATION VOLUME & MASSIVE RESPONSES
# ==============================================================================


def test_stress_massive_response_hundreds_of_citations(synthetic_repo: Path) -> None:
    """Stress-test verify() and split_sentences() on 50 sentences with 200 total citations."""
    evidence = retrieve("auth", synthetic_repo, k=4)
    assert len(evidence) >= 2
    sha1 = evidence[0].commit.short
    sha2 = evidence[1].commit.short

    # Build 50 sentences, each with 4 citations alternating sha1 and sha2
    sentence_list = []
    for i in range(50):
        sentence_list.append(
            f"Sentence number {i} provides archival context for maintainers [{sha1}] [{sha2}] [{sha1}] [{sha2}]."
        )
    massive_text = " ".join(sentence_list)

    # 1. Test split_sentences
    split_result = split_sentences(massive_text)
    assert len(split_result) == 50

    # 2. Test verify
    v_res = verify(massive_text, evidence, repo_path=synthetic_repo)
    assert v_res.is_fully_verified is True
    assert len(v_res.violations) == 0
    assert len(v_res.sentences) == 50

    total_citations = sum(len(s.citations) for s in v_res.sentences)
    assert total_citations == 200
    for s in v_res.sentences:
        assert s.status == "verified"
        assert len(s.citations) == 4
        assert all(c.exists and c.grounded for c in s.citations)


def test_stress_dense_citations_single_sentence(synthetic_repo: Path) -> None:
    """Stress-test a single sentence containing 50 citations packed together."""
    evidence = retrieve("auth", synthetic_repo, k=2)
    sha = evidence[0].commit.short

    # 50 citations in one single sentence
    citations_str = " ".join(f"[{sha}]" for _ in range(50))
    sentence = f"We performed widespread refactoring across the repository {citations_str}."

    split_result = split_sentences(sentence)
    assert len(split_result) == 1

    v_res = verify(sentence, evidence, repo_path=synthetic_repo)
    assert v_res.is_fully_verified is True
    assert len(v_res.sentences) == 1
    assert len(v_res.sentences[0].citations) == 50
    assert all(c.exists and c.grounded for c in v_res.sentences[0].citations)


def test_stress_guarded_remediation_massive_mixed_sentences(synthetic_repo: Path) -> None:
    """Stress-test guarded remediation when 10 valid sentences are mixed with 10 hallucinated sentences."""
    evidence = retrieve("deprecated request", synthetic_repo, k=2)
    top_sha = evidence[0].commit.short
    fake_sha = "deadbeef99"

    # Pass 1: 20 sentences (alternating valid and hallucinated)
    pass1_sentences = []
    for i in range(10):
        pass1_sentences.append(f"We maintained subsystem {i} securely in [{top_sha}].")
        pass1_sentences.append(f"We redesigned subsystem {i} in [{fake_sha}].")
    pass1_text = " ".join(pass1_sentences)

    # Pass 2: model persists with same 20 sentences
    backend = MockBackend(responses=[pass1_text, pass1_text])

    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
        )
    )

    # Verify ReconsideringEvent was emitted
    recons = [ev for ev in events if isinstance(ev, ReconsideringEvent)]
    assert len(recons) == 1
    assert any(fake_sha in v for v in recons[0].violations)

    # Verify final verdict
    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert verdict_ev.verdict.is_fully_verified is True

    # Final answer should have stripped all 10 hallucinated sentences and kept 10 valid ones
    final_answer = extract_answer_from_events(events)
    assert fake_sha not in final_answer
    assert f"[{top_sha}]" in final_answer
    assert GHOST_DISCLAIMER in final_answer

    # Verify all remaining sentences in the final verdict are 100% verified
    for s in verdict_ev.verdict.sentences:
        assert s.status == "verified"
        for c in s.citations:
            assert c.exists is True
            assert c.grounded is True


# ==============================================================================
# 2. EDGE-CASE HASHES & PUNCTUATION FUZZING
# ==============================================================================


def test_stress_hash_case_insensitivity_matrix(synthetic_repo: Path) -> None:
    """Verify uppercase, lowercase, and mixed-case commit hashes resolve and verify identically."""
    evidence = retrieve("deprecated request", synthetic_repo, k=1)
    base_sha = evidence[0].commit.short.lower()

    upper_sha = base_sha.upper()
    mixed_sha = "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(base_sha))

    text = f"We updated dependencies in [{upper_sha}]. We also cleaned docs in [{mixed_sha}]."
    v_res = verify(text, evidence, repo_path=synthetic_repo)

    assert v_res.is_fully_verified is True
    assert len(v_res.violations) == 0
    assert len(v_res.sentences) == 2
    assert v_res.sentences[0].status == "verified"
    assert v_res.sentences[1].status == "verified"
    assert v_res.sentences[0].citations[0].grounded is True
    assert v_res.sentences[1].citations[0].grounded is True


def test_stress_citations_embedded_in_complex_punctuation(synthetic_repo: Path) -> None:
    """Stress-test citations adjacent to diverse quotation marks, parens, colons, and semicolons."""
    evidence = retrieve("deprecated request", synthetic_repo, k=1)
    sha = evidence[0].commit.short

    text = (
        f'We stated: "[{sha}]"; then we noted ([{sha}]). '
        f"Sarah said, “We removed the legacy code in [{sha}]!” "
        f"Next, config was updated [{sha}]. "
        f"Finally, this additional claim has no citation whatsoever."
    )

    sentences = split_sentences(text)
    assert len(sentences) == 4

    v_res = verify(text, evidence, repo_path=synthetic_repo)
    # The last sentence lacks citations, so it must trigger uncited claim violation
    assert any("without citations" in v for v in v_res.violations)
    # The first 3 sentences must be verified
    assert v_res.sentences[0].status == "verified"
    assert v_res.sentences[1].status == "verified"
    assert v_res.sentences[2].status == "verified"
    assert v_res.sentences[3].status == "uncited"


def test_stress_sub7_and_super40_hash_lengths(synthetic_repo: Path) -> None:
    """Verify hashes strictly less than 7 hex chars or greater than 40 chars do not get parsed as valid citations."""
    evidence = retrieve("deprecated request", synthetic_repo, k=1)

    # 6-char hex is invalid citation length
    text_6 = "We modified auth in [3f2a9c]."
    cites_6 = extract_citations(text_6)
    assert len(cites_6) == 0

    v_6 = verify(text_6, evidence, repo_path=synthetic_repo)
    assert v_6.is_fully_verified is False
    assert v_6.sentences[0].status == "uncited"

    # 41-char hex is invalid citation length
    text_41 = "We modified auth in [0123456789abcdef0123456789abcdef012345678]."
    cites_41 = extract_citations(text_41)
    assert len(cites_41) == 0

    v_41 = verify(text_41, evidence, repo_path=synthetic_repo)
    assert v_41.is_fully_verified is False
    assert v_41.sentences[0].status == "uncited"


def test_stress_english_words_with_hex_characters() -> None:
    """Verify common English words containing only [a-f] do not trigger bare hex false alarms."""
    natural_text = (
        "We faced a decade of defaced access before we decided to feed coffee to our staff."
    )
    bare = audit_bare_hex(natural_text, commit_store=None, repo_path=None)
    assert len(bare) == 0


# ==============================================================================
# 3. EMPTY RESPONSES, REFUSAL TRIGGERS & DISCLAIMERS
# ==============================================================================


def test_stress_empty_generation_handling(synthetic_repo: Path) -> None:
    """Verify completely empty backend output triggers guarded retry and falls back to refusal."""
    backend = MockBackend(responses=["", ""])
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
        )
    )

    # ReconsideringEvent was emitted due to empty response violation
    recons = [ev for ev in events if isinstance(ev, ReconsideringEvent)]
    assert len(recons) == 1
    assert any("empty" in v.lower() for v in recons[0].violations)

    # Final answer falls back to silence
    answer = extract_answer_from_events(events)
    assert answer == GHOST_REFUSAL_MESSAGE

    done = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done.retries == 1


def test_stress_whitespace_only_generation(synthetic_repo: Path) -> None:
    """Verify whitespace-only backend output triggers guarded remediation cleanly."""
    backend = MockBackend(responses=["   \n\t\r\n   ", "   \n   "])
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
        )
    )

    answer = extract_answer_from_events(events)
    assert answer == GHOST_REFUSAL_MESSAGE

    done = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done.retries == 1


def test_stress_refusal_with_spurious_text_not_shortcircuited(synthetic_repo: Path) -> None:
    """Verify refusal string with extra text is NOT passed through as immediate refusal."""
    evidence = retrieve("deprecated request", synthetic_repo, k=1)
    sha = evidence[0].commit.short

    # Prompt with refusal text AND an extra sentence
    turn0 = f"The dead do not remember. But we overhauled auth in [{sha}]."
    backend = MockBackend(responses=[turn0])

    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
        )
    )

    # It was not treated as a pure refusal, but split into 2 sentences and verified
    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert len(verdict_ev.verdict.sentences) == 2
    assert verdict_ev.verdict.sentences[0].text == GHOST_REFUSAL_MESSAGE
    assert verdict_ev.verdict.sentences[0].status == "verified"
    assert verdict_ev.verdict.sentences[1].status == "verified"


def test_stress_disclaimer_not_duplicated_if_present(synthetic_repo: Path) -> None:
    """Verify disclaimer is not duplicated if already included in backend generation."""
    evidence = retrieve("deprecated request", synthetic_repo, k=1)
    sha = evidence[0].commit.short

    text_with_disclaimer = f"We deprecated request in [{sha}].\n\n{GHOST_DISCLAIMER}"
    backend = MockBackend(responses=[text_with_disclaimer])

    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
        )
    )

    answer = extract_answer_from_events(events)
    assert answer.count(GHOST_DISCLAIMER) == 1


# ==============================================================================
# 4. STREAMING & HTTP ERROR HANDLING
# ==============================================================================


def test_stress_strip_think_tags_extreme_fragmentation() -> None:
    """Verify strip_think_tags_stream when <think> and </think> are cut across 1-character chunks."""
    chunks = (
        ["<", "t", "h", "i", "n", "k", ">"]
        + list("step-by-step reasoning")
        + ["<", "/", "t", "h", "i", "n", "k", ">"]
        + list("Final response [3f2a9c1].")
    )

    filtered = list(strip_think_tags_stream(iter(chunks)))
    assert "".join(filtered) == "Final response [3f2a9c1]."


def test_stress_strip_think_tags_prefix_boundary_behavior() -> None:
    """Verify that strip_think_tags_stream functions as a start-of-stream prefix filter.

    Initial <think> tag is stripped, while subsequent content streams normally.
    """
    chunks = [
        "<think>thought 1</think>",
        "We modified config in [3f2a9c1].",
    ]
    filtered = list(strip_think_tags_stream(iter(chunks)))
    result = "".join(filtered)
    assert "<think>" not in result
    assert "</think>" not in result
    assert "thought 1" not in result
    assert result == "We modified config in [3f2a9c1]."


def test_stress_openai_compat_http_status_errors() -> None:
    """Verify OpenAICompatBackend correctly maps HTTP 429 and 500 into BackendError."""

    def handler_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})

    client_429 = httpx.Client(transport=httpx.MockTransport(handler_429))
    backend_429 = OpenAICompatBackend(base_url="http://localhost:11434/v1", client=client_429)

    with pytest.raises(BackendError) as exc_info:
        list(backend_429.generate([{"role": "user", "content": "test"}]))
    assert "429" in str(exc_info.value)

    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "Internal Server Error"}})

    client_500 = httpx.Client(transport=httpx.MockTransport(handler_500))
    backend_500 = OpenAICompatBackend(base_url="http://localhost:11434/v1", client=client_500)

    with pytest.raises(BackendError) as exc_info500:
        list(backend_500.generate([{"role": "user", "content": "test"}]))
    assert "500" in str(exc_info500.value)


def test_stress_openai_compat_connection_timeout(synthetic_repo: Path) -> None:
    """Verify connection timeout in OpenAICompatBackend yields ErrorEvent in Seance."""

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection to LLM host timed out")

    client = httpx.Client(transport=httpx.MockTransport(timeout_handler))
    backend = OpenAICompatBackend(base_url="http://localhost:11434/v1", client=client)

    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            backend=backend,
        )
    )

    err = next(ev for ev in events if isinstance(ev, ErrorEvent))
    assert "timed out" in err.message.lower() or "failed" in err.message.lower()

    done = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done.retries == 0


# ==============================================================================
# 5. EVIDENCE FORMATTING STRESS
# ==============================================================================


def test_stress_evidence_formatting_massive_data(synthetic_repo: Path) -> None:
    """Stress-test format_evidence_block with 30 commits, 20 files each, and long body text."""
    from datetime import datetime

    fake_commits = []
    for i in range(30):
        fc = Commit(
            sha=f"{i:040x}",
            short=f"{i:07x}",
            author=f"Author {i}",
            email=f"author{i}@example.com",
            date=datetime(2020, 1, 1, 12, 0, tzinfo=UTC),
            subject=f"Subject {i}: Major architectural overhaul of the persistence layer",
            body="Long commit explanation with multiple paragraphs.\n" * 10,
            files=tuple(
                FileChange(path=f"src/subsystem_{i}/file_{j}.py", added=10, deleted=5)
                for j in range(15)
            ),
            hunks=(f"@@ -1,10 +1,15 @@ def func_{i}():",),
        )
        fake_commits.append(Evidence(tag=f"E{i + 1}", commit=fc, score=1.5 - (i * 0.02)))

    formatted = format_evidence_block(fake_commits, max_body_len=150)
    assert len(formatted) > 1000
    assert "more" in formatted  # truncated files list
    assert "..." in formatted  # truncated body

    # Build full prompt
    prompt_msgs = build_seance_prompt("What happened across subsystems?", fake_commits)
    assert len(prompt_msgs) == 6
    assert prompt_msgs[0]["role"] == "system"
    assert "EVIDENCE" in prompt_msgs[-1]["content"]


# ==============================================================================
# 6. CONCURRENCY & THREAD-SAFETY
# ==============================================================================


def test_stress_concurrent_seance_queries(synthetic_repo: Path) -> None:
    """Stress-test 10 concurrent queries executed simultaneously on the same repository."""
    evidence = retrieve("deprecated request", synthetic_repo, k=1)
    sha = evidence[0].commit.short

    def run_query(idx: int) -> dict[str, Any]:
        mock = MockBackend(mode=MockMode.HONEST, default_hash=sha)
        events = list(
            ask(
                f"Query {idx}: Why was request deprecated?",
                synthetic_repo,
                mode="guarded",
                backend=mock,
            )
        )
        answer = extract_answer_from_events(events)
        verdict = next(ev for ev in events if isinstance(ev, VerdictEvent))
        done = next(ev for ev in events if isinstance(ev, DoneEvent))
        return {
            "idx": idx,
            "answer": answer,
            "is_fully_verified": verdict.verdict.is_fully_verified,
            "retries": done.retries,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_query, i) for i in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 10
    for res in results:
        assert res["is_fully_verified"] is True
        assert f"[{sha}]" in res["answer"]
        assert GHOST_DISCLAIMER in res["answer"]
        assert res["retries"] == 0


def test_stress_concurrent_mixed_modes_and_queries(synthetic_repo: Path) -> None:
    """Stress-test concurrent executions with differing query types (refusal gate, guarded repair, honest)."""
    evidence = retrieve("deprecated request", synthetic_repo, k=1)
    sha = evidence[0].commit.short

    def worker_gate(idx: int) -> str:
        events = list(
            ask(
                "Why migrate to COBOL?",
                synthetic_repo,
                min_score=999.0,
                backend=MockBackend(),
            )
        )
        return extract_answer_from_events(events)

    def worker_honest(idx: int) -> str:
        events = list(
            ask(
                "Why was request deprecated?",
                synthetic_repo,
                mode="guarded",
                backend=MockBackend(mode=MockMode.HONEST, default_hash=sha),
            )
        )
        return extract_answer_from_events(events)

    def worker_repair(idx: int) -> str:
        events = list(
            ask(
                "Why was request deprecated?",
                synthetic_repo,
                mode="guarded",
                backend=MockBackend(
                    mode=MockMode.RETRY_REPAIR, fake_hash="deadbeef11", default_hash=sha
                ),
            )
        )
        return extract_answer_from_events(events)

    workers = [worker_gate, worker_honest, worker_repair] * 4  # 12 concurrent jobs

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(fn, i) for i, fn in enumerate(workers)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 12
    gate_results = [r for r in results if r == GHOST_REFUSAL_MESSAGE]
    honest_and_repair_results = [r for r in results if f"[{sha}]" in r]

    assert len(gate_results) == 4
    assert len(honest_and_repair_results) == 8
