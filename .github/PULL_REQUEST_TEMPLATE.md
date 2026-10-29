## Description

Provide a clear and concise summary of the changes made and the motivation behind them.

Closes #(issue number)

---

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change fixing an issue)
- [ ] 💡 New feature (non-breaking change adding functionality)
- [ ] 🛡️ Honesty / Security fix (strengthening retrieval gate, citation verifier, or isolation)
- [ ] 🧹 Refactor or performance enhancement
- [ ] 📚 Documentation update
- [ ] 🧪 Tests or evaluation benchmark additions

---

## Invariant Checklist

- [ ] **Zero Target Repository Mutations**: No files or branches are created or modified in target git repos.
- [ ] **Honesty Pipeline Unaltered**: Retrieval gate refuses (`"The dead do not remember."`) below `GHOST_MIN_SCORE`.
- [ ] **Strict Typing**: Code passes `uv run mypy src` with 0 errors.
- [ ] **Style & Linting**: Code passes `uv run ruff check .` and `uv run ruff format --check .`.
- [ ] **Test Coverage**: All unit, integration, and adversarial tests pass (`uv run pytest`).
- [ ] **Web Build**: Frontend compiles cleanly (`cd web && npm run lint && npm run build`).

---

## Verification Steps

Describe the exact steps you took to verify your changes locally:
1. Ran `...`
2. Expected output `...`
