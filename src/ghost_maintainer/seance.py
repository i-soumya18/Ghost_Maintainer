"""Seance orchestrator: 3-stage defense-in-depth honesty pipeline and streaming responses."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ghost_maintainer.backends import get_backend
from ghost_maintainer.backends.base import Backend, BackendError
from ghost_maintainer.config import (
    GHOST_DISCLAIMER,
    GHOST_REFUSAL_MESSAGE,
    settings,
)
from ghost_maintainer.gitlog import GitError, check_git_repo
from ghost_maintainer.prompt import build_retry_messages, build_seance_prompt
from ghost_maintainer.retrieve import Evidence, check_retrieval_gate, retrieve
from ghost_maintainer.verify import VerificationResult, verify


# --- Event Data Classes (F19) ---
@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    """Emitted immediately after BM25 retrieval, providing top-k evidence cards before generation."""

    evidence: list[Evidence]
    event: str = "evidence"

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": [
                {
                    "tag": e.tag,
                    "score": e.score,
                    "commit": e.commit.to_dict(),
                }
                for e in self.evidence
            ]
        }


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """Emitted as incremental text chunks stream from backend, or as final repaired/refusal tokens."""

    token: str
    event: str = "token"

    def to_dict(self) -> dict[str, Any]:
        return {"token": self.token}


@dataclass(frozen=True, slots=True)
class ReconsideringEvent:
    """Emitted in guarded mode when verifier catches violations, signaling Pass 2 retry to client."""

    violations: tuple[str, ...]
    event: str = "reconsidering"

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": "The spirits reconsider...",
            "violations": list(self.violations),
        }


@dataclass(frozen=True, slots=True)
class VerdictEvent:
    """Emitted after verification completes, containing sentence verdicts and citation audits."""

    verdict: VerificationResult
    event: str = "verdict"

    def to_dict(self) -> dict[str, Any]:
        return self.verdict.to_dict()


@dataclass(frozen=True, slots=True)
class DoneEvent:
    """Terminal event marking completion of the stream."""

    mode: str = "guarded"
    retries: int = 0
    disclaimer: str = GHOST_DISCLAIMER
    event: str = "done"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "retries": self.retries,
            "disclaimer": self.disclaimer,
        }


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """Emitted when an unhandled git, backend, or operational error occurs."""

    message: str
    event: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {"message": self.message}


SeanceEvent = (
    EvidenceEvent | TokenEvent | ReconsideringEvent | VerdictEvent | DoneEvent | ErrorEvent
)


def extract_answer_from_events(events: list[SeanceEvent]) -> str:
    """Extract final text response from an event sequence.

    Any tokens emitted prior to the last ReconsideringEvent are discarded.
    """
    tokens: list[str] = []
    for ev in events:
        if isinstance(ev, ReconsideringEvent):
            tokens.clear()
        elif isinstance(ev, TokenEvent):
            tokens.append(ev.token)
    return "".join(tokens)


class Seance:
    """Orchestrates retrieval gate, model generation, and guarded verification."""

    def __init__(
        self,
        backend: Backend | None = None,
        *,
        min_score: float | None = None,
    ) -> None:
        self.backend = backend
        self.min_score = min_score

    def ask(
        self,
        question: str,
        repo_path: Path | str,
        *,
        mode: Literal["guarded", "raw"] = "guarded",
        backend_name: str | None = None,
        backend: Backend | None = None,
        k: int = 8,
        min_score: float | None = None,
    ) -> Iterator[SeanceEvent]:
        """Execute the 3-stage honesty pipeline streaming typed SSE events."""
        resolved_repo = Path(repo_path).resolve()

        # Validate git repository
        try:
            check_git_repo(resolved_repo)
        except (GitError, Exception) as err:
            yield ErrorEvent(
                message=f"Directory '{resolved_repo}' is not a valid git repository: {err}"
            )
            yield DoneEvent(mode=mode, retries=0, disclaimer=GHOST_DISCLAIMER)
            return

        # Stage 1: Retrieval Gate
        try:
            evidence = retrieve(question, resolved_repo, k=k)
        except Exception as err:
            yield ErrorEvent(message=f"Failed to retrieve evidence: {err}")
            yield DoneEvent(mode=mode, retries=0, disclaimer=GHOST_DISCLAIMER)
            return

        yield EvidenceEvent(evidence=evidence)

        effective_threshold = (
            min_score
            if min_score is not None
            else (self.min_score if self.min_score is not None else settings.min_score)
        )
        gate_ok, refusal_msg = check_retrieval_gate(evidence, min_score=effective_threshold)

        if not gate_ok:
            yield TokenEvent(token=refusal_msg)
            yield DoneEvent(mode=mode, retries=0, disclaimer=GHOST_DISCLAIMER)
            return

        # Resolve active backend
        active_backend: Backend
        if backend is not None:
            active_backend = backend
        elif self.backend is not None:
            active_backend = self.backend
        elif backend_name is not None:
            try:
                active_backend = get_backend(backend_name)
            except Exception as err:
                yield ErrorEvent(message=f"Failed to initialize backend '{backend_name}': {err}")
                yield DoneEvent(mode=mode, retries=0, disclaimer=GHOST_DISCLAIMER)
                return
        else:
            try:
                active_backend = get_backend(settings.backend)
            except Exception as err:
                yield ErrorEvent(
                    message=f"Failed to initialize default backend '{settings.backend}': {err}"
                )
                yield DoneEvent(mode=mode, retries=0, disclaimer=GHOST_DISCLAIMER)
                return

        # Stage 2: Initial Generation & Verification
        repo_name = resolved_repo.name
        messages = build_seance_prompt(question, evidence, repo_name=repo_name)

        pass1_tokens: list[str] = []
        try:
            for chunk in active_backend.generate(messages, max_new_tokens=512, temperature=0.0):
                pass1_tokens.append(chunk)
                yield TokenEvent(token=chunk)
        except (BackendError, Exception) as err:
            yield ErrorEvent(message=f"Backend generation failed: {err}")
            yield DoneEvent(mode=mode, retries=0, disclaimer=GHOST_DISCLAIMER)
            return

        pass1_text = "".join(pass1_tokens)
        pass1_verdict = verify(pass1_text, evidence, repo_path=resolved_repo)

        # Check if model correctly initiated refusal
        if pass1_text.strip() == GHOST_REFUSAL_MESSAGE:
            yield VerdictEvent(verdict=pass1_verdict)
            yield DoneEvent(mode=mode, retries=0, disclaimer=GHOST_DISCLAIMER)
            return

        # Raw Mode: Passthrough without retry or repair
        if mode == "raw":
            yield VerdictEvent(verdict=pass1_verdict)
            yield DoneEvent(mode="raw", retries=0, disclaimer=GHOST_DISCLAIMER)
            return

        # Stage 3: Guarded Remediation
        if pass1_verdict.is_fully_verified and pass1_verdict.sentences:
            # Pass 1 was completely clean
            if GHOST_DISCLAIMER not in pass1_text:
                yield TokenEvent(token=f"\n\n{GHOST_DISCLAIMER}")
            yield VerdictEvent(verdict=pass1_verdict)
            yield DoneEvent(mode="guarded", retries=0, disclaimer=GHOST_DISCLAIMER)
            return

        # Violations detected -> emit ReconsideringEvent and retry
        yield ReconsideringEvent(violations=pass1_verdict.violations)

        retry_messages = build_retry_messages(messages, pass1_text, pass1_verdict.violations)
        try:
            pass2_tokens: list[str] = list(
                active_backend.generate(retry_messages, max_new_tokens=512, temperature=0.0)
            )
            pass2_text = "".join(pass2_tokens)
        except (BackendError, Exception) as err:
            yield ErrorEvent(message=f"Backend generation retry failed: {err}")
            yield DoneEvent(mode="guarded", retries=1, disclaimer=GHOST_DISCLAIMER)
            return

        # Check if Pass 2 replied with refusal
        if pass2_text.strip() == GHOST_REFUSAL_MESSAGE:
            yield TokenEvent(token=GHOST_REFUSAL_MESSAGE)
            pass2_verdict = verify(pass2_text, evidence, repo_path=resolved_repo)
            yield VerdictEvent(verdict=pass2_verdict)
            yield DoneEvent(mode="guarded", retries=1, disclaimer=GHOST_DISCLAIMER)
            return

        pass2_verdict = verify(pass2_text, evidence, repo_path=resolved_repo)

        # Sub-branch: Pass 2 Clean
        if pass2_verdict.is_fully_verified and pass2_verdict.sentences:
            yield TokenEvent(token=pass2_text)
            if GHOST_DISCLAIMER not in pass2_text:
                yield TokenEvent(token=f"\n\n{GHOST_DISCLAIMER}")
            yield VerdictEvent(verdict=pass2_verdict)
            yield DoneEvent(mode="guarded", retries=1, disclaimer=GHOST_DISCLAIMER)
            return

        # Sub-branch: Violations Persist -> Guarded Repair
        verified_sentences = [s for s in pass2_verdict.sentences if s.status == "verified"]

        if not verified_sentences:
            # Fallback to silence
            yield TokenEvent(token=GHOST_REFUSAL_MESSAGE)
            refusal_verdict = verify(GHOST_REFUSAL_MESSAGE, evidence, repo_path=resolved_repo)
            yield VerdictEvent(verdict=refusal_verdict)
            yield DoneEvent(mode="guarded", retries=1, disclaimer=GHOST_DISCLAIMER)
            return

        # Retain only verified sentences
        repaired_text = " ".join(s.text for s in verified_sentences)
        yield TokenEvent(token=repaired_text)
        yield TokenEvent(token=f"\n\n{GHOST_DISCLAIMER}")

        full_repaired = f"{repaired_text}\n\n{GHOST_DISCLAIMER}"
        repaired_verdict = verify(full_repaired, evidence, repo_path=resolved_repo)
        yield VerdictEvent(verdict=repaired_verdict)
        yield DoneEvent(mode="guarded", retries=1, disclaimer=GHOST_DISCLAIMER)


def ask(
    question: str,
    repo_path: Path | str,
    *,
    mode: Literal["guarded", "raw"] = "guarded",
    backend_name: str | None = None,
    backend: Backend | None = None,
    k: int = 8,
    min_score: float | None = None,
) -> Iterator[SeanceEvent]:
    """Convenience function delegating to Seance().ask(...)."""
    return Seance(backend=backend, min_score=min_score).ask(
        question=question,
        repo_path=repo_path,
        mode=mode,
        backend_name=backend_name,
        backend=backend,
        k=k,
        min_score=min_score,
    )
