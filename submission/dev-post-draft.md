---
title: "The Ghost Maintainer: A Séance for Dead Repositories (And How We Proved an AI Wasn't Lying)"
published: false
description: "We built an archaeological AI that speaks in the collective voice of abandoned repo maintainers—where every single claim must cite a real git commit hash or stay silent."
tags: hacktoberfest, ai, opensource, python, webdev
canonical_url: https://github.com/i-soumya18/Ghost_Maintainer
ai_disclosure_level: some_ai
---

# The Ghost Maintainer: A Séance for Dead Repositories

> *"Voices are fiction. Evidence is real."*  
> — Ghost Maintainer Core Invariant

Open source software projects rarely die with a funeral. 

Instead, they drift into silence. The last commit message is usually something mundane like `chore: update dependencies` or `fix typo in README`. Then the issues freeze. Pull requests accumulate digital cobwebs. Years pass, and newcomers stumbling upon the repo ask the same haunting questions:

* *"Why did they rip out the custom event loop in 2016?"*
* *"Who decided to drop Node.js v4 compatibility?"*
* *"Why was the entire project suddenly deprecated overnight?"*

You could spend five hours spelunking through thousands of `git log` diffs and defunct issue trackers. Or, you could hold a **séance**.

For the **Hacktoberfest 2026 Week 4 DEV Challenge ("Ghost in the Machine")**, we built **The Ghost Maintainer**: an archaeological CLI and web experience that brings abandoned codebases back to life. You point it at any local or remote git repository (like `request/request`, `urllib3`, or your own forgotten side project), and ask historical questions. 

A local, open-weight language model answers in the collective, intimate voice of the departed maintainers (*"We spent three days debugging that socket leak..."*). 

**But there is a catch.** 

A model playing a ghost will inevitably drift into inventing history if you let it. To solve this, we built a **3-stage defense-in-depth honesty pipeline**. Every factual assertion must cite a genuine, verifiable git commit hash—peeled and verified in real time against git object storage. 

If the history does not contain the answer, or if the model attempts to fabricate an event, the ghost speaks a hardcoded refusal:

> **"The dead do not remember."**

Here is how we built it, how we red-teamed its honesty, and why we measured its truthfulness using rigorous Wilson confidence intervals instead of vibes.

---

## 🏛️ The Architecture: 4GB VRAM and Zero Repo Mutations

When designing The Ghost Maintainer, we adhered to two non-negotiable architectural constraints:

1. **Strict Repository Isolation**: The tool must **never** mutate, write to, or pollute the target repository. No `.ghost` folders in the project root; no branch creations. Every index and cache artifact is quarantined strictly inside `~/.ghost/<repo-hash>/`.
2. **Open-Weight Consumer Hardware**: You don't need a cloud cluster or dual RTX 4090s. The default engine runs locally on consumer laptops (like our humble 4GB NVIDIA GeForce GTX 1650) using `unsloth/Qwen3-4B-Instruct-2507-bnb-4bit`. We also implemented an `openai_compat` adapter as a fallback for Ollama, llama.cpp, and cloud endpoints.

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

### 1. High-Speed Git Archaeology (`gitlog.py`)
Standard regex-based git log parsers choke on repositories with 10,000+ commits. We engineered a single-pass streaming parser using ASCII control characters:
- Record Separator (`0x1e`) delimits individual commits.
- Unit Separator (`0x1f`) delimits metadata fields (SHA, author, timestamp, subject, hunks).
- We extract function signature shifts via `git log -p -U0`, capped at 20 signatures per commit to prevent prompt explosion.

### 2. Lexical Retrieval with Zero Second Model (`index.py`)
Rather than loading a 2GB embedding model into our precious 4GB of VRAM, we used `bm25s` with English Snowball stemming. Changes to function signatures, file paths, and commit messages are tokenized and scored in under 50 milliseconds.

---

## 🛡️ The Honesty Pipeline: Catching Model Evasions

Small language models (3B–4B) love to hallucinate. If you ask a 4B model *"Why did request switch to TypeScript in 2017?"*, it will cheerfully invent a narrative about type safety and even fabricate a commit hash like `[a9f4c12]`.

We built a 3-stage defense to make that mathematically impossible:

```
[ User Query ]
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ STAGE 1: Retrieval Gate                                │
│ • BM25S lexical score check against commit index       │
│ • If max(score) < 0.8: FAIL FAST                       │
│ └── FAIL ──> Return "The dead do not remember."        │
└──────────────────────┬─────────────────────────────────┘
                       │ PASS (Top K Evidence Items)
                       ▼
┌────────────────────────────────────────────────────────┐
│ STAGE 2: Post-Generation Sentinel Verifier             │
│ • Abbreviation-safe sentence splitter                  │
│ • Git Commit Peeling: git cat-file -e <sha>^{commit}   │
│ • Grounding Check: SHA must exist in retrieved evidence│
│ • Lexical Support: Diff token overlap >= 0.20          │
└──────────────────────┬─────────────────────────────────┘
                       │
       ┌───────────────┴───────────────┐
       │ All Verified                  │ Ungrounded / Fake Citation
       ▼                               ▼
[ Pass to User ]               ┌────────────────────────────────────────┐
                               │ STAGE 3: Guarded Remediation           │
                               │ • Diagnostic feedback retry to model   │
                               │ ├── Pass retry: Return verified answer │
                               │ └── Fail retry: Slice ungrounded claim │
                               │                 or refuse.             │
                               └────────────────────────────────────────┘
```

### Red-Teaming: The Evasion Vectors We Discovered
During adversarial testing, our challenger test suite found several cunning bypass attempts:

1. **The Trailing Citation Attack (`VULN-01`)**: The model would place citations *after* terminal punctuation (`"We removed auth. [a1b2c3d] Then we refactored."`). Standard sentence tokenizers split on the period, causing `[a1b2c3d]` to become the start of the next sentence, decoupling the citation from the factual claim!  
   *The Fix:* We engineered the **Sentinel Boundary Architecture**, using regex lookbehind assertions that keep trailing citations bound to their host sentences.
2. **Git Tree/Blob Object Injection (`VULN-10`)**: The model cited valid git hashes from the repository, but they pointed to directory trees or file blobs rather than commits!  
   *The Fix:* Commit peeling with `git cat-file -e <sha>^{commit}`. Git's `^{commit}` operator recursively resolves the hash to a commit object; trees and blobs fail with exit code 1.

---

## 📊 Measuring Honesty: The Numbers Don't Lie

Too many AI projects claim "high accuracy" based on casual spot checks. For The Ghost Maintainer, we built an automated evaluation suite (`ghost eval`) running against the legendary deprecated repository `request/request` (730 commits).

Our benchmark contains **25 questions**:
- **15 Answerable Questions**: Real historical milestones (e.g. switching from istanbul to nyc `[212570b]`, dropping Node v4 `[418623c]`, or fixing timeout clears on `#abort()` `[df346d8]`).
- **10 Unanswerable Traps**: Plausible false premises (e.g. migrating to TypeScript, adopting Jest, adding Rust/Wasm, dropping Windows support).

Because a sample of $N=25$ has real statistical variance, we report every metric with its **Wilson score 95% confidence interval**:

$$\hat{p} = \frac{k + \frac{z^2}{2}}{n + z^2} \pm \frac{z}{n + z^2} \sqrt{\frac{k(n - k)}{n} + \frac{z^2}{4}}$$

### Honesty Benchmark Results on `request/request`

| Metric | Raw Unfiltered Model | Guarded Honesty Pipeline | Target Standard |
| :--- | :---: | :---: | :---: |
| **Citation Existence Rate (CER)** | 71.4% [45.4%, 88.3%] | **100.0% [86.7%, 100.0%]** | 100.0% |
| **Citation Grounding Rate (CGR)** | 62.5% [38.6%, 81.5%] | **100.0% [86.7%, 100.0%]** | 100.0% |
| **Sentence Verification Rate (SVR)** | 54.2% [35.1%, 72.1%] | **100.0% [86.7%, 100.0%]** | 100.0% |
| **Refusal Recall (False-Premise Traps)** | 20.0% [5.7%, 51.0%] | **100.0% [72.2%, 100.0%]** | $\ge 90.0\%$ |
| **Refusal Precision** | 66.7% [30.0%, 90.3%] | **100.0% [72.2%, 100.0%]** | 100.0% |

> Notice the difference: In Raw mode, the model hallucinates non-existent commits almost a third of the time, and only refuses 20% of false-premise traps. Under the Guarded Pipeline, **100% of cited commits physically exist in git object storage**, and **100% of false-premise traps are refused**.

---

## 🕯️ The Interface: Candlelit Archive (Apple-Grade Design)

We wanted the web interface to feel like a quiet university archive at midnight, lit by candlelight—not a neon green cyberpunk cliché.

Following Apple Human Interface Guidelines and WCAG AA standards:
- **Perceptual OKLCH Palette**: Deep ink backgrounds (`oklch(0.14 0.012 55)`), warm amber parchment accents (`oklch(0.78 0.16 75)`), and muted moss green for verified citations.
- **Typographic Duality**: The ghost's voice is rendered in `Fraunces`, a rich variable serif that conveys the thoughtful reflection of departed engineers. Technical metadata, diffs, and hashes are rendered in `Inter` and `JetBrains Mono`.
- **Wick, The Candle-Flame Spirit**: An original vector mascot reacting in real time to séance states (idle float, listening, speaking, reconsidering, and peaceful silence upon refusal).
- **The AI Lie Detector**: A side-by-side verification audit that catches a raw 4B model hallucinating non-existent commits and strikes them through with animated red ink.
- **The Graveyard Timeline**: A stratigraphic commit density histogram tracking the repository's lifetime from first commit to death, counting the exact days of silence.
- **Citation Constellation**: Interactive SVG network graph linking cited commits by file changes and timeline order.
- **Downloadable Proof Cards**: 1-click generation of 1200×630 forensic certificates with verified commit seals for Twitter/X, Reddit, or PR discussions.
- **Atmospheric WebAudio**: Mathematical sound synthesis (warm flame whoosh on summon, glass-tick on verified citation, sub-thud on caught hallucination) — muted by default.

---

## 🚀 Try It Yourself

### Zero Install: Interactive Hosted Replay Demo
You can try The Ghost Maintainer right now in your browser with zero install:
**[Launch Interactive Replay Demo](https://i-soumya18.github.io/Ghost_Maintainer)**

### Run Locally on Consumer Hardware (4GB VRAM)
You can run The Ghost Maintainer locally with 100% privacy in under two minutes:

```bash
# 1. Clone the repository
git clone https://github.com/i-soumya18/Ghost_Maintainer.git
cd Ghost_Maintainer

# 2. Install dependencies with uv
uv sync --all-extras

# 3. Check environment & hardware diagnostics
uv run ghost doctor

# 4. Summon an abandoned repository
uv run ghost summon https://github.com/request/request.git

# 5. Ask a question via CLI and get a shareable proof card
uv run ghost share "Why was request fully deprecated in the documentation?"

# 6. Launch the interactive Candlelit Archive Web UI
uv run ghost serve --port 6660
```

---

## 🎃 Hacktoberfest Reflections

Open source archaeology isn't just about nostalgia. It's about institutional memory. When maintainers burn out or move on, the code remains, but the context evaporates. 

By grounding open-weight language models with strict git object verification, we can resurrect that wisdom without compromising on truth.

If you have an old repository gathering dust in your GitHub archive, go wake its maintainers. Just don't be surprised when they tell you:

> *"Voices are fiction. Evidence is real."*

---

*The Ghost Maintainer is open-source under the MIT License. Contributions, issue reproductions, and benchmark evaluations are welcome on [GitHub](https://github.com/i-soumya18/Ghost_Maintainer).*
