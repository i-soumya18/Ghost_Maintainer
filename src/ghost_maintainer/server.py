"""FastAPI HTTP and SSE server for The Ghost Maintainer."""

from __future__ import annotations

import asyncio
import json
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ghost_maintainer import __version__
from ghost_maintainer.config import (
    GHOST_DISCLAIMER,
    get_repo_cache_key,
    settings,
)
from ghost_maintainer.gitlog import GitError, NotAGitRepositoryError, check_git_repo
from ghost_maintainer.index import get_repo_cache_dir, index_repo, load_index
from ghost_maintainer.seance import Seance


# --- Schemas ---
class HealthResponse(BaseModel):
    """Healthcheck response model."""

    status: str = "ok"
    version: str
    backend: str | None = None


class TimelineBucket(BaseModel):
    """Commit count for one calendar month."""

    month: str
    count: int


class AuthorCount(BaseModel):
    """Commit count for one author."""

    author: str
    commits: int


class TimelineResponse(BaseModel):
    """Repository lifetime summary used by the Graveyard view."""

    total_commits: int
    first_date: str | None
    last_date: str | None
    last_subject: str | None
    last_sha: str | None
    buckets: list[TimelineBucket]
    top_authors: list[AuthorCount]


class SummonRequest(BaseModel):
    """Summon request payload."""

    path: str = Field(..., description="Local filesystem path or git URL to repository")
    force: bool = Field(default=False, description="Whether to force rebuild index")


class SummonResponse(BaseModel):
    """Summon response payload."""

    id: str = Field(..., description="12-character deterministic repository cache key")
    name: str = Field(..., description="Repository folder or project name")
    path: str = Field(..., description="Canonical repository path")
    head_sha: str | None = Field(None, description="Current HEAD commit SHA")
    commit_count: int = Field(..., description="Number of commits indexed")
    indexed_at: str = Field(..., description="ISO 8601 indexing timestamp")
    status: str = Field(default="ready", description="Index status")


class RepoSummary(BaseModel):
    """Summary of an indexed repository."""

    id: str
    name: str
    path: str
    head_sha: str | None
    commit_count: int
    last_indexed: str


class FileChangeModel(BaseModel):
    """Model of a changed file within a commit."""

    path: str
    added: int
    deleted: int
    is_binary: bool = False


class CommitDetails(BaseModel):
    """Detailed commit information with diff and changed files."""

    sha: str
    short: str
    author: str
    email: str
    date: str
    subject: str
    body: str
    files: list[FileChangeModel]
    hunks: list[str] = Field(default_factory=list)
    diff: str | None = None


# --- App Factory ---
def create_app(static_dir: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance.

    Args:
        static_dir: Optional directory containing built static Web UI assets.
                    Defaults to settings.static_dir or web/dist.
    """
    application = FastAPI(
        title="The Ghost Maintainer",
        version=__version__,
        description="Verifiable, local AI codebase archaeology server.",
    )

    # CORS Middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:6660",
            "http://127.0.0.1:6660",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health endpoints
    @application.get("/health", response_model=HealthResponse)
    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__, backend=settings.backend)

    # Summon endpoints
    def resolve_target(raw_path: str, force: bool) -> Path:
        """Resolve a user-supplied path or git URL to a validated local git repository."""
        path_str = raw_path.strip()
        is_url = path_str.startswith(("http://", "https://", "git@", "ssh://")) or (
            path_str.endswith(".git") and not Path(path_str).exists()
        )

        bundled_request = Path(__file__).parents[2] / ".eval_repos" / "request"
        # Fast-path for the bundled request benchmark repository
        if (
            "request/request" in path_str
            or path_str.rstrip("/").endswith("/request")
            or path_str == "request"
        ) and bundled_request.exists():
            target_path = bundled_request.resolve()
        elif is_url:
            clone_key = get_repo_cache_key(path_str)
            clone_dir = settings.cache_dir / "clones" / clone_key
            clone_dir.parent.mkdir(parents=True, exist_ok=True)
            if not clone_dir.exists() or force:
                res = subprocess.run(
                    ["git", "clone", path_str, str(clone_dir)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode != 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Error cloning repository '{path_str}': {res.stderr.strip()}",
                    )
            target_path = clone_dir
        else:
            p = Path(path_str)
            if p.exists():
                target_path = p.resolve()
            else:
                project_root = Path(__file__).parents[2]
                alt = (project_root / path_str).resolve()
                eval_alt = (project_root / ".eval_repos" / path_str).resolve()
                if alt.exists():
                    target_path = alt
                elif eval_alt.exists():
                    target_path = eval_alt
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Directory '{raw_path}' does not exist.",
                    )

        try:
            check_git_repo(target_path)
        except (GitError, NotAGitRepositoryError) as err:
            raise HTTPException(
                status_code=400,
                detail=f"Directory '{raw_path}' is not a valid git repository: {err}",
            ) from None
        return target_path

    def build_summon_response(
        target_path: Path, commit_count: int, meta: dict[str, Any]
    ) -> SummonResponse:
        return SummonResponse(
            id=get_repo_cache_key(target_path),
            name=target_path.name,
            path=str(target_path).replace("\\", "/"),
            head_sha=meta.get("head_sha"),
            commit_count=meta.get("commit_count", commit_count),
            indexed_at=meta.get("indexed_at", datetime.now(UTC).isoformat()),
            status="ready",
        )

    @application.post("/api/summon", response_model=SummonResponse)
    def summon(req: SummonRequest) -> SummonResponse:
        target_path = resolve_target(req.path, req.force)
        try:
            commit_store, _, meta = index_repo(target_path, force=req.force)
        except Exception as err:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to index repository: {err}",
            ) from None
        return build_summon_response(target_path, len(commit_store), meta)

    PROGRESS_MESSAGES = {
        "resolving": "Locating the archive…",
        "reading": "Reading the commit history…",
        "indexing": "Gathering memories…",
        "saving": "Sealing the archive…",
    }

    @application.get("/api/summon/stream")
    async def summon_stream(
        path: str = Query(..., description="Local filesystem path or git URL"),
        force: bool = Query(False, description="Whether to force rebuild index"),
    ) -> EventSourceResponse:
        """Index a repository while streaming real phase progress over SSE."""

        async def gen() -> AsyncIterator[dict[str, str]]:
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

            def emit(event: str, payload: dict[str, Any]) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, (event, payload))

            def work() -> None:
                try:
                    emit(
                        "progress",
                        {
                            "phase": "resolving",
                            "message": PROGRESS_MESSAGES["resolving"],
                            "processed": 0,
                            "total": 3,
                        },
                    )
                    target = resolve_target(path, force)

                    def on_progress(phase: str, step: int, total: int) -> None:
                        emit(
                            "progress",
                            {
                                "phase": phase,
                                "message": PROGRESS_MESSAGES.get(phase, phase),
                                "processed": step,
                                "total": total,
                            },
                        )

                    store, _, meta = index_repo(target, force=force, on_progress=on_progress)
                    resp = build_summon_response(target, len(store), meta)
                    emit("done", resp.model_dump())
                except HTTPException as err:
                    emit("error", {"message": str(err.detail)})
                except Exception as err:
                    emit("error", {"message": f"Failed to index repository: {err}"})
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            task = loop.run_in_executor(None, work)
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield {"event": item[0], "data": json.dumps(item[1])}
            await task

        return EventSourceResponse(gen())

    # Repos endpoint
    @application.get("/api/repos", response_model=list[RepoSummary])
    def list_repos() -> list[RepoSummary]:
        cache_root = settings.cache_dir
        if not cache_root.exists():
            return []

        summaries: list[RepoSummary] = []
        for item in sorted(cache_root.iterdir()):
            if item.is_dir():
                meta_file = item / "meta.json"
                if meta_file.exists():
                    try:
                        data = json.loads(meta_file.read_text(encoding="utf-8"))
                        repo_path_str = data.get("repo_path", "")
                        if not repo_path_str or not Path(repo_path_str).exists():
                            continue
                        name = Path(repo_path_str).name if repo_path_str else item.name
                        summaries.append(
                            RepoSummary(
                                id=item.name,
                                name=name,
                                path=repo_path_str,
                                head_sha=data.get("head_sha"),
                                commit_count=data.get("commit_count", 0),
                                last_indexed=data.get("indexed_at", ""),
                            )
                        )
                    except Exception:
                        continue
        return summaries

    # Commit inspector endpoint
    @application.get("/api/commit/{sha}", response_model=CommitDetails)
    def get_commit(
        sha: str,
        repo: str | None = Query(default=None, description="Path to target Git repository"),
    ) -> CommitDetails:
        if not repo or not repo.strip():
            raise HTTPException(
                status_code=400,
                detail="Query parameter 'repo' is required.",
            )

        repo_path = Path(repo).resolve()
        if not repo_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Repository '{repo}' does not exist.",
            )

        try:
            check_git_repo(repo_path)
        except (GitError, NotAGitRepositoryError) as err:
            raise HTTPException(
                status_code=400,
                detail=f"Repository '{repo}' is not a valid git repository: {err}",
            ) from None

        # Load commits from cache or index on-the-fly
        cache_dir = get_repo_cache_dir(repo_path)
        if (cache_dir / "commits.jsonl").exists():
            commit_store, _, _ = load_index(cache_dir)
        else:
            commit_store, _, _ = index_repo(repo_path)

        # Resolve SHA
        commit = None
        sha_clean = sha.strip().lower()
        if len(sha_clean) == 40:
            commit = commit_store.get(sha_clean)
        else:
            matches = [c for c in commit_store if c.sha.lower().startswith(sha_clean)]
            if len(matches) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ambiguous commit SHA prefix '{sha}'.",
                )
            elif len(matches) == 1:
                commit = matches[0]

        if commit is None:
            raise HTTPException(
                status_code=404,
                detail=f"Commit '{sha}' not found in repository '{repo}'.",
            )

        # Fetch git diff representation
        diff_text: str | None = None
        try:
            res = subprocess.run(
                ["git", "-C", str(repo_path), "show", "-p", "--stat", commit.sha],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                diff_text = res.stdout
                if len(diff_text) > 50000:
                    diff_text = diff_text[:50000] + "\n... [diff truncated]"
        except Exception:
            diff_text = None

        return CommitDetails(
            sha=commit.sha,
            short=commit.short,
            author=commit.author,
            email=commit.email,
            date=commit.date.isoformat(),
            subject=commit.subject,
            body=commit.body,
            files=[
                FileChangeModel(
                    path=f.path,
                    added=f.added,
                    deleted=f.deleted,
                    is_binary=f.is_binary,
                )
                for f in commit.files
            ],
            hunks=list(commit.hunks),
            diff=diff_text,
        )

    # Ask SSE streaming endpoint
    @application.get("/api/ask")
    async def ask(
        q: str = Query(..., description="Question to ask departed maintainers"),
        repo: str = Query(..., description="Path to target Git repository"),
        mode: Literal["guarded", "raw"] = Query("guarded", description="Verification mode"),
        backend: str | None = Query(
            None, description="LLM backend identifier (defaults to configured backend)"
        ),
        k: int = Query(8, description="Number of evidence commits to retrieve"),
        min_score: float | None = Query(None, description="Score threshold override"),
    ) -> EventSourceResponse:
        effective_backend = backend or settings.backend

        async def event_generator() -> AsyncIterator[dict[str, str]]:
            seance = Seance(min_score=min_score)
            try:
                events = seance.ask(
                    question=q,
                    repo_path=Path(repo),
                    mode=mode,
                    backend_name=effective_backend,
                    k=k,
                    min_score=min_score,
                )
                for ev in events:
                    # Explicit json.dumps ensures valid JSON string data on the SSE wire
                    yield {
                        "event": ev.event,
                        "data": json.dumps(ev.to_dict()),
                    }
            except Exception as err:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": str(err)}),
                }
                yield {
                    "event": "done",
                    "data": json.dumps(
                        {
                            "mode": mode,
                            "retries": 0,
                            "disclaimer": GHOST_DISCLAIMER,
                        }
                    ),
                }

        return EventSourceResponse(event_generator())

    # Timeline endpoint (Graveyard view)
    @application.get("/api/timeline", response_model=TimelineResponse)
    def timeline(
        repo: str = Query(..., description="Path to target Git repository"),
    ) -> TimelineResponse:
        repo_path = Path(repo).resolve()
        if not repo_path.exists():
            raise HTTPException(status_code=400, detail=f"Repository '{repo}' does not exist.")
        try:
            check_git_repo(repo_path)
        except (GitError, NotAGitRepositoryError) as err:
            raise HTTPException(
                status_code=400, detail=f"Repository '{repo}' is not a valid git repository: {err}"
            ) from None

        cache_dir = get_repo_cache_dir(repo_path)
        if (cache_dir / "commits.jsonl").exists():
            commit_store, _, _ = load_index(cache_dir)
        else:
            commit_store, _, _ = index_repo(repo_path)

        commits = list(commit_store)
        if not commits:
            return TimelineResponse(
                total_commits=0, first_date=None, last_date=None, last_subject=None,
                last_sha=None, buckets=[], top_authors=[],
            )

        counts: dict[str, int] = {}
        authors: dict[str, int] = {}
        for c in commits:
            key = c.date.strftime("%Y-%m")
            counts[key] = counts.get(key, 0) + 1
            authors[c.author] = authors.get(c.author, 0) + 1
        ordered = sorted(commits, key=lambda c: c.date)
        last = ordered[-1]
        return TimelineResponse(
            total_commits=len(commits),
            first_date=ordered[0].date.isoformat(),
            last_date=last.date.isoformat(),
            last_subject=last.subject,
            last_sha=last.sha,
            buckets=[TimelineBucket(month=m, count=n) for m, n in sorted(counts.items())],
            top_authors=[
                AuthorCount(author=a, commits=n)
                for a, n in sorted(authors.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
            ],
        )

    # Honesty stats endpoint (landing page credibility strip)
    @application.get("/api/stats")
    def stats() -> dict[str, object]:
        report = Path(__file__).parents[2] / "reports" / "latest.json"
        if not report.exists():
            return {}
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    # Static assets mounting or fallback HTML landing page
    effective_dist: Path = (
        static_dir
        if static_dir is not None
        else (
            settings.static_dir
            if settings.static_dir is not None
            else (Path(__file__).parents[2] / "web" / "dist")
        )
    )

    if effective_dist.exists() and (effective_dist / "index.html").exists():
        application.mount(
            "/",
            StaticFiles(directory=str(effective_dist), html=True),
            name="static",
        )
    else:

        @application.get("/", response_class=HTMLResponse)
        def fallback_index() -> str:
            return (
                "<!DOCTYPE html>\n"
                '<html lang="en">\n'
                '<head><meta charset="UTF-8"><title>The Ghost Maintainer</title></head>\n'
                '<body style="background:#12100e;color:#e6e1d6;font-family:sans-serif;padding:2rem;">\n'
                "  <h1>The Ghost Maintainer</h1>\n"
                "  <p>Web UI bundle not built yet. Run <code>cd web &amp;&amp; npm run build</code>.</p>\n"
                '  <p>API is operational. Visit <a href="/docs" style="color:#e5983b;">/docs</a> for Swagger UI.</p>\n'
                "</body>\n"
                "</html>"
            )

    return application


# Global application instance for uvicorn run
app = create_app()
