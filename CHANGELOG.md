# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-29

### Added
- **Git Archaeology Engine (`gitlog.py`)**:
  - Single-pass high-throughput git history parser utilizing ASCII `0x1e` and `0x1f` record delimiters.
  - Granular hunk parsing (`-p -U0`) extracting function signature shifts capped at 20 signatures per commit.
  - Shallow clone detection and warning heuristics.
  - Empty commit (`--allow-empty`) and zero-file commit preservation.
- **BM25 Search & Retrieval Core (`index.py`, `retrieve.py`)**:
  - Fast lexically-ranked index via `bm25s` with Snowball stemming.
  - Path-tokenized commit document synthesis with function change boosts.
  - Zero target repository mutation: all indices and metadata saved to `~/.ghost/<repo-hash>/`.
  - Retrieval Gate: immediate threshold gating on `GHOST_MIN_SCORE` (`0.8`), failing with `"The dead do not remember."` before invoking any model.
- **Pluggable Inference Backends (`backends/`)**:
  - `unsloth_backend.py`: Open-weight local inference using `unsloth/Qwen3-4B-Instruct-2507-bnb-4bit` (4-bit quantization, greedy decoding).
  - `openai_compat.py`: Streaming OpenAI-compatible client supporting local servers (Ollama, llama.cpp) and cloud models, featuring `<think>` reasoning block suppression.
  - `mock.py`: 8 deterministic mock modes for exhaustive pipeline verification and automated CI testing.
- **Honesty Verification Pipeline (`verify.py`, `prompt.py`, `seance.py`)**:
  - 3-stage defense-in-depth pipeline (Retrieval Gate -> Post-Generation Verifier -> Guarded Remediation).
  - Sentinel Boundary Architecture: robust abbreviation-safe sentence splitting handling trailing citations and quotes.
  - Git commit peeling via `git cat-file -e <sha>^{commit}` to reject non-commit objects (trees, blobs).
  - Retrieval evidence grounding cross-check and lexical support ratio calculation.
  - Guarded self-correction retry with specific verification failure diagnostics.
- **CLI & Server Interfaces (`cli.py`, `server.py`)**:
  - Typer CLI with commands: `summon`, `ask`, `seance` (interactive multi-turn REPL), `serve`, `eval`, and `doctor`.
  - FastAPI SSE streaming server streaming real-time events (`evidence`, `token`, `reconsidering`, `verdict`, `done`, `error`).
  - Embedded static serving of production React Single Page Application.
- **Candlelit Archive Web UI (`web/`)**:
  - Modern Vite + React + TypeScript single-page app adhering to `apple-grade-design`.
  - Semantic OKLCH color palette (ink and warm amber tones), Fraunces serif and Inter sans typography.
  - 10 designed interaction states (idle summon, indexing, asking, evidence preview, streaming tokens, reconsidering retry, verified response, ungrounded warning, dead refusal, system error).
  - Keyboard-navigable commit drawer and citation popover cards.
- **Honesty Benchmark Suite (`eval.py`, `evals/`, `scripts/`)**:
  - Wilson score 95% confidence intervals for Citation Existence Rate (CER), Citation Grounding Rate (CGR), Sentence Verification Rate (SVR), Refusal Recall (RR), Refusal Precision (RP), and Answer Support (AS).
  - Evaluation CLI with detailed Markdown and JSON reporting.
  - Adversarial citation evasion fuzz testing suite.
