"""Git log archaeology streaming parser and commit models."""

from __future__ import annotations

import re
import subprocess
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

HUNK_LINE_RE = re.compile(r"^@@\s+-[0-9]+(?:,[0-9]+)?\s+\+[0-9]+(?:,[0-9]+)?\s+@@\s*(.*)$")


class GitError(Exception):
    """Base exception for Git archaeology errors."""


class NotAGitRepositoryError(GitError):
    """Raised when a target directory is not a valid Git repository."""


class ShallowCloneWarning(UserWarning):
    """Warning emitted when analyzing a shallow Git clone."""


@dataclass(frozen=True, slots=True)
class FileChange:
    """Represents a file modified in a commit."""

    path: str
    added: int
    deleted: int
    is_binary: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize file change to a dictionary."""
        return {
            "path": self.path,
            "added": self.added,
            "deleted": self.deleted,
            "is_binary": self.is_binary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileChange:
        """Deserialize file change from a dictionary."""
        return cls(
            path=str(data["path"]),
            added=int(data["added"]),
            deleted=int(data["deleted"]),
            is_binary=bool(data.get("is_binary", False)),
        )


@dataclass(frozen=True, slots=True)
class Commit:
    """Immutable commit record extracted from git archaeology."""

    sha: str
    short: str
    author: str
    email: str
    date: datetime
    subject: str
    body: str
    files: tuple[FileChange, ...]
    hunks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize commit record to a JSON-compatible dictionary."""
        return {
            "sha": self.sha,
            "short": self.short,
            "author": self.author,
            "email": self.email,
            "date": self.date.isoformat(),
            "subject": self.subject,
            "body": self.body,
            "files": [f.to_dict() for f in self.files],
            "hunks": list(self.hunks),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Commit:
        """Deserialize commit record from a dictionary."""
        raw_date = data["date"]
        dt = datetime.fromisoformat(str(raw_date)) if isinstance(raw_date, str) else raw_date
        raw_files = data.get("files", [])
        files = tuple(FileChange.from_dict(f) if isinstance(f, dict) else f for f in raw_files)
        raw_hunks = data.get("hunks", ())
        hunks = tuple(str(h) for h in raw_hunks)
        return cls(
            sha=str(data["sha"]),
            short=str(data.get("short", str(data["sha"])[:7])),
            author=str(data["author"]),
            email=str(data["email"]),
            date=dt,
            subject=str(data["subject"]),
            body=str(data.get("body", "")),
            files=files,
            hunks=hunks,
        )


def stream_records(stream: Any, sep: str = "\x1e") -> Iterator[str]:
    """Stream records from a text stream delimited by a custom separator.

    Avoids Python's universal newline splitting of 0x1e.
    """
    buf = ""
    while True:
        chunk = stream.read(65536)
        if not chunk:
            break
        buf += chunk
        parts = buf.split(sep)
        for part in parts[:-1]:
            trimmed = part.strip()
            if trimmed:
                yield trimmed
        buf = parts[-1]
    if buf.strip():
        yield buf.strip()


def check_git_repo(repo_path: Path | str) -> None:
    """Verify that a path is a valid git repository and check for shallow clone.

    Raises:
        NotAGitRepositoryError: If path does not exist or is not a git repository.
    """
    resolved = Path(repo_path).resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise NotAGitRepositoryError(f"Directory '{repo_path}' is not a valid git repository.")

    # Check git repository validity and shallow status
    proc = subprocess.run(
        ["git", "-C", str(resolved), "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise NotAGitRepositoryError(f"Directory '{repo_path}' is not a valid git repository.")

    if proc.stdout.strip().lower() == "true":
        warnings.warn(
            "History is shallow; the dead remember less.",
            ShallowCloneWarning,
            stacklevel=2,
        )


def is_empty_repo(repo_path: Path | str) -> bool:
    """Check if repository has no commits yet."""
    resolved = Path(repo_path).resolve()
    proc = subprocess.run(
        ["git", "-C", str(resolved), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.returncode != 0


def extract_hunk_contexts(
    repo_path: Path | str,
    max_hunks_per_commit: int = 20,
) -> dict[str, tuple[str, ...]]:
    """Secondary pass extracting function/context signatures from diff hunks.

    Invokes `git log -p -U0 --format=%x1e%H` and captures up to max_hunks_per_commit
    non-empty @@ ... @@ <context> lines per commit.
    """
    resolved = Path(repo_path).resolve()
    if is_empty_repo(resolved):
        return {}

    cmd = [
        "git",
        "-C",
        str(resolved),
        "-c",
        "core.quotepath=false",
        "log",
        "--all",
        "-p",
        "-U0",
        "--format=%x1e%H",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=65536,
    )
    if proc.stdout is None:
        return {}

    hunk_map: dict[str, tuple[str, ...]] = {}
    try:
        for rec in stream_records(proc.stdout, sep="\x1e"):
            lines = rec.splitlines()
            if not lines:
                continue
            sha = lines[0].strip().lower()
            if not sha:
                continue
            hunks: list[str] = []
            for line in lines[1:]:
                if line.startswith("@@"):
                    m = HUNK_LINE_RE.match(line)
                    if m:
                        ctx = m.group(1).strip()
                        if ctx and len(hunks) < max_hunks_per_commit:
                            hunks.append(line.strip())
            if hunks:
                hunk_map[sha] = tuple(hunks)
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()

    return hunk_map


def _parse_numstat_line(line: str) -> FileChange | None:
    """Parse a single line from git log --numstat."""
    line = line.strip()
    if not line:
        return None
    fields = line.split("\t", 2)
    if len(fields) < 3:
        return None
    added_str, deleted_str, path = fields
    is_binary = added_str == "-" and deleted_str == "-"
    added = int(added_str) if not is_binary and added_str.isdigit() else 0
    deleted = int(deleted_str) if not is_binary and deleted_str.isdigit() else 0
    return FileChange(
        path=path,
        added=added,
        deleted=deleted,
        is_binary=is_binary,
    )


def parse_git_log(
    repo_path: Path | str,
    *,
    extract_hunk_contexts_flag: bool = True,
    first_parent_merges: bool = True,
    max_hunks_per_commit: int = 20,
) -> Iterator[Commit]:
    """Single-pass streaming parser extracting immutable Commit records from a Git repository.

    Args:
        repo_path: Path to target git repository.
        extract_hunk_contexts_flag: Whether to perform secondary pass for hunk headers.
        first_parent_merges: If True, include -m --first-parent to retain merge diff stats.
        max_hunks_per_commit: Max @@ hunk contexts to retain per commit.

    Yields:
        Immutable Commit records in reverse chronological order.
    """
    resolved = Path(repo_path).resolve()
    check_git_repo(resolved)

    if is_empty_repo(resolved):
        return

    hunk_map: dict[str, tuple[str, ...]] = {}
    if extract_hunk_contexts_flag:
        hunk_map = extract_hunk_contexts(resolved, max_hunks_per_commit=max_hunks_per_commit)

    cmd = [
        "git",
        "-C",
        str(resolved),
        "-c",
        "core.quotepath=false",
        "log",
        "--all",
        "--no-color",
        "--numstat",
    ]
    if first_parent_merges:
        cmd.extend(["-m", "--first-parent"])
    cmd.append("--format=%x1e%H%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b%x1f")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=65536,
    )
    if proc.stdout is None:
        return

    try:
        for rec in stream_records(proc.stdout, sep="\x1e"):
            parts = rec.split("\x1f", 6)
            if len(parts) < 6:
                continue
            sha = parts[0].strip().lower()
            if not sha:
                continue
            author = parts[1].strip()
            email = parts[2].strip()
            date_str = parts[3].strip()
            try:
                dt = datetime.fromisoformat(date_str)
            except ValueError:
                dt = datetime.now()
            subject = parts[4].strip()
            body = parts[5].strip()
            numstat_block = parts[6] if len(parts) > 6 else ""

            files: list[FileChange] = []
            for line in numstat_block.splitlines():
                fc = _parse_numstat_line(line)
                if fc is not None:
                    files.append(fc)

            hunks = hunk_map.get(sha, ())
            yield Commit(
                sha=sha,
                short=sha[:7],
                author=author,
                email=email,
                date=dt,
                subject=subject,
                body=body,
                files=tuple(files),
                hunks=hunks,
            )
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()


def get_commits(
    repo_path: Path | str,
    *,
    extract_hunk_contexts_flag: bool = True,
    max_hunks_per_commit: int = 20,
) -> list[Commit]:
    """Convenience function returning all commits as a list."""
    return list(
        parse_git_log(
            repo_path,
            extract_hunk_contexts_flag=extract_hunk_contexts_flag,
            max_hunks_per_commit=max_hunks_per_commit,
        )
    )
