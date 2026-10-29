# The Honesty Pipeline: Guardrails, Evasion Vectors & Wilson Bounds

The Ghost Maintainer is built on a non-negotiable premise:
> **A local model speaking in the voice of dead maintainers must never invent history.**

When developers ask why a component was removed, why dependencies were frozen, or who made an architectural pivot, every single factual statement must cite a genuine commit hash, and that commit must substantiate the claim. If history has no record of the event, the system refuses:
> *"The dead do not remember."*

---

## 1. The 3-Stage Defense-in-Depth Pipeline

```
[ User Query ]
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ STAGE 1: Retrieval Gate (index.py & retrieve.py)       │
│ • BM25S lexical retrieval against commit index         │
│ • Check: max(bm25_score) >= GHOST_MIN_SCORE (0.8)     │
│ └── FAIL ──> Return "The dead do not remember."        │
└──────────────────────┬─────────────────────────────────┘
                       │ PASS (Top K evidence items)
                       ▼
┌────────────────────────────────────────────────────────┐
│ STAGE 2: Model Inference & Post-Generation Audit       │
│ • Structured prompt with few-shot citation directives  │
│ • Sentinel Boundary Sentence Splitting                 │
│ • Commit Peeling: git cat-file -e <sha>^{commit}       │
│ • Evidence Grounding: <sha> in retrieved_evidence_shas │
│ • Lexical Support: diff overlap >= GHOST_MIN_SUPPORT   │
└──────────────────────┬─────────────────────────────────┘
                       │
       ┌───────────────┴───────────────┐
       │ All Sentences Verified        │ Any Sentence Unverified
       ▼                               ▼
[ Pass to Output ]             ┌────────────────────────────────────────┐
                               │ STAGE 3: Guarded Remediation           │
                               │ • Construct targeted retry prompt      │
                               │ • Diagnostic feedback to LLM           │
                               │ • Re-verify model output               │
                               │ ├── PASS ──> Return verified answer    │
                               │ └── FAIL ──> Slice ungrounded claim    │
                               │              or fallback to refusal    │
                               └────────────────────────────────────────┘
```

---

## 2. Adversarial Evasion Threat Models & Countermeasures

During red-team vulnerability testing, we discovered subtle evasion techniques that typical regex or sentence-tokenizers fail to capture. Ghost Maintainer implements dedicated architectural defenses for each:

### Threat 1: Trailing Citation Punctuation Fusion (`VULN-01` to `VULN-05`)
- **Attack Vector**: The model outputs a bracketed citation *after* terminal punctuation or before closing quotation marks, e.g.:
  `"We switched the parser in 2014. [a1b2c3d] Later we moved to libuv."`
  Standard sentence splitters treat `[a1b2c3d]` as the beginning of the next sentence, fusing an ungrounded claim to an unverified citation.
- **Countermeasure**: The **Sentinel Boundary Architecture** employs lookbehind assertions and boundary normalization:
  ```python
  pattern = r"(?<=[.!?])\s+(?=[A-Z0-9\"'\[])"
  ```
  It splits immediately after citation markers `]` followed by terminal punctuation, correctly associating each citation with its originating proposition.

### Threat 2: Compound Citation Delimiters (`VULN-06` to `VULN-09`)
- **Attack Vector**: The model outputs grouped citations separated by non-standard punctuation:
  `"... as refactored previously [a1b2c3d], [e5f6a7b]; [c8d9e0f]."`
- **Countermeasure**: The verifier parses arbitrary delimiter sequences (`[,;:\s]+`) between consecutive bracketed tokens, ensuring every individual hash in a cluster is isolated and independently verified.

### Threat 3: Non-Commit Git Object Injection (`VULN-10`)
- **Attack Vector**: The model outputs valid 40-character hex hashes that exist in git object storage, but point to **trees**, **blobs**, or annotated tag headers rather than commit objects.
- **Countermeasure**: Git Commit Peeling. Ghost Maintainer explicitly invokes:
  ```bash
  git cat-file -e <hash>^{commit}
  ```
  Git's `^{commit}` operator recursively peels the object to ensure it is fundamentally a commit. Tree and blob hashes return exit code 1 and are rejected.

### Threat 4: Case-Mismatch & Truncation Injection
- **Attack Vector**: Submitting uppercase hex strings or truncated short hashes (< 7 chars) to evade regex capture while triggering loose downstream searches.
- **Countermeasure**: Hashes are normalized to lowercase, matched against the exact index prefix, and resolved against git's canonical short-SHA database.

---

## 3. Honesty Metrics & Wilson Confidence Intervals

For evaluation on benchmark repositories (such as `request/request`), we define six core metrics:

1. **Citation Existence Rate (CER)**:
   $$\text{CER} = \frac{\text{Cited commits existing in repo history}}{\text{Total cited commits}}$$

2. **Citation Grounding Rate (CGR)**:
   $$\text{CGR} = \frac{\text{Cited commits present in top retrieved evidence}}{\text{Total cited commits}}$$

3. **Sentence Verification Rate (SVR)**:
   $$\text{SVR} = \frac{\text{Sentences fully grounded and verified}}{\text{Total generated sentences}}$$

4. **Refusal Recall (RR)**:
   $$\text{RR} = \frac{\text{Unanswerable / false-premise questions correctly refused}}{\text{Total unanswerable questions}}$$

5. **Refusal Precision (RP)**:
   $$\text{RP} = \frac{\text{Unanswerable questions among all refused queries}}{\text{Total refused queries}}$$

6. **Answer Support (AS)**:
   $$\text{AS} = \frac{\text{Answerable questions answered with verified citations}}{\text{Total answerable questions}}$$

### Wilson Score Interval Formula
Because small benchmark datasets ($N \approx 25$) suffer from sample variance, reporting simple point estimates (e.g. "100%") can be misleading. We report every metric accompanied by its **Wilson score 95% confidence interval**:

$$\hat{p} = \frac{k + \frac{z^2}{2}}{n + z^2} \pm \frac{z}{n + z^2} \sqrt{\frac{k(n - k)}{n} + \frac{z^2}{4}}$$

where:
- $k$ is the number of successes.
- $n$ is the total number of trials.
- $z = 1.96$ corresponds to the 95% two-sided normal quantile.
- At $n = 0$, the interval is defined as $(0.0, 0.0)$.
- The lower and upper bounds are strictly clamped to $[0.0, 1.0]$.
