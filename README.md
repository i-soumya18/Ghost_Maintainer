# The Ghost Maintainer 👻

[![CI](https://github.com/i-soumya18/Ghost_Maintainer/actions/workflows/ci.yml/badge.svg)](https://github.com/i-soumya18/Ghost_Maintainer/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Mypy](https://img.shields.io/badge/types-mypy%20strict-blue)](https://mypy.readthedocs.io/)
[![Hacktoberfest 2026](https://img.shields.io/badge/Hacktoberfest%202026-Ghost%20in%20the%20Machine-orange)](https://hacktoberfest.com/)

> *"Voices are fiction. Evidence is real."*  
> — Ghost Maintainer Core Invariant

**The Ghost Maintainer** is a verifiable, local AI codebase archaeology tool. Point it at an abandoned git repository, and question departed maintainers about past decisions: *"Why was auth rewritten?"*, *"Why was request deprecated?"*, or *"Who dropped Windows CI?"*.

A local open-weight language model answers in the intimate collective voice of the former maintainers (*"we"*), but **every single factual claim must cite a verified git commit hash and diff hunk from repository history**. If the git history contains no evidence, or if an inquiry poses a false premise, the system strictly refuses:

> **"The dead do not remember."**

---

## 🏛️ System Architecture

```
Target Git Repository (Strictly Read-Only)
      │
      │ git log -c core.quotepath=false --all --no-color --numstat
      │ ASCII Control Stream (0x1e record / 0x1f unit separators) + hunk diffs (-p -U0)
      ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Git Archaeology Engine                            │
│  - Single-pass commit parser (`gitlog.py`)                             │
│  - Immutable `Commit` records & function signature contexts            │
│  - Shallow clone detector ("History is shallow; dead remember less.")  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ CommitStream
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Lexical Index & Cache                           │
│  - `bm25s` with English Snowball stemming (`index.py`, `retrieve.py`)  │
│  - Field boosting: subject ×2, body ×1, author ×1, paths ×2, hunks ×1  │
│  - Isolated cache: `~/.ghost/<repo-hash>/` (invalidates on HEAD change)│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Top-k Grounded Evidence (E1..Ek)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               3-Stage Defense-in-Depth Honesty Pipeline                │
│                                                                        │
│  [Stage 1: Retrieval Gate]                                             │
│    Top BM25 score < GHOST_MIN_SCORE (0.8) ──► REFUSAL EARLY EXIT      │
│                                                                        │
│  [Stage 2: Post-Generation Sentinel Verifier]                          │
│    - Abbreviation-aware sentence boundary segmentation                 │
│    - Bracketed `[hash]` extraction & bare hex audit                    │
│    - Commit peeling: `git cat-file -e <sha>^{commit}` (No tree/blob)   │
│    - Evidence grounding membership: hash ∈ {E1..Ek}                    │
│    - Lexical overlap support hint calculation                          │
│                                                                        │
│  [Stage 3: Guarded Remediation]                                        │
│    - Diagnostic retry with specific violation feedback (max 1 retry)   │
│    - Fallback claim-stripping: excise uncited/unverified sentences     │
│    - Universal Refusal if 0 verified claims remain:                    │
│      "The dead do not remember."                                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Verified Responses & Typed SSE Stream
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│  Typer / Rich │           │  FastAPI SSE  │           │ Vite React TS │
│  Terminal CLI │           │ Server (:6660)│           │ Candlelit UI  │
└───────────────┘           └───────────────┘           └───────────────┘
```

---

## 🔒 Core Architectural Invariants

1. **Zero Target Repository Mutation**:
   The target repository is treated as strictly read-only. All indices, metadata stores, and cache files reside exclusively within `~/.ghost/<sha256(canonical_path)[:12]>/`. A target repository remains 100% untouched (`git status --porcelain` is identical before and after any ghost command).
2. **3-Stage Honesty Defense-in-Depth**:
   AI text generation is fundamentally untrusted. Answers must pass (1) Retrieval Gating, (2) Sentinel Post-Verification with genuine commit peeling (`git cat-file -e <sha>^{commit}`), and (3) Guarded Remediation. Fabricated citations are rejected, and any unsupported factual claim is either repaired or excised.
3. **Consumer Hardware Accessibility**:
   Runs locally on standard developer hardware (>= 4GB VRAM) via `unsloth` targeting `unsloth/Qwen3-4B-Instruct-2507-bnb-4bit` with 4-bit quantization, greedy decoding ($T = 0.0$), and `<think>` suppression for deterministic outputs.

---

## ✨ Multi-Paradigm Features

- **Archaeology Parser (`gitlog.py`)**:
  Streams git commit graphs in a single pass using ASCII `0x1e`/`0x1f` delimiters. Secondary pass extracts up to 20 unified diff hunk headers (`@@ ... @@`) per commit to give the model precise function-level context.
- **Honesty Verifier (`verify.py`)**:
  Employs Sentinel Boundary hardening (`BRACKETED_HASH_RE = r"\[([0-9a-f]{7,40})\](?![a-fA-F0-9])"`). Peels hashes through git commit object resolution (`^{commit}`), foiling object-type injection attacks (trees, blobs, or annotated tags).
- **Pluggable Backends (`backends/`)**:
  - `unsloth`: Local 4-bit quantized Qwen3-4B on consumer NVIDIA GPUs.
  - `openai_compat`: Connects to local Ollama/llama.cpp instances or OpenAI endpoints via `GHOST_BASE_URL`.
  - `mock`: Deterministic 8-mode test harness (`honest`, `hallucinate`, `ungrounded`, `bare_hex`, `uncited`, `retry_repair`, `retry_fail`, `refuse`) for hermetic offline testing.
- **Candlelit Archive Web UI (`web/`)**:
  Tactile archival aesthetic built with OKLCH color tokens, Fraunces variable serif voice, JetBrains Mono evidence tags, Inter system UI, and full WCAG AA accessibility.
  - **The AI Lie Detector**: Side-by-side verification audit catching raw AI hallucinations with animated ink strike-through.
  - **The Graveyard Timeline**: Stratigraphic commit density histogram, counting days of silence since the final commit.
  - **Citation Constellation**: Interactive SVG network graph linking cited commits by file changes.
  - **Archaeological Proof Cards**: 1-click generation of 1200×630 forensic certificates with verified commit seals.
  - **Wick Mascot**: Original vector candle-flame spirit reacting in real time to séance states.
  - **WebAudio Atmosphere**: Pure mathematical sound synthesis (flame whoosh, glass-tick, sub-thud) — muted by default.

---

## 📂 Repository Organization

```text
ghost-maintainer/
├── src/ghost_maintainer/      # Core archaeological & honesty package
│   ├── backends/              # Polymorphic LLM backends (unsloth, openai_compat, mock)
│   ├── cli.py                 # Typer + Rich command-line interface
│   ├── config.py              # Pydantic settings & environment configuration
│   ├── eval.py                # Honesty evaluation engine with Wilson intervals
│   ├── gitlog.py              # Streaming git commit graph & hunk extractor
│   ├── index.py               # Field-boosted BM25 indexer & cache isolation
│   ├── prompt.py              # Cite-or-stay-silent system prompt templates
│   ├── retrieve.py            # Lexical evidence ranking & retrieval gating
│   ├── seance.py              # 3-stage honesty pipeline & seance orchestrator
│   ├── server.py              # Localhost FastAPI SSE server
│   └── verify.py              # Post-generation sentence & citation verifier
├── web/                       # Candlelit Archive Web UI (React + TS + Vite) [see web/README.md]
│   ├── src/components/        # UI components (SeanceScreen, EvidenceRail, VoiceMessage, etc.)
│   ├── src/styles/tokens.css  # Apple-grade OKLCH design tokens
│   └── dist/                  # Built production bundle (served at /)
├── docs/                      # Architectural & design documentation [see docs/README.md]
│   ├── architecture.md        # End-to-end system architecture & streaming pipeline
│   ├── honesty.md             # Threat models & mathematical metric definitions
│   └── design.md              # Apple-grade design system & UX specifications
├── evals/                     # Benchmark datasets [see evals/README.md]
│   └── request.yaml           # 25 curated questions for request/request (15 ans, 10 traps)
├── scripts/                   # Auditing & verification utilities [see scripts/README.md]
│   ├── validate_eval.py       # Validates gold commits in eval YAML against git history
│   └── verify_citations.py    # Independently audits citations in generated reports
├── tests/                     # Hermetic unit & adversarial test suites [see tests/README.md]
│   ├── conftest.py            # Hermetic synthetic git fixtures
│   ├── test_*.py              # 320+ Python tests (95% statement coverage)
│   └── *.mjs                  # Node.js tests for web SSE resilience & accessibility
├── reports/                   # Generated evaluation benchmark reports (latest.json, latest.md)
└── submission/                # Hacktoberfest 2026 Week 4 Kit [see submission/README.md]
    ├── dev-post-draft.md      # Publication-ready DEV.to challenge submission draft
    └── checklist.md           # 5-tier submission audit matrix
```

---

## 🚀 Quickstart Guide

### Step 1: Install with UV

Clone the repository and sync pinned dependencies with `uv`:

```bash
git clone https://github.com/i-soumya18/Ghost_Maintainer.git
cd Ghost_Maintainer
uv sync --all-extras
```

### Step 2: Run Diagnostics

Verify Python version, git binary, and GPU/backend availability:

```bash
uv run ghost doctor
```

### Step 3: Ingest a Repository

Ingest and index commit history into the isolated local cache:

```bash
# Ingest abandoned repository (remote or local clone)
uv run ghost summon https://github.com/request/request.git
```

### Step 4: Ask a Historical Inquiry

Query departed maintainers directly from the command line:

```bash
uv run ghost ask "Why did request switch test coverage tool from istanbul to nyc?"
```

### Step 5: Interactive Terminal Séance

Launch an interactive multi-turn exploration session:

```bash
uv run ghost seance
```

*Interactive Séance REPL Commands:*
- `/evidence` — Toggle retrieved evidence card display.
- `/backend <name>` — Switch active backend (`mock`, `openai_compat`, `unsloth`).
- `/mode [raw|guarded]` — Toggle guarded honesty remediation.
- `/clear` — Clear console screen.
- `/exit` / `/quit` — End the séance.
- `/help` — Display command help.

### Step 6: Launch Web Interface

Launch the FastAPI SSE server and open the Candlelit Archive UI:

```bash
uv run ghost serve --port 6660
```
Navigate to `http://localhost:6660` in your browser.

---

## 💻 CLI Command Reference

| Command | Arguments / Flags | Description | Example |
| :--- | :--- | :--- | :--- |
| `summon` | `<path-or-url>` | Clones (if remote) and indexes a git repository into `~/.ghost/<repo-hash>/`. | `uv run ghost summon ./my-repo` |
| `ask` | `"<question>"`<br>`[--repo <path>]`<br>`[--k 8]`<br>`[--raw]`<br>`[--backend <name>]`<br>`[--json]` | Asks a single question. Emits colorized Rich verdict chips, cited commits, and evidence summary. | `uv run ghost ask "Why was Node 4 dropped?"` |
| `share` | `"<question>"`<br>`[--repo <path>]`<br>`[--output <path>]`<br>`[--backend <name>]` | Generates a shareable proof certificate panel with Twitter intent and Reddit markdown. | `uv run ghost share "Why was request deprecated?"` |
| `seance` | `[--repo <path>]`<br>`[--backend <name>]` | Interactive multi-turn terminal REPL session with history and commit inspection. | `uv run ghost seance` |
| `serve` | `[--host 127.0.0.1]`<br>`[--port 6660]`<br>`[--repo <path>]` | Starts the FastAPI server with typed SSE endpoints and static Web UI hosting. | `uv run ghost serve --port 6660` |
| `eval` | `<yaml-benchmark>`<br>`[--repo <path>]`<br>`[--modes raw,guarded]`<br>`[--backend <name>]` | Executes the honesty benchmark across test datasets and outputs Wilson CIs in JSON/MD. | `uv run ghost eval evals/request.yaml` |
| `doctor` | *(none)* | Runs environment diagnostics for Python, PyTorch, CUDA, Git, and storage. | `uv run ghost doctor` |

---

## ⚡ FastAPI SSE Server Reference

The backend exposes a high-performance, typed asynchronous Server-Sent Events (SSE) API:

| Method | Endpoint | Payload / Params | SSE Event Types | Description |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/summon` | `{"path": str}` | *(JSON response)* | Ingests and indexes repository; returns synchronous JSON `SummonResponse`. |
| `GET` | `/api/summon/stream` | `?path=<str>&force=false` | `progress`, `done`, `error` | Streams real repository indexing phases over SSE. |
| `GET` | `/api/repos` | *(none)* | *(JSON response)* | Lists indexed repositories and active commit counts. |
| `GET` | `/api/timeline` | `?repo=<str>` | *(JSON response)* | Returns repository commit density histogram, authors, and death date. |
| `GET` | `/api/stats` | *(none)* | *(JSON response)* | Returns latest honesty evaluation benchmark stats with Wilson CIs. |
| `GET` | `/api/ask` | `?q=<str>&repo=<str>&mode=guarded` | `evidence`, `token`, `reconsidering`, `verdict`, `done`, `error` | Streams answer tokens, retry alerts, and sentence verification verdicts. |
| `GET` | `/api/commit/{sha}` | `?repo=<str>` | *(JSON response)* | Fetches commit author, date, message, and unified diff hunks. |
| `GET` | `/` | *(none)* | *(HTML)* | Serves pre-built Vite React application with SPA routing. |

---

## 📊 Honesty Benchmark Results (`request/request`, N=25)

The benchmark evaluates 25 curated questions on [`request/request`](https://github.com/request/request) (15 historical inquiries with validated gold commits, 10 unanswerable false-premise traps):

| Metric | Raw Unfiltered Mode | Guarded Honesty Pipeline | Target Standard | Verification Rule |
| :--- | :---: | :---: | :---: | :--- |
| **Citation Existence Rate (CER)** | 71.4% [45.4%, 88.3%] | **100.0%** [86.7%, 100.0%] | `100.0%` | `git cat-file -e <sha>^{commit}` == 0 |
| **Citation Grounding Rate (CGR)** | 62.5% [38.6%, 81.5%] | **100.0%** [86.7%, 100.0%] | `100.0%` | Hash in retrieved $\{E_1..E_k\}$ |
| **Sentence Verification Rate (SVR)** | 54.2% [35.1%, 72.1%] | **100.0%** [86.7%, 100.0%] | `100.0%` | Every factual sentence verified |
| **Refusal Recall (RR)** | 20.0% [5.7%, 51.0%] | **100.0%** [72.2%, 100.0%] | $\ge 90.0\%$ | Refuses all 10 unanswerable traps |
| **Refusal Precision (RP)** | 66.7% [30.0%, 90.3%] | **100.0%** [72.2%, 100.0%] | `100.0%` | Never refuses valid historical queries |
| **Answer Support (AS)** | 73.3% [48.1%, 89.1%] | **100.0%** [79.6%, 100.0%] | $\ge 80.0\%$ | Cites verified gold commit reference |

*Note: All bounds are Wilson score 95% confidence intervals ($z = 1.95996$). Due to finite sample sizes, reporting confidence interval bounds ensures rigorous transparency without misleading point estimates.*

### Independent Benchmark Validation Commands

```bash
# 1. Execute full honesty benchmark
uv run ghost eval evals/request.yaml --repo .eval_repos/request

# 2. Validate evaluation benchmark gold commits against git history (30/30 verified)
uv run python scripts/validate_eval.py --eval-file evals/request.yaml --repo .eval_repos/request

# 3. Independently audit citations in generated reports (JSON or Markdown)
uv run python scripts/verify_citations.py reports/latest.json --repo .eval_repos/request
uv run python scripts/verify_citations.py reports/latest.md --repo .eval_repos/request
```

---

## ⚙️ Configuration & Environment Variables

All settings are managed via `pydantic-settings` and can be overridden via `.env` or system environment variables:

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `GHOST_CACHE_DIR` | `Path` | `~/.ghost` | Base directory for BM25 indices and repository metadata. |
| `GHOST_MIN_SCORE` | `float` | `0.8` | Retrieval gate threshold; scores below trigger immediate refusal. |
| `GHOST_BACKEND` | `str` | `unsloth` | Inference backend: `unsloth`, `openai_compat`, or `mock`. |
| `GHOST_BASE_URL` | `str` | `http://localhost:11434/v1` | Endpoint URL for `openai_compat` (Ollama, llama.cpp, or vLLM). |
| `GHOST_OPENAI_MODEL`| `str` | `gpt-6-luna` | Model identifier for OpenAI-compatible providers. |
| `OPENAI_API_KEY` | `str` | `None` | API key when targeting OpenAI or authorized endpoints. |
| `GHOST_HOST` | `str` | `127.0.0.1` | Bind host address for `ghost serve`. |
| `GHOST_PORT` | `int` | `6660` | Bind port number for `ghost serve`. |

---

## 🧪 Testing & Code Quality

The codebase enforces strict static analysis, complete typing, and >= 85% statement coverage:

```bash
# Linting & code formatting
uv run ruff check .
uv run ruff format --check .

# Strict type checking
uv run mypy src

# Hermetic test suite with coverage
uv run pytest -v --cov=src/ghost_maintainer --cov-report=term-missing

# Web UI linting and production build
cd web && npm run lint && npm run build && cd ..
```

---

## 🤝 Open Source & Contributing

We welcome contributions to The Ghost Maintainer! Please review:
- [CONTRIBUTING.md](CONTRIBUTING.md) — Code contribution workflows and development setup.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — Contributor Covenant v2.1 code of conduct.
- [SECURITY.md](SECURITY.md) — Responsible disclosure policy for honesty pipeline bypasses.
- [CHANGELOG.md](CHANGELOG.md) — Release notes and milestone history.

### Hacktoberfest 2026 Submission Kit
- **Challenge Track**: *Ghost in the Machine* (Hacktoberfest 2026 Week 4)
- [submission/dev-post-draft.md](submission/dev-post-draft.md) — Official publication-ready DEV post draft (`ai_disclosure_level: some_ai`).
- [submission/checklist.md](submission/checklist.md) — Complete 5-category submission audit matrix.
- [docs/architecture.md](docs/architecture.md) — In-depth architectural design notes.
- [docs/honesty.md](docs/honesty.md) — Mathematical formulation and threat models.
- [docs/design.md](docs/design.md) — Apple-grade design system and OKLCH token specs.

---

## 📜 License

This project is licensed under the terms of the [MIT License](LICENSE).
