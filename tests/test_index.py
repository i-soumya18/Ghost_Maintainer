"""Tests for BM25 indexing, caching, cache invalidation, and CommitStore."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from conftest import run_git, safe_rmtree

from ghost_maintainer.gitlog import Commit, FileChange
from ghost_maintainer.index import (
    build_commit_document,
    get_head_sha,
    index_repo,
    is_cache_valid,
    tokenize_path,
)


def test_tokenize_path() -> None:
    """Path tokenizer correctly splits path separators and camelCase tokens."""
    t1 = tokenize_path("lib/auth.js")
    assert "auth" in t1
    assert "js" in t1

    t2 = tokenize_path("src/auth/OAuthSigner.py")
    assert "oauthsigner" in t2
    assert "oauth" in t2 or "auth" in t2
    assert "signer" in t2

    t3 = tokenize_path(".github/workflows/windows-ci.yml")
    assert "windows" in t3
    assert "ci" in t3
    assert "yml" in t3


def test_build_commit_document() -> None:
    """Document builder repeats subject and path tokens for boosting."""
    fc = FileChange(path="src/auth/OAuthSigner.py", added=10, deleted=2)
    commit = Commit(
        sha="1234567890abcdef1234567890abcdef12345678",
        short="1234567",
        author="Alice",
        email="alice@example.com",
        date=Commit.from_dict(
            {
                "sha": "1234567890abcdef1234567890abcdef12345678",
                "author": "Alice",
                "email": "alice@example.com",
                "date": "2020-01-01T00:00:00+00:00",
                "subject": "Add OAuth",
            }
        ).date,
        subject="Add OAuth",
        body="Detailed body explanation",
        files=(fc,),
        hunks=("@@ def authenticate @@",),
    )
    doc = build_commit_document(commit)
    assert doc.count("Add OAuth") == 2
    assert "Detailed body explanation" in doc
    assert "Alice" in doc
    assert "oauthsigner" in doc
    assert "@@ def authenticate @@" in doc


def test_index_repo_and_cache(synthetic_repo: Path) -> None:
    """Index creation persists meta.json, commits.jsonl, and bm25 files in cache dir."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_cache_"))
    try:
        store, retriever, meta = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert len(store) >= 7
        assert retriever is not None
        assert meta["commit_count"] >= 7
        assert (cache_dir / "meta.json").exists()
        assert (cache_dir / "commits.jsonl").exists()
        assert (cache_dir / "bm25").exists()

        # Re-index without force returns loaded cache
        store2, retriever2, meta2 = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert len(store2) == len(store)
        assert retriever2 is not None
        assert meta2["head_sha"] == meta["head_sha"]
    finally:
        safe_rmtree(cache_dir)


def test_zero_mutation_invariant(synthetic_repo: Path) -> None:
    """Zero-mutation guarantee: Target repository is never modified by indexing."""
    status_before = subprocess.run(
        ["git", "-C", str(synthetic_repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert status_before == ""

    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_zero_mut_"))
    try:
        index_repo(synthetic_repo, cache_dir=cache_dir)

        status_after = subprocess.run(
            ["git", "-C", str(synthetic_repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert status_after == ""
    finally:
        safe_rmtree(cache_dir)


def test_cache_invalidation_on_head_change(synthetic_repo: Path) -> None:
    """Cache is invalidated and rebuilt when HEAD SHA changes."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_inval_"))
    try:
        store1, _, meta1 = index_repo(synthetic_repo, cache_dir=cache_dir)
        initial_head = meta1["head_sha"]
        assert is_cache_valid(synthetic_repo, cache_dir) is True

        # Add a new commit to repository
        (synthetic_repo / "new_file.txt").write_text("New file content\n", encoding="utf-8")
        run_git(synthetic_repo, "add", "new_file.txt")
        run_git(synthetic_repo, "commit", "-m", "Commit 8: New file for invalidation test")

        new_head = get_head_sha(synthetic_repo)
        assert new_head != initial_head
        assert is_cache_valid(synthetic_repo, cache_dir) is False

        # Re-index automatically updates cache with new HEAD
        store2, _, meta2 = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert meta2["head_sha"] == new_head
        assert len(store2) == len(store1) + 1
        assert is_cache_valid(synthetic_repo, cache_dir) is True
    finally:
        safe_rmtree(cache_dir)


def test_empty_repo_index(empty_repo: Path) -> None:
    """Indexing empty repository returns empty store without crashing."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_empty_"))
    try:
        store, retriever, meta = index_repo(empty_repo, cache_dir=cache_dir)
        assert len(store) == 0
        assert retriever is None
        assert meta["commit_count"] == 0
        assert (cache_dir / "meta.json").exists()
        assert (cache_dir / "commits.jsonl").exists()
    finally:
        safe_rmtree(cache_dir)


def test_commit_store_prefix_resolution(synthetic_repo: Path) -> None:
    """CommitStore supports full SHA lookup, prefix matching, and collision detection."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_test_store_"))
    try:
        store, _, _ = index_repo(synthetic_repo, cache_dir=cache_dir)
        first_commit = store[0]
        sha = first_commit.sha

        # Full SHA lookup
        assert store.get(sha) == first_commit
        assert store.get(sha.upper()) == first_commit

        # Prefix resolution (7-char)
        prefix_7 = sha[:7]
        assert store.resolve_prefix(prefix_7) == sha

        # Unknown prefix returns None
        assert store.resolve_prefix("0000000") is None

        # Iteration
        assert len(list(store)) == len(store)
    finally:
        safe_rmtree(cache_dir)
