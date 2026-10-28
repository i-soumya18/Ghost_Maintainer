"""Empirical adversarial challenge suite for Backends and Seance Streaming pipeline.

Stress-tests:
1. Chunked streaming & boundary conditions for think tag suppression (strip_think_tags_stream).
2. MockBackend under extreme conditions (multiple calls, custom modes, ungrounded mode, hallucinated mode).
3. Retry feedback loop in seance.py (verifying violation details are communicated to retry prompt).
4. SSE Event sequencing, structure, JSON serialization, and error handling.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from ghost_maintainer.backends import (
    BackendError,
    MockBackend,
    MockMode,
    OpenAICompatBackend,
    strip_think_tags_stream,
)
from ghost_maintainer.config import GHOST_REFUSAL_MESSAGE
from ghost_maintainer.retrieve import retrieve
from ghost_maintainer.seance import (
    DoneEvent,
    ErrorEvent,
    EvidenceEvent,
    ReconsideringEvent,
    TokenEvent,
    VerdictEvent,
    ask,
    extract_answer_from_events,
)

# ==============================================================================
# CHALLENGE SUITE 1: CHUNKED STREAMING & BOUNDARY CONDITIONS FOR THINK TAGS
# ==============================================================================


def test_strip_think_tags_dispatch_adversarial_pattern() -> None:
    """Explicitly verify the exact dispatch split pattern:

    ["<th", "ink>thinking", "</th", "ink>actual"] -> "actual".
    """
    stream = iter(["<th", "ink>thinking", "</th", "ink>actual"])
    filtered = list(strip_think_tags_stream(stream))
    assert "".join(filtered) == "actual"


def test_strip_think_tags_single_character_fuzz() -> None:
    """Stress-test single-character chunk stream across think boundary."""
    full_text = (
        "<think>deep reasoning step 1\nstep 2</think>We preserved the architecture [3f2a9c1]."
    )
    single_char_stream = iter(list(full_text))
    filtered = list(strip_think_tags_stream(single_char_stream))
    assert "".join(filtered) == "We preserved the architecture [3f2a9c1]."


def test_strip_think_tags_all_split_permutations() -> None:
    """Systematically test cutting '<think>pondering</think>Final result' at every possible index."""
    prefix = "<think>pondering</think>"
    suffix = "Final result [a1b2c3d]."
    combined = prefix + suffix

    # Test 2-chunk partition at every possible split point from 1 to len(combined)-1
    for cut in range(1, len(combined)):
        c1 = combined[:cut]
        c2 = combined[cut:]
        result = "".join(strip_think_tags_stream(iter([c1, c2])))
        assert result == suffix, f"Failed at cut index {cut}: c1={c1!r}, c2={c2!r}, got={result!r}"


def test_strip_think_tags_false_alarm_prefixes() -> None:
    """Buffer starting with '<', '<t', '<th', '<thi' that does not become '<think>' must not drop chars."""
    candidates = [
        ["<th", "is is not a think tag>"],
        ["<", "table>content</table>"],
        ["<thi", "s commit introduced a bug>"],
        ["<think", "er was our maintainer>"],  # starts with <think but 7th char is 'e', not '>'
        ["<", "b", ">bold text</b>"],
    ]
    for chunks in candidates:
        expected = "".join(chunks)
        actual = "".join(strip_think_tags_stream(iter(chunks)))
        assert actual == expected, (
            f"Corrupted non-think chunks: expected {expected!r}, got {actual!r}"
        )


def test_strip_think_tags_unclosed_stream() -> None:
    """Stream cut off before </think> closes (e.g. max_new_tokens hit during thinking) must not leak."""
    unclosed_chunks = ["<th", "ink>pondering infinitely without ever emitting the closing tag..."]
    filtered = list(strip_think_tags_stream(iter(unclosed_chunks)))
    assert filtered == [], f"Unclosed think tag leaked tokens: {filtered}"


def test_strip_think_tags_whitespace_attached_to_closing_tag() -> None:
    """Whitespace attached to </think> in the same chunk must be stripped by remainder.lstrip."""
    chunks = [
        "",
        "<think>",
        "reasoning",
        "</think>\r\n  \n",
        "The actual statement [3f2a9c1].",
        "",
    ]
    filtered = list(strip_think_tags_stream(iter(chunks)))
    assert "".join(filtered) == "The actual statement [3f2a9c1]."


def test_strip_think_tags_whitespace_in_separate_chunk_behavior() -> None:
    """Whitespace delivered in a separate chunk AFTER </think> passes through as stream tokens."""
    chunks = [
        "<think>reasoning</think>",
        "\r\n  \n",
        "The actual statement [3f2a9c1].",
    ]
    filtered = list(strip_think_tags_stream(iter(chunks)))
    # Because </think> closed in chunk 0, chunk 1 is outside think mode and streams normally
    assert "".join(filtered) == "\r\n  \nThe actual statement [3f2a9c1]."


def test_strip_think_tags_leading_whitespace_boundary_leak() -> None:
    """Empirical finding: Leading whitespace before <think> causes <think> detection to fail."""
    chunks = ["\n\n", "<think>reasoning trace</think>", "Answer [3f2a9c1]."]
    filtered = list(strip_think_tags_stream(iter(chunks)))
    # Demonstrates that start_checked trips on '\n\n', leaking the think tag
    assert "<think>" in "".join(filtered)


def test_strip_think_tags_empty_think_tag() -> None:
    """Empty think tag <think></think> must produce exact answer without artifact."""
    chunks = ["<think></think>", "Immediate answer [3f2a9c1]."]
    filtered = list(strip_think_tags_stream(iter(chunks)))
    assert "".join(filtered) == "Immediate answer [3f2a9c1]."


def test_openai_compat_backend_with_chunked_think_tags() -> None:
    """Integration test: OpenAICompatBackend filters split <think> tags received via SSE stream."""
    sse_lines = [
        b'data: {"choices": [{"delta": {"content": "<th"}}]}\n\n',
        b'data: {"choices": [{"delta": {"content": "ink>Analyzing commit log... "}}]}\n\n',
        b'data: {"choices": [{"delta": {"content": "</th"}}]}\n\n',
        b'data: {"choices": [{"delta": {"content": "ink>\\n\\nWe modified auth in [3f2a9c1]."}}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, content=b"".join(sse_lines)
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    backend = OpenAICompatBackend(base_url="http://localhost:11434/v1", client=client)

    result = "".join(backend.generate([{"role": "user", "content": "test"}]))
    assert "<think>" not in result
    assert "</think>" not in result
    assert "Analyzing commit log" not in result
    assert result == "We modified auth in [3f2a9c1]."


# ==============================================================================
# CHALLENGE SUITE 2: MOCKBACKEND EXTREME CONDITIONS
# ==============================================================================


def test_mock_backend_multiple_sequential_calls_and_reset() -> None:
    """Verify MockBackend state tracking across 12 sequential calls and reset."""
    backend = MockBackend(mode=MockMode.HONEST)
    assert backend.call_count == 0
    assert len(backend.calls) == 0

    for i in range(12):
        msgs = [{"role": "user", "content": f"QUESTION {i}: Test"}]
        list(backend.generate(msgs))
        assert backend.call_count == i + 1
        assert len(backend.calls) == i + 1
        assert backend.calls[i] == msgs

    backend.reset()
    assert backend.call_count == 0
    assert len(backend.calls) == 0


def test_mock_backend_all_aliases_and_casing() -> None:
    """Verify all mode aliases, hyphens, underscores, and uppercase variations."""
    mode_variants = [
        ("HONEST", MockMode.HONEST),
        ("honest", MockMode.HONEST),
        ("CANNED", MockMode.HONEST),
        ("valid", MockMode.HONEST),
        ("canned_valid", MockMode.HONEST),
        ("canned-valid", MockMode.HONEST),
        ("HALLUCINATE", MockMode.HALLUCINATE),
        ("hallucinate_hash", MockMode.HALLUCINATE),
        ("hallucinate-hash", MockMode.HALLUCINATE),
        ("ungrounded", MockMode.UNGROUNDED),
        ("UNGROUNDED", MockMode.UNGROUNDED),
        ("bare_hex", MockMode.BARE_HEX),
        ("bare-hex", MockMode.BARE_HEX),
        ("uncited", MockMode.UNCITED),
        ("uncited_claim", MockMode.UNCITED),
        ("uncited-claim", MockMode.UNCITED),
        ("refuse", MockMode.REFUSE),
        ("refusal", MockMode.REFUSE),
        ("stream_think", MockMode.STREAM_THINK),
        ("stream-think", MockMode.STREAM_THINK),
        ("think", MockMode.STREAM_THINK),
        ("unsloth_style", MockMode.UNSLOTH_STYLE),
        ("unsloth-style", MockMode.UNSLOTH_STYLE),
        ("slow", MockMode.SLOW),
        ("retry_repair", MockMode.RETRY_REPAIR),
        ("retry-repair", MockMode.RETRY_REPAIR),
        ("retry_fail", MockMode.RETRY_FAIL),
        ("retry-fail", MockMode.RETRY_FAIL),
    ]

    for mode_str, expected_mode in mode_variants:
        b = MockBackend(mode=mode_str)
        assert b.mode == expected_mode, f"Mode '{mode_str}' did not map to {expected_mode}"


def test_mock_backend_chunking_modes_and_token_capping() -> None:
    """Verify chunk_by='full' vs chunk_by='word' and strict max_new_tokens clamping."""
    full_backend = MockBackend(mode=MockMode.HONEST, chunk_by="full")
    chunks_full = list(full_backend.generate([{"role": "user", "content": "q"}]))
    assert len(chunks_full) == 1
    assert "We deprecated" in chunks_full[0]

    # Word chunking with max_new_tokens=2
    word_backend = MockBackend(mode=MockMode.HONEST, chunk_by="word")
    chunks_2 = list(word_backend.generate([{"role": "user", "content": "q"}], max_new_tokens=2))
    assert len(chunks_2) == 2


def test_mock_backend_responses_exhaustion_and_clamping() -> None:
    """Verify when responses list is provided, subsequent calls clamp to the last response."""
    backend = MockBackend(responses=["Response Alpha", "Response Beta"])
    r0 = "".join(backend.generate([]))
    r1 = "".join(backend.generate([]))
    r2 = "".join(backend.generate([]))
    r3 = "".join(backend.generate([]))

    assert r0 == "Response Alpha"
    assert r1 == "Response Beta"
    assert r2 == "Response Beta"
    assert r3 == "Response Beta"
    assert backend.call_count == 4


def test_mock_backend_evidence_extraction_robustness() -> None:
    """Test _extract_evidence_hashes with tricky prompt structures and hex validity."""
    backend = MockBackend(mode=MockMode.HONEST)

    # 1. Reverse priority: Few-shot has [a1b2c3d], User query has [c0ffee1]
    msgs_with_fewshot = [
        {"role": "user", "content": "EVIDENCE\n[a1b2c3d] · old commit\n\nQUESTION: Why?"},
        {"role": "assistant", "content": "Answer [a1b2c3d]."},
        {
            "role": "user",
            "content": "EVIDENCE\n[c0ffee1] · real commit\n\nQUESTION: What happened?",
        },
    ]
    ans1 = "".join(backend.generate(msgs_with_fewshot))
    assert "[c0ffee1]" in ans1

    # 2. No QUESTION: delimiter in user prompt
    msgs_no_q = [{"role": "user", "content": "Check this evidence: [e5f6a7b] and tell me why."}]
    ans2 = "".join(backend.generate(msgs_no_q))
    assert "[e5f6a7b]" in ans2

    # 3. Non-hex characters in brackets [nothex12] are ignored; falls back to default_hash
    msgs_non_hex = [{"role": "user", "content": "EVIDENCE\n[nothex12] · commit\n\nQUESTION: What?"}]
    ans3 = "".join(backend.generate(msgs_non_hex))
    assert f"[{backend.default_hash}]" in ans3

    # 4. No hashes at all: falls back to default_hash
    msgs_no_hash = [{"role": "user", "content": "No hashes anywhere here."}]
    ans4 = "".join(backend.generate(msgs_no_hash))
    assert f"[{backend.default_hash}]" in ans4


# ==============================================================================
# CHALLENGE SUITE 3: RETRY FEEDBACK LOOP IN SEANCE.PY
# ==============================================================================


def test_retry_feedback_loop_hallucinated_hash(synthetic_repo: Path) -> None:
    """Verify that hallucinated hash violation is communicated precisely to retry prompt."""
    fake_sha = "deadbeef99"
    backend = MockBackend(
        mode=MockMode.RETRY_REPAIR,
        fake_hash=fake_sha,
    )

    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
        )
    )

    # Verify 2 calls occurred
    assert backend.call_count == 2
    pass1_call = backend.calls[0]
    pass2_call = backend.calls[1]

    # Verify pass2 received multi-turn retry messages
    assert len(pass2_call) == len(pass1_call) + 2
    assistant_turn = pass2_call[-2]
    user_feedback_turn = pass2_call[-1]

    assert assistant_turn["role"] == "assistant"
    assert fake_sha in assistant_turn["content"]

    assert user_feedback_turn["role"] == "user"
    feedback = user_feedback_turn["content"]
    assert (
        "Your previous response contained citations that violated archive honesty rules:"
        in feedback
    )
    assert f"Commit [{fake_sha}] does not exist in repository history." in feedback
    assert "CORRECTION RULES:" in feedback

    # Verify ReconsideringEvent was emitted with the violation
    recons = next(ev for ev in events if isinstance(ev, ReconsideringEvent))
    assert any(fake_sha in v for v in recons.violations)

    # Verify final verdict is clean and retries=1
    done = next(ev for ev in events if isinstance(ev, DoneEvent))
    assert done.retries == 1


def test_retry_feedback_loop_ungrounded_hash(synthetic_repo: Path) -> None:
    """Verify ungrounded commit hash (exists in repo, but not in evidence) violation in retry prompt."""
    evidence = retrieve("deprecated request", synthetic_repo, k=2)
    ev_shas = {ev.commit.sha.lower() for ev in evidence}

    # Find a real commit in synthetic_repo that is NOT in retrieved evidence
    # Commit 1 (Initial commit) is guaranteed not to be in top-2 for "deprecated request"
    import subprocess

    proc = subprocess.run(
        ["git", "-C", str(synthetic_repo), "log", "--format=%H"],
        capture_output=True,
        text=True,
        check=True,
    )
    all_shas = proc.stdout.strip().splitlines()
    ungrounded_real_sha = next(sha for sha in all_shas if sha.lower() not in ev_shas)[:7]

    # Turn 0 uses ungrounded real commit; Turn 1 repairs with top evidence commit
    top_grounded = evidence[0].commit.short
    turn0 = f"We configured the initial project files in [{ungrounded_real_sha}]."
    turn1 = f"We deprecated request in [{top_grounded}]."

    backend = MockBackend(responses=[turn0, turn1])
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
            k=2,
        )
    )

    assert backend.call_count == 2
    retry_prompt = backend.calls[1][-1]["content"]
    assert (
        f"Commit [{ungrounded_real_sha}] exists in repository history but was NOT in the provided EVIDENCE."
        in retry_prompt
    )

    recons = next(ev for ev in events if isinstance(ev, ReconsideringEvent))
    assert any("NOT in the provided EVIDENCE" in v for v in recons.violations)

    verdict_ev = next(ev for ev in events if isinstance(ev, VerdictEvent))
    assert verdict_ev.verdict.is_fully_verified is True


def test_retry_feedback_loop_bare_hex(synthetic_repo: Path) -> None:
    """Verify bare hex violation communicated to retry prompt."""
    evidence = retrieve("deprecated request", synthetic_repo, k=2)
    top_sha = evidence[0].commit.short

    turn0 = f"We deprecated request in commit {top_sha} without brackets."
    turn1 = f"We deprecated request in [{top_sha}]."

    backend = MockBackend(responses=[turn0, turn1])
    list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
            k=2,
        )
    )

    assert backend.call_count == 2
    retry_prompt = backend.calls[1][-1]["content"]
    assert (
        f"Sentence contains bare unbracketed commit hash '{top_sha}': citations must be formatted as '[{top_sha}]'."
        in retry_prompt
    )


def test_retry_feedback_loop_uncited_claim(synthetic_repo: Path) -> None:
    """Verify uncited factual claim violation communicated to retry prompt."""
    evidence = retrieve("deprecated request", synthetic_repo, k=2)
    top_sha = evidence[0].commit.short

    turn0 = "We decided to deprecate the request library completely."
    turn1 = f"We deprecated request in [{top_sha}]."

    backend = MockBackend(responses=[turn0, turn1])
    list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
            k=2,
        )
    )

    assert backend.call_count == 2
    retry_prompt = backend.calls[1][-1]["content"]
    assert "Sentence makes factual claims without citations" in retry_prompt


def test_retry_feedback_loop_multiple_violations(synthetic_repo: Path) -> None:
    """Verify that multiple simultaneous violations are all enumerated in retry prompt."""
    fake_sha = "deadbeef42"
    turn0 = f"We refactored auth in [{fake_sha}]. We also redesigned the whole architecture."
    turn1 = GHOST_REFUSAL_MESSAGE

    backend = MockBackend(responses=[turn0, turn1])
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
        )
    )

    retry_prompt = backend.calls[1][-1]["content"]
    assert f"Commit [{fake_sha}] does not exist in repository history." in retry_prompt
    assert "Sentence makes factual claims without citations" in retry_prompt

    recons = next(ev for ev in events if isinstance(ev, ReconsideringEvent))
    assert len(recons.violations) >= 2


def test_retry_refusal_response(synthetic_repo: Path) -> None:
    """Verify that when retry responds with GHOST_REFUSAL_MESSAGE, it is accepted and emitted."""
    fake_sha = "deadbeef88"
    turn0 = f"We rewrote auth in [{fake_sha}]."
    turn1 = GHOST_REFUSAL_MESSAGE

    backend = MockBackend(responses=[turn0, turn1])
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


# ==============================================================================
# CHALLENGE SUITE 4: SSE EVENT SEQUENCING, STRUCTURE & SERIALIZATION
# ==============================================================================


def test_sse_event_sequencing_gate_refusal(synthetic_repo: Path) -> None:
    """Exact sequence for Stage 1 Gate Refusal: EvidenceEvent -> TokenEvent -> DoneEvent."""
    backend = MockBackend()
    events = list(
        ask(
            "Why did the maintainers migrate to Rust?",
            synthetic_repo,
            min_score=999.0,
            backend=backend,
        )
    )

    expected_types = [EvidenceEvent, TokenEvent, DoneEvent]
    assert [type(ev) for ev in events] == expected_types
    assert isinstance(events[1], TokenEvent)
    assert events[1].token == GHOST_REFUSAL_MESSAGE
    assert isinstance(events[2], DoneEvent)
    assert events[2].retries == 0


def test_sse_event_sequencing_guarded_clean(synthetic_repo: Path) -> None:
    """Exact sequence for Guarded Mode clean Pass 1:

    EvidenceEvent -> TokenEvent* -> (Disclaimer TokenEvent) -> VerdictEvent -> DoneEvent.
    """
    evidence = retrieve("deprecated request", synthetic_repo, k=1)
    sha = evidence[0].commit.short

    backend = MockBackend(mode=MockMode.HONEST, default_hash=sha)
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
            k=1,
        )
    )

    assert isinstance(events[0], EvidenceEvent)
    # Middle events must be TokenEvents
    for ev in events[1:-2]:
        assert isinstance(ev, TokenEvent)
    assert isinstance(events[-2], VerdictEvent)
    assert isinstance(events[-1], DoneEvent)
    done_ev = events[-1]
    assert done_ev.retries == 0


def test_sse_event_sequencing_guarded_retry_repair(synthetic_repo: Path) -> None:
    """Exact sequence for Guarded Retry Repair:

    EvidenceEvent -> TokenEvent(pass1)* -> ReconsideringEvent -> TokenEvent(pass2) -> VerdictEvent -> DoneEvent.
    """
    evidence = retrieve("deprecated request", synthetic_repo, k=1)
    sha = evidence[0].commit.short

    backend = MockBackend(
        mode=MockMode.RETRY_REPAIR,
        fake_hash="deadbeef01",
        default_hash=sha,
    )
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=backend,
            k=1,
        )
    )

    event_types = [type(ev) for ev in events]
    assert event_types[0] == EvidenceEvent
    assert ReconsideringEvent in event_types

    recons_idx = event_types.index(ReconsideringEvent)
    # Before ReconsideringEvent, there are TokenEvents from Pass 1
    assert all(t == TokenEvent for t in event_types[1:recons_idx])

    # After ReconsideringEvent, there is TokenEvent from Pass 2
    assert event_types[recons_idx + 1] == TokenEvent
    assert event_types[-2] == VerdictEvent
    assert event_types[-1] == DoneEvent
    last_ev = events[-1]
    assert isinstance(last_ev, DoneEvent)
    assert last_ev.retries == 1


def test_sse_event_sequencing_error_during_pass1(synthetic_repo: Path) -> None:
    """Error raised during Pass 1 generation:

    EvidenceEvent -> TokenEvent* -> ErrorEvent -> DoneEvent.
    """

    class FaultyBackend:
        name = "faulty"

        def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> Iterator[str]:
            yield "Starting token..."
            raise BackendError("GPU CUDA out of memory error!")

    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=FaultyBackend(),
        )
    )

    event_types = [type(ev) for ev in events]
    assert event_types[0] == EvidenceEvent
    assert event_types[1] == TokenEvent
    assert event_types[2] == ErrorEvent
    assert event_types[3] == DoneEvent
    err_ev = events[2]
    done_ev = events[3]
    assert isinstance(err_ev, ErrorEvent)
    assert isinstance(done_ev, DoneEvent)
    assert "GPU CUDA out of memory error!" in err_ev.message
    assert done_ev.retries == 0


def test_sse_event_sequencing_error_during_pass2(synthetic_repo: Path) -> None:
    """Error raised during Pass 2 retry generation:

    EvidenceEvent -> TokenEvent* -> ReconsideringEvent -> ErrorEvent -> DoneEvent.
    """

    class RetryFailingBackend:
        name = "retry_failing"

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> Iterator[str]:
            self.calls += 1
            if self.calls == 1:
                yield "We overhauled auth in [deadbeef01]."
            else:
                raise BackendError("Network connection reset during retry generation!")

    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=RetryFailingBackend(),
        )
    )

    event_types = [type(ev) for ev in events]
    assert event_types[0] == EvidenceEvent
    assert ReconsideringEvent in event_types
    assert ErrorEvent in event_types
    assert event_types[-1] == DoneEvent
    final_ev = events[-1]
    assert isinstance(final_ev, DoneEvent)
    assert final_ev.retries == 1


def test_all_seance_events_json_serialization(synthetic_repo: Path) -> None:
    """Empirically test that to_dict() on every event across runs produces valid JSON."""
    mock = MockBackend(mode=MockMode.RETRY_REPAIR)
    events = list(
        ask(
            "Why was request deprecated?",
            synthetic_repo,
            mode="guarded",
            backend=mock,
        )
    )

    for ev in events:
        d = ev.to_dict()
        assert isinstance(d, dict)
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)
        assert isinstance(deserialized, dict)

    # Test error event serialization
    err_ev = ErrorEvent(message="Critical backend failure")
    err_json = json.dumps(err_ev.to_dict())
    assert "Critical backend failure" in err_json
