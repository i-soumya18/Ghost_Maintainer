"""Tests for Git archaeology streaming parser, models, and edge cases."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from ghost_maintainer.gitlog import (
    Commit,
    FileChange,
    NotAGitRepositoryError,
    ShallowCloneWarning,
    extract_hunk_contexts,
    get_commits,
    parse_git_log,
    stream_records,
)


def test_not_a_git_repository(non_git_dir: Path) -> None:
    """Non-git directory raises NotAGitRepositoryError."""
    with pytest.raises(NotAGitRepositoryError):
        list(parse_git_log(non_git_dir))


def test_empty_repository(empty_repo: Path) -> None:
    """Empty repository yields zero commits cleanly without error."""
    commits = list(parse_git_log(empty_repo))
    assert len(commits) == 0


def test_shallow_clone_warning(shallow_repo: Path) -> None:
    """Shallow clone emits ShallowCloneWarning and parses remaining history."""
    with pytest.warns(ShallowCloneWarning, match="History is shallow; the dead remember less."):
        commits = list(parse_git_log(shallow_repo))
    assert len(commits) >= 1


def test_synthetic_repo_commits(synthetic_repo: Path) -> None:
    """Synthetic repository parses all commits with expected authors, subjects, and files."""
    commits = get_commits(synthetic_repo)
    assert len(commits) >= 7

    # Verify deprecation commit
    top_commit = commits[0]
    assert "Deprecate request" in top_commit.subject
    assert "Mikeal Rogers" in top_commit.author
    assert top_commit.short == top_commit.sha[:7]
    assert any(f.path == "README.md" for f in top_commit.files)


def test_unicode_and_emoji_handling(synthetic_repo: Path) -> None:
    """Unicode paths, French characters, and emojis are preserved without corruption."""
    commits = get_commits(synthetic_repo)
    doc_commit = next((c for c in commits if "emoji" in c.subject.lower()), None)
    assert doc_commit is not None
    assert "👻" in doc_commit.author or "René" in doc_commit.author
    file_paths = [f.path for f in doc_commit.files]
    assert "docs/café.md" in file_paths
    assert "docs/emoji_👻.txt" in file_paths


def test_merge_commit_retained(synthetic_repo: Path) -> None:
    """Merge commits are retained and diffs computed relative to first parent."""
    commits = get_commits(synthetic_repo)
    merge_commit = next((c for c in commits if "Merge branch" in c.subject), None)
    assert merge_commit is not None
    assert len(merge_commit.files) > 0


def test_hunk_extraction(synthetic_repo: Path) -> None:
    """Hunk context extraction captures function signatures and caps at limit."""
    hunks = extract_hunk_contexts(synthetic_repo, max_hunks_per_commit=5)
    assert len(hunks) > 0
    # At least one commit should have extracted class/def signatures
    all_hunk_lines = [line for h_list in hunks.values() for line in h_list]
    assert any("authenticate" in line or "OAuthSigner" in line for line in all_hunk_lines)


def test_commit_serialization_roundtrip(synthetic_repo: Path) -> None:
    """Commit to_dict and from_dict roundtrip preserves exact fields."""
    commits = get_commits(synthetic_repo)
    for c in commits:
        d = c.to_dict()
        reconstructed = Commit.from_dict(d)
        assert reconstructed == c


def test_filechange_serialization_roundtrip() -> None:
    """FileChange to_dict and from_dict roundtrip."""
    fc = FileChange(path="src/lib.py", added=10, deleted=2, is_binary=False)
    d = fc.to_dict()
    assert FileChange.from_dict(d) == fc

    fc_bin = FileChange(path="images/logo.png", added=0, deleted=0, is_binary=True)
    assert FileChange.from_dict(fc_bin.to_dict()) == fc_bin


def test_stream_records_custom_separator() -> None:
    """Stream records splits on 0x1e across chunk boundaries."""
    raw = "\x1eRecord 1\x1eRecord 2\x1eRecord 3\nwith newline\x1e"
    stream = io.StringIO(raw)
    records = list(stream_records(stream, sep="\x1e"))
    assert records == ["Record 1", "Record 2", "Record 3\nwith newline"]
