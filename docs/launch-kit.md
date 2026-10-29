# The Ghost Maintainer: Viral Launch Kit 🚀

This kit contains copy, thread structures, and distribution assets engineered for the open-source community, Hacker News, X (Twitter), Reddit, and DEV.to.

---

## 🎯 The Core Narrative Hooks

1. **The Ghost Angle**: *"Open source repos rarely get a funeral. They drift into silence. What if you could hold a séance with their departed maintainers?"*
2. **The Honesty Angle**: *"Small AI models lie 29% of the time. We built a 3-stage defense where an AI must cite a real git commit hash from `git cat-file -e <sha>^{commit}` or stay completely silent."*
3. **The Proof Angle**: *"Every answer generates a cryptographic proof card you can drop into GitHub PRs or tweet."*

---

## 🐦 Twitter / X Launch Thread

### Tweet 1 (Hook + Video / GIF)
Open source projects rarely die with a funeral.

Instead, issues freeze. Digital cobwebs form. And newcomers ask: "Why did they rewrite this in 2016?"

So for Hacktoberfest, we built The Ghost Maintainer 🕯

An archaeological AI that brings dead repos back to life—where every claim must cite a real git commit hash.

🧵👇 [Attach GIF: Lie Detector catching fake commit hash]

### Tweet 2 (The Lie Detector Problem)
Small language models love inventing history.

If you ask a 4B model why `request` switched to TypeScript, it will cheerfully invent a narrative and fabricate a commit hash like `[a9f4c12]`.

So we built an AI Lie Detector into the web UI to show you exactly when a model hallucinates.

### Tweet 3 (The Honesty Pipeline)
To make hallucination impossible, we built a 3-stage defense-in-depth pipeline:

1. BM25 Retrieval Gate (score < 0.8 fails fast)
2. Post-Generation Sentinel Verifier (`git cat-file -e <sha>^{commit}`)
3. Guarded Remediation (strips ungrounded sentences or refuses)

If it’s not in git:
"The dead do not remember."

### Tweet 4 (The Numbers with Wilson 95% CI)
We evaluated honesty across 25 questions on the legendary `request/request` repo:

• Citation Existence Rate: 71.4% (Raw) ➔ 100.0% (Guarded)
• Refusal Recall on Traps: 20.0% (Raw) ➔ 100.0% (Guarded)

Every number is measured with rigorous Wilson 95% confidence intervals, not vibes.

### Tweet 5 (Interactive Features)
The web interface is built with Apple-grade archival aesthetics:
• 🕯 Candlelit OKLCH color palette
• ⚡ Side-by-side AI Lie Detector
• 🪦 Repository Graveyard Timeline (measuring days of silence)
• 📜 One-click 1200x630 shareable Proof Cards
• 🔊 Mathematical WebAudio sound effects

### Tweet 6 (Try it now)
Zero install required. Try the live demo right in your browser on GitHub Pages:
🔗 https://i-soumya18.github.io/Ghost_Maintainer

Or run it locally with 100% privacy:
`uv run ghost summon https://github.com/request/request`
`uv run ghost ask "Why did request switch test coverage tool to nyc?"`

⭐ Star it on GitHub: https://github.com/i-soumya18/Ghost_Maintainer

---

## 🍊 Hacker News "Show HN" Post

**Title:**
> Show HN: The Ghost Maintainer – Codebase archaeology where AI cites git commits or stays silent

**URL:**
> https://github.com/i-soumya18/Ghost_Maintainer

**Text Submission:**

Hi HN,

When maintainers burn out or move on, the code remains, but the context evaporates. You could spend three hours spelunking through `git log -S` diffs and defunct issue trackers—or you could hold a séance.

For the Hacktoberfest "Ghost in the Machine" challenge, we built **The Ghost Maintainer**: a verifiable, local codebase archaeology CLI and web experience.

You point it at any local or remote git repository (like `request/request` or `bower/bower`), and ask historical questions (*"Why was the event loop rewritten?"*, *"When was Node v4 dropped?"*).

A local model answers in the collective voice of the former maintainers (*"we"*).

**The catch: Models playing ghosts will happily invent history.**

To solve this, we built a 3-stage defense-in-depth honesty pipeline:
1. **Retrieval Gating**: Lexical BM25S ranking against streamed commit graphs. If max relevance < 0.8, it fails fast.
2. **Sentinel Post-Verifier**: Sentence tokenizer with boundary lookbehinds for citations. We peel hashes directly against git object storage with `git cat-file -e <sha>^{commit}` to foil tree/blob object injections.
3. **Guarded Remediation**: Diagnostic feedback retry. If unsupported claims persist, they are excised. If zero claims remain, the ghost speaks a hardcoded refusal: *"The dead do not remember."*

**Key Architectural Invariants:**
- **Zero Repo Mutations**: Never writes to the target repository. Everything lives in `~/.ghost/<hash>/`.
- **Runs on Humble Hardware**: 4GB VRAM (e.g. GTX 1650) using 4-bit Qwen3-4B via Unsloth, or Ollama via `openai_compat`.
- **Honesty Benchmark**: Evaluated across 25 historical queries and false-premise traps on `request/request` with Wilson 95% confidence intervals (Raw CER 71.4% ➔ Guarded CER 100.0%).

We also built an interactive web app with a side-by-side **AI Lie Detector**, an interactive **Graveyard Timeline**, and downloadable **Proof Cards**.

Zero-install demo running on GitHub Pages:
https://i-soumya18.github.io/Ghost_Maintainer

Code (MIT):
https://github.com/i-soumya18/Ghost_Maintainer

Feedback and questions about the honesty verifier are very welcome!

---

## 👾 Reddit Post Drafts

### r/programming
**Title:** The Ghost Maintainer: A Séance for Dead Repositories (and how we proved an AI wasn't lying)
**Body:**
*Link to blog post / GitHub repo.* Highlight the commit peeling verification (`git cat-file -e`), ASCII control stream streaming parser (`0x1e`/`0x1f`), and Wilson confidence intervals.

### r/LocalLLaMA
**Title:** Running a 4B Model on a 4GB GTX 1650 for Codebase Archaeology with 100% Git-Peeled Citations
**Body:**
Focus on how small models (Qwen3-4B) can be constrained with lexical BM25 evidence blocks and deterministic sentence verification without requiring 70B parameter models or heavy embeddings. Include the Lie Detector screenshots.

---

## 📸 Screenshot & Video Shot List

1. **Shot 1**: The AI Lie Detector view comparing Raw vs Guarded on the TypeScript trap.
2. **Shot 2**: The Graveyard Timeline showing `request/request` with 2,400+ days of silence and commit histogram.
3. **Shot 3**: Downloaded 1200x630 Archaeological Proof Certificate.
4. **Shot 4**: The Séance Chat with Citation Chips and the slide-out Git Diff Drawer.
5. **Shot 5**: Wick mascot in various mood states (`idle`, `speaking`, `silent`).

