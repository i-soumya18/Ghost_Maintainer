"""Deterministic mock backend with scripted behavioral modes for testing."""

from __future__ import annotations

import re
from collections.abc import Iterator
from enum import StrEnum

from ghost_maintainer.config import GHOST_REFUSAL_MESSAGE


class MockMode(StrEnum):
    """Behavioral modes supported by MockBackend."""

    HONEST = "honest"
    HALLUCINATE = "hallucinate"
    UNGROUNDED = "ungrounded"
    BARE_HEX = "bare_hex"
    UNCITED = "uncited"
    RETRY_REPAIR = "retry_repair"
    RETRY_FAIL = "retry_fail"
    REFUSE = "refuse"
    STREAM_THINK = "stream_think"
    UNSLOTH_STYLE = "unsloth_style"
    SLOW = "slow"

    # Aliases for specification compatibility
    CANNED_VALID = "honest"
    HALLUCINATE_HASH = "hallucinate"
    UNCITED_CLAIM = "uncited"
    REFUSAL = "refuse"


class MockBackend:
    """Deterministic scripted LLM backend for CI, unit testing, and eval validation."""

    def __init__(
        self,
        mode: MockMode | str = MockMode.HONEST,
        *,
        responses: list[str] | None = None,
        default_hash: str = "3f2a9c1",
        fake_hash: str = "deadbeef01",
        ungrounded_hash: str = "c1c1c1c1c1c1",
        chunk_by: str = "word",
    ) -> None:
        if isinstance(mode, str):
            normalized = mode.strip().lower().replace("-", "_")
            if normalized in ("canned", "valid", "canned_valid", "honest"):
                normalized = "honest"
            elif normalized in ("hallucinate", "hallucinate_hash"):
                normalized = "hallucinate"
            elif normalized in ("uncited", "uncited_claim"):
                normalized = "uncited"
            elif normalized in ("refuse", "refusal"):
                normalized = "refuse"
            elif normalized in ("think", "stream_think"):
                normalized = "stream_think"
            try:
                self.mode = MockMode(normalized)
            except ValueError:
                raise ValueError(f"Unsupported MockMode: '{mode}'") from None
        else:
            self.mode = mode

        self.responses = list(responses) if responses is not None else None
        self.default_hash = default_hash
        self.fake_hash = fake_hash
        self.ungrounded_hash = ungrounded_hash
        self.chunk_by = chunk_by

        self.name: str = "mock"
        self.call_count: int = 0
        self.calls: list[list[dict[str, str]]] = []

    def reset(self) -> None:
        """Reset call counter and recorded messages history."""
        self.call_count = 0
        self.calls.clear()

    def _extract_evidence_hashes(self, messages: list[dict[str, str]]) -> list[str]:
        """Extract commit hashes formatted as [hash] from user prompt evidence.

        Searches messages in reverse order so the real user query's EVIDENCE block
        is prioritized over fictional few-shot examples at the start of conversation.
        """
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if "EVIDENCE" in content and "QUESTION:" in content:
                    evidence_part = content.split("QUESTION:")[0]
                    found = re.findall(r"\[([0-9a-fA-F]{7,40})\]", evidence_part)
                    if found:
                        unique: list[str] = []
                        for h in found:
                            hl = h.lower()
                            if hl not in unique:
                                unique.append(hl)
                        return unique

        # Fallback to any user message hashes if no structured EVIDENCE block matched
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                found = re.findall(r"\[([0-9a-fA-F]{7,40})\]", content)
                if found:
                    return [h.lower() for h in found]

        return []

    def _resolve_response_text(self, messages: list[dict[str, str]]) -> str:
        """Determine deterministic response string based on mode and turn count."""
        if self.responses is not None and len(self.responses) > 0:
            idx = min(self.call_count, len(self.responses) - 1)
            return self.responses[idx]

        evidence_hashes = self._extract_evidence_hashes(messages)
        grounded_hash = evidence_hashes[0] if evidence_hashes else self.default_hash

        if self.mode in (MockMode.HONEST, MockMode.CANNED_VALID, MockMode.SLOW):
            return f"We deprecated the request library in favor of native fetch [{grounded_hash}]."

        if self.mode in (MockMode.HALLUCINATE, MockMode.HALLUCINATE_HASH):
            return f"We overhauled the internal transport layer in [{self.fake_hash}]."

        if self.mode == MockMode.UNGROUNDED:
            return f"We initialized project configuration and metadata in [{self.ungrounded_hash}]."

        if self.mode == MockMode.BARE_HEX:
            return (
                f"We updated the project dependencies in commit {grounded_hash} without brackets."
            )

        if self.mode in (MockMode.UNCITED, MockMode.UNCITED_CLAIM):
            return "We decided to deprecate the request library because the ecosystem moved to standard fetch."

        if self.mode in (MockMode.REFUSE, MockMode.REFUSAL):
            return GHOST_REFUSAL_MESSAGE

        if self.mode == MockMode.RETRY_REPAIR:
            if self.call_count == 0:
                return f"We overhauled the authentication mechanism in [{self.fake_hash}]."
            return f"We deprecated the request library in favor of native fetch [{grounded_hash}]."

        if self.mode == MockMode.RETRY_FAIL:
            if self.call_count == 0:
                return f"We overhauled the authentication mechanism in [{self.fake_hash}]."
            return "We still believe the changes occurred in [feedface02]."

        if self.mode in (MockMode.STREAM_THINK, MockMode.UNSLOTH_STYLE):
            return (
                f"<think>Inspecting commit history for deprecated library...</think>"
                f"We deprecated the request library in favor of native fetch [{grounded_hash}]."
            )

        return GHOST_REFUSAL_MESSAGE

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Stream scripted response text chunks incrementally."""
        self.calls.append([dict(m) for m in messages])
        text = self._resolve_response_text(messages)
        self.call_count += 1

        if self.chunk_by == "full":
            yield text
            return

        tokens = re.findall(r"\S+|\s+", text)
        for yielded_count, token in enumerate(tokens):
            if yielded_count >= max_new_tokens:
                break
            yield token

    def generate_stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Alias for generate to satisfy streaming interfaces."""
        return self.generate(messages, max_new_tokens=max_new_tokens, temperature=temperature)
