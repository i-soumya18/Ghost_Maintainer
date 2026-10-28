"""Tests for evidence retrieval engine and retrieval gate."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from conftest import safe_rmtree

from ghost_maintainer.config import GHOST_REFUSAL_MESSAGE
from ghost_maintainer.gitlog import Commit
from ghost_maintainer.retrieve import Evidence, check_retrieval_gate, retrieve


def test_retrieve_ranked_evidence(synthetic_repo: Path) -> None:
    """Retrieve returns ranked Evidence instances with tags and descending scores."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_ret_"))
    try:
        results = retrieve("why was request deprecated", synthetic_repo, k=5, cache_dir=cache_dir)
        assert len(results) > 0
        assert results[0].tag == "E1"
        assert "Deprecate request" in results[0].commit.subject
        assert results[0].score > 0.0

        # Check descending scores
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score
            assert results[i].tag == f"E{i + 1}"
    finally:
        safe_rmtree(cache_dir)


def test_retrieve_path_and_hunk_matching(synthetic_repo: Path) -> None:
    """Retrieve matches file paths and function signatures from hunks."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_ret_path_"))
    try:
        results = retrieve("OAuthSigner authenticate", synthetic_repo, k=3, cache_dir=cache_dir)
        assert len(results) > 0
        top_subjects = [e.commit.subject for e in results]
        assert any("OAuth" in s or "auth" in s.lower() for s in top_subjects)
    finally:
        safe_rmtree(cache_dir)


def test_retrieve_clamping_k(synthetic_repo: Path) -> None:
    """Requesting k larger than corpus size is clamped without bm25s exception."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_clamp_"))
    try:
        # Request k=50 on a ~7 commit repository
        results = retrieve("auth", synthetic_repo, k=50, cache_dir=cache_dir)
        assert len(results) <= 7
    finally:
        safe_rmtree(cache_dir)


def test_retrieve_stopword_and_empty_query(synthetic_repo: Path) -> None:
    """Empty queries or stopword-only queries return empty list."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_empty_q_"))
    try:
        assert retrieve("", synthetic_repo, cache_dir=cache_dir) == []
        assert retrieve("   ", synthetic_repo, cache_dir=cache_dir) == []
        assert retrieve("why did they do this", synthetic_repo, cache_dir=cache_dir) == []
    finally:
        safe_rmtree(cache_dir)


def test_retrieve_empty_repo(empty_repo: Path) -> None:
    """Retrieval on an empty repository returns empty list cleanly."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_empty_repo_"))
    try:
        results = retrieve("anything", empty_repo, cache_dir=cache_dir)
        assert results == []
    finally:
        safe_rmtree(cache_dir)


def test_retrieval_gate() -> None:
    """Retrieval gate refuses when evidence is empty or top score below threshold."""
    # Empty evidence
    ok, msg = check_retrieval_gate([], min_score=0.8)
    assert ok is False
    assert msg == GHOST_REFUSAL_MESSAGE

    # Dummy commit for gate check
    c = Commit(
        sha="abcdef0123456789abcdef0123456789abcdef01",
        short="abcdef0",
        author="Alice",
        email="alice@example.com",
        date=datetime.now(UTC),
        subject="Dummy",
        body="",
        files=(),
    )

    # Low score
    low_ev = [Evidence(tag="E1", commit=c, score=0.65)]
    ok, msg = check_retrieval_gate(low_ev, min_score=0.8)
    assert ok is False
    assert msg == GHOST_REFUSAL_MESSAGE

    # High score
    high_ev = [Evidence(tag="E1", commit=c, score=1.45)]
    ok, msg = check_retrieval_gate(high_ev, min_score=0.8)
    assert ok is True
    assert msg == ""
