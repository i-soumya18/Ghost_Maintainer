# Hacktoberfest 2026 / DEV Challenge Submission Checklist

**Challenge Track:** Ghost in the Machine (Hacktoberfest 2026 Week 4)  
**Project:** The Ghost Maintainer — A Séance for Dead Repositories  
**License:** MIT  
**Primary Backend:** Local open-weight (`unsloth/Qwen3-4B-Instruct-2507-bnb-4bit` 4-bit) with `openai_compat` fallback  

---

## 📋 Core Deliverables Checklist

### 1. Repository & Open Source Standard
- [x] **Repository Root**: Clean root directory with zero extraneous build junk.
- [x] **License**: Standard OSI-approved `LICENSE` (MIT).
- [x] **Readme**: Comprehensive, beautifully structured `README.md` with:
  - Architecture diagram
  - Quickstart with `uv` and `npm`
  - Honest verifiable metrics summary table
  - CLI and Web usage guide
  - Threat models and safety guarantees
- [x] **Contributing Guide**: `CONTRIBUTING.md` documenting setup, test commands, and quality gates.
- [x] **Code of Conduct**: `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1).
- [x] **Security Policy**: `SECURITY.md` defining threat models and vulnerability reporting.
- [x] **Changelog**: `CHANGELOG.md` adhering to Keep a Changelog and SemVer.
- [x] **GitHub Templates**: Issue templates (`bug_report.yml`, `feature_request.yml`, `haunting_report.yml`) and `PULL_REQUEST_TEMPLATE.md`.
- [x] **CI/CD Automation**: `.github/workflows/ci.yml` running linting (`ruff`), typing (`mypy`), tests (`pytest`), and web build (`npm run build`).

### 2. Architecture & Honesty Guarantees
- [x] **Zero Target Repository Mutation**: Indices and caches stored strictly under `~/.ghost/<repo-hash>/`. Target repos are strictly read-only.
- [x] **Retrieval Gate**: Fast BM25 gating failing to `"The dead do not remember."` when evidence score is below `0.8`.
- [x] **Sentinel Boundary Architecture**: Trailing citation and quotation parsing defeating sentence-fusing evasion attacks.
- [x] **Git Commit Peeling**: Verifying commits with `git cat-file -e <sha>^{commit}` to prevent tree/blob hash injection.
- [x] **Guarded Remediation**: Diagnostic retry loop repairing or excising ungrounded claims.
- [x] **Universal Disclaimer**: Every response carries `"Voices are fiction. Evidence is real."`.

### 3. Verification & Evaluation Suite
- [x] **Evaluation Dataset**: `evals/request.yaml` with 25 curated questions (15 answerable, 10 unanswerable false-premise traps).
- [x] **Dataset Validator**: `scripts/validate_eval.py` verifying all 30 gold commit references exist in target git history.
- [x] **Citation Auditor**: `scripts/verify_citations.py` auditing model-generated reports against git commit objects.
- [x] **Wilson Confidence Intervals**: Statistical rigor evaluating CER, CGR, SVR, RR, RP, and AS at 95% confidence bounds.

### 4. Apple-Grade Web Interface (`web/`)
- [x] **Design Tokens**: Perceptually uniform OKLCH color space (`tokens.css`).
- [x] **Atmosphere**: Candlelit archival aesthetic (no cheesy neon skulls or cartoon Halloween clichés).
- [x] **Typography**: High-contrast `Fraunces` variable serif paired with `Inter` and `JetBrains Mono`.
- [x] **Interaction States**: 10 distinct, fully-designed operational and error states.
- [x] **Accessibility**: WCAG AA compliant contrast, full keyboard focus rings, and screen reader live regions.

### 5. DEV Post Submission
- [x] **Publication Draft**: `submission/dev-post-draft.md` ready for staging and publication.
- [x] **AI Disclosure**: Transparent attribution (`ai_disclosure_level: some_ai`).
