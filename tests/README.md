# Ghost Maintainer Test Suite 🧪

Comprehensive test suite enforcing complete verification, adversarial resilience, and statement coverage ($\ge 95\%$) across all core modules.

---

## 📁 Test Suite Structure

The test suite is organized into three primary tiers:

### 1. Core Unit & Functional Tests
Tests core functionality in hermetic, offline environments using synthetic git repositories:
- **`test_gitlog.py`**: Git log streaming parser, ASCII separator handling (`0x1e`/`0x1f`), hunk header extraction, shallow clone warnings.
- **`test_index.py`**: Field-boosted BM25 indexing, tokenization, automatic index invalidation on HEAD change.
- **`test_retrieve.py`**: BM25 retrieval, top-$k$ evidence ranking, path-token boosting.
- **`test_prompt.py`**: Strict system prompt rendering, grounded/refusal few-shot templates, think-tag suppression.
- **`test_backends.py`**: Polymorphic inference interfaces (`unsloth`, `openai_compat`, `mock`).
- **`test_verify.py`**: Sentence splitting, bracketed citation extraction, bare hex auditing, git object verification (`^{commit}`), grounding check, lexical support hints.
- **`test_seance.py`**: 3-stage defense orchestration (retrieval gate $\to$ model generation $\to$ verifier audit $\to$ retry loop $\to$ repair/refusal).
- **`test_cli.py`**: Typer CLI commands (`summon`, `ask`, `seance`, `serve`, `eval`, `doctor`) and formatted Rich output.
- **`test_server.py`**: FastAPI SSE endpoints (`/api/summon`, `/api/ask`), `/api/repos`, `/api/commit/{sha}`, static bundle serving.
- **`test_eval.py`**: Wilson score 95% confidence intervals, metric calculation (CER, CGR, SVR, RR, RP, AS), YAML loader.
- **`test_config.py`**: Pydantic settings, environment variable overrides, cache path resolution.

### 2. Adversarial & Empirical Stress Harnesses
Red-team suites specifically designed to probe hallucination detection, evasion attacks, and edge cases:
- **`test_adversarial_gitlog.py`**: Malformed commit messages, detached HEAD, multi-line subjects, unicode author names, merge diffs.
- **`test_adversarial_honesty.py`**: Hallucinated commit hashes, ungrounded citations, citation-fusing evasion attacks, bare hex injections, prefix collisions.
- **`test_adversarial_stress_m2.py`**: High citation volume (50–200 citations), concurrent query stress, fragmented think tags, network timeouts.
- **`test_challenge_m1.py`**: BM25 indexer stress, cache isolation enforcement, corrupt index recovery.
- **`test_challenge_m2.py`**: Backend and streaming boundary conditions, retry prompt feedback verification.
- **`test_m2_r3_probe_harness.py`**: Targeted evasion probes for complex multi-clause sentence structures.
- **`test_cli_adversarial.py`**: CLI shallow clone handling, pipe errors, ANSI encoding edge cases.
- **`test_server_adversarial.py`**: SSE stream disconnects, client aborts, malformed request bodies, concurrent streaming requests.

### 3. Frontend & SSE Web Resilience Tests (Node.js)
Unit and browser emulation tests for the web interface and SSE stream consumer:
- **`test_frontend_challenge.mjs`**: Single-byte network fragmentation, abort signal propagation, SSR markup verification, design token accessibility.
- **`test_challenger_m4_adversarial.mjs`**: CRLF boundary splits, multi-byte UTF-8 streaming across chunks, calm error banners, component prop contracts.

---

## 🏃 Running the Tests

### Python Test Suite
```bash
# Run all Python tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with code coverage report
uv run pytest --cov=src/ghost_maintainer --cov-report=term-missing
```

### Frontend Tests
```bash
# Run from web directory
npm --prefix web test

# Or run directly via Node.js test runner
node --test tests/test_frontend_challenge.mjs tests/test_challenger_m4_adversarial.mjs
```

### Hermetic Test Environment
All unit and integration tests use hermetic synthetic git fixtures defined in [`conftest.py`](conftest.py), requiring zero internet access or external credentials.
