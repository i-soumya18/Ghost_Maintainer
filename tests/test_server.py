"""Hermetic integration tests for the FastAPI HTTP and SSE server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ghost_maintainer import __version__
from ghost_maintainer.config import settings
from ghost_maintainer.index import get_head_sha
from ghost_maintainer.server import create_app


def parse_sse_events(lines: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """Parse raw SSE stream lines into a list of (event_name, json_data) tuples."""
    events: list[tuple[str, dict[str, Any]]] = []
    current_event = "message"
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        if line_clean.startswith("event:"):
            current_event = line_clean[len("event:") :].strip()
        elif line_clean.startswith("data:"):
            raw_data = line_clean[len("data:") :].strip()
            data = json.loads(raw_data)
            events.append((current_event, data))
    return events


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Fixture providing a TestClient with isolated cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "cache_dir", cache_dir)
    app = create_app()
    return TestClient(app)


def test_health(client: TestClient) -> None:
    """GET /health and GET /api/health return status ok and version."""
    for endpoint in ("/health", "/api/health"):
        res = client.get(endpoint)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["version"] == __version__


def test_cors_preflight(client: TestClient) -> None:
    """OPTIONS /api/health responds with appropriate CORS headers."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    res = client.options("/api/health", headers=headers)
    assert res.status_code == 200
    assert (
        res.headers.get("access-control-allow-origin") == "http://localhost:5173"
        or res.headers.get("access-control-allow-origin") == "*"
    )


def test_summon_success(client: TestClient, synthetic_repo: Path) -> None:
    """POST /api/summon indexes synthetic repository and returns metadata."""
    head_sha = get_head_sha(synthetic_repo)
    res = client.post("/api/summon", json={"path": str(synthetic_repo)})
    assert res.status_code == 200
    data = res.json()
    assert data["commit_count"] >= 7
    assert data["head_sha"] == head_sha
    assert data["status"] == "ready"
    assert len(data["id"]) == 12


def test_summon_empty_repo(client: TestClient, empty_repo: Path) -> None:
    """POST /api/summon handles an empty repository cleanly with commit count 0."""
    res = client.post("/api/summon", json={"path": str(empty_repo)})
    assert res.status_code == 200
    data = res.json()
    assert data["commit_count"] == 0
    assert data["status"] == "ready"


def test_summon_invalid_dir(client: TestClient, non_git_dir: Path) -> None:
    """POST /api/summon on non-git directory returns 400 Bad Request."""
    res = client.post("/api/summon", json={"path": str(non_git_dir)})
    assert res.status_code == 400
    assert "not a valid git repository" in res.json()["detail"].lower()


def test_summon_missing_dir(client: TestClient, tmp_path: Path) -> None:
    """POST /api/summon on nonexistent directory returns 404 Not Found."""
    nonexistent = tmp_path / "does_not_exist_at_all"
    res = client.post("/api/summon", json={"path": str(nonexistent)})
    assert res.status_code == 404
    assert "does not exist" in res.json()["detail"].lower()


def test_repos_list(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/repos lists indexed repositories from cache."""
    # Index synthetic repo first
    summon_res = client.post("/api/summon", json={"path": str(synthetic_repo)})
    assert summon_res.status_code == 200

    res = client.get("/api/repos")
    assert res.status_code == 200
    repos = res.json()
    assert len(repos) >= 1
    found = next((r for r in repos if r["name"] == synthetic_repo.name), None)
    assert found is not None
    assert found["commit_count"] >= 7


def test_repos_empty(client: TestClient) -> None:
    """GET /api/repos returns an empty list when cache is empty."""
    res = client.get("/api/repos")
    assert res.status_code == 200
    assert res.json() == []


def test_repos_skips_corrupted_directory(
    client: TestClient, synthetic_repo: Path, tmp_path: Path
) -> None:
    """GET /api/repos skips directories with invalid or unreadable meta.json."""
    # Index synthetic repo
    client.post("/api/summon", json={"path": str(synthetic_repo)})

    # Add a corrupt cache directory
    corrupt_dir = settings.cache_dir / "badcache0001"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_dir / "meta.json").write_text("{corrupt json", encoding="utf-8")

    res = client.get("/api/repos")
    assert res.status_code == 200
    repos = res.json()
    assert len(repos) == 1
    assert repos[0]["name"] == synthetic_repo.name


def test_commit_inspector_full_sha(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/commit/{sha} returns detailed commit metadata and diff."""
    head_sha = get_head_sha(synthetic_repo)
    res = client.get(f"/api/commit/{head_sha}?repo={synthetic_repo}")
    assert res.status_code == 200
    data = res.json()
    assert data["sha"] == head_sha
    assert "author" in data
    assert "date" in data
    assert "subject" in data
    assert isinstance(data["files"], list)
    assert isinstance(data["diff"], (str, type(None)))


def test_commit_inspector_short_sha(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/commit/{sha} resolves short prefix to full commit details."""
    head_sha = get_head_sha(synthetic_repo)
    short_sha = head_sha[:7]
    res = client.get(f"/api/commit/{short_sha}?repo={synthetic_repo}")
    assert res.status_code == 200
    data = res.json()
    assert data["sha"] == head_sha


def test_commit_inspector_not_found(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/commit/{sha} returns 404 if SHA is not in repository."""
    fake_sha = "0" * 40
    res = client.get(f"/api/commit/{fake_sha}?repo={synthetic_repo}")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_commit_inspector_missing_repo(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/commit/{sha} without repo query param returns 400 Bad Request."""
    head_sha = get_head_sha(synthetic_repo)
    res = client.get(f"/api/commit/{head_sha}")
    assert res.status_code == 400
    assert "repo" in res.json()["detail"].lower()


def test_ask_sse_success_stream(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/ask streams evidence, tokens, verdict, and done events in order."""
    url = f"/api/ask?q=Why%20was%20request%20deprecated?&repo={synthetic_repo}&backend=mock"
    with client.stream("GET", url) as res:
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        lines = list(res.iter_lines())

    events = parse_sse_events(lines)
    event_names = [e[0] for e in events]

    assert "evidence" in event_names
    assert "token" in event_names
    assert "verdict" in event_names
    assert "done" in event_names

    # Check evidence payload
    ev_item = next(e[1] for e in events if e[0] == "evidence")
    assert "evidence" in ev_item
    assert len(ev_item["evidence"]) > 0

    # Check tokens accumulation
    token_strings = [e[1]["token"] for e in events if e[0] == "token"]
    accumulated = "".join(token_strings)
    assert len(accumulated.strip()) > 0

    # Check verdict payload
    verdict_item = next(e[1] for e in events if e[0] == "verdict")
    assert "is_fully_verified" in verdict_item
    assert "sentences" in verdict_item


def test_ask_sse_gate_refusal(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/ask with high min_score triggers immediate retrieval refusal."""
    url = (
        f"/api/ask?q=nonexistent+chocolate+cake&repo={synthetic_repo}&backend=mock&min_score=999.0"
    )
    with client.stream("GET", url) as res:
        assert res.status_code == 200
        lines = list(res.iter_lines())

    events = parse_sse_events(lines)
    tokens = [e[1]["token"] for e in events if e[0] == "token"]
    assert "The dead do not remember." in "".join(tokens)


def test_ask_sse_invalid_repo(client: TestClient, non_git_dir: Path) -> None:
    """GET /api/ask with invalid repo yields error event followed by done."""
    url = f"/api/ask?q=test&repo={non_git_dir}&backend=mock"
    with client.stream("GET", url) as res:
        assert res.status_code == 200
        lines = list(res.iter_lines())

    events = parse_sse_events(lines)
    event_names = [e[0] for e in events]
    assert "error" in event_names
    assert "done" in event_names


def test_ask_sse_raw_mode(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/ask with mode=raw streams without guarded remediation."""
    url = (
        f"/api/ask?q=Why%20was%20request%20deprecated?&repo={synthetic_repo}&mode=raw&backend=mock"
    )
    with client.stream("GET", url) as res:
        assert res.status_code == 200
        lines = list(res.iter_lines())

    events = parse_sse_events(lines)
    done_item = next(e[1] for e in events if e[0] == "done")
    assert done_item["mode"] == "raw"


def test_static_mount_with_dist(tmp_path: Path) -> None:
    """Static assets from static_dir are served at / when index.html exists."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<h1>Ghost Archive</h1>", encoding="utf-8")

    app = create_app(static_dir=dist_dir)
    custom_client = TestClient(app)

    res = custom_client.get("/")
    assert res.status_code == 200
    assert "<h1>Ghost Archive</h1>" in res.text


def test_static_mount_without_dist(tmp_path: Path) -> None:
    """Fallback HTML landing page is served when static_dir has no index.html."""
    empty_dist = tmp_path / "empty_dist"
    empty_dist.mkdir(parents=True, exist_ok=True)

    app = create_app(static_dir=empty_dist)
    custom_client = TestClient(app)

    res = custom_client.get("/")
    assert res.status_code == 200
    assert "The Ghost Maintainer" in res.text
    assert "Web UI bundle not built yet" in res.text


def test_timeline_endpoint(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/timeline summarises repository lifetime."""
    res = client.get("/api/timeline", params={"repo": str(synthetic_repo)})
    assert res.status_code == 200
    data = res.json()
    assert data["total_commits"] > 0
    assert sum(b["count"] for b in data["buckets"]) == data["total_commits"]
    assert data["last_sha"]
    assert data["top_authors"]


def test_timeline_missing_repo(client: TestClient, tmp_path: Path) -> None:
    """GET /api/timeline rejects nonexistent repositories."""
    res = client.get("/api/timeline", params={"repo": str(tmp_path / "nope")})
    assert res.status_code == 400


def test_stats_endpoint_returns_object(client: TestClient) -> None:
    """GET /api/stats always returns a JSON object."""
    res = client.get("/api/stats")
    assert res.status_code == 200
    assert isinstance(res.json(), dict)


def test_cors_rejects_foreign_origin(client: TestClient) -> None:
    """Foreign origins are not echoed back as allowed."""
    res = client.options(
        "/api/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert res.headers.get("access-control-allow-origin") not in ("*", "http://evil.example")


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    import json as _json

    events: list[tuple[str, dict]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data = "message", None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = _json.loads(line[5:].strip())
        if data is not None:
            events.append((name, data))
    return events


def test_summon_stream_reports_real_phases(client: TestClient, synthetic_repo: Path) -> None:
    """GET /api/summon/stream emits ordered progress phases and a final done event."""
    res = client.get("/api/summon/stream", params={"path": str(synthetic_repo), "force": "true"})
    assert res.status_code == 200
    events = _parse_sse(res.text)
    names = [n for n, _ in events]
    assert names[-1] == "done"
    phases = [d["phase"] for n, d in events if n == "progress"]
    assert phases[0] == "resolving"
    for expected in ("reading", "indexing", "saving"):
        assert expected in phases
    assert events[-1][1]["commit_count"] > 0


def test_summon_stream_error_for_missing_dir(client: TestClient, tmp_path: Path) -> None:
    """Streaming summon reports failures as an SSE error event."""
    res = client.get("/api/summon/stream", params={"path": str(tmp_path / "nope")})
    events = _parse_sse(res.text)
    assert events[-1][0] == "error"
    assert "does not exist" in events[-1][1]["message"]
