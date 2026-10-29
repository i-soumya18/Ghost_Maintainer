# Ghost Maintainer Documentation 📚

Technical architecture, design specifications, and mathematical honesty formulations for The Ghost Maintainer.

---

## 📑 Documentation Index

### 1. [Architecture Overview](architecture.md)
Detailed walkthrough of the end-to-end system design:
- **Strict Read-Only Isolation**: How the tool audits target git repositories without modifying a single byte.
- **ASCII Control-Character Git Streaming**: Single-pass `git log` streaming using `0x1e` (record separator) and `0x1f` (unit separator).
- **BM25 Lexical Retrieval Engine**: In-memory tokenization and scoring boosted across commit subjects, file path segments, and unified diff hunk headers.
- **Polymorphic Backend Subsystem**: Architectural details of the `unsloth`, `openai_compat`, and `mock` inference engines.
- **FastAPI SSE Server**: Streaming events (`evidence`, `token`, `reconsidering`, `verdict`, `done`, `error`) and static asset delivery.

### 2. [The Honesty Pipeline](honesty.md)
Comprehensive analysis of hallucination prevention and statistical validation:
- **Threat Models**: Common failure modes in small open-weight language models (fabricated hashes, plausible fiction, ungrounded extrapolation, syntax manipulation).
- **3-Stage Defense-in-Depth**:
  1. *Retrieval Gate*: Pre-inference thresholding triggering immediate refusal for low-evidence queries.
  2. *Post-Generation Verifier*: Sentence segmentation, regex citation extraction, git object peeling (`git cat-file -e <sha>^{commit}`), and evidence grounding.
  3. *Guarded Remediation*: Diagnostic retry with structured feedback, sentence pruning, and refusal fallback.
- **Statistical Metric Formulations**: Rigorous definitions of Citation Existence Rate (CER), Citation Grounding Rate (CGR), Sentence Verification Rate (SVR), Refusal Recall (RR), Refusal Precision (RP), and Answer Support (AS) with Wilson 95% confidence intervals.

### 3. [Design System & UX Architecture](design.md)
Complete design document for the Candlelit Archive web experience:
- **Guiding Metaphor**: *"A late-night séance in a quiet archive."* — zero Halloween clichés, neon skulls, or cartoon novelties.
- **OKLCH Design Tokens**: Perceptually uniform color tokens defined in `tokens.css` (near-black ink backgrounds, warm candle-amber accents).
- **Typography Matrix**: `Fraunces` variable serif for the ghost's voice, `JetBrains Mono` for verifiable evidence, and `Inter` for interface controls.
- **10 Core Operational States**: Initial summon, indexing progress, ready state with mined suggestion chips, evidence pre-rendering, token streaming, retry indicator, verification chips, refusal message, calm error alerts, and 200% zoom responsive reflow.
- **Accessibility & WCAG AA**: Contrast ratios, screen reader announcements (`aria-live="polite"`), and full keyboard navigation.
