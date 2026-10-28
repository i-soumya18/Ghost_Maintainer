"""Hermetic unit tests for polymorphic streaming LLM backends."""

from __future__ import annotations

import httpx
import pytest

from ghost_maintainer.backends import (
    Backend,
    BackendConfigError,
    BackendError,
    BackendUnavailableError,
    MockBackend,
    MockMode,
    OpenAICompatBackend,
    UnslothBackend,
    get_backend,
    strip_think_tags_stream,
)
from ghost_maintainer.config import GHOST_REFUSAL_MESSAGE


def test_backend_protocol_conformance() -> None:
    """Verify that MockBackend, OpenAICompatBackend, and UnslothBackend satisfy Backend protocol."""
    mock = MockBackend()
    assert isinstance(mock, Backend)
    assert mock.name == "mock"

    openai = OpenAICompatBackend(base_url="http://localhost:11434/v1")
    assert isinstance(openai, Backend)
    assert openai.name == "openai_compat"

    unsloth = UnslothBackend()
    assert isinstance(unsloth, Backend)
    assert unsloth.name == "unsloth"


def test_mock_backend_honest_mode() -> None:
    """Verify honest mode extracts evidence hash from user prompt."""
    backend = MockBackend(mode=MockMode.HONEST)
    messages = [
        {"role": "system", "content": "You are a spirit."},
        {"role": "user", "content": "EVIDENCE\n[a1b2c3d] 2020-01-01 · Auth\n\nQUESTION: Why?"},
    ]
    tokens = list(backend.generate(messages))
    result = "".join(tokens)
    assert "[a1b2c3d]" in result
    assert backend.call_count == 1
    assert len(backend.calls) == 1
    assert backend.calls[0] == messages

    # Test reset
    backend.reset()
    assert backend.call_count == 0
    assert len(backend.calls) == 0


def test_mock_backend_modes() -> None:
    """Verify scripted responses for all MockMode settings."""
    messages = [{"role": "user", "content": "QUESTION: Test?"}]

    # Hallucinate
    h_backend = MockBackend(mode="hallucinate", fake_hash="feedbeef12")
    assert "[feedbeef12]" in "".join(h_backend.generate(messages))

    # Ungrounded
    u_backend = MockBackend(mode=MockMode.UNGROUNDED, ungrounded_hash="9999999")
    assert "[9999999]" in "".join(u_backend.generate(messages))

    # Bare hex
    b_backend = MockBackend(mode=MockMode.BARE_HEX, default_hash="3f2a9c1")
    res_b = "".join(b_backend.generate(messages))
    assert "3f2a9c1" in res_b
    assert "[3f2a9c1]" not in res_b

    # Uncited
    unc_backend = MockBackend(mode="uncited")
    res_unc = "".join(unc_backend.generate(messages))
    assert "[" not in res_unc

    # Refuse / refusal
    ref_backend = MockBackend(mode="refusal")
    assert "".join(ref_backend.generate(messages)) == GHOST_REFUSAL_MESSAGE

    # Stream think
    st_backend = MockBackend(mode="stream_think")
    res_st = "".join(st_backend.generate(messages))
    assert "<think>" in res_st and "</think>" in res_st


def test_mock_backend_retry_repair_and_retry_fail() -> None:
    """Verify 2-turn behavior for retry_repair and retry_fail modes."""
    messages = [{"role": "user", "content": "EVIDENCE\n[7777777] · commit\n\nQUESTION: What?"}]

    # Retry repair
    repair_backend = MockBackend(mode=MockMode.RETRY_REPAIR, fake_hash="fake1234")
    turn1 = "".join(repair_backend.generate(messages))
    assert "[fake1234]" in turn1
    turn2 = "".join(repair_backend.generate(messages))
    assert "[7777777]" in turn2

    # Retry fail
    fail_backend = MockBackend(mode=MockMode.RETRY_FAIL, fake_hash="fake1234")
    f_turn1 = "".join(fail_backend.generate(messages))
    assert "[fake1234]" in f_turn1
    f_turn2 = "".join(fail_backend.generate(messages))
    assert "[feedface02]" in f_turn2


def test_mock_backend_custom_responses_and_chunking() -> None:
    """Verify custom responses list and chunking options."""
    backend = MockBackend(
        responses=["First custom response.", "Second custom response."],
        chunk_by="full",
    )
    res1 = list(backend.generate([]))
    assert res1 == ["First custom response."]
    res2 = list(backend.generate([]))
    assert res2 == ["Second custom response."]
    res3 = list(backend.generate([]))
    assert res3 == ["Second custom response."]

    # max_new_tokens capping
    word_backend = MockBackend(chunk_by="word")
    capped = list(word_backend.generate([], max_new_tokens=3))
    assert len(capped) == 3


def test_mock_backend_aliases_and_errors() -> None:
    """Verify alias parsing and error handling for unknown mode."""
    b1 = MockBackend(mode="canned_valid")
    assert b1.mode == MockMode.HONEST

    b2 = MockBackend(mode="uncited_claim")
    assert b2.mode == MockMode.UNCITED

    with pytest.raises(ValueError, match="Unsupported MockMode"):
        MockBackend(mode="invalid_mode_xyz")


def test_strip_think_tags_stream() -> None:
    """Verify streaming suppression of <think>...</think> tags across chunk boundaries."""
    # Case 1: No think tags
    stream1 = iter(["Hello", " ", "world!"])
    assert list(strip_think_tags_stream(stream1)) == ["Hello", " ", "world!"]

    # Case 2: Think tag contained in single chunk
    stream2 = iter(["<think>reasoning...</think>Answer"])
    assert list(strip_think_tags_stream(stream2)) == ["Answer"]

    # Case 3: Split think tags across chunks
    stream3 = iter(["<th", "ink>", "pondering", "...", "</th", "ink>\n\nFinal answer"])
    assert list(strip_think_tags_stream(stream3)) == ["Final answer"]

    # Case 4: Buffer that looks like <think> initially but isn't
    stream4 = iter(["<table", "><tr><td>data</td></tr></table>"])
    assert "".join(strip_think_tags_stream(stream4)) == "<table><tr><td>data</td></tr></table>"


def test_openai_compat_backend_mock_transport() -> None:
    """Verify OpenAICompatBackend streaming via httpx.MockTransport."""
    sse_lines = [
        b": ping\n\n",
        b'data: {"choices": [{"delta": {"content": "We deprecated "}}]}\n\n',
        b"\n\n",
        b'data: {"choices": [{"delta": {"content": "request [3f2a9c1]."}}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, content=b"".join(sse_lines)
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    backend = OpenAICompatBackend(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        client=client,
    )

    tokens = list(backend.generate([{"role": "user", "content": "hi"}]))
    assert "".join(tokens) == "We deprecated request [3f2a9c1]."


def test_openai_compat_backend_errors() -> None:
    """Verify error handling in OpenAICompatBackend."""
    # Missing API key for official OpenAI
    with pytest.raises(BackendConfigError, match="OPENAI_API_KEY is required"):
        OpenAICompatBackend(base_url="https://api.openai.com/v1", api_key=None)

    # 401 error
    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized")

    client_401 = httpx.Client(transport=httpx.MockTransport(handler_401))
    backend_401 = OpenAICompatBackend(base_url="http://localhost:11434/v1", client=client_401)
    with pytest.raises(BackendConfigError, match="401 Unauthorized"):
        list(backend_401.generate([]))

    # 500 error
    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client_500 = httpx.Client(transport=httpx.MockTransport(handler_500))
    backend_500 = OpenAICompatBackend(base_url="http://localhost:11434/v1", client=client_500)
    with pytest.raises(BackendError, match="HTTP 500 error"):
        list(backend_500.generate([]))


def test_unsloth_backend_availability() -> None:
    """Verify UnslothBackend availability check and safe error when unsloth missing."""
    backend = UnslothBackend()
    if not backend.is_available():
        with pytest.raises(BackendUnavailableError, match="requires 'unsloth' and 'torch'"):
            list(backend.generate([]))


def test_get_backend_factory() -> None:
    """Verify get_backend factory instantiates correct backend by name."""
    b_mock = get_backend("mock")
    assert isinstance(b_mock, MockBackend)

    b_openai = get_backend("openai-compat", base_url="http://localhost:8080/v1")
    assert isinstance(b_openai, OpenAICompatBackend)

    b_openai_short = get_backend("openai", base_url="http://localhost:8080/v1")
    assert isinstance(b_openai_short, OpenAICompatBackend)

    b_unsloth = get_backend("unsloth")
    assert isinstance(b_unsloth, UnslothBackend)

    with pytest.raises(ValueError, match="Unknown backend 'unknown_backend'"):
        get_backend("unknown_backend")
