"""Adversarial stress tests for git log archaeology streaming parser and commit models.

Empirically tests:
1. Extremely large commit bodies / subjects and delimiter injection.
2. Deep nested paths, unicode characters, spaces, and special characters.
3. Massive diffs (>100 files, >1000 hunks) and hunk capping at 20.
4. Complex branch histories: octopus merges, cherry-picks, detached HEAD, empty commits, binary diffs.
5. Parser throughput, memory footprint, and read-only worktree preservation.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import tracemalloc
from collections.abc import Generator
from pathlib import Path

import pytest

from ghost_maintainer.gitlog import (
    Commit,
    FileChange,
    extract_hunk_contexts,
    get_commits,
    is_empty_repo,
    parse_git_log,
)
from tests.conftest import run_git, safe_rmtree


@pytest.fixture
def stress_repo() -> Generator[Path, None, None]:
    """Temporary repository for adversarial stress testing."""
    temp_dir = Path(tempfile.mkdtemp(prefix="ghost_stress_repo_"))
    try:
        run_git(temp_dir, "init", "-b", "main")
        run_git(temp_dir, "config", "core.quotepath", "false")
        run_git(temp_dir, "config", "user.name", "Stress Tester")
        run_git(temp_dir, "config", "user.email", "stress@example.com")
        yield temp_dir
    finally:
        safe_rmtree(temp_dir)


def test_adversarial_large_commit_body_and_subject(stress_repo: Path) -> None:
    """Commit with extreme subject length, 2MB body, and record separator delimiters."""
    # Commit 1: Extreme subject (5,000 characters)
    huge_subject = "A" * 5000
    (stress_repo / "file1.txt").write_text("initial content\n", encoding="utf-8")
    run_git(stress_repo, "add", "file1.txt")
    run_git(stress_repo, "commit", "-m", huge_subject)

    # Commit 2: 2MB commit body (20,000 lines)
    body_lines = [f"Line {i}: Details regarding architectural refactoring and deprecations." for i in range(20000)]
    huge_body = "\n".join(body_lines)
    (stress_repo / "file2.txt").write_text("another file\n", encoding="utf-8")
    run_git(stress_repo, "add", "file2.txt")
    # Commit using file to avoid command-line length limits on Windows
    msg_file = stress_repo / ".git_msg_temp.txt"
    msg_file.write_text(f"Large body commit\n\n{huge_body}\n", encoding="utf-8")
    try:
        run_git(stress_repo, "commit", "-F", str(msg_file))
    finally:
        if msg_file.exists():
            msg_file.unlink()

    # Commit 3: Delimiter injection (0x1e Record Separator and 0x1f Unit Separator in body)
    (stress_repo / "file3.txt").write_text("delimiter test\n", encoding="utf-8")
    run_git(stress_repo, "add", "file3.txt")
    msg_file = stress_repo / ".git_msg_temp.txt"
    adversarial_msg = "Subject with \x1f US delimiter\n\nBody containing \x1e RS and \x1f US delimiters repeatedly."
    msg_file.write_text(adversarial_msg, encoding="utf-8")
    try:
        run_git(stress_repo, "commit", "-F", str(msg_file))
    finally:
        if msg_file.exists():
            msg_file.unlink()

    # Parse and verify
    commits = get_commits(stress_repo)
    assert len(commits) >= 2  # Delimiter injection may split or pass cleanly, but MUST NOT crash

    # Find the large body commit
    large_commit = next((c for c in commits if c.subject == "Large body commit"), None)
    assert large_commit is not None
    assert len(large_commit.body) > 1_000_000
    assert "Line 19999" in large_commit.body

    # Find the huge subject commit
    subject_commit = next((c for c in commits if c.subject.startswith("AAAA")), None)
    assert subject_commit is not None
    assert len(subject_commit.subject) == 5000

    # Verify serialization roundtrip on large commit
    d = large_commit.to_dict()
    reconstructed = Commit.from_dict(d)
    assert reconstructed.sha == large_commit.sha
    assert len(reconstructed.body) == len(large_commit.body)


def test_adversarial_deep_unicode_and_special_paths(stress_repo: Path) -> None:
    """Deeply nested directories and paths with unicode, spaces, and punctuation."""
    # Deep path (12 levels deep)
    deep_dir = stress_repo
    for seg in ["level1", "level2", "level3", "level4", "level5", "level6", "level7", "level8", "level9", "level10"]:
        deep_dir = deep_dir / seg
    deep_dir.mkdir(parents=True, exist_ok=True)
    (deep_dir / "deep_module.py").write_text("def deep_fn():\n    return 42\n", encoding="utf-8")

    # Unicode directories and files
    unicode_dir = stress_repo / "каталог_юникод" / "مجلد_عربي" / "日本語ディレクトリ"
    unicode_dir.mkdir(parents=True, exist_ok=True)
    (unicode_dir / "файл_тест.txt").write_text("Russian content\n", encoding="utf-8")
    (unicode_dir / "ملف_عربي.txt").write_text("Arabic content\n", encoding="utf-8")
    (unicode_dir / "日本語_テスト.txt").write_text("Japanese content\n", encoding="utf-8")
    (unicode_dir / "emoji_👻_⚡_🔥.txt").write_text("Emoji presence\n", encoding="utf-8")

    # Files with spaces and legal punctuation (brackets, single quotes, plus, tilde)
    special_file = stress_repo / "file with spaces, and (brackets) & [tags] 'quote'.txt"
    special_file.write_text("Special characters in path\n", encoding="utf-8")

    run_git(stress_repo, "add", "-A")
    run_git(stress_repo, "commit", "-m", "Add deep, unicode, and special character paths")

    commits = get_commits(stress_repo)
    assert len(commits) == 1
    c = commits[0]
    recorded_paths = [f.path for f in c.files]

    # Verify deep path
    assert any("deep_module.py" in p and "level10" in p for p in recorded_paths)

    # Verify unicode paths preserved without corruption
    assert any("файл_тест.txt" in p for p in recorded_paths)
    assert any("ملف_عربي.txt" in p for p in recorded_paths)
    assert any("日本語_テスト.txt" in p for p in recorded_paths)
    assert any("emoji_👻_⚡_🔥.txt" in p for p in recorded_paths)

    # Verify special filename preserved
    assert any("file with spaces" in p and "'quote'" in p for p in recorded_paths)


def test_adversarial_massive_diff_and_hunk_cap(stress_repo: Path) -> None:
    """Commit modifying 110 files with over 1,000 hunks, enforcing 20 hunk context cap."""
    num_files = 110
    hunks_per_file = 10  # 110 * 10 = 1,100 function signatures

    for i in range(num_files):
        filename = f"module_{i:03d}.py"
        content_lines: list[str] = [f"# Module {i}"]
        for h in range(hunks_per_file):
            content_lines.append(f"def func_{i:03d}_{h:02d}():\n    return {i * 100 + h}\n")
        (stress_repo / filename).write_text("\n".join(content_lines), encoding="utf-8")

    run_git(stress_repo, "add", "-A")
    run_git(stress_repo, "commit", "-m", f"Massive commit with {num_files} files and 1100 functions")

    # Test extract_hunk_contexts independently
    hunk_map = extract_hunk_contexts(stress_repo, max_hunks_per_commit=20)
    assert len(hunk_map) == 1
    sha = next(iter(hunk_map.keys()))
    hunks = hunk_map[sha]
    assert len(hunks) == 20  # Capped at exactly 20!
    for h in hunks:
        assert h.startswith("@@")
        assert "def func_" in h

    # Test parse_git_log full commit object
    commits = get_commits(stress_repo, max_hunks_per_commit=20)
    assert len(commits) == 1
    commit = commits[0]
    assert len(commit.files) == num_files
    assert len(commit.hunks) == 20
    assert commit.sha == sha


def test_adversarial_complex_branch_history(stress_repo: Path) -> None:
    """Octopus merge, cherry-picks, detached HEAD, empty commits, and binary diffs."""
    # Commit 1: Root
    (stress_repo / "common.txt").write_text("common line\n", encoding="utf-8")
    run_git(stress_repo, "add", "common.txt")
    run_git(stress_repo, "commit", "-m", "Root commit")

    # Branch feature-a
    run_git(stress_repo, "checkout", "-b", "feature-a")
    (stress_repo / "feature_a.txt").write_text("Feature A content\n", encoding="utf-8")
    run_git(stress_repo, "add", "feature_a.txt")
    run_git(stress_repo, "commit", "-m", "Commit on feature-a")

    # Branch feature-b
    run_git(stress_repo, "checkout", "main")
    run_git(stress_repo, "checkout", "-b", "feature-b")
    (stress_repo / "feature_b.txt").write_text("Feature B content\n", encoding="utf-8")
    run_git(stress_repo, "add", "feature_b.txt")
    run_git(stress_repo, "commit", "-m", "Commit on feature-b")

    # Cherry-pick commit from feature-a onto feature-b
    commit_a_sha = run_git(stress_repo, "rev-parse", "feature-a")
    run_git(stress_repo, "cherry-pick", commit_a_sha)

    # Branch feature-c
    run_git(stress_repo, "checkout", "main")
    run_git(stress_repo, "checkout", "-b", "feature-c")
    (stress_repo / "feature_c.txt").write_text("Feature C content\n", encoding="utf-8")
    run_git(stress_repo, "add", "feature_c.txt")
    run_git(stress_repo, "commit", "-m", "Commit on feature-c")

    # Return to main and execute Octopus Merge of feature-b and feature-c
    run_git(stress_repo, "checkout", "main")
    run_git(stress_repo, "merge", "--no-ff", "feature-b", "feature-c", "-m", "Octopus merge of feature-b and feature-c")

    # Empty commit
    run_git(stress_repo, "commit", "--allow-empty", "-m", "Deliberate empty commit")

    # Binary file commit
    bin_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\xff\x00\xaa" * 1000
    (stress_repo / "image.png").write_bytes(bin_data)
    run_git(stress_repo, "add", "image.png")
    run_git(stress_repo, "commit", "-m", "Add binary PNG asset")

    # Detached HEAD commit
    main_sha = run_git(stress_repo, "rev-parse", "HEAD")
    run_git(stress_repo, "checkout", main_sha)
    (stress_repo / "detached.txt").write_text("Detached HEAD state\n", encoding="utf-8")
    run_git(stress_repo, "add", "detached.txt")
    run_git(stress_repo, "commit", "-m", "Commit in detached HEAD state")

    # Parse all commits across repository
    commits = get_commits(stress_repo)

    # Verify octopus merge is handled gracefully
    merge_commit = next((c for c in commits if "Octopus merge" in c.subject), None)
    assert merge_commit is not None
    assert merge_commit.short == merge_commit.sha[:7]

    # Verify empty commit is handled without error
    empty_commit = next((c for c in commits if "Deliberate empty commit" in c.subject), None)
    assert empty_commit is not None
    assert len(empty_commit.files) == 0

    # Verify binary file is detected with added=0, deleted=0, is_binary=True
    binary_commit = next((c for c in commits if "Add binary PNG asset" in c.subject), None)
    assert binary_commit is not None
    assert len(binary_commit.files) == 1
    bin_file = binary_commit.files[0]
    assert bin_file.path == "image.png"
    assert bin_file.is_binary is True
    assert bin_file.added == 0
    assert bin_file.deleted == 0

    # Return to main branch
    run_git(stress_repo, "checkout", "main")


def test_adversarial_parser_performance_and_memory(stress_repo: Path) -> None:
    """Benchmark throughput and peak memory on 100 sequential commits."""
    # Generate 100 commits rapidly
    for i in range(100):
        (stress_repo / f"file_{i % 10}.txt").write_text(f"Update {i}\n", encoding="utf-8")
        run_git(stress_repo, "add", f"file_{i % 10}.txt")
        run_git(stress_repo, "commit", "-m", f"Sequential commit {i}\n\nDescription for commit {i}.")

    # Measure time and memory for parsing 100 commits
    tracemalloc.start()
    t0 = time.perf_counter()

    commits = get_commits(stress_repo)

    elapsed = time.perf_counter() - t0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)

    assert len(commits) == 100
    # Throughput check: parsing 100 commits with hunk extraction must take < 5.0 seconds
    assert elapsed < 5.0, f"Parser too slow: took {elapsed:.2f}s for 100 commits"
    # Memory check: peak memory must be under 20 MB
    assert peak_mb < 20.0, f"Memory footprint too high: peak {peak_mb:.2f}MB"


def test_adversarial_read_only_clean_worktree(stress_repo: Path) -> None:
    """Ensure parser never mutates the target worktree even with dirty staged/untracked files."""
    # Create base commit
    (stress_repo / "tracked.txt").write_text("clean state\n", encoding="utf-8")
    run_git(stress_repo, "add", "tracked.txt")
    run_git(stress_repo, "commit", "-m", "Base commit")

    # Dirty worktree: staged modification + unstaged modification + untracked file
    (stress_repo / "staged.txt").write_text("staged content\n", encoding="utf-8")
    run_git(stress_repo, "add", "staged.txt")
    (stress_repo / "tracked.txt").write_text("unstaged modification\n", encoding="utf-8")
    (stress_repo / "untracked.txt").write_text("untracked file\n", encoding="utf-8")

    # Get status before
    status_before = run_git(stress_repo, "status", "--porcelain")
    assert "A  staged.txt" in status_before
    assert " M tracked.txt" in status_before
    assert "?? untracked.txt" in status_before

    # Run parser
    commits = get_commits(stress_repo)
    assert len(commits) == 1

    # Verify status after is 100% identical
    status_after = run_git(stress_repo, "status", "--porcelain")
    assert status_after == status_before
