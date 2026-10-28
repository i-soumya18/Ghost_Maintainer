"""Hermetic pytest fixtures creating synthetic Git repositories."""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest


def _remove_readonly(func: Any, path: str, exc_info: Any) -> None:
    """Clear readonly bit on Windows and retry removal."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def safe_rmtree(path: Path | str) -> None:
    """Safely remove a directory tree, handling Windows read-only git files."""
    p = Path(path)
    if p.exists():
        with contextlib.suppress(Exception):
            shutil.rmtree(p, onerror=_remove_readonly)


def run_git(
    cwd: Path,
    *args: str,
    author: str = "Test Maintainer <maintainer@example.com>",
    date: str = "2020-01-01T12:00:00+00:00",
) -> str:
    """Execute a git command hermetically inside cwd."""
    name, email = author.split("<")
    name = name.strip()
    email = email.rstrip(">").strip()

    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = name
    env["GIT_AUTHOR_EMAIL"] = email
    env["GIT_AUTHOR_DATE"] = date
    env["GIT_COMMITTER_NAME"] = name
    env["GIT_COMMITTER_EMAIL"] = email
    env["GIT_COMMITTER_DATE"] = date

    cmd = ["git", "-c", "core.quotepath=false", *args]
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Git command failed: {' '.join(cmd)}\nStderr: {proc.stderr}")
    return proc.stdout.strip()


@pytest.fixture
def non_git_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory that is not a git repository."""
    temp_dir = Path(tempfile.mkdtemp(prefix="ghost_non_git_"))
    try:
        yield temp_dir
    finally:
        safe_rmtree(temp_dir)


@pytest.fixture
def empty_repo() -> Generator[Path, None, None]:
    """Provide a freshly initialized Git repository with zero commits."""
    temp_dir = Path(tempfile.mkdtemp(prefix="ghost_empty_repo_"))
    try:
        run_git(temp_dir, "init", "-b", "main")
        yield temp_dir
    finally:
        safe_rmtree(temp_dir)


@pytest.fixture
def synthetic_repo() -> Generator[Path, None, None]:
    """Hermetic 7-commit Git repository fixture covering all archaeology scenarios.

    Commits:
        1. Initial commit (README.md, package.json) by Mikeal Rogers
        2. Add OAuth authentication handler (OAuthSigner.py, lib/auth.js) by Alice Developer
        3. Rewrite auth subsystem with JWT support by Bob Maintainer
        4. Drop Windows CI due to flakey test runner by Charlie Architect
        5. (branch feature/docs) Add multilingual and emoji documentation by René Descartes 👻
        6. Merge branch 'feature/docs' into main by Alice Developer
        7. Deprecate request library in favor of native fetch by Mikeal Rogers
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="ghost_synthetic_repo_"))
    try:
        # Initialize repository
        run_git(temp_dir, "init", "-b", "main")
        run_git(temp_dir, "config", "core.quotepath", "false")
        run_git(temp_dir, "config", "user.name", "Test Committer")
        run_git(temp_dir, "config", "user.email", "committer@example.com")

        # Commit 1: Initial commit
        (temp_dir / "README.md").write_text(
            "# Project\nSimplified HTTP client.\n", encoding="utf-8"
        )
        (temp_dir / "package.json").write_text(
            '{"name": "request", "version": "1.0.0"}\n', encoding="utf-8"
        )
        run_git(temp_dir, "add", "README.md", "package.json")
        run_git(
            temp_dir,
            "commit",
            "-m",
            "Initial commit\n\nSetup initial project files.",
            author="Mikeal Rogers <mikeal.rogers@gmail.com>",
            date="2011-01-15T10:00:00+00:00",
        )

        # Commit 2: OAuth authentication handler
        auth_dir = temp_dir / "src" / "auth"
        auth_dir.mkdir(parents=True, exist_ok=True)
        (auth_dir / "OAuthSigner.py").write_text(
            "class OAuthSigner:\n"
            "    def authenticate(self, user):\n"
            "        return f'token_{user}'\n",
            encoding="utf-8",
        )
        lib_dir = temp_dir / "lib"
        lib_dir.mkdir(parents=True, exist_ok=True)
        (lib_dir / "auth.js").write_text(
            "function authenticate(credentials) {\n    return 'auth-ok';\n}\n",
            encoding="utf-8",
        )
        run_git(temp_dir, "add", "src/auth/OAuthSigner.py", "lib/auth.js")
        run_git(
            temp_dir,
            "commit",
            "-m",
            "Add OAuth authentication handler\n\nIntroduce OAuthSigner class and authenticate helpers.",
            author="Alice Developer <alice@example.com>",
            date="2013-05-20T14:30:00+00:00",
        )

        # Commit 3: Rewrite auth subsystem with JWT support
        (auth_dir / "OAuthSigner.py").write_text(
            "class OAuthSigner:\n"
            "    def authenticate(self, user):\n"
            "        return f'jwt_{user}'\n"
            "    def verify_jwt_token(self, token):\n"
            "        return True\n",
            encoding="utf-8",
        )
        run_git(temp_dir, "add", "src/auth/OAuthSigner.py")
        run_git(
            temp_dir,
            "commit",
            "-m",
            "Rewrite auth subsystem with JWT support\n\nMigrate authentication mechanism to JWT tokens.",
            author="Bob Maintainer <bob@example.com>",
            date="2016-08-11T09:15:00+00:00",
        )

        # Commit 4: Drop Windows CI
        ci_dir = temp_dir / ".github" / "workflows"
        ci_dir.mkdir(parents=True, exist_ok=True)
        (ci_dir / "ci.yml").write_text(
            "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
            encoding="utf-8",
        )
        (ci_dir / "windows-ci.yml").write_text(
            "name: Windows CI\non: [push]\njobs:\n  test:\n    runs-on: windows-latest\n",
            encoding="utf-8",
        )
        run_git(temp_dir, "add", ".github/workflows/ci.yml", ".github/workflows/windows-ci.yml")
        run_git(
            temp_dir,
            "commit",
            "-m",
            "Add CI matrix workflows",
            author="Charlie Architect <charlie@example.com>",
            date="2017-02-01T16:00:00+00:00",
        )

        # Now remove Windows CI
        (ci_dir / "windows-ci.yml").unlink()
        run_git(temp_dir, "rm", ".github/workflows/windows-ci.yml")
        run_git(
            temp_dir,
            "commit",
            "-m",
            "Drop Windows CI due to flakey test runner\n\nWindows tests are perpetually red and unmaintained.",
            author="Charlie Architect <charlie@example.com>",
            date="2018-04-12T11:20:00+00:00",
        )

        # Create branch feature/docs for unicode & merge scenario
        run_git(temp_dir, "checkout", "-b", "feature/docs")
        docs_dir = temp_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "café.md").write_text(
            "# Documentation en Français\nBienvenue dans notre guide café.\n",
            encoding="utf-8",
        )
        (docs_dir / "emoji_👻.txt").write_text(
            "The ghostly presence lingers here.\n",
            encoding="utf-8",
        )
        run_git(temp_dir, "add", "docs/café.md", "docs/emoji_👻.txt")
        run_git(
            temp_dir,
            "commit",
            "-m",
            "Add multilingual and emoji documentation\n\nFrench translation and ghost emoji documentation.",
            author="René Descartes 👻 <rene@example.com>",
            date="2018-09-05T13:00:00+00:00",
        )

        # Switch back to main and merge
        run_git(temp_dir, "checkout", "main")
        run_git(
            temp_dir,
            "merge",
            "--no-ff",
            "feature/docs",
            "-m",
            "Merge branch 'feature/docs' into main\n\nIncorporate French docs and unicode files.",
            author="Alice Developer <alice@example.com>",
            date="2018-09-06T15:45:00+00:00",
        )

        # Commit 7: Deprecation commit
        (temp_dir / "README.md").write_text(
            "# Project (DEPRECATED)\n\n"
            "Request is officially deprecated. Please use native fetch or alternative packages.\n",
            encoding="utf-8",
        )
        (temp_dir / "package.json").write_text(
            '{"name": "request", "version": "2.88.2", "deprecated": true}\n',
            encoding="utf-8",
        )
        run_git(temp_dir, "add", "README.md", "package.json")
        run_git(
            temp_dir,
            "commit",
            "-m",
            "Deprecate request library in favor of native fetch\n\n"
            "We have decided to deprecate request. Ecosystem has moved to standard fetch.",
            author="Mikeal Rogers <mikeal.rogers@gmail.com>",
            date="2019-02-11T14:32:00+00:00",
        )

        yield temp_dir
    finally:
        safe_rmtree(temp_dir)


@pytest.fixture
def shallow_repo(synthetic_repo: Path) -> Generator[Path, None, None]:
    """Provide a shallow clone (--depth 1) of the synthetic repository."""
    temp_dir = Path(tempfile.mkdtemp(prefix="ghost_shallow_repo_"))
    try:
        run_git(temp_dir, "clone", "--depth", "1", f"file:///{synthetic_repo.as_posix()}", ".")
        yield temp_dir
    finally:
        safe_rmtree(temp_dir)
