# Ghost Maintainer Utility Scripts 🛠️

Standalone audit and verification scripts for benchmarking and repository analysis.

---

## 📜 Available Scripts

### 1. `validate_eval.py`
Audits an evaluation benchmark YAML file against a local git repository to verify that:
1. Every answerable question references valid commit SHAs (`git cat-file -e <sha>^{commit}`).
2. Gold commit references are not empty or malformed.
3. Unanswerable trap questions are properly configured with `expected_refusal: true`.

#### Usage:
```bash
uv run python scripts/validate_eval.py --eval-file evals/request.yaml --repo /path/to/target/repo
```

#### Options:
- `--eval-file`, `-e`: Path to evaluation benchmark YAML (default: `evals/request.yaml`).
- `--repo`, `-r`: Path to target git repository (default: `.eval_repos/request`).

---

### 2. `verify_citations.py`
Independently audits generated evaluation reports (both JSON and Markdown formats) against a target git repository:
1. Extracts all bracketed citations (`[hash]`).
2. Checks object existence in the git database (`git cat-file -e <sha>^{commit}`).
3. Verifies grounding against the retrieved evidence set.
4. Alerts on any hallucinated or ungrounded commit hashes.

#### Usage:
```bash
# Audit a JSON evaluation report
uv run python scripts/verify_citations.py reports/latest.json --repo /path/to/target/repo

# Audit a Markdown evaluation report
uv run python scripts/verify_citations.py reports/latest.md --repo /path/to/target/repo
```

#### Options:
- `report`: Path to evaluation report (`.json` or `.md`).
- `--repo`, `-r`: Path to target git repository (default: `.eval_repos/request`).
