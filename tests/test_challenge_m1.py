"""Empirical adversarial challenge suite for BM25 indexer, cache isolation, and retrieval engine.

This module stress-tests:
1. Strict read-only invariant (clean repo, dirty repo, read-only repo, failure injection, concurrent calls)
2. Cache invalidation (HEAD mutation, commit amends, branch switches, detached HEAD, cache corruption recovery)
3. BM25 edge queries (stopwords only, zero matching tokens, special regex/control characters, k bounds: k>N, k=0, k<0, empty)
4. Retrieval score threshold consistency (0.8 boundary conditions, custom min_score, gate behavior)
"""

from __future__ import annotations

import concurrent.futures
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import run_git, safe_rmtree

from ghost_maintainer.config import GHOST_REFUSAL_MESSAGE
from ghost_maintainer.gitlog import Commit
from ghost_maintainer.index import (
    get_head_sha,
    index_repo,
    is_cache_valid,
)
from ghost_maintainer.retrieve import Evidence, check_retrieval_gate, retrieve

# ==============================================================================
# CHALLENGE SUITE 1: STRICT READ-ONLY INVARIANT
# ==============================================================================


def test_challenge_read_only_clean_repo(synthetic_repo: Path) -> None:
    """Target repository must have zero changes before and after multiple aggressive indexing runs."""
    status_proc = subprocess.run(
        ["git", "-C", str(synthetic_repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert status_proc.stdout.strip() == "", "Repo initially dirty"

    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_readonly_"))
    try:
        # 1. First index
        index_repo(synthetic_repo, cache_dir=cache_dir)
        # 2. Second index (cache hit)
        index_repo(synthetic_repo, cache_dir=cache_dir)
        # 3. Third index (forced rebuild)
        index_repo(synthetic_repo, force=True, cache_dir=cache_dir)
        # 4. Retrieval queries
        retrieve("OAuth authentication", synthetic_repo, k=5, cache_dir=cache_dir)
        retrieve("Windows CI", synthetic_repo, k=5, cache_dir=cache_dir)

        # Verify git status remains completely empty
        status_after = subprocess.run(
            ["git", "-C", str(synthetic_repo), "status", "--porcelain", "--ignored"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert status_after == "", f"Target repo contaminated with files: {status_after}"
    finally:
        safe_rmtree(cache_dir)


def test_challenge_read_only_dirty_repo(synthetic_repo: Path) -> None:
    """Indexing a dirty working tree leaves uncommitted modifications untouched."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_dirty_"))
    try:
        # Create uncommitted modifications
        modified_file = synthetic_repo / "README.md"
        modified_file.write_text("Uncommitted modification line\n", encoding="utf-8")

        untracked_file = synthetic_repo / "untracked_test_artifact.tmp"
        untracked_file.write_text("Should remain untouched\n", encoding="utf-8")

        status_raw = subprocess.run(
            ["git", "-C", str(synthetic_repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        assert any("README.md" in line for line in status_raw.splitlines())
        assert any("untracked_test_artifact.tmp" in line for line in status_raw.splitlines())

        # Execute indexing and retrieval
        store, retriever, meta = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert len(store) >= 7
        assert retriever is not None

        retrieve("uncommitted modification", synthetic_repo, cache_dir=cache_dir)

        status_after = subprocess.run(
            ["git", "-C", str(synthetic_repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        assert status_after == status_raw, "Dirty working tree was altered by indexing!"
        assert modified_file.read_text(encoding="utf-8") == "Uncommitted modification line\n"
        assert untracked_file.read_text(encoding="utf-8") == "Should remain untouched\n"
    finally:
        safe_rmtree(cache_dir)


def test_challenge_read_only_error_midway(synthetic_repo: Path) -> None:
    """If an indexing failure occurs midway, target repository must remain completely pristine."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_err_"))
    try:
        # Simulate an exception midway through index_repo during tokenization
        with (
            patch("bm25s.tokenize", side_effect=RuntimeError("Simulated mid-index crash")),
            pytest.raises(RuntimeError, match="Simulated mid-index crash"),
        ):
            index_repo(synthetic_repo, cache_dir=cache_dir)

        # Check git status in target repo
        status = subprocess.run(
            ["git", "-C", str(synthetic_repo), "status", "--porcelain", "--ignored"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert status == "", f"Target repo corrupted during index failure: {status}"
    finally:
        safe_rmtree(cache_dir)


def test_challenge_concurrency_stress(synthetic_repo: Path) -> None:
    """Concurrent indexing and retrieval calls must maintain read-only invariant and stability."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_concurrent_"))
    try:

        def worker(idx: int) -> int:
            if idx % 2 == 0:
                store, _, _ = index_repo(synthetic_repo, cache_dir=cache_dir)
                return len(store)
            else:
                evs = retrieve("authentication jwt", synthetic_repo, k=4, cache_dir=cache_dir)
                return len(evs)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(16)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert all(r > 0 for r in results), f"Worker results failed: {results}"

        status_after = subprocess.run(
            ["git", "-C", str(synthetic_repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert status_after == "", "Target repo modified during concurrent indexing!"
    finally:
        safe_rmtree(cache_dir)


# ==============================================================================
# CHALLENGE SUITE 2: CACHE INVALIDATION & LIFECYCLE
# ==============================================================================


def test_challenge_cache_amend_commit(synthetic_repo: Path) -> None:
    """Amending the latest commit changes HEAD SHA and triggers cache invalidation and rebuild."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_amend_"))
    try:
        store1, _, meta1 = index_repo(synthetic_repo, cache_dir=cache_dir)
        old_head = meta1["head_sha"]
        old_count = meta1["commit_count"]
        assert is_cache_valid(synthetic_repo, cache_dir) is True

        # Amend latest commit with a different message and timestamp
        run_git(
            synthetic_repo,
            "commit",
            "--amend",
            "-m",
            "Deprecate request library in favor of native fetch [AMENDED-AUDIT]",
            author="Mikeal Rogers <mikeal.rogers@gmail.com>",
            date="2019-02-12T10:00:00+00:00",
        )

        new_head = get_head_sha(synthetic_repo)
        assert new_head != old_head, "HEAD SHA did not change after amend"
        assert is_cache_valid(synthetic_repo, cache_dir) is False

        # Rebuild cache
        store2, retriever2, meta2 = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert meta2["head_sha"] == new_head
        assert meta2["commit_count"] == old_count
        assert is_cache_valid(synthetic_repo, cache_dir) is True

        # Search for amended text
        results = retrieve("AMENDED-AUDIT", synthetic_repo, k=3, cache_dir=cache_dir)
        assert len(results) > 0
        assert "AMENDED-AUDIT" in results[0].commit.subject
    finally:
        safe_rmtree(cache_dir)


def test_challenge_cache_branch_switching(synthetic_repo: Path) -> None:
    """Switching between branches with distinct HEAD commits triggers reload vs rebuild."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_branch_"))
    try:
        # Index on main
        store_main, _, meta_main = index_repo(synthetic_repo, cache_dir=cache_dir)
        main_head = meta_main["head_sha"]

        # Create branch 'feature/exp' and commit new file
        run_git(synthetic_repo, "checkout", "-b", "feature/exp")
        (synthetic_repo / "exp.txt").write_text("Experimental quantum flux\n", encoding="utf-8")
        run_git(synthetic_repo, "add", "exp.txt")
        run_git(synthetic_repo, "commit", "-m", "Add experimental quantum flux module")

        branch_head = get_head_sha(synthetic_repo)
        assert branch_head != main_head
        assert is_cache_valid(synthetic_repo, cache_dir) is False

        # Index on feature/exp
        store_branch, _, meta_branch = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert meta_branch["head_sha"] == branch_head
        assert len(store_branch) == len(store_main) + 1
        assert is_cache_valid(synthetic_repo, cache_dir) is True

        # Switch back to main
        run_git(synthetic_repo, "checkout", "main")
        assert get_head_sha(synthetic_repo) == main_head
        assert is_cache_valid(synthetic_repo, cache_dir) is False

        # Re-index on main restores main cache: HEAD is main_head, and git log --all
        # retains all commits across all repo branches (including feature/exp)
        store_main2, _, meta_main2 = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert meta_main2["head_sha"] == main_head
        assert len(store_main2) == len(store_branch)
        assert is_cache_valid(synthetic_repo, cache_dir) is True
    finally:
        safe_rmtree(cache_dir)


def test_challenge_cache_detached_head(synthetic_repo: Path) -> None:
    """Detached HEAD is accurately detected, cached, and validated."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_detached_"))
    try:
        # Get SHA of 2nd commit
        store, _, _ = index_repo(synthetic_repo, cache_dir=cache_dir)
        target_commit = store[-2]
        target_sha = target_commit.sha

        # Detach HEAD to this commit
        run_git(synthetic_repo, "checkout", target_sha)
        current_head = get_head_sha(synthetic_repo)
        assert current_head == target_sha.lower()

        # Index detached HEAD
        store_detached, retriever_detached, meta_detached = index_repo(
            synthetic_repo, cache_dir=cache_dir
        )
        assert meta_detached["head_sha"] == target_sha.lower()
        assert is_cache_valid(synthetic_repo, cache_dir) is True

        # Return to main
        run_git(synthetic_repo, "checkout", "main")
        assert is_cache_valid(synthetic_repo, cache_dir) is False
    finally:
        safe_rmtree(cache_dir)


def test_challenge_cache_corruption_recovery(synthetic_repo: Path) -> None:
    """Index gracefully detects and recovers from damaged/corrupted cache artifacts."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_corrupt_"))
    try:
        index_repo(synthetic_repo, cache_dir=cache_dir)
        assert is_cache_valid(synthetic_repo, cache_dir) is True

        # Scenario A: Corrupted meta.json (truncated JSON)
        meta_file = cache_dir / "meta.json"
        meta_file.write_text("{ incomplete json ...", encoding="utf-8")
        assert is_cache_valid(synthetic_repo, cache_dir) is False
        store_rec, ret_rec, meta_rec = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert len(store_rec) >= 7
        assert ret_rec is not None
        assert is_cache_valid(synthetic_repo, cache_dir) is True

        # Scenario B: Missing bm25 folder
        bm25_dir = cache_dir / "bm25"
        safe_rmtree(bm25_dir)
        assert is_cache_valid(synthetic_repo, cache_dir) is False
        store_rec2, ret_rec2, _ = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert len(store_rec2) >= 7
        assert ret_rec2 is not None
        assert (cache_dir / "bm25").exists()

        # Scenario C: Missing commits.jsonl
        commits_file = cache_dir / "commits.jsonl"
        commits_file.unlink()
        assert is_cache_valid(synthetic_repo, cache_dir) is False
        store_rec3, ret_rec3, _ = index_repo(synthetic_repo, cache_dir=cache_dir)
        assert len(store_rec3) >= 7
        assert ret_rec3 is not None
        assert commits_file.exists()
    finally:
        safe_rmtree(cache_dir)


# ==============================================================================
# CHALLENGE SUITE 3: BM25 ADVERSARIAL EDGE QUERIES
# ==============================================================================


@pytest.mark.parametrize(
    "stopword_query",
    [
        "the",
        "and or if",
        "why did they do this to that",
        "in on at by with from as into through",
        "a an the is are was were be been being",
    ],
)
def test_challenge_bm25_stopwords_only(synthetic_repo: Path, stopword_query: str) -> None:
    """Queries composed strictly of English stopwords return empty list without crashing."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_sw_"))
    try:
        results = retrieve(stopword_query, synthetic_repo, cache_dir=cache_dir)
        assert results == [], (
            f"Expected empty list for stopword query '{stopword_query}', got {results}"
        )
    finally:
        safe_rmtree(cache_dir)


def test_challenge_bm25_zero_matching_tokens(synthetic_repo: Path) -> None:
    """Queries containing non-existent tokens return empty list cleanly."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_zero_"))
    try:
        results = retrieve(
            "zyxwvutsrqponmlkjihgfedcba supercalifragilistic12345 nonexistenttermxyz",
            synthetic_repo,
            cache_dir=cache_dir,
        )
        assert results == []
    finally:
        safe_rmtree(cache_dir)


@pytest.mark.parametrize(
    "regex_query",
    [
        r".*+?^${}()|[]\\",
        r"(?:[a-z]+|\d+)",
        r"^.*(?=.*[a-z])(?=.*[A-Z]).*$",
        r"[\w.-]+@[\w.-]+",
        r"/^https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}/",
        r"\b(def|class|return)\b",
        r"'; DROP TABLE commits; --",
        r"<script>alert('xss')</script>",
        "@@ -1,5 +1,6 @@ def authenticate",
    ],
)
def test_challenge_bm25_special_regex_and_punctuation(
    synthetic_repo: Path, regex_query: str
) -> None:
    """Special regex operators, SQL injection syntax, and hunk delimiters execute without error."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_regex_"))
    try:
        # Must execute without raising re.error or ValueError
        results = retrieve(regex_query, synthetic_repo, cache_dir=cache_dir)
        assert isinstance(results, list)
    finally:
        safe_rmtree(cache_dir)


def test_challenge_bm25_control_and_null_chars(synthetic_repo: Path) -> None:
    """Queries with control characters and null bytes are handled without unhandled exceptions."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_ctrl_"))
    try:
        query = "\x00\x01\x1e\x1f\t\r\n auth \x00"
        results = retrieve(query, synthetic_repo, cache_dir=cache_dir)
        assert isinstance(results, list)
        if results:
            assert any("auth" in r.commit.subject.lower() for r in results)
    finally:
        safe_rmtree(cache_dir)


def test_challenge_bm25_unicode_and_emojis(synthetic_repo: Path) -> None:
    """Queries containing unicode accents and emojis match indexed content or return gracefully."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_unicode_"))
    try:
        # Match French accented word in docs/café.md
        results_cafe = retrieve("café", synthetic_repo, k=5, cache_dir=cache_dir)
        assert len(results_cafe) > 0
        assert any(
            "docs" in r.commit.subject.lower() or "french" in r.commit.body.lower()
            for r in results_cafe
        )

        # Query with ghost emoji
        results_ghost = retrieve("ghost 👻", synthetic_repo, k=5, cache_dir=cache_dir)
        assert isinstance(results_ghost, list)
    finally:
        safe_rmtree(cache_dir)


@pytest.mark.parametrize("k_val", [0, -1, -100])
def test_challenge_bm25_k_zero_and_negative(synthetic_repo: Path, k_val: int) -> None:
    """k <= 0 must cleanly return empty list without attempting slice/index."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_kzero_"))
    try:
        results = retrieve("OAuth authentication", synthetic_repo, k=k_val, cache_dir=cache_dir)
        assert results == [], f"Expected [] for k={k_val}, got {results}"
    finally:
        safe_rmtree(cache_dir)


@pytest.mark.parametrize("k_val", [10, 50, 500, 10000])
def test_challenge_bm25_k_exceeding_corpus_size(synthetic_repo: Path, k_val: int) -> None:
    """k > len(corpus) is clamped safely to corpus size without bm25s IndexError/ValueError."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_kmax_"))
    try:
        results = retrieve("auth", synthetic_repo, k=k_val, cache_dir=cache_dir)
        assert len(results) <= 7
        assert len(results) > 0
        # Tags must be correctly numbered E1..En
        for i, ev in enumerate(results):
            assert ev.tag == f"E{i + 1}"
            assert ev.score > 0.0
    finally:
        safe_rmtree(cache_dir)


# ==============================================================================
# CHALLENGE SUITE 4: RETRIEVAL SCORE THRESHOLD CONSISTENCY (0.8 BOUNDARY)
# ==============================================================================


def test_challenge_score_boundary_precision() -> None:
    """Strict verification of the 0.8 retrieval gate score boundary."""
    dummy_commit = Commit(
        sha="0123456789abcdef0123456789abcdef01234567",
        short="0123456",
        author="Tester",
        email="tester@example.com",
        date=datetime.now(UTC),
        subject="Dummy",
        body="",
        files=(),
    )

    # 1. Just below threshold (0.7999999) -> must refuse
    ev_below = [Evidence(tag="E1", commit=dummy_commit, score=0.7999999)]
    ok_below, msg_below = check_retrieval_gate(ev_below, min_score=0.8)
    assert ok_below is False
    assert msg_below == GHOST_REFUSAL_MESSAGE

    # 2. Exactly at threshold (0.8000000) -> must pass
    ev_exact = [Evidence(tag="E1", commit=dummy_commit, score=0.8000000)]
    ok_exact, msg_exact = check_retrieval_gate(ev_exact, min_score=0.8)
    assert ok_exact is True
    assert msg_exact == ""

    # 3. Just above threshold (0.8000001) -> must pass
    ev_above = [Evidence(tag="E1", commit=dummy_commit, score=0.8000001)]
    ok_above, msg_above = check_retrieval_gate(ev_above, min_score=0.8)
    assert ok_above is True
    assert msg_above == ""

    # 4. Zero score -> must refuse
    ev_zero = [Evidence(tag="E1", commit=dummy_commit, score=0.0)]
    ok_zero, msg_zero = check_retrieval_gate(ev_zero, min_score=0.8)
    assert ok_zero is False
    assert msg_zero == GHOST_REFUSAL_MESSAGE

    # 5. Empty evidence -> must refuse
    ok_empty, msg_empty = check_retrieval_gate([], min_score=0.8)
    assert ok_empty is False
    assert msg_empty == GHOST_REFUSAL_MESSAGE

    # 6. Default min_score uses settings.min_score (0.8)
    ok_def_low, _ = check_retrieval_gate(ev_below)
    assert ok_def_low is False
    ok_def_high, _ = check_retrieval_gate(ev_above)
    assert ok_def_high is True

    # 7. Multiple evidence items: gate evaluates the TOP score (evidence[0])
    ev_multi = [
        Evidence(tag="E1", commit=dummy_commit, score=0.85),
        Evidence(tag="E2", commit=dummy_commit, score=0.45),
    ]
    ok_multi, _ = check_retrieval_gate(ev_multi, min_score=0.8)
    assert ok_multi is True

    ev_multi_fail = [
        Evidence(tag="E1", commit=dummy_commit, score=0.75),
        Evidence(tag="E2", commit=dummy_commit, score=0.30),
    ]
    ok_multi_fail, msg_mf = check_retrieval_gate(ev_multi_fail, min_score=0.8)
    assert ok_multi_fail is False
    assert msg_mf == GHOST_REFUSAL_MESSAGE


def test_challenge_retrieval_gate_end_to_end(synthetic_repo: Path) -> None:
    """End-to-end queries against synthetic repository test gate pass/refusal on real BM25 scores."""
    cache_dir = Path(tempfile.mkdtemp(prefix="ghost_chal_gate_e2e_"))
    try:
        # High relevance query -> top score should pass 0.8
        ev_pass = retrieve(
            "why was request deprecated native fetch", synthetic_repo, cache_dir=cache_dir
        )
        assert len(ev_pass) > 0
        assert ev_pass[0].score >= 0.8, f"Expected top score >= 0.8, got {ev_pass[0].score}"
        passed, reason = check_retrieval_gate(ev_pass)
        assert passed is True
        assert reason == ""

        # Unrelated query with zero matching tokens -> empty evidence -> gate refuses
        ev_unrelated = retrieve(
            "completely unrelated extraterrestrial galaxy", synthetic_repo, cache_dir=cache_dir
        )
        assert ev_unrelated == []
        passed, reason = check_retrieval_gate(ev_unrelated)
        assert passed is False
        assert reason == GHOST_REFUSAL_MESSAGE
    finally:
        safe_rmtree(cache_dir)
