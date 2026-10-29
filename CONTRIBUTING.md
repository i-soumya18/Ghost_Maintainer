# Contributing to The Ghost Maintainer

Thank you for your interest in contributing to **The Ghost Maintainer**! We welcome bug reports, feature suggestions, architectural improvements, and code contributions.

Please review this document to ensure a smooth contribution process.

---

## 🏛️ Code of Conduct

All contributors and maintainers are expected to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please report violations to `conduct@ghostmaintainer.dev`.

---

## 🛠️ Development Setup

The Ghost Maintainer is built using **Python 3.12** and managed with [`uv`](https://github.com/astral-sh/uv). The Web UI is built with **Node.js (>=18)** and **Vite + React + TypeScript**.

### 1. Clone the Repository

```bash
git clone https://github.com/i-soumya18/Ghost_Maintainer.git
cd Ghost_Maintainer
```

### 2. Set Up Python Environment

Using `uv`:
```bash
# Install Python dependencies into virtual environment
uv sync --all-extras

# Activate virtual environment (optional, or prefix with uv run)
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
```

### 3. Set Up Web UI

```bash
cd web
npm install
npm run build
cd ..
```

---

## 🧪 Testing & Quality Gates

We enforce strict type safety, formatting standards, and test coverage before any PR can be merged.

### Run Linting and Formatting Check

```bash
# Check code style and common mistakes
uv run ruff check .

# Check code formatting
uv run ruff format --check .

# Auto-fix issues
uv run ruff format .
uv run ruff check --fix .
```

### Run Static Type Analysis

```bash
# Full static type check across the package
uv run mypy src
```

### Run Full Test Suite

```bash
# Run all unit, integration, and adversarial fuzz tests
uv run pytest -v

# Run with test coverage
uv run pytest --cov=src/ghost_maintainer --cov-report=term-missing
```

### Run Web Verification

```bash
cd web
npm run lint
npm run build
cd ..
```

---

## 🛡️ Honesty Pipeline Invariants

When modifying or contributing to retrieval, prompting, or verification routines, you must preserve these architectural invariants:

1. **Read-Only Repositories**: The tool must never mutate, create files in, or reconfigure the target git repository. All cache files belong in `~/.ghost/<repo-hash>/`.
2. **Refusal Gate**: If top BM25 evidence score is below `GHOST_MIN_SCORE` (default `0.8`), the system must immediately refuse with `"The dead do not remember."` without executing model inference.
3. **Citation Verification**: Every bracketed citation (e.g. `[a1b2c3d]`) must:
   - Be an actual commit in the git repository (`git cat-file -e <sha>^{commit}`).
   - Exist within the retrieved evidence set for the query.
4. **Remediation**: If an initial model generation produces hallucinated or ungrounded hashes, a single retry prompt must guide self-correction. If that still fails, ungrounded claims must be sliced or fallen back to `"The dead do not remember."`.

---

## 🔀 Pull Request Guidelines

1. **Create a topic branch**:
   ```bash
   git checkout -b feat/my-feature
   ```
2. **Write clear commit messages**:
   Follow conventional commits (`feat: ...`, `fix: ...`, `docs: ...`, `test: ...`).
3. **Add automated tests**:
   Any new feature or bug fix must include corresponding tests in `tests/`.
4. **Run the quality check checklist**:
   - [ ] `uv run ruff check .`
   - [ ] `uv run ruff format --check .`
   - [ ] `uv run mypy src`
   - [ ] `uv run pytest`
   - [ ] `cd web && npm run lint && npm run build`
5. **Open a Pull Request**:
   Fill out the PR template completely and link any relevant issues.
