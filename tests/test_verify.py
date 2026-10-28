"""Hermetic unit and integration tests for post-generation verifier."""

from __future__ import annotations

from pathlib import Path

from ghost_maintainer.config import GHOST_DISCLAIMER, GHOST_REFUSAL_MESSAGE
from ghost_maintainer.gitlog import Commit, FileChange
from ghost_maintainer.index import CommitStore
from ghost_maintainer.retrieve import retrieve
from ghost_maintainer.verify import (
    audit_bare_hex,
    compute_support_hint,
    extract_citations,
    resolve_commit,
    split_sentences,
    verify,
)


def test_sentence_splitting_edge_cases() -> None:
    """Verify sentence splitting handles versions, abbreviations, code spans, and paths."""
    text = (
        "We released v1.2.3 in 2020. "
        "The file lib/auth.js was modified e.g. for OAuth support. "
        "See `config.sub.method()` for details! "
        "Was this deprecated in 2.88.2? "
        "Yes, we replaced it... [3f2a9c1]."
    )
    sentences = split_sentences(text)
    assert len(sentences) == 5
    assert sentences[0] == "We released v1.2.3 in 2020."
    assert sentences[1] == "The file lib/auth.js was modified e.g. for OAuth support."
    assert sentences[2] == "See `config.sub.method()` for details!"
    assert sentences[3] == "Was this deprecated in 2.88.2?"
    assert sentences[4] == "Yes, we replaced it... [3f2a9c1]."


def test_extract_citations() -> None:
    """Verify lowercase bracketed commit hash extraction."""
    text = "We touched auth in [3F2A9C1] and later refactored in [a1b2c3d4e5f6]."
    cites = extract_citations(text)
    assert cites == ["3f2a9c1", "a1b2c3d4e5f6"]


def test_audit_bare_hex() -> None:
    """Verify detection of bare unbracketed commit hashes."""
    # Mixed digits and hex characters
    text1 = "In commit 3f2a9c1 we removed request."
    bare1 = audit_bare_hex(text1)
    assert "3f2a9c1" in bare1

    # Bracketed citation should NOT be flagged as bare hex
    text2 = "We removed request [3f2a9c1]."
    bare2 = audit_bare_hex(text2)
    assert len(bare2) == 0

    # Normal non-hex words should NOT be flagged
    text3 = "This is a regular statement about documentation and features."
    bare3 = audit_bare_hex(text3)
    assert len(bare3) == 0


def test_verify_clean_grounded_response(synthetic_repo: Path) -> None:
    """Verify fully grounded response against synthetic repository evidence."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    assert len(evidence) > 0

    top_sha = evidence[0].commit.short
    text = f"We deprecated the request library in favor of native fetch [{top_sha}]."

    res = verify(text, evidence, repo_path=synthetic_repo)
    assert res.is_fully_verified is True
    assert len(res.violations) == 0
    assert len(res.sentences) == 1
    assert res.sentences[0].status == "verified"
    assert res.sentences[0].citations[0].exists is True
    assert res.sentences[0].citations[0].grounded is True
    assert res.sentences[0].support_hint > 0.0


def test_verify_hallucinated_hash(synthetic_repo: Path) -> None:
    """Verify detection and violation recording for non-existent commit hashes."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    text = "We overhauled the core storage subsystem in [deadbeef01]."

    res = verify(text, evidence, repo_path=synthetic_repo)
    assert res.is_fully_verified is False
    assert len(res.violations) == 1
    assert "does not exist in repository history" in res.violations[0]
    assert res.sentences[0].status == "unverified"
    assert res.sentences[0].citations[0].exists is False
    assert res.sentences[0].citations[0].grounded is False


def test_verify_ungrounded_real_hash(synthetic_repo: Path) -> None:
    """Verify detection when a cited commit exists in the repo but not in retrieved evidence."""
    all_evidence = retrieve("Mikeal Rogers", synthetic_repo, k=8)
    assert len(all_evidence) >= 2

    # Restrict evidence to just the first item
    top_evidence = [all_evidence[0]]
    excluded_sha = all_evidence[1].commit.short

    text = f"We made additional changes in commit [{excluded_sha}]."
    res = verify(text, top_evidence, repo_path=synthetic_repo)
    assert res.is_fully_verified is False
    assert len(res.violations) >= 1
    assert "was NOT in the provided EVIDENCE" in res.violations[0]
    assert res.sentences[0].status == "unverified"
    assert res.sentences[0].citations[0].exists is True
    assert res.sentences[0].citations[0].grounded is False


def test_verify_bare_hex_violation(synthetic_repo: Path) -> None:
    """Verify bare unbracketed commit hash results in unverified sentence status."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    text = f"We removed the request dependency in {top_sha}."
    res = verify(text, evidence, repo_path=synthetic_repo)
    assert res.is_fully_verified is False
    assert res.sentences[0].status == "unverified"
    assert any("bare unbracketed commit hash" in v for v in res.violations)


def test_verify_uncited_factual_sentence(synthetic_repo: Path) -> None:
    """Verify uncited factual assertions are flagged."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    text = "We completely rebuilt the user authentication flow."

    res = verify(text, evidence, repo_path=synthetic_repo)
    assert res.is_fully_verified is False
    assert res.sentences[0].status == "uncited"
    assert any("without citations" in v for v in res.violations)


def test_verify_boilerplate_exempt(synthetic_repo: Path) -> None:
    """Verify disclaimer and refusal boilerplate strings are exempt from citation requirements."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.short

    text = f"We deprecated the request library [{top_sha}].\n\n{GHOST_DISCLAIMER}"
    res = verify(text, evidence, repo_path=synthetic_repo)
    assert res.is_fully_verified is True
    assert len(res.sentences) == 2
    assert res.sentences[0].status == "verified"
    assert res.sentences[1].status == "verified"
    assert res.sentences[1].support_hint == 1.0

    # Test refusal sentence exemption
    res_refusal = verify(GHOST_REFUSAL_MESSAGE, evidence, repo_path=synthetic_repo)
    assert res_refusal.is_fully_verified is True
    assert res_refusal.sentences[0].status == "verified"
    assert res_refusal.sentences[0].support_hint == 1.0


def test_verify_empty_response(synthetic_repo: Path) -> None:
    """Verify empty response returns unverified result with violation."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    res = verify("", evidence, repo_path=synthetic_repo)
    assert res.is_fully_verified is False
    assert res.violations == ("Response is empty.",)


def test_verify_support_hint_lexical_overlap() -> None:
    """Verify lexical support hint calculation accurately measures token overlap."""
    commit = Commit(
        sha="1111111111111111111111111111111111111111",
        short="1111111",
        author="Alice",
        email="alice@example.com",
        date="2020-01-01",  # type: ignore[arg-type]
        subject="Add OAuth authentication handler",
        body="Support bearer tokens and token refresh.",
        files=(FileChange(path="OAuthSigner.py", added=10, deleted=0),),
        hunks=("@@ def authenticate @@",),
    )

    # High overlap sentence
    high_sent = "We added OAuth authentication and bearer tokens [1111111]."
    overlap_high = compute_support_hint(high_sent, [commit])
    assert overlap_high >= 0.4

    # Disjoint sentence
    disjoint_sent = "The weather was cloudy and raining in Seattle [1111111]."
    overlap_disjoint = compute_support_hint(disjoint_sent, [commit])
    assert overlap_disjoint == 0.0


def test_two_tier_git_fallback(synthetic_repo: Path) -> None:
    """Verify git cat-file fallback resolves commit existence without CommitStore."""
    evidence = retrieve("deprecated request", synthetic_repo, k=3)
    top_sha = evidence[0].commit.sha

    exists, resolved = resolve_commit(
        top_sha[:7],
        commit_store=None,
        repo_path=synthetic_repo,
    )
    assert exists is True
    assert resolved == top_sha.lower()

    # Non-existent hash
    fake_exists, fake_resolved = resolve_commit(
        "deadbeef01",
        commit_store=None,
        repo_path=synthetic_repo,
    )
    assert fake_exists is False
    assert fake_resolved is None


def test_verify_prefix_collision() -> None:
    """Verify ambiguous short commit prefixes that match multiple commits are rejected."""
    c1 = Commit(
        sha="aabbcc1111111111111111111111111111111111",
        short="aabbcc1",
        author="Dev 1",
        email="d1@example.com",
        date="2020-01-01",  # type: ignore[arg-type]
        subject="Commit 1",
        body="",
        files=(),
        hunks=(),
    )
    c2 = Commit(
        sha="aabbcc2222222222222222222222222222222222",
        short="aabbcc2",
        author="Dev 2",
        email="d2@example.com",
        date="2020-01-02",  # type: ignore[arg-type]
        subject="Commit 2",
        body="",
        files=(),
        hunks=(),
    )
    store = CommitStore([c1, c2])

    # Ambiguous 6-char prefix
    exists, resolved = resolve_commit("aabbcc", commit_store=store)
    assert exists is False
    assert resolved is None

    # Unambiguous 7-char prefix
    exists1, resolved1 = resolve_commit("aabbcc1", commit_store=store)
    assert exists1 is True
    assert resolved1 == c1.sha.lower()
