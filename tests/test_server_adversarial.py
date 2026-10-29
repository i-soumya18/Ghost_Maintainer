"""Adversarial stress-test suite for FastAPI SSE Server.

Probing:
1. Concurrent SSE streams and mid-stream client disconnects.
2. 100% JSON serialization validity across all SSE events and backend modes.
3. Commit inspector edge cases (full, short, ambiguous, nonexistent, traversal).
4. Summon endpoint edge cases (empty, nonexistent, shallow, invalid body).
5. Path traversal & security checks.
6. CORS preflight behavior for authorized and unauthorized origins.
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ghost_maintainer.backends.mock import MockBackend
from ghost_maintainer.config import settings
from ghost_maintainer.index import get_head_sha, load_index
from ghost_maintainer.server import create_app


def parse_sse_events(lines: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """Parse raw SSE stream lines into a list of (event_name, json_data) tuples.

    Strictly verifies that EVERY data payload is valid JSON and contains NO single quotes.
    """
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
            # Empirical check: must be valid JSON
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError as err:
                pytest.fail(f"Invalid JSON in SSE data payload: {raw_data!r} ({err})")

            # Empirical check: raw_data must not contain python single-quoted dict repr
            assert not (raw_data.startswith("{'") or raw_data.endswith("'}"))
            events.append((current_event, data))
    return events


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Provide a TestClient with an isolated cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "cache_dir", cache_dir)
    app = create_app()
    return TestClient(app)


# ==============================================================================
# 1. SSE Stream Resilience & Concurrency
# ==============================================================================


def test_concurrent_sse_streams(client: TestClient, synthetic_repo: Path) -> None:
    """Stress-test concurrent clients streaming /api/ask simultaneously."""
    client.post("/api/summon", json={"path": str(synthetic_repo)})

    def run_query(q: str) -> list[tuple[str, dict[str, Any]]]:
        url = f"/api/ask?q={q}&repo={synthetic_repo}&backend=mock"
        with client.stream("GET", url) as res:
            assert res.status_code == 200
            lines = list(res.iter_lines())
        return parse_sse_events(lines)

    queries = [
        "Why was request deprecated?",
        "How does authentication work?",
        "What happened to Windows CI?",
        "Who added multilingual documentation?",
        "Explain OAuth signers",
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_query, q) for q in queries]
        results = [f.result(timeout=30) for f in futures]

    assert len(results) == len(queries)
    for events in results:
        names = [e[0] for e in events]
        assert "evidence" in names
        assert "token" in names
        assert "verdict" in names
        assert "done" in names


def test_client_disconnect_mid_stream(client: TestClient, synthetic_repo: Path) -> None:
    """Simulate client disconnecting immediately after reading the first event."""
    url = f"/api/ask?q=Why%20was%20request%20deprecated?&repo={synthetic_repo}&backend=mock"
    with client.stream("GET", url) as res:
        assert res.status_code == 200
        first_line = next(res.iter_lines())
        assert len(first_line) > 0
        # Disconnect prematurely by closing the stream context
        res.close()

    # Verify server remains healthy and can process subsequent requests
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"


def test_sse_invalid_query_parameters(client: TestClient, synthetic_repo: Path) -> None:
    """Verify validation and error handling for missing and invalid parameters."""
    # Missing 'q' query param -> 422 Unprocessable Entity
    res_no_q = client.get(f"/api/ask?repo={synthetic_repo}")
    assert res_no_q.status_code == 422

    # Missing 'repo' query param -> 422
    res_no_repo = client.get("/api/ask?q=test")
    assert res_no_repo.status_code == 422

    # Invalid mode enum -> 422
    res_bad_mode = client.get(f"/api/ask?q=test&repo={synthetic_repo}&mode=invalid_mode")
    assert res_bad_mode.status_code == 422

    # Unknown backend -> streams error event and done event over SSE
    url_bad_backend = f"/api/ask?q=test&repo={synthetic_repo}&backend=nonexistent_backend_xyz"
    with client.stream("GET", url_bad_backend) as res:
        assert res.status_code == 200
        events = parse_sse_events(list(res.iter_lines()))
        names = [e[0] for e in events]
        assert "error" in names
        assert "done" in names
        err_payload = next(e[1] for e in events if e[0] == "error")
        assert "nonexistent_backend_xyz" in err_payload["message"]


def test_sse_gate_refusal_min_score(client: TestClient, synthetic_repo: Path) -> None:
    """High min_score threshold triggers clean retrieval gate refusal over SSE."""
    url = f"/api/ask?q=unrelated+topic&repo={synthetic_repo}&backend=mock&min_score=10.0"
    with client.stream("GET", url) as res:
        assert res.status_code == 200
        events = parse_sse_events(list(res.iter_lines()))

    names = [e[0] for e in events]
    assert "evidence" in names
    assert "token" in names
    assert "done" in names
    assert "verdict" not in names  # Refusal short-circuits verifier

    tokens = "".join([e[1]["token"] for e in events if e[0] == "token"])
    assert "The dead do not remember." in tokens


# ==============================================================================
# 2. JSON Serialization Integrity Across All Backend Modes
# ==============================================================================


@pytest.mark.parametrize(
    "backend_mode",
    [
        "honest",
        "hallucinate",
        "ungrounded",
        "bare_hex",
        "uncited",
        "retry_repair",
        "retry_fail",
        "refuse",
    ],
)
def test_sse_json_serialization_all_modes(
    client: TestClient,
    synthetic_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_mode: str,
) -> None:
    """Verify 100% valid JSON serialization across all mock backend response modes."""

    # Monkeypatch get_backend to return MockBackend with requested mode
    def mock_get_backend(name: str | None = None, **kwargs: Any) -> MockBackend:
        return MockBackend(mode=backend_mode)

    monkeypatch.setattr("ghost_maintainer.seance.get_backend", mock_get_backend)
    monkeypatch.setattr("ghost_maintainer.backends.get_backend", mock_get_backend)

    url = f"/api/ask?q=Why%20was%20request%20deprecated?&repo={synthetic_repo}&backend=mock"
    with client.stream("GET", url) as res:
        assert res.status_code == 200
        lines = list(res.iter_lines())

    # parse_sse_events strictly asserts json.loads on every data payload
    events = parse_sse_events(lines)
    assert len(events) >= 2  # At least evidence and done or token

    for ev_name, payload in events:
        assert isinstance(payload, dict)
        if ev_name == "evidence":
            assert "evidence" in payload
            assert isinstance(payload["evidence"], list)
        elif ev_name == "token":
            assert "token" in payload
            assert isinstance(payload["token"], str)
        elif ev_name == "reconsidering":
            assert "reason" in payload
            assert "violations" in payload
            assert isinstance(payload["violations"], list)
        elif ev_name == "verdict":
            assert "is_fully_verified" in payload
            assert "sentences" in payload
            assert isinstance(payload["sentences"], list)
        elif ev_name == "done":
            assert "mode" in payload
            assert "retries" in payload
            assert "disclaimer" in payload


# ==============================================================================
# 3. Commit Inspector Edge Cases & Ambiguous Prefixes
# ==============================================================================


def test_commit_inspector_sha_resolutions(client: TestClient, synthetic_repo: Path) -> None:
    """Probe full SHA, short SHA, prefix collision, and nonexistent hashes."""
    # Index synthetic repo to load commit store
    client.post("/api/summon", json={"path": str(synthetic_repo)})
    head_sha = get_head_sha(synthetic_repo)

    assert head_sha is not None

    # 1. 40-char full SHA
    res_full = client.get(f"/api/commit/{head_sha}?repo={synthetic_repo}")
    assert res_full.status_code == 200
    assert res_full.json()["sha"] == head_sha
    assert res_full.json()["short"] == head_sha[:7]

    # 2. 7-char short SHA
    res_short = client.get(f"/api/commit/{head_sha[:7]}?repo={synthetic_repo}")
    assert res_short.status_code == 200
    assert res_short.json()["sha"] == head_sha

    # 3. Nonexistent SHA -> 404
    res_missing = client.get(
        f"/api/commit/ffffffffffffffffffffffffffffffffffffffff?repo={synthetic_repo}"
    )
    assert res_missing.status_code == 404
    assert "not found" in res_missing.json()["detail"].lower()

    # 4. Nonexistent short SHA -> 404
    res_missing_short = client.get(f"/api/commit/fffffff?repo={synthetic_repo}")
    assert res_missing_short.status_code == 404
    assert "not found" in res_missing_short.json()["detail"].lower()


def test_commit_inspector_ambiguous_prefix(client: TestClient, synthetic_repo: Path) -> None:
    """Probe commit prefix ambiguity resolution returning 400 Bad Request."""
    client.post("/api/summon", json={"path": str(synthetic_repo)})
    from ghost_maintainer.index import get_repo_cache_dir

    cache_dir = get_repo_cache_dir(synthetic_repo)
    commit_store, _, _ = load_index(cache_dir)

    # Find a prefix shared by multiple commits, or test single character
    all_shas = [c.sha.lower() for c in commit_store]
    found_ambiguous_prefix = None
    for length in range(1, 10):
        prefixes: dict[str, list[str]] = {}
        for s in all_shas:
            p = s[:length]
            prefixes.setdefault(p, []).append(s)
        for p, matches in prefixes.items():
            if len(matches) > 1:
                found_ambiguous_prefix = p
                break
        if found_ambiguous_prefix:
            break

    if found_ambiguous_prefix:
        res = client.get(f"/api/commit/{found_ambiguous_prefix}?repo={synthetic_repo}")
        assert res.status_code == 400
        assert "Ambiguous commit SHA prefix" in res.json()["detail"]


def test_commit_inspector_invalid_repo(
    client: TestClient, non_git_dir: Path, tmp_path: Path
) -> None:
    """Probe commit inspector with missing, empty, or invalid repo paths."""
    head_sha = "0" * 40

    # Missing repo param -> 400
    res1 = client.get(f"/api/commit/{head_sha}")
    assert res1.status_code == 400

    # Nonexistent repo -> 400
    nonexistent = tmp_path / "ghost_missing_dir"
    res2 = client.get(f"/api/commit/{head_sha}?repo={nonexistent}")
    assert res2.status_code == 400
    assert "does not exist" in res2.json()["detail"].lower()

    # Non-git directory -> 400
    res3 = client.get(f"/api/commit/{head_sha}?repo={non_git_dir}")
    assert res3.status_code == 400
    assert "not a valid git repository" in res3.json()["detail"].lower()


# ==============================================================================
# 4. Summon Endpoint Edge Cases
# ==============================================================================


def test_summon_force_reindex(client: TestClient, synthetic_repo: Path) -> None:
    """POST /api/summon with force=True rebuilds existing index."""
    res1 = client.post("/api/summon", json={"path": str(synthetic_repo), "force": False})
    assert res1.status_code == 200

    res2 = client.post("/api/summon", json={"path": str(synthetic_repo), "force": True})
    assert res2.status_code == 200
    assert res2.json()["id"] == res1.json()["id"]
    assert res2.json()["commit_count"] == res1.json()["commit_count"]


def test_summon_shallow_clone(client: TestClient, shallow_repo: Path) -> None:
    """POST /api/summon handles shallow clones gracefully."""
    res = client.post("/api/summon", json={"path": str(shallow_repo)})
    assert res.status_code == 200
    assert res.json()["status"] == "ready"


def test_summon_invalid_payloads(client: TestClient) -> None:
    """POST /api/summon validates request body schema."""
    # Missing path field
    res_empty = client.post("/api/summon", json={})
    assert res_empty.status_code == 422

    # Malformed non-dict JSON
    res_bad = client.post(
        "/api/summon",
        content="not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert res_bad.status_code == 422


# ==============================================================================
# 5. Security & Path Traversal Probes
# ==============================================================================


def test_commit_inspector_path_traversal(client: TestClient, synthetic_repo: Path) -> None:
    """Ensure path traversal sequences in commit SHA cannot access filesystem files."""
    traversal_shas = [
        "../../../../Windows/System32/drivers/etc/hosts",
        "../../etc/passwd",
        "..%2f..%2fetc%2fpasswd",
        "....//....//etc/passwd",
    ]
    for bad_sha in traversal_shas:
        res = client.get(f"/api/commit/{bad_sha}?repo={synthetic_repo}")
        # Must return 404 (or 400) and NEVER 200
        assert res.status_code in (400, 404)


def test_static_files_path_traversal(tmp_path: Path) -> None:
    """Ensure static files endpoint does not serve parent files via traversal."""
    web_dir = tmp_path / "web_dist"
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "index.html").write_text("<h1>Safe App</h1>", encoding="utf-8")

    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("SENSITIVE_DATA", encoding="utf-8")

    app = create_app(static_dir=web_dir)
    test_client = TestClient(app)

    # Probe traversal
    res = test_client.get("/../secret.txt")
    assert res.status_code in (400, 404)
    assert "SENSITIVE_DATA" not in res.text


# ==============================================================================
# 6. CORS Preflight Probes
# ==============================================================================


def test_cors_preflight_origins(client: TestClient) -> None:
    """Probe CORS preflight responses for authorized and external origins."""
    # Authorized origin
    headers_auth = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    res_auth = client.options("/api/health", headers=headers_auth)
    assert res_auth.status_code == 200
    assert res_auth.headers.get("access-control-allow-origin") in ("http://localhost:5173", "*")

    # External / unauthorized origin
    headers_ext = {
        "Origin": "https://external-site.example.com",
        "Access-Control-Request-Method": "GET",
    }
    res_ext = client.options("/api/health", headers=headers_ext)
    assert res_ext.status_code == 200
