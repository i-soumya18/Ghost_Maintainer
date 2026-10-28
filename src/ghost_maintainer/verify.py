"""Post-generation verifier for commit citations, existence, grounding, and support."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import bm25s

from ghost_maintainer.config import GHOST_DISCLAIMER, GHOST_REFUSAL_MESSAGE
from ghost_maintainer.gitlog import Commit
from ghost_maintainer.index import CommitStore
from ghost_maintainer.retrieve import Evidence

# Bracketed citation pattern: [short_sha] or [full_sha] (7 to 40 hex digits)
BRACKETED_CITE_RE = re.compile(r"\[([0-9a-fA-F]{7,40})\]")

# Word-boundary hex string candidate pattern
BARE_HEX_RE = re.compile(r"\b([0-9a-fA-F]{7,40})\b")

# Common abbreviations to prevent false sentence boundaries
ABBREVIATIONS: tuple[str, ...] = (
    "e.g.",
    "i.e.",
    "vs.",
    "etc.",
    "v.",
    "dr.",
    "mr.",
    "mrs.",
    "ms.",
    "dept.",
    "fig.",
    "al.",
    "approx.",
    "est.",
    "no.",
    "ref.",
    "feat.",
)

# Stopwords set for lexical overlap
_ENGLISH_STOPWORDS: frozenset[str] = frozenset(
    set(bm25s.stopwords.STOPWORDS_EN)
    | {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "were",
        "are",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "we",
        "our",
        "ours",
        "they",
        "their",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "which",
        "what",
        "who",
        "whom",
        "into",
        "through",
        "after",
    }
)


@dataclass(frozen=True, slots=True)
class CitationVerdict:
    """Verification verdict for an individual commit citation."""

    raw_hash: str
    resolved_sha: str | None
    exists: bool
    grounded: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_hash": self.raw_hash,
            "resolved_sha": self.resolved_sha,
            "exists": self.exists,
            "grounded": self.grounded,
        }


@dataclass(frozen=True, slots=True)
class SentenceVerdict:
    """Verification verdict for an individual sentence."""

    text: str
    citations: tuple[CitationVerdict, ...]
    status: Literal["verified", "unverified", "uncited"]
    support_hint: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "citations": [c.to_dict() for c in self.citations],
            "status": self.status,
            "support_hint": self.support_hint,
        }


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Aggregated verification result for an entire model response."""

    sentences: tuple[SentenceVerdict, ...]
    is_fully_verified: bool
    violations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentences": [s.to_dict() for s in self.sentences],
            "is_fully_verified": self.is_fully_verified,
            "violations": list(self.violations),
        }


def split_sentences(text: str) -> list[str]:
    """Split text into sentences with awareness of abbreviations, versions, and code spans.

    Protects:
        - Inline code spans: `...`
        - Known abbreviations: e.g., i.e., vs., etc.
        - Versions and decimal numbers: v1.2.3, 2.88.2, 0.8
        - File paths: lib/auth.js, README.md
        - Citations immediately trailing terminal punctuation: . [3f2a9c1]
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    # Sentinel characters (rare private use characters)
    SENTINEL_DOT = "\ue000"
    SENTINEL_EXCL = "\ue001"
    SENTINEL_QMARK = "\ue002"

    def mask_str(s: str) -> str:
        return s.replace(".", SENTINEL_DOT).replace("!", SENTINEL_EXCL).replace("?", SENTINEL_QMARK)

    # 1. Mask GHOST_DISCLAIMER so it stays as one sentence unit
    working = cleaned.replace(GHOST_DISCLAIMER, mask_str(GHOST_DISCLAIMER))

    # 2. Mask punctuation inside code spans
    def replace_code_span(match: re.Match[str]) -> str:
        return mask_str(match.group(0))

    working = re.sub(r"`[^`]+`", replace_code_span, working)

    # 3. Mask known abbreviations (case-insensitive)
    for abbrev in ABBREVIATIONS:
        pattern = re.compile(re.escape(abbrev), re.IGNORECASE)
        working = pattern.sub(mask_str(abbrev), working)

    # 4. Mask dots flanked by alphanumeric characters (v1.2.3, auth.js, 3.14)
    working = re.sub(
        r"(?<=[a-zA-Z0-9])\.(?=[a-zA-Z0-9])",
        SENTINEL_DOT,
        working,
    )

    # 5. Mask ellipses (...)
    working = working.replace("...", f"{SENTINEL_DOT}{SENTINEL_DOT}{SENTINEL_DOT}")

    # 5. Split sentences on terminal punctuation + whitespace,
    # except when immediately followed by a citation like [3f2a9c1]
    split_pattern = re.compile(r"(?<=[.!?])(?:\s+|\n+)(?![\[\(]?[0-9a-fA-F]{7,40}[\]\)])")

    raw_sentences = split_pattern.split(working)

    # 6. Unmask and clean
    def unmask_str(s: str) -> str:
        return s.replace(SENTINEL_DOT, ".").replace(SENTINEL_EXCL, "!").replace(SENTINEL_QMARK, "?")

    sentences: list[str] = []
    for s in raw_sentences:
        unmasked = unmask_str(s).strip()
        if unmasked:
            sentences.append(unmasked)

    return sentences


def extract_citations(text: str) -> list[str]:
    """Extract all bracketed commit hashes from text in lowercase."""
    return [m.group(1).lower() for m in BRACKETED_CITE_RE.finditer(text)]


def resolve_commit(
    raw_hash: str,
    commit_store: CommitStore | None = None,
    repo_path: Path | str | None = None,
    evidence_commits: Sequence[Commit] | None = None,
) -> tuple[bool, str | None]:
    """Resolve commit hash to full 40-char SHA via memory or git cat-file."""
    cleaned_hash = raw_hash.strip().lower()
    if len(cleaned_hash) < 7:
        return False, None

    # Check evidence commits first
    if evidence_commits:
        ev_matches = [
            c.sha.lower() for c in evidence_commits if c.sha.lower().startswith(cleaned_hash)
        ]
        if len(ev_matches) == 1:
            return True, ev_matches[0]
        if len(ev_matches) > 1:
            # Ambiguous within evidence
            return False, None

    # Tier 1: Fast in-memory CommitStore prefix lookup
    if commit_store is not None:
        resolved = commit_store.resolve_prefix(cleaned_hash)
        if resolved is not None:
            return True, resolved.lower()
        c = commit_store.get(cleaned_hash)
        if c is not None:
            return True, c.sha.lower()

    # Tier 2: Git fallback via rev-parse and cat-file -e with ^{commit}
    if repo_path is not None:
        resolved_repo = Path(repo_path).resolve()
        try:
            # rev-parse with ^{commit} ensures commit peel and outputs full 40-char SHA
            proc = subprocess.run(
                [
                    "git",
                    "-C",
                    str(resolved_repo),
                    "rev-parse",
                    "--verify",
                    "--quiet",
                    f"{cleaned_hash}^{{commit}}",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                full_sha = proc.stdout.strip().lower()
                # Secondary verification with git cat-file -e
                cat_proc = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(resolved_repo),
                        "cat-file",
                        "-e",
                        f"{full_sha}^{{commit}}",
                    ],
                    capture_output=True,
                    check=False,
                )
                if cat_proc.returncode == 0:
                    return True, full_sha
        except Exception:
            pass

    return False, None


def audit_bare_hex(
    text: str,
    commit_store: CommitStore | None = None,
    repo_path: Path | str | None = None,
    evidence_commits: Sequence[Commit] | None = None,
) -> list[str]:
    """Detect unbracketed bare commit hashes in text."""
    # Strip bracketed citations to isolate bare candidates
    unbracketed = BRACKETED_CITE_RE.sub(" ", text)

    bare_hashes: list[str] = []
    for match in BARE_HEX_RE.finditer(unbracketed):
        candidate = match.group(1).lower()

        # Case 1: Mixed digits and letters (e.g. 3f2a9c1, a1b2c3d) -> definite bare hex
        has_alpha = any(c in "abcdef" for c in candidate)
        has_digit = any(c.isdigit() for c in candidate)

        if has_alpha and has_digit:
            bare_hashes.append(candidate)
            continue

        # Case 2: Pure hex letters (e.g. deadbeef) or pure digits
        # Check against commit store / git
        exists, _ = resolve_commit(
            candidate,
            commit_store=commit_store,
            repo_path=repo_path,
            evidence_commits=evidence_commits,
        )
        if exists:
            bare_hashes.append(candidate)

    return bare_hashes


def compute_support_hint(
    sentence: str,
    commits: Sequence[Commit],
) -> float:
    """Compute word overlap ratio between sentence text and referenced commit text."""
    # Clean citations out of sentence
    sentence_clean = BRACKETED_CITE_RE.sub(" ", sentence).lower()
    sent_tokens = {
        tok
        for tok in re.findall(r"\b[a-zA-Z0-9_-]+\b", sentence_clean)
        if tok not in _ENGLISH_STOPWORDS and len(tok) >= 2
    }

    if not sent_tokens:
        clean_text = sentence.strip()
        if clean_text in (
            GHOST_DISCLAIMER,
            GHOST_REFUSAL_MESSAGE,
            "Voices are fiction.",
            "Evidence is real.",
        ):
            return 1.0
        return 0.0

    if not commits:
        return 0.0

    commit_tokens: set[str] = set()
    for c in commits:
        content = (
            f"{c.subject} {c.body} " + " ".join(f.path for f in c.files) + " " + " ".join(c.hunks)
        )
        for tok in re.findall(r"\b[a-zA-Z0-9_-]+\b", content.lower()):
            if tok not in _ENGLISH_STOPWORDS and len(tok) >= 2:
                commit_tokens.add(tok)

    if not commit_tokens:
        return 0.0

    overlap = len(sent_tokens & commit_tokens) / len(sent_tokens)
    return round(min(1.0, max(0.0, overlap)), 3)


def verify(
    text: str,
    evidence: Sequence[Evidence],
    repo_path: Path | str | None = None,
    commit_store: CommitStore | None = None,
) -> VerificationResult:
    """Verify an entire model response against retrieved evidence and repository history."""
    clean_text = text.strip()
    if not clean_text:
        return VerificationResult(
            sentences=(),
            is_fully_verified=False,
            violations=("Response is empty.",),
        )

    # Build lookup maps from evidence
    evidence_commits = [ev.commit for ev in evidence]
    evidence_map: dict[str, Commit] = {ev.commit.sha.lower(): ev.commit for ev in evidence}
    grounded_shas: set[str] = set(evidence_map.keys())

    sentences = split_sentences(clean_text)
    sentence_verdicts: list[SentenceVerdict] = []
    violations: list[str] = []

    for s_text in sentences:
        s_clean = s_text.strip()

        # Check for boilerplate sentences
        if s_clean in (
            GHOST_DISCLAIMER,
            GHOST_REFUSAL_MESSAGE,
            "Voices are fiction.",
            "Evidence is real.",
        ):
            sentence_verdicts.append(
                SentenceVerdict(
                    text=s_clean,
                    citations=(),
                    status="verified",
                    support_hint=1.0,
                )
            )
            continue

        raw_cites = extract_citations(s_clean)
        bare_hashes = audit_bare_hex(
            s_clean,
            commit_store=commit_store,
            repo_path=repo_path,
            evidence_commits=evidence_commits,
        )

        citation_verdicts: list[CitationVerdict] = []
        cited_commits: list[Commit] = []
        has_invalid_citation = False

        for raw_h in raw_cites:
            exists, resolved_sha = resolve_commit(
                raw_h,
                commit_store=commit_store,
                repo_path=repo_path,
                evidence_commits=evidence_commits,
            )
            grounded = False

            if exists and resolved_sha is not None:
                grounded = resolved_sha in grounded_shas
                # Find commit object for lexical support hint
                c_obj = evidence_map.get(resolved_sha)
                if c_obj is None and commit_store is not None:
                    c_obj = commit_store.get(resolved_sha)
                if c_obj is not None:
                    cited_commits.append(c_obj)
            else:
                violations.append(f"Commit [{raw_h}] does not exist in repository history.")
                has_invalid_citation = True

            if exists and not grounded:
                violations.append(
                    f"Commit [{raw_h}] exists in repository history but was NOT in the provided EVIDENCE."
                )
                has_invalid_citation = True

            citation_verdicts.append(
                CitationVerdict(
                    raw_hash=raw_h,
                    resolved_sha=resolved_sha,
                    exists=exists,
                    grounded=grounded,
                )
            )

        # Audit bare unbracketed hashes
        has_bare_hex = bool(bare_hashes)
        for bh in bare_hashes:
            violations.append(
                f"Sentence contains bare unbracketed commit hash '{bh}': citations must be formatted as '[{bh}]'."
            )

        # Lexical support hint
        support_hint = compute_support_hint(s_clean, cited_commits)

        # Determine sentence status
        if citation_verdicts:
            if not has_invalid_citation and not has_bare_hex:
                status: Literal["verified", "unverified", "uncited"] = "verified"
            else:
                status = "unverified"
        else:
            if has_bare_hex:
                status = "unverified"
            else:
                status = "uncited"
                violations.append(
                    f"Sentence makes factual claims without citations: '{s_clean[:60]}...'."
                )

        sentence_verdicts.append(
            SentenceVerdict(
                text=s_clean,
                citations=tuple(citation_verdicts),
                status=status,
                support_hint=support_hint,
            )
        )

    is_fully_verified = len(violations) == 0 and all(
        sv.status == "verified" for sv in sentence_verdicts
    )

    return VerificationResult(
        sentences=tuple(sentence_verdicts),
        is_fully_verified=is_fully_verified,
        violations=tuple(violations),
    )
