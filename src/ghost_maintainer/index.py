"""BM25 indexing, isolated cache persistence, and CommitStore for git archaeology."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import bm25s
import Stemmer

from ghost_maintainer.config import get_repo_cache_key, settings
from ghost_maintainer.gitlog import Commit, check_git_repo, get_commits

INDEX_VERSION: int = 1


def tokenize_path(path: str) -> list[str]:
    """Tokenize a file path into lowercase tokens splitting on delimiters and camelCase.

    Examples:
        'lib/auth.js' -> ['lib', 'auth', 'js']
        'src/auth/OAuthSigner.py' -> ['src', 'auth', 'oauthsigner', 'o', 'auth', 'signer', 'py']
        '.github/workflows/ci.yml' -> ['github', 'workflows', 'ci', 'yml']
    """
    raw_parts = re.split(r"[/\\_.-]+", path)
    tokens: list[str] = []
    for part in raw_parts:
        if not part:
            continue
        p_lower = part.lower()
        tokens.append(p_lower)
        # Split camelCase: 'camelCase' -> 'camel Case'
        split1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", part)
        # Split acronyms: 'OAuthSigner' -> 'O Auth Signer'
        split2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", split1)
        subwords = [w.lower() for w in split2.split() if w]
        for w in subwords:
            if w != p_lower:
                tokens.append(w)
    return tokens


def build_commit_document(commit: Commit) -> str:
    """Construct the boosted document text representation of a commit for BM25 indexing.

    Field weights:
        - subject: x2
        - body: x1
        - author: x1
        - path tokens: x2
        - hunk contexts: x1
    """
    parts: list[str] = []

    # 1. Subject x2
    if commit.subject:
        parts.append(commit.subject)
        parts.append(commit.subject)

    # 2. Body x1
    if commit.body:
        parts.append(commit.body)

    # 3. Author x1
    if commit.author:
        parts.append(commit.author)

    # 4. Path tokens x2
    if commit.files:
        path_toks: list[str] = []
        for f in commit.files:
            path_toks.extend(tokenize_path(f.path))
        if path_toks:
            path_str = " ".join(path_toks)
            parts.append(path_str)
            parts.append(path_str)

    # 5. Hunk contexts x1
    if commit.hunks:
        parts.append(" ".join(commit.hunks))

    return " ".join(parts)


def get_cache_root() -> Path:
    """Resolve the root cache directory from settings."""
    return settings.cache_dir


def get_repo_cache_dir(repo_path: Path | str, cache_root: Path | None = None) -> Path:
    """Resolve the isolated cache directory for a target repository.

    Ensures zero mutation of the target repository.
    """
    root = cache_root if cache_root is not None else get_cache_root()
    key = get_repo_cache_key(repo_path)
    target = root / key
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_head_sha(repo_path: Path | str) -> str | None:
    """Get the current HEAD commit SHA for a repository."""
    resolved = Path(repo_path).resolve()
    proc = subprocess.run(
        ["git", "-C", str(resolved), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode == 0:
        sha = proc.stdout.strip().lower()
        if sha:
            return sha
    return None


def is_cache_valid(repo_path: Path | str, cache_dir: Path) -> bool:
    """Check if the cache directory contains a valid, up-to-date index."""
    meta_path = cache_dir / "meta.json"
    if not meta_path.exists():
        return False

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    if meta.get("version") != INDEX_VERSION:
        return False

    current_head = get_head_sha(repo_path)
    if meta.get("head_sha") != current_head:
        return False

    commits_path = cache_dir / "commits.jsonl"
    if not commits_path.exists():
        return False

    commit_count = meta.get("commit_count", 0)
    if commit_count > 0:
        bm25_dir = cache_dir / "bm25"
        if not bm25_dir.exists():
            return False

    return True


class CommitStore:
    """In-memory commit store with O(1) SHA lookup and prefix matching."""

    def __init__(self, commits: list[Commit]):
        self.commits: list[Commit] = list(commits)
        self._by_sha: dict[str, Commit] = {c.sha.lower(): c for c in commits}
        self._prefix_map: dict[str, list[str]] = {}
        for c in commits:
            sha = c.sha.lower()
            for length in range(7, len(sha) + 1):
                prefix = sha[:length]
                if prefix not in self._prefix_map:
                    self._prefix_map[prefix] = []
                self._prefix_map[prefix].append(sha)

    def get(self, sha: str) -> Commit | None:
        """Get commit by full 40-char SHA (or resolved prefix)."""
        return self._by_sha.get(sha.lower())

    def resolve_prefix(self, prefix: str) -> str | None:
        """Resolve short commit hash (7-40 chars) to unique full 40-char SHA.

        Returns:
            Full 40-char SHA if exactly one commit matches.
            None if no commits match or if the prefix is ambiguous.
        """
        prefix_lower = prefix.lower()
        if len(prefix_lower) < 7:
            matches = [s for s in self._by_sha if s.startswith(prefix_lower)]
            return matches[0] if len(matches) == 1 else None
        matches = self._prefix_map.get(prefix_lower, [])
        if len(matches) == 1:
            return matches[0]
        return None

    def __len__(self) -> int:
        return len(self.commits)

    def __getitem__(self, idx: int) -> Commit:
        return self.commits[idx]

    def __iter__(self) -> Iterator[Commit]:
        return iter(self.commits)


def save_index(
    cache_dir: Path,
    commits: list[Commit],
    retriever: bm25s.BM25 | None,
    meta: dict[str, Any],
) -> None:
    """Persist commits.jsonl, bm25 index files, and meta.json to cache_dir."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save commits.jsonl
    commits_path = cache_dir / "commits.jsonl"
    with commits_path.open("w", encoding="utf-8") as f:
        for c in commits:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")

    # 2. Save BM25 index if available
    bm25_dir = cache_dir / "bm25"
    if retriever is not None:
        bm25_dir.mkdir(parents=True, exist_ok=True)
        retriever.save(str(bm25_dir))
    elif bm25_dir.exists():
        shutil.rmtree(bm25_dir, ignore_errors=True)

    # 3. Save meta.json
    meta_path = cache_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def load_index(cache_dir: Path) -> tuple[CommitStore, bm25s.BM25 | None, dict[str, Any]]:
    """Load commits, BM25 retriever, and metadata from cache_dir."""
    meta_path = cache_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    commits_path = cache_dir / "commits.jsonl"
    commits: list[Commit] = []
    if commits_path.exists():
        with commits_path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    commits.append(Commit.from_dict(json.loads(stripped)))

    commit_store = CommitStore(commits)

    bm25_dir = cache_dir / "bm25"
    retriever: bm25s.BM25 | None = None
    if bm25_dir.exists() and meta.get("commit_count", 0) > 0:
        try:
            retriever = bm25s.BM25.load(str(bm25_dir), mmap=False)
        except Exception:
            retriever = None

    return commit_store, retriever, meta


def index_repo(
    repo_path: Path | str,
    *,
    force: bool = False,
    cache_dir: Path | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> tuple[CommitStore, bm25s.BM25 | None, dict[str, Any]]:
    """Index a git repository, building BM25 model and CommitStore with cache persistence.

    Zero-mutation guarantee: The target repository is never written to. All index
    artifacts are stored strictly inside the isolated cache directory.

    Args:
        repo_path: Path to target git repository.
        force: If True, ignore existing cache and rebuild.
        cache_dir: Optional explicit cache directory override.
        on_progress: Optional callback ``(phase, step, total_steps)`` invoked at the
            real phase boundaries: ``reading``, ``indexing``, ``saving``.

    Returns:
        Tuple of (CommitStore, optional BM25 retriever, metadata dict).
    """
    resolved = Path(repo_path).resolve()
    check_git_repo(resolved)

    def _progress(phase: str, step: int) -> None:
        if on_progress is not None:
            on_progress(phase, step, 3)

    target_cache_dir = cache_dir if cache_dir is not None else get_repo_cache_dir(resolved)

    # Check cache validity
    if not force and is_cache_valid(resolved, target_cache_dir):
        return load_index(target_cache_dir)

    # Re-index repository
    _progress("reading", 0)
    commits = get_commits(resolved)
    head_sha = get_head_sha(resolved)

    meta: dict[str, Any] = {
        "repo_path": str(resolved).replace("\\", "/"),
        "head_sha": head_sha,
        "commit_count": len(commits),
        "version": INDEX_VERSION,
        "indexed_at": datetime.now(UTC).isoformat(),
    }

    if not commits:
        save_index(target_cache_dir, [], None, meta)
        return CommitStore([]), None, meta

    # Build corpus texts
    _progress("indexing", 1)
    corpus = [build_commit_document(c) for c in commits]
    stemmer = Stemmer.Stemmer("english")
    tokens = bm25s.tokenize(corpus, stopwords="en", stemmer=stemmer, show_progress=False)

    # Guard against 0 vocabulary terms (e.g. all empty texts or stopwords)
    if not hasattr(tokens, "vocab") or not tokens.vocab or len(tokens.vocab) == 0:
        retriever = None
    else:
        retriever = bm25s.BM25()
        retriever.index(tokens, show_progress=False)

    _progress("saving", 2)
    save_index(target_cache_dir, commits, retriever, meta)
    _progress("saving", 3)
    return CommitStore(commits), retriever, meta
