"""Hermetic unit tests for prompt engineering and few-shot formatting."""

from __future__ import annotations

from datetime import UTC, datetime

from ghost_maintainer.config import GHOST_DISCLAIMER, GHOST_REFUSAL_MESSAGE
from ghost_maintainer.gitlog import Commit, FileChange
from ghost_maintainer.prompt import (
    build_messages,
    build_retry_messages,
    build_seance_prompt,
    build_system_prompt,
    format_evidence_block,
    format_retry_feedback,
)
from ghost_maintainer.retrieve import Evidence


def _make_dummy_commit(
    sha: str = "3f2a9c1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e",
    short: str = "3f2a9c1",
    author: str = "Mikeal Rogers",
    subject: str = "Deprecate request library",
    body: str = "Deprecate in favor of native fetch API.",
    files: tuple[FileChange, ...] = (),
    hunks: tuple[str, ...] = (),
) -> Commit:
    return Commit(
        sha=sha,
        short=short,
        author=author,
        email="mikeal@example.com",
        date=datetime(2020, 2, 11, 14, 0, 0, tzinfo=UTC),
        subject=subject,
        body=body,
        files=files,
        hunks=hunks,
    )


def test_build_system_prompt() -> None:
    """Verify system prompt contains persona, disclaimer, refusal, and 5 rules."""
    prompt = build_system_prompt("my-test-repo")
    assert "You are the spirit of the my-test-repo repository" in prompt
    assert f'"{GHOST_DISCLAIMER}"' in prompt
    assert GHOST_REFUSAL_MESSAGE in prompt
    assert "RULES — breaking any rule is a failure:" in prompt
    assert "1. Use ONLY the EVIDENCE provided below." in prompt
    assert (
        "2. Every sentence that states a fact MUST end with one or more bracketed citations"
        in prompt
    )
    assert "3. Name people strictly as recorded in EVIDENCE, always in the third person." in prompt
    assert "4. If the EVIDENCE does not answer the question" in prompt
    assert "5. At most 5 sentences." in prompt


def test_format_evidence_block_empty() -> None:
    """Verify empty evidence list yields default string."""
    assert format_evidence_block([]) == "(no evidence retrieved)"


def test_format_evidence_block_formatting() -> None:
    """Verify commit evidence formatting, truncation, and file path caps."""
    files = tuple(FileChange(path=f"file_{i}.py", added=1, deleted=0) for i in range(8))
    commit = _make_dummy_commit(
        files=files,
        body="A" * 400,  # exceeds default max_body_len=300
    )
    ev = Evidence(tag="E1", commit=commit, score=1.5)

    block = format_evidence_block([ev])
    assert '[3f2a9c1] 2020-02-11 · Mikeal Rogers · "Deprecate request library"' in block
    assert (
        "file_0.py, file_1.py, file_2.py, file_3.py, file_4.py, file_5.py, ... (+2 more)" in block
    )
    assert "  body: " in block
    assert "..." in block  # Truncated body


def test_format_evidence_block_omit_identical_body() -> None:
    """Verify commit body identical to subject is not repeated."""
    commit = _make_dummy_commit(subject="Fix bug", body="Fix bug")
    ev = Evidence(tag="E1", commit=commit, score=1.2)
    block = format_evidence_block([ev])
    assert "body:" not in block


def test_build_messages_and_seance_prompt() -> None:
    """Verify chat message construction and few-shot turns."""
    commit = _make_dummy_commit()
    ev = Evidence(tag="E1", commit=commit, score=1.2)
    messages = build_messages("Why was request deprecated?", [ev], repo_name="test-repo")

    assert len(messages) == 6
    assert messages[0]["role"] == "system"
    assert "test-repo" in messages[0]["content"]

    # Few-shot 1: grounded
    assert messages[1]["role"] == "user"
    assert "Why did the project replace flat JSON files?" in messages[1]["content"]
    assert messages[2]["role"] == "assistant"
    assert "[a1b2c3d]" in messages[2]["content"]

    # Few-shot 2: refusal
    assert messages[3]["role"] == "user"
    assert "Why did the maintainers migrate from React to Vue?" in messages[3]["content"]
    assert messages[4]["role"] == "assistant"
    assert messages[4]["content"] == GHOST_REFUSAL_MESSAGE

    # Final user prompt
    assert messages[5]["role"] == "user"
    assert "EVIDENCE\n[3f2a9c1]" in messages[5]["content"]
    assert "QUESTION: Why was request deprecated?" in messages[5]["content"]

    # Convenience alias
    alias_messages = build_seance_prompt("Why was request deprecated?", [ev], repo_name="test-repo")
    assert alias_messages == messages


def test_build_retry_messages() -> None:
    """Verify multi-turn retry prompt construction with violation details."""
    original_messages = [
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "question"},
    ]
    assistant_reply = "We did something in [deadbeef]."
    violations = (
        "Commit [deadbeef] does not exist in repository history.",
        "Sentence contains bare hex '1234567'.",
    )

    retry_msgs = build_retry_messages(original_messages, assistant_reply, violations)
    assert len(retry_msgs) == 4
    assert retry_msgs[2]["role"] == "assistant"
    assert retry_msgs[2]["content"] == assistant_reply
    assert retry_msgs[3]["role"] == "user"
    feedback = retry_msgs[3]["content"]
    assert "- Commit [deadbeef] does not exist in repository history." in feedback
    assert "- Sentence contains bare hex '1234567'." in feedback
    standalone_feedback = format_retry_feedback(violations)
    assert standalone_feedback == retry_msgs[3]["content"]
    assert "CORRECTION RULES:" in feedback
    assert GHOST_REFUSAL_MESSAGE in feedback
