# Architecture of The Ghost Maintainer

The Ghost Maintainer is an open-source archaeological tool that allows developers to summon the departed collective voice of an abandoned or historical software repository.

```
                         +-----------------------------+
                         |      Target Git Repo        |
                         |   (STRICTLY READ-ONLY)      |
                         +--------------+--------------+
                                        | git log (0x1e/0x1f stream)
                                        v
                         +-----------------------------+
                         |  Git Archaeology Engine     |
                         |        (gitlog.py)          |
                         +--------------+--------------+
                                        | CommitStream
                                        v
                         +-----------------------------+
                         |      BM25 Index & Store     |
                         |    (~/.ghost/<repo-hash>/)  |
                         +--------------+--------------+
                                        | Top Evidence Chunks
                                        v
+---------------+        +-----------------------------+        +---------------+
|  CLI Surface  | <====> |  Honesty & Inference Engine | <====> |   Web Server  |
|  (Typer/Rich) |        |    (Prompt, Verify, Seance) |        | (FastAPI SSE) |
+---------------+        +--------------+--------------+        +-------+-------+
                                        |                               |
                                        v                               v
                         +-----------------------------+        +---------------+
                         |     Inference Backends      |        | React Web UI  |
                         | (Unsloth / OpenAI / Mock)   |        |  (Candlelit)  |
                         +-----------------------------+        +---------------+
```

---

## Core Invariants

### 1. Zero Mutation of Target Repositories
The tool never creates, alters, or removes files or git configurations inside any target repository directory. All generated state—BM25 index structures, commit caches, token stores, and session artifacts—is isolated strictly within the user's local application cache directory:
```
~/.ghost/<repo-hash>/
  ├── commits.json        # Serialized commits and metadata
  ├── index/              # BM25S pre-computed lexical index
  └── meta.json           # Repo SHA, commit count, index timestamp
```

### 2. The Honesty Invariant
The ghost voice speaks with evocative literary immersion ("we decided", "we tore down"), but **every factual claim must be backed by a verifiable commit hash from repository history**.
- If history does not contain evidence for a query, the system immediately refuses:
  > *"The dead do not remember."*
- Every response carries an unyielding disclaimer:
  > *"Voices are fiction. Evidence is real."*

---

## Subsystem Breakdown

### 1. Git Archaeology Engine (`src/ghost_maintainer/gitlog.py`)
- **Single-Pass Stream Parsing**: Employs ASCII record separators (`0x1e`) and unit separators (`0x1f`) with `git log --all --no-color --numstat --format=<FMT>` to stream millions of lines of history directly into lightweight immutable `Commit` objects without regex bottlenecks.
- **Granular Hunk Capture**: Runs `git log -p -U0` selectively extracting function and method signature shifts, capped at 20 signatures per commit to prevent context window explosion.
- **Resilience**: Gracefully handles empty commits (`--allow-empty`), zero-file commits, uninitialized repositories, and shallow clones (`git rev-parse --is-shallow-repository`).

### 2. Indexing & Retrieval Core (`src/ghost_maintainer/index.py`, `retrieve.py`)
- **BM25S Lexical Indexing**: Uses sparse BM25 scoring with English Snowball stemming and custom tokenization.
- **Weighted Structural Documents**: Combines commit subject, author, date, file path fragments, and function signatures. Changes to critical paths or function signatures receive amplified BM25 weight.
- **Retrieval Gating**: Evaluates the highest evidence score against `GHOST_MIN_SCORE` (`0.8`). If insufficient evidence is found, retrieval fails fast without executing expensive LLM inference.

### 3. Verification & Remediation Engine (`src/ghost_maintainer/verify.py`)
- **Sentinel Boundary Architecture**: Splitting sentences reliably across abbreviation boundaries, trailing bracketed citations (`... [hash].`), and quotation marks (`... [hash]." `).
- **Commit Peeling**: Validates hashes with `git cat-file -e <sha>^{commit}` to ensure hashes represent genuine commit objects rather than trees, blobs, or tags.
- **Grounding Verification**: Ensures cited hashes exist in the top retrieved evidence set for that specific query.
- **Lexical Support Auditing**: Computes the token overlap ratio between the ghost's claim and the commit diff/message.
- **Self-Correction Remediation**: If citations are hallucinated or ungrounded, the engine constructs a structured diagnostic prompt for a single retry pass. If still ungrounded, sentences are excised or the response falls back cleanly to the refusal message.

### 4. Pluggable Backend Adapters (`src/ghost_maintainer/backends/`)
- **`UnslothBackend`**: Local 4-bit quantized open-weight inference targeting `unsloth/Qwen3-4B-Instruct-2507-bnb-4bit` for high-throughput execution on consumer GPUs (>= 4GB VRAM).
- **`OpenAICompatBackend`**: Adapter for OpenAI-compatible HTTP endpoints (Ollama, llama.cpp, vLLM, or cloud models), featuring automated suppression of `<think>` reasoning traces.
- **`MockBackend`**: 8 deterministic operational modes for zero-GPU unit testing and CI test suites.

### 5. Interfaces: CLI and Web (`src/ghost_maintainer/cli.py`, `server.py`, `web/`)
- **Typer CLI**: Subcommands `summon`, `ask`, `seance` (interactive multi-turn REPL), `serve`, `eval`, and `doctor`.
- **FastAPI SSE Server**: Streams fine-grained progress events (`evidence`, `token`, `reconsidering`, `verdict`, `done`, `error`) over Server-Sent Events.
- **Candlelit Archive Web UI**: React 18 + TypeScript SPA built with Vite, following Apple Human Interface Guidelines and WCAG AA standards.
