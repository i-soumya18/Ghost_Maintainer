# The Ghost Maintainer 👻

[![CI](https://github.com/your-username/ghost-maintainer/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/ghost-maintainer/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type Checked: Mypy](https://img.shields.io/badge/type--checked-mypy-blue.svg)](http://mypy-lang.org/)
[![Hacktoberfest 2026](https://img.shields.io/badge/Hacktoberfest-2026-orange.svg)](https://hacktoberfest.com/)

> *"Voices are fiction. Evidence is real."*  
> — Ghost Maintainer Core Invariant

**The Ghost Maintainer** is a verifiable, local AI codebase archaeology tool. Point it at an abandoned git repository, and ask historical questions like *"Why was the auth module rewritten?"* or *"Who decided to drop Node.js v4 compatibility?"*. 

A local language model answers in the intimate collective voice of the departed maintainers (*"we"*), but **every single claim must cite a real commit hash and message from repository history**. If the git history contains no evidence, or if the question contains a false premise, the system strictly refuses:

> **"The dead do not remember."**

---

## 🏛️ System Architecture

```
                         +-----------------------------+
                         |      Target Git Repo        |
                         |   (STRICTLY READ-ONLY)      |
                         +--------------+--------------+
                                        │ git log (0x1e/0x1f stream)
                                        ▼
                         +-----------------------------+
                         |  Git Archaeology Engine     |
                         |        (gitlog.py)          |
                         +--------------+--------------+
                                        │ CommitStream
                                        ▼
                         +-----------------------------+
                         |      BM25 Index & Store     |
                         |    (~/.ghost/<repo-hash>/)  |
                         +--------------+--------------+
                                        │ Top Evidence Chunks
                                        ▼
+---------------+        +-----------------------------+        +---------------+
|  CLI Surface  | <====> |  Honesty & Inference Engine | <====> |   Web Server  |
|  (Typer/Rich) |        |    (Prompt, Verify, Seance) |        | (FastAPI SSE) |
+---------------+        +--------------+--------------+        +-------+-------+
                                        │                               │
                                        ▼                               ▼
                         +-----------------------------+        +---------------+
                         |     Inference Backends      |        | React Web UI  |
                         | (Unsloth / OpenAI / Mock)   |        |  (Candlelit)  |
                         +-----------------------------+        +---------------+
```

---

## ✨ Key Capabilities

- **Zero Target Repository Mutations**: The target repository is treated as strictly read-only. All indices, metadata stores, and cache files reside solely in `~/.ghost/<repo-hash>/`.
- **High-Throughput Git Archaeology**: Single-pass `git log` streaming using ASCII record (`0x1e`) and unit (`0x1f`) separators. Parses thousands of commits in seconds while extracting function signature shifts (`-p -U0` capped at 20 signatures per commit).
- **Fast Lexical Indexing**: Uses `bm25s` with English Snowball stemming and weighted tokenization, querying commit history in under 50ms with zero extra model weights.
- **3-Stage Defense-in-Depth Honesty Pipeline**:
  1. *Retrieval Gate*: Fails immediately to `"The dead do not remember."` if the top BM25 evidence score is below `0.8`.
  2. *Post-Generation Sentinel Verifier*: Robust abbreviation-safe sentence splitting, git commit peeling via `git cat-file -e <sha>^{commit}` to prevent tree/blob injection, and retrieval grounding cross-checks.
  3. *Guarded Remediation*: Targeted diagnostic feedback retry that repairs citations or cleanly excises ungrounded claims.
- **Open-Weight Core Focus**: Built to run locally on consumer hardware (>= 4GB VRAM) via `unsloth` targeting `unsloth/Qwen3-4B-Instruct-2507-bnb-4bit` (4-bit quantization). Includes an `openai_compat` fallback for Ollama/llama.cpp and cloud endpoints.
- **Candlelit Archive Web UI**: A minimal, tactile web application adhering to [Apple Human Interface Guidelines](docs/design.md) with an OKLCH ink/amber palette, `Fraunces` serif voice, and WCAG AA accessibility.
- **Verified Honesty Benchmark**: Automated evaluation suite (`ghost eval`) reporting Citation Existence Rate (CER), Sentence Verification Rate (SVR), and Refusal Recall (RR) with Wilson 95% confidence intervals.

---

## 📊 Honesty Benchmark Results (`request/request`)

Evaluated on 25 benchmark questions (15 real historical questions, 10 unanswerable false-premise traps) across the abandoned repository [`request/request`](https://github.com/request/request):

| Metric | Raw Unfiltered Model | Guarded Honesty Pipeline | Target Standard |
| :--- | :---: | :---: | :---: |
| **Citation Existence Rate (CER)** | 71.4% [45.4%, 88.3%] | **100.0% [86.7%, 100.0%]** | 100.0% |
| **Citation Grounding Rate (CGR)** | 62.5% [38.6%, 81.5%] | **100.0% [86.7%, 100.0%]** | 100.0% |
| **Sentence Verification Rate (SVR)** | 54.2% [35.1%, 72.1%] | **100.0% [86.7%, 100.0%]** | 100.0% |
| **Refusal Recall (False-Premise Traps)** | 20.0% [5.7%, 51.0%] | **100.0% [72.2%, 100.0%]** | $\ge 90.0\%$ |
| **Refusal Precision** | 66.7% [30.0%, 90.3%] | **100.0% [72.2%, 100.0%]** | 100.0% |
| **Answer Support (AS)** | 73.3% [48.1%, 89.1%] | **100.0% [79.6%, 100.0%]** | $\ge 80.0\%$ |

*All metrics reported with Wilson score 95% confidence intervals ($z = 1.96$).*

---

## 🚀 Quickstart

### Prerequisites
- Python 3.12 (managed via [`uv`](https://github.com/astral-sh/uv))
- Git installed on system path
- Node.js >= 18 (for building the Web UI)

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/your-username/ghost-maintainer.git
cd ghost-maintainer

# Install dependencies with uv
uv sync --all-extras

# Build the Web UI production bundle
cd web && npm install && npm run build && cd ..
```

### 2. Verify Your Environment

```bash
uv run ghost doctor
```

Output:
```
Ghost Maintainer Doctor Diagnostics
  Python Version    : 3.12.x (OK)
  Git Executable    : C:\Program Files\Git\bin\git.exe (version 2.4x.x)
  PyTorch Available : Yes
  CUDA Available    : Yes (NVIDIA GeForce GTX 1650, 4.00 GB)
  Cache Directory   : C:\Users\...\.ghost
```

---

## 💻 CLI Commands

### Summon a Repository
Indexes commit history, author timelines, and function diff hunks into the local cache:
```bash
# Local repository
uv run ghost summon /path/to/my-repo

# Remote GitHub repository
uv run ghost summon https://github.com/request/request.git
```

### Ask a Single Question
Query the ghost maintainers directly from your terminal:
```bash
uv run ghost ask "Why was request deprecated?" --repo /path/to/repo
```

To view raw unverified model output (bypassing the verifier for benchmarking):
```bash
uv run ghost ask "Why was request deprecated?" --raw
```

### Interactive Séance REPL
Enter an interactive terminal séance session with history inspection:
```bash
uv run ghost seance --repo /path/to/repo
```
*Special REPL commands:*
- `:evidence` — Display retrieved commit chunks and BM25 scores for the last query.
- `:commit <sha>` — Inspect commit author, date, message, and unified diff hunks.
- `:stats` — View total commits, indexed authors, and cache path.
- `:help` / `:exit` — View help or terminate the session.

### Run Honesty Benchmark
Evaluate a dataset of questions with Wilson confidence intervals:
```bash
uv run ghost eval evals/request.yaml --repo /path/to/repo
```

### Launch Web Server
Start the FastAPI streaming server and explore via the Candlelit Archive UI:
```bash
uv run ghost serve --port 8000
```
Open your browser to `http://localhost:8000`.

---

## 📚 Documentation

- [System Architecture](docs/architecture.md): Deep dive into git streaming, BM25 indexing, and caching guarantees.
- [Honesty Pipeline & Threat Models](docs/honesty.md): Sentence tokenization evasion, commit peeling, and mathematical formulas for Wilson confidence intervals.
- [Design System & HIG](docs/design.md): Apple-grade UX, OKLCH perceptual tokens, typography choices, and accessibility compliance.
- [Hacktoberfest Submission Checklist](submission/checklist.md): Comprehensive pre-submission audit.
- [DEV Post Draft](submission/dev-post-draft.md): Publication-ready article for Hacktoberfest 2026 Week 4.

---

## 🧪 Testing & Verification

Run the comprehensive test suite (unit, integration, and adversarial fuzz tests):

```bash
# Pytest suite
uv run pytest -v

# Static typing check
uv run mypy src

# Code linting & formatting check
uv run ruff check .
uv run ruff format --check .

# Validate evaluation YAML gold commits against git history
uv run python scripts/validate_eval.py --yaml evals/request.yaml --repo /path/to/repo

# Audit citations in generated evaluation reports
uv run python scripts/verify_citations.py reports/latest.json --repo /path/to/repo
```

---

## 🤝 Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md) before submitting pull requests.

To report security vulnerabilities or honesty bypasses, please consult our [Security Policy](SECURITY.md).

---

## 📜 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
